"""Upgrade Agent - Main LangGraph Workflow"""

# mypy: disable-error-code=assignment

import json
import os
import sys
from datetime import datetime
from typing import Literal

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from upgrade_agent.config import GEMINI_API_KEY, GEMINI_MODEL, validate_config
from upgrade_agent.constants import MAX_ATTEMPTS_PER_ISSUE
from upgrade_agent.decision.risk_scorer import calculate_risk_score
from upgrade_agent.decision.test_coverage import get_test_coverage_for_vulnerabilities
from upgrade_agent.prompts.reason import (
    build_error_analysis_prompt,
    build_planning_prompt,
    build_reasoning_prompt,
)
from upgrade_agent.rate_limiter import rate_limiter
from upgrade_agent.state import (
    AgentState,
    AvailableUpdate,
    Dependency,
    TraceEvent,
    UpdateAttempt,
    UpdateStatus,
)
from upgrade_agent.tools.advisory import (
    get_vulnerability_scan,
)
from upgrade_agent.tools.dependencies import (
    check_dockerhub_version,
    check_pypi_version,
    get_all_dependencies,
)
from upgrade_agent.tools.execution import run_tests
from upgrade_agent.tools.github import (
    github_create_branch,
    github_revert_branch,
    github_update_file,
)
from upgrade_agent.tools.health_checker import run_health_check_suite
from upgrade_agent.tools.langfuse import log_event, log_upgrade_result
from upgrade_agent.tools.memory import append_memory, read_memory
from upgrade_agent.tools.state_recovery import restore_working_state

# Initialize LLM
llm = None


def get_llm():
    """Get or create LLM instance."""
    global llm
    if llm is None:
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not configured")
        llm = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL,
            temperature=0,
            convert_system_message_to_human=True,
        )
    return llm


def add_trace(state: AgentState, event_type: str, node: str, data: dict) -> AgentState:
    """Add a trace event to state."""
    trace = TraceEvent(
        timestamp=datetime.now(),
        event_type=event_type,
        node=node,
        data=data,
    )
    state["traces"].append(trace)

    # Also log to LangFuse
    try:
        log_event.invoke(event_type=event_type, node=node, data=data)
    except Exception:
        pass

    return state


def observe(state: AgentState) -> AgentState:
    """Scan for available updates."""
    state = dict(state)
    state["traces"] = state.get("traces", [])

    add_trace(state, "observe_start", "observe", {"status": "scanning"})

    # Get all dependencies
    deps_json = get_all_dependencies.invoke({})
    dependencies = json.loads(deps_json)

    available_updates = []

    for dep in dependencies:
        # Check latest version
        if dep.get("update_type") == "python_package":
            version_info = check_pypi_version.invoke(dep["name"])
            info = json.loads(version_info)
            if "latest_version" in info:
                latest = info["latest_version"]
                current = dep.get("current_version", "latest")

                # Determine version bump type
                bump_type = "minor"
                if current != "latest" and latest != "latest":
                    try:
                        curr_parts = [int(x) for x in current.split(".")]
                        latest_parts = [int(x) for x in latest.split(".")]
                        if latest_parts[0] > curr_parts[0]:
                            bump_type = "major"
                        elif latest_parts[1] > curr_parts[1]:
                            bump_type = "minor"
                    except Exception:
                        bump_type = "unknown"

                if latest != current:
                    dep_obj = Dependency(**dep)
                    update = AvailableUpdate(
                        dependency=dep_obj,
                        latest_version=latest,
                        version_bump=bump_type,
                    )
                    available_updates.append(update)

        elif dep.get("update_type") == "docker_image":
            version_info = check_dockerhub_version.invoke(dep["name"])
            info = json.loads(version_info)
            if "latest_tag" in info:
                latest = info["latest_tag"]
                current = dep.get("current_version", "latest")

                if latest != current:
                    dep_obj = Dependency(**dep)
                    update = AvailableUpdate(
                        dependency=dep_obj,
                        latest_version=latest,
                        version_bump="minor",  # Docker tags don't follow semver
                    )
                    available_updates.append(update)

    state["available_updates"] = available_updates

    # Scan for vulnerabilities
    try:
        vuln_scan_result = get_vulnerability_scan.invoke({})
        vuln_data = json.loads(vuln_scan_result)
        state["vulnerabilities"] = vuln_data.get("vulnerabilities", [])
    except Exception:
        state["vulnerabilities"] = []

    add_trace(
        state,
        "observe_complete",
        "observe",
        {
            "count": len(available_updates),
            "updates": [u.dict() for u in available_updates],
        },
    )

    return state


