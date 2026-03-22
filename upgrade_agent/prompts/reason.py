"""Upgrade Agent - LLM Prompts"""


REASONING_PROMPT = """You are analyzing whether to upgrade a dependency.

Dependency: {name}
Current Version: {current_version}
Latest Version: {latest_version}
Version Bump: {version_bump}

Previous upgrades of this dependency:
{previous_upgrades}

Check the following:
1. Is this a major version bump? Major bumps may have breaking changes.
2. Are there known breaking changes? Search if major.
3. Is it safe to upgrade automatically?

Respond in JSON format:
{{
    "decision": "PROCEED" | "PROCEED_WITH_CAUTION" | "BLOCK",
    "reasoning": "Your detailed reasoning",
    "risk_level": "low" | "medium" | "high",
    "requires_approval": true | false
}}"""


PLANNING_PROMPT = """You are creating an upgrade plan.

Dependency: {name}
From: {current_version}
To: {latest_version}
Type: {update_type}

Previous successful upgrades:
{previous_upgrades}

Create a step-by-step plan:
1. Update version in file
2. Run tests
3. Handle any issues

Respond in JSON format:
{{
    "steps": ["step 1", "step 2", ...],
    "files_to_modify": ["path/to/file", ...],
    "tests_to_run": ["test_name", ...],
    "estimated_time_minutes": 5
}}"""


ERROR_ANALYSIS_PROMPT = """You are analyzing a test failure.

Test Command: {test_command}
Exit Code: {exit_code}
Stdout:
{stdout}

Stderr:
{stderr}

Previous errors with this dependency:
{previous_errors}

Analyze the error and propose a fix:
1. What is the root cause?
2. What change would fix it?
3. Apply the fix

Respond in JSON format:
{{
    "root_cause": "Description of the error",
    "proposed_fix": "What to change",
    "fix_applied": true | false,
    "test_result": "pass" | "fail" | "unknown"
}}"""


PR_BODY_TEMPLATE = """## Upgrade: {name} {from_version} → {to_version}

### Agent Decision Log

| Decision | Reasoning | Your Input Needed? |
|----------|-----------|-------------------|
{decisions}

### Changes Made

- Updated {name} from {from_version} to {to_version}
- File changes: {files_changed}

### Test Results

```
{test_results}
```

### Human Review Required

{review_needed}

---

**Quick Actions:**
- Comment `APPROVE ALL` to merge immediately
- Comment `REVERT <file>` to undo specific changes
- Comment with changes to request modifications

---

_This PR was created by the autonomous upgrade agent._
"""


def build_reasoning_prompt(
    name: str,
    current_version: str,
    latest_version: str,
    version_bump: str,
    previous_upgrades: str = "None",
) -> str:
    """Build the reasoning prompt for a dependency upgrade."""
    return REASONING_PROMPT.format(
        name=name,
        current_version=current_version,
        latest_version=latest_version,
        version_bump=version_bump,
        previous_upgrades=previous_upgrades,
    )


def build_planning_prompt(
    name: str,
    current_version: str,
    latest_version: str,
    update_type: str,
    previous_upgrades: str = "None",
) -> str:
    """Build the planning prompt for a dependency upgrade."""
    return PLANNING_PROMPT.format(
        name=name,
        current_version=current_version,
        latest_version=latest_version,
        update_type=update_type,
        previous_upgrades=previous_upgrades,
    )


def build_error_analysis_prompt(
    test_command: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    previous_errors: str = "None",
) -> str:
    """Build the error analysis prompt."""
    return ERROR_ANALYSIS_PROMPT.format(
        test_command=test_command,
        exit_code=exit_code,
        stdout=stdout[:2000],  # Limit output
        stderr=stderr[:2000],
        previous_errors=previous_errors,
    )


def build_pr_body(
    name: str,
    from_version: str,
    to_version: str,
    decisions: list,
    files_changed: list,
    test_results: str,
    review_needed: str,
) -> str:
    """Build the PR body with decision log."""
    decisions_md = "\n".join(
        [
            f"| {d.get('decision', '')} | {d.get('reasoning', '')} | {'⚠️ YES' if d.get('needs_approval') else 'No'} |"
            for d in decisions
        ]
    )

    return PR_BODY_TEMPLATE.format(
        name=name,
        from_version=from_version,
        to_version=to_version,
        decisions=decisions_md,
        files_changed=", ".join(files_changed),
        test_results=test_results[:1000],
        review_needed=review_needed or "No human review required.",
    )
