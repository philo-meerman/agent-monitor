"""Upgrade Agent - Main LangGraph Workflow"""

# mypy: disable-error-code=assignment

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from upgrade_agent.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    PROJECT_DIR,
    validate_config,
)
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
    Update,
    UpdateAttempt,
    UpdateStatus,
    UpdateType,
)
from upgrade_agent.tools.advisory import (
    get_vulnerability_scan,
)
from upgrade_agent.tools.dependencies import (
    check_dockerhub_version,
    check_pypi_version,
    get_all_dependencies,
    upgrade_package_version,
)
from upgrade_agent.tools.docker import (
    restart_docker_compose,
    wait_for_service_health,
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
from upgrade_agent.tools.poetry import run_poetry_lock, update_pyproject_toml
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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
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
    """Decide which updates to apply."""
    if hasattr(state, "model_dump"):
        state = state.model_dump()
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
    if hasattr(update, "model_dump"):
        update = Update(**update.model_dump())
    elif isinstance(update, dict):
        update = Update(**update)

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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    state = dict(state)

    if not state.get("available_updates"):
        return state

    update = state["available_updates"][0]
    if hasattr(update, "model_dump"):
        update = Update(**update.model_dump())
    elif isinstance(update, dict):
        update = Update(**update)

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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    state = dict(state)

    if not state.get("current_update"):
        return state

    update_data = state["current_update"]
    if hasattr(update_data, "model_dump"):
        update_data = update_data.model_dump()
        state["current_update"] = update_data
    update = UpdateAttempt(**update_data)
    dep = update.update.dependency
    dep_dict = dep.model_dump() if hasattr(dep, "model_dump") else dict(dep)
    update_type = dep_dict.get("update_type", "python_package")
    file_path = dep_dict["file_path"]
    name = dep_dict["name"]
    new_version = update.update.latest_version
    old_version = dep_dict.get("current_version", "")

    try:
        # Handle different update types
        if update_type == UpdateType.DOCKER_IMAGE:
            state = _act_docker_image(
                state, dep_dict, file_path, name, old_version, new_version
            )
        elif update_type in (UpdateType.NODE_NPM, UpdateType.NODE_YARN):
            state = _act_node_package(
                state, dep_dict, file_path, name, old_version, new_version
            )
        elif update_type == UpdateType.PYTHON_POETRY:
            state = _act_poetry_package(
                state, dep_dict, file_path, name, old_version, new_version
            )
        else:
            # Default: Python pip package
            state = _act_python_package(
                state, dep_dict, file_path, name, old_version, new_version
            )

    except Exception as e:
        state["current_update"]["error"] = str(e)
        state["current_update"]["status"] = UpdateStatus.FAILED

    add_trace(
        state,
        "act_complete",
        "act",
        {
            "status": state["current_update"].get("status"),
            "update_type": update_type,
        },
    )

    return state


def _act_python_package(
    state: dict,
    dep: dict,
    file_path: str,
    name: str,
    old_version: str,
    new_version: str,
) -> dict:
    """Handle Python package upgrade (pip)."""
    # Use upgrade_package_version tool
    result = upgrade_package_version.invoke(
        package=name,
        from_version=old_version,
        to_version=new_version,
        file_path=file_path,
    )
    result_data = json.loads(result)

    if result_data.get("success"):
        # Create branch and commit
        branch_name = f"upgrade/{name}-{new_version}"
        branch_result = json.loads(github_create_branch.invoke(branch_name, "main"))

        if branch_result.get("success"):
            new_content = Path(file_path).read_text()
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

    # Run tests
    test_result = json.loads(run_tests.invoke({}))
    state["current_update"]["test_results"] = test_result

    if not test_result.get("success"):
        state["current_update"]["status"] = UpdateStatus.FAILED

    return state


def _act_docker_image(
    state: dict,
    dep: dict,
    file_path: str,
    name: str,
    old_version: str,
    new_version: str,
) -> dict:
    """Handle Docker image upgrade."""
    # Update docker-compose file
    result = upgrade_package_version.invoke(
        package=name,
        from_version=old_version,
        to_version=new_version,
        file_path=file_path,
    )
    result_data = json.loads(result)

    if result_data.get("success"):
        # Create branch and commit
        branch_name = f"upgrade/{name}-{new_version}"
        branch_result = json.loads(github_create_branch.invoke(branch_name, "main"))

        if branch_result.get("success"):
            new_content = Path(file_path).read_text()
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

    # Restart docker-compose
    restart_result = json.loads(restart_docker_compose.invoke(file_path))
    state["current_update"]["restart_result"] = restart_result

    # Wait for health and verify
    if restart_result.get("success"):
        # Try to determine health URL based on image
        health_url = _get_health_url_for_image(name)
        if health_url:
            health_result = json.loads(
                wait_for_service_health.invoke(
                    url=health_url,
                    max_wait=60,
                )
            )
            state["current_update"]["health_check"] = health_result
            if not health_result.get("healthy"):
                state["current_update"]["status"] = UpdateStatus.FAILED

    return state


def _act_node_package(
    state: dict,
    dep: dict,
    file_path: str,
    name: str,
    old_version: str,
    new_version: str,
) -> dict:
    """Handle Node.js package upgrade (npm/yarn)."""
    from upgrade_agent.tools.nodejs import install_npm_dependencies, update_npm_package

    # Update package.json
    result = update_npm_package.invoke(
        package=name,
        version=new_version,
        file_path=file_path,
    )
    result_data = json.loads(result)

    if result_data.get("success"):
        # Install dependencies
        install_result = json.loads(
            install_npm_dependencies.invoke(
                path=str(Path(file_path).parent),
            )
        )
        state["current_update"]["install_result"] = install_result

        if install_result.get("success"):
            # Create branch and commit
            branch_name = f"upgrade/{name}-{new_version}"
            branch_result = json.loads(github_create_branch.invoke(branch_name, "main"))

            if branch_result.get("success"):
                new_content = Path(file_path).read_text()
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

    return state


def _act_poetry_package(
    state: dict,
    dep: dict,
    file_path: str,
    name: str,
    old_version: str,
    new_version: str,
) -> dict:
    """Handle Poetry package upgrade."""
    # Update pyproject.toml
    result = update_pyproject_toml.invoke(
        package=name,
        version=new_version,
        file_path=file_path,
    )
    result_data = json.loads(result)

    if result_data.get("success"):
        # Run poetry lock
        lock_result = json.loads(
            run_poetry_lock.invoke(
                path=str(Path(file_path).parent),
            )
        )
        state["current_update"]["lock_result"] = lock_result

        if lock_result.get("success"):
            # Create branch and commit
            branch_name = f"upgrade/{name}-{new_version}"
            branch_result = json.loads(github_create_branch.invoke(branch_name, "main"))

            if branch_result.get("success"):
                # Commit pyproject.toml and poetry.lock
                new_content = Path(file_path).read_text()
                commit_result = json.loads(
                    github_update_file.invoke(
                        path=file_path,
                        content=new_content,
                        message=f"Upgrade {name} from {old_version} to {new_version}",
                        branch=branch_name,
                    )
                )

                # Also commit poetry.lock if it exists
                lock_path = Path(file_path).parent / "poetry.lock"
                if lock_path.exists():
                    lock_content = lock_path.read_text()
                    json.loads(
                        github_update_file.invoke(
                            path=str(lock_path),
                            content=lock_content,
                            message=f"Update poetry.lock for {name} upgrade",
                            branch=branch_name,
                        )
                    )

                if commit_result.get("success"):
                    state["current_update"]["status"] = UpdateStatus.SUCCESS

    return state


def _get_health_url_for_image(image: str) -> str:
    """Determine health check URL based on Docker image."""
    image_lower = image.lower()

    # Map common images to their health endpoints
    health_urls = {
        "langfuse/langfuse": "http://localhost:3000/",
        "postgres": "http://localhost:5432",  # Can't really check this via HTTP
        "redis": "http://localhost:6379",
        "minio": "http://localhost:9000/minio/health/live",
    }

    for key, url in health_urls.items():
        if key in image_lower:
            return url

    return None


def fix(state: AgentState) -> AgentState:
    """Attempt to fix test failures."""
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    state = dict(state)

    if not state.get("current_update"):
        return state

    current_update = state["current_update"]
    if hasattr(current_update, "model_dump"):
        current_update = current_update.model_dump()
        state["current_update"] = current_update
    update = UpdateAttempt(**current_update)
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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    state = dict(state)

    # Store upgrade result in memory
    if state.get("current_update"):
        current_update = state["current_update"]
        if hasattr(current_update, "model_dump"):
            current_update = current_update.model_dump()
            state["current_update"] = current_update
        update = UpdateAttempt(**current_update)

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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
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
    if hasattr(state, "model_dump"):
        state = state.model_dump()
    state = dict(state)

    if not state.get("current_update"):
        return state

    update_data = state["current_update"]
    if hasattr(update_data, "model_dump"):
        update_data = update_data.model_dump()
        state["current_update"] = update_data
    update = UpdateAttempt(**update_data)
    dep = update.update.dependency
    dep_dict = dep.model_dump() if hasattr(dep, "model_dump") else dict(dep)
    update_type = dep_dict.get("update_type", "python_package")

    # Verify based on update type
    if update_type == UpdateType.DOCKER_IMAGE:
        state = _verify_docker_upgrade(state, dep_dict)
    elif update_type in (UpdateType.NODE_NPM, UpdateType.NODE_YARN):
        state = _verify_node_upgrade(state, dep_dict)
    elif update_type == UpdateType.PYTHON_POETRY:
        state = _verify_poetry_upgrade(state, dep_dict)
    elif update_type == UpdateType.PYTHON_PACKAGE:
        state = _verify_python_upgrade(state, dep_dict)
    else:
        # Default: Python package - run health check suite
        health_result = json.loads(run_health_check_suite.invoke({}))
        state["current_update"]["health_check"] = health_result

        all_passed = health_result.get("success", False) and state[
            "current_update"
        ].get("test_results", {}).get("success", False)

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
            "verified": state["current_update"].get("status") == UpdateStatus.SUCCESS,
            "update_type": update_type,
        },
    )

    return state