def decide(state: AgentState) -> AgentState:
    """Decision node - evaluate whether to auto-upgrade or request review based on vulnerabilities."""
    state = dict(state)

    # Get vulnerabilities from observe step
    vulnerabilities = state.get("vulnerabilities", [])

    if not vulnerabilities:
        state["decisions"] = []
        state["should_proceed"] = True
        return state

    # Get test coverage for affected packages
    packages = [v.get("package", "") for v in vulnerabilities if v.get("package")]
    if packages:
        coverage_result = get_test_coverage_for_vulnerabilities.invoke(
            json.dumps(packages)
        )
        coverage_data = json.loads(coverage_result)
        state["test_coverage"] = coverage_data.get("coverage", {})

    # Make decisions for each vulnerability
    decisions = []
    has_block = False
    has_review = False

    for vuln in vulnerabilities:
        severity = vuln.get("severity", "UNKNOWN")
        version_bump = vuln.get("version_bump", "minor")
        test_coverage = state.get("test_coverage", {}).get("coverage_score", 0.5)
        is_direct = vuln.get("is_direct", True)

        score_result = calculate_risk_score(
            cve_severity=severity,
            version_bump=version_bump,
            test_coverage=test_coverage,
            is_direct_dependency=is_direct,
            has_known_fix=True,
        )

        decision = {
            "vulnerability_id": vuln.get("id", ""),
            "package": vuln.get("package", ""),
            "severity": severity,
            "score": score_result["score"],
            "risk_level": score_result["risk_level"],
            "recommendation": score_result["recommendation"],
            "reasoning": score_result["reasoning"],
        }
        decisions.append(decision)

        if score_result["recommendation"] == "BLOCK":
            has_block = True
        elif score_result["recommendation"] == "REQUEST_REVIEW":
            has_review = True

    state["decisions"] = decisions

    if has_block:
        state["should_proceed"] = False
        state["requires_human_review"] = True
    elif has_review:
        state["should_proceed"] = True
        state["requires_human_review"] = True
    else:
        state["should_proceed"] = True
        state["requires_human_review"] = False

    add_trace(
        state,
        "decide_complete",
        "decide",
        {
            "decisions": decisions,
            "should_proceed": state["should_proceed"],
            "requires_human_review": state.get("requires_human_review", False),
        },
    )

    return state
    """Reason about whether to upgrade."""
    state = dict(state)

    if not state.get("available_updates"):
        state["reasoning"] = "No updates available"
        return state

    # Get previous upgrades for context
    prev_json = read_memory.invoke("upgrades")
    prev_upgrades = json.loads(prev_json)
    prev_str = json.dumps(prev_upgrades[-5:] if prev_upgrades else [])

    # Get first update to reason about
    update = state["available_updates"][0]

    prompt = build_reasoning_prompt(
        name=update.dependency.name,
        current_version=update.dependency.current_version,
        latest_version=update.latest_version,
        version_bump=update.version_bump,
        previous_upgrades=prev_str,
    )

    # Call LLM
    if not rate_limiter.wait_and_acquire():
        state["reasoning"] = "Rate limited, skipping"
        return state

    try:
        llm = get_llm()
        response = llm.invoke(prompt)
        state["reasoning"] = response.content

        # Parse decision
        try:
            decision_data = json.loads(response.content)
            state["decision"] = decision_data
        except Exception:
            state["decision"] = {
                "decision": "PROCEED_WITH_CAUTION",
                "reasoning": response.content,
            }
    except Exception as e:
        state["reasoning"] = f"Error: {e!s}"

    add_trace(
        state,
        "reason_complete",
        "reason",
        {
            "update": update.dict(),
            "decision": state.get("decision", {}),
        },
    )

    return state


def plan(state: AgentState) -> AgentState:
    """Create upgrade plan."""
    state = dict(state)

    if not state.get("available_updates"):
        return state

    update = state["available_updates"][0]

    # Get previous upgrades
    prev_json = read_memory.invoke("upgrades")
    prev_upgrades = json.loads(prev_json)
    prev_str = json.dumps(prev_upgrades[-5:] if prev_upgrades else [])

    prompt = build_planning_prompt(
        name=update.dependency.name,
        current_version=update.dependency.current_version,
        latest_version=update.latest_version,
        update_type=update.version_bump,
        previous_upgrades=prev_str,
    )

    # Call LLM
    if not rate_limiter.wait_and_acquire():
        state["reasoning"] = "Rate limited"
        return state

    try:
        llm = get_llm()
        response = llm.invoke(prompt)

        try:
            plan_data = json.loads(response.content)
            plan_steps = plan_data.get("steps", [])
        except Exception:
            plan_steps = [response.content]

        # Create update attempt
        attempt = UpdateAttempt(
            update=update,
            attempt_number=1,
            status=UpdateStatus.IN_PROGRESS,
            plan=plan_steps,
            started_at=datetime.now(),
        )

        state["current_update"] = attempt.dict()
        state["attempts"] = 1

    except Exception as e:
        state["reasoning"] = f"Error: {e!s}"

    add_trace(
        state,
        "plan_complete",
        "plan",
        {
            "plan": state.get("current_update", {}).get("plan", []),
        },
    )

    return state


def act(state: AgentState) -> AgentState:
    """Execute the upgrade."""
    state = dict(state)

    if not state.get("current_update"):
        return state

    # Get file content, update version
    update_data = state["current_update"]
    update = UpdateAttempt(**update_data)
    dep = update.update.dependency
    file_path = dep["file_path"]
    name = dep["name"]
    new_version = update.update.latest_version

    # Read current file
    try:
        with open(file_path) as f:
            content = f.read()

        # Simple replacement (in production, use proper parsing)
        old_version = dep.get("current_version", "")
        if old_version and old_version != "latest":
            new_content = content.replace(
                f"{name}=={old_version}", f"{name}=={new_version}"
            )
        else:
            # For docker or latest, append
            new_content = content + f"\n{name}=={new_version}"

        # Write back
        with open(file_path, "w") as f:
            f.write(new_content)

        # Create branch and commit
        branch_name = f"upgrade/{name}-{new_version}"

        # Create branch
        branch_result = json.loads(github_create_branch.invoke(branch_name, "main"))

        if branch_result.get("success"):
            # Commit file
            commit_result = json.loads(
                github_update_file.invoke(
                    path=file_path,
                    content=new_content,
                    message=f"Upgrade {name} from {old_version} to {new_version}",
                    branch=branch_name,
                )
            )

            if commit_result.get("success"):
                state["current_update"]["status"] = UpdateStatus.SUCCESS

    except Exception as e:
        state["current_update"]["error"] = str(e)
        state["current_update"]["status"] = UpdateStatus.FAILED

    # Run tests
    test_result = json.loads(run_tests.invoke({}))
    state["current_update"]["test_results"] = test_result

    if not test_result.get("success"):
        state["current_update"]["status"] = UpdateStatus.FAILED

    add_trace(
        state,
        "act_complete",
        "act",
        {
            "status": state["current_update"].get("status"),
            "test_passed": test_result.get("success"),
        },
    )

    return state


def fix(state: AgentState) -> AgentState:
    """Attempt to fix test failures."""
    state = dict(state)

    if not state.get("current_update"):
        return state

    update = UpdateAttempt(**state["current_update"])
    test_results = update.test_results or {}

    prompt = build_error_analysis_prompt(
        test_command=test_results.get("cmd", "pytest"),
        exit_code=test_results.get("return_code", 1),
        stdout=test_results.get("stdout", ""),
        stderr=test_results.get("stderr", ""),
    )

    # Call LLM to analyze error
    if not rate_limiter.wait_and_acquire():
        state["reasoning"] = "Rate limited"
        return state

    try:
        llm = get_llm()
        response = llm.invoke(prompt)

        try:
            fix_data = json.loads(response.content)
            state["current_update"]["error_analysis"] = fix_data
        except Exception:
            state["current_update"]["error_analysis"] = {"raw": response.content}

    except Exception as e:
        state["current_update"]["error"] = str(e)

    state["attempts"] = state.get("attempts", 0) + 1
    state["current_update"]["attempt_number"] = state["attempts"]

    add_trace(
        state,
        "fix_complete",
        "fix",
        {
            "attempts": state["attempts"],
            "error": state["current_update"].get("error"),
        },
    )

    return state


def reflect(state: AgentState) -> AgentState:
    """Reflect on the upgrade and store in memory."""
    state = dict(state)

    # Store upgrade result in memory
    if state.get("current_update"):
        update = UpdateAttempt(**state["current_update"])

        memory_entry = {
            "dependency": update.update.dependency.name,
            "from_version": update.update.dependency.current_version,
            "to_version": update.update.latest_version,
            "success": update.status == UpdateStatus.SUCCESS,
            "attempts": state.get("attempts", 1),
            "error": update.error,
            "timestamp": datetime.now().isoformat(),
        }

        append_memory.invoke("upgrades", memory_entry)

        # Log to LangFuse
        try:
            log_upgrade_result.invoke(
                dependency=update.update.dependency.name,
                from_version=update.update.dependency.current_version,
                to_version=update.update.latest_version,
                success=update.status == UpdateStatus.SUCCESS,
                error=update.error,
            )
        except Exception:
            pass

    # Move to completed
    if state.get("current_update"):
        state["completed_updates"] = state.get("completed_updates", [])
        state["completed_updates"].append(state["current_update"])
        state["current_update"] = None

    add_trace(
        state,
        "reflect_complete",
        "reflect",
        {
            "completed": len(state.get("completed_updates", [])),
        },
    )

    return state