def _verify_python_upgrade(state: dict, dep: dict) -> dict:
    """Verify Python package upgrade - run tests + verify app can start."""
    from upgrade_agent.tools.execution import check_app_health

    # Check test results first
    test_results = state["current_update"].get("test_results", {})
    if not test_results.get("success"):
        state["current_update"]["status"] = UpdateStatus.FAILED
        state["verification_failed"] = True
        return state

    # Try to verify the app can start (if it's a Flask/web app)
    # Check if there's a web app file we can test
    app_path = PROJECT_DIR / "app.py"
    if app_path.exists():
        # Try to check if app is already running or can be reached
        # Check common ports
        for port in [5000, 5001, 8080]:
            health_result = json.loads(
                check_app_health.invoke({"url": f"http://localhost:{port}/"})
            )
            if health_result.get("healthy"):
                state["current_update"]["app_verified"] = True
                state["current_update"]["app_port"] = port
                break

    state["current_update"]["status"] = UpdateStatus.SUCCESS
    return state


def _verify_docker_upgrade(state: dict, dep: dict) -> dict:
    """Verify Docker image upgrade."""
    # Check restart result from act
    restart_result = state["current_update"].get("restart_result", {})

    if not restart_result.get("success"):
        state["current_update"]["status"] = UpdateStatus.FAILED
        state["verification_failed"] = True
        return state

    # Check health result from act
    health_result = state["current_update"].get("health_check", {})

    if health_result and not health_result.get("healthy"):
        state["current_update"]["status"] = UpdateStatus.FAILED
        state["verification_failed"] = True
    else:
        state["current_update"]["status"] = UpdateStatus.SUCCESS

    return state


def _verify_node_upgrade(state: dict, dep: dict) -> dict:
    """Verify Node.js package upgrade."""
    install_result = state["current_update"].get("install_result", {})

    if not install_result.get("success"):
        state["current_update"]["status"] = UpdateStatus.FAILED
        state["verification_failed"] = True
    else:
        state["current_update"]["status"] = UpdateStatus.SUCCESS

    return state


def _verify_poetry_upgrade(state: dict, dep: dict) -> dict:
    """Verify Poetry package upgrade."""
    lock_result = state["current_update"].get("lock_result", {})

    if not lock_result.get("success"):
        state["current_update"]["status"] = UpdateStatus.FAILED
        state["verification_failed"] = True
    else:
        state["current_update"]["status"] = UpdateStatus.SUCCESS

    return state


def handle_failure(state: AgentState) -> AgentState:
    """Called when verification fails - rollback changes."""
    if hasattr(state, "model_dump"):
        state = state.model_dump()
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
        lambda state: (
            "handle_failure" if state.get("verification_failed") else "reflect"
        ),
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