def should_continue(state: AgentState) -> Literal["fix", "reflect", "end"]:
    """Determine if should continue or end."""
    if not state.get("current_update"):
        return "end"

    test_results = state["current_update"].get("test_results", {})

    if test_results.get("success"):
        return "reflect"

    if state.get("attempts", 0) >= MAX_ATTEMPTS_PER_ISSUE:
        return "reflect"

    return "fix"


def verify(state: AgentState) -> AgentState:
    """Verify the upgrade was successful."""
    state = dict(state)

    if not state.get("current_update"):
        return state

    health_result = json.loads(run_health_check_suite.invoke({}))
    state["current_update"]["health_check"] = health_result

    all_passed = health_result.get("success", False) and state["current_update"].get(
        "test_results", {}
    ).get("success", False)

    if not all_passed:
        state["current_update"]["status"] = UpdateStatus.FAILED
        state["verification_failed"] = True
    else:
        state["current_update"]["status"] = UpdateStatus.SUCCESS

    add_trace(
        state,
        "verify_complete",
        "verify",
        {
            "health_check": health_result.get("success", False),
            "tests_passed": state["current_update"]
            .get("test_results", {})
            .get("success", False),
            "verified": all_passed,
        },
    )

    return state


def handle_failure(state: AgentState) -> AgentState:
    """Called when verification fails - rollback changes."""
    state = dict(state)

    branch = state.get("current_update", {}).get("branch")
    if branch:
        try:
            revert_result = json.loads(
                github_revert_branch.invoke(branch, "Auto-revert: verification failed")
            )
            state["revert_result"] = revert_result
        except Exception:
            pass

    try:
        restore_result = json.loads(restore_working_state.invoke({}))
        state["restore_result"] = restore_result
    except Exception:
        pass

    state["needs_human_help"] = True
    state["failure_reason"] = "Tests failed / App didn't start / CVE not fixed"

    add_trace(
        state,
        "handle_failure_complete",
        "handle_failure",
        {
            "reverted": branch is not None,
            "restored": state.get("restore_result", {}).get("success", False),
        },
    )

    return state


def create_agent() -> CompiledStateGraph:
    """Create the LangGraph upgrade agent."""

    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("observe", observe)
    workflow.add_node("decide", decide)
    workflow.add_node("plan", plan)
    workflow.add_node("act", act)
    workflow.add_node("fix", fix)
    workflow.add_node("verify", verify)
    workflow.add_node("handle_failure", handle_failure)
    workflow.add_node("reflect", reflect)

    # Set entry point
    workflow.set_entry_point("observe")

    # Add edges
    workflow.add_edge("observe", "decide")
    workflow.add_edge("decide", "plan")
    workflow.add_edge("plan", "act")
    workflow.add_conditional_edges(
        "act",
        should_continue,
        {
            "fix": "fix",
            "verify": "verify",
            "end": END,
        },
    )
    workflow.add_edge("fix", "act")
    workflow.add_conditional_edges(
        "verify",
        lambda state: "handle_failure"
        if state.get("verification_failed")
        else "reflect",
        {
            "handle_failure": "handle_failure",
            "reflect": "reflect",
        },
    )
    workflow.add_edge("handle_failure", "reflect")
    workflow.add_edge("reflect", END)

    return workflow.compile()


# Create the agent
agent = create_agent()


async def run_upgrade_agent():
    """Run the upgrade agent."""
    # Validate config
    missing = validate_config()
    if missing:
        return {"error": f"Missing config: {missing}"}

    # Check rate limits
    status = rate_limiter.get_status()
    if status["in_backoff"] or status["daily_used"] >= status["daily_limit"]:
        return {"error": "Rate limit exceeded", "status": status}

    # Run agent
    initial_state = AgentState(
        dependencies=[],
        available_updates=[],
        started_at=datetime.now(),
    )

    result = await agent.ainvoke(initial_state.dict())

    return {
        "completed": len(result.get("completed_updates", [])),
        "updates": result.get("available_updates", []),
        "traces": len(result.get("traces", [])),
    }


def run_upgrade_agent_sync():
    """Run the upgrade agent synchronously."""
    import asyncio

    return asyncio.run(run_upgrade_agent())
