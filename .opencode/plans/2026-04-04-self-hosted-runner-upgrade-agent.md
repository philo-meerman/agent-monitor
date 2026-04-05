# Event-Driven Upgrade Agent with Self-Hosted Runner

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a system where the upgrade agent automatically runs on your Mac (via self-hosted GitHub Actions runner) whenever GitHub detects a vulnerability in your dependencies, with full LangFuse tracing.

**Architecture:** GitHub detects CVE → sends dependabot_alert webhook → triggers GitHub Actions workflow → self-hosted runner on your Mac executes agent → full LangFuse trace captured with trigger_type tag.

**Tech Stack:** GitHub Actions, self-hosted runner, LangFuse SDK, launchd

---

## Implementation Sequence

### Task 1: Set Up Self-Hosted Runner on Mac

**Files:**
- Create: `~/actions-runner/` (new directory on your Mac)
- Modify: `/Users/Philo/GitHub/agent-monitor/.env` (ensure GITHUB_TOKEN present)

**Step 1: Create runner directory and download**

```bash
mkdir -p ~/actions-runner
cd ~/actions-runner
curl -o actions-runner-osx-arm64-2.324.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.324.0/actions-runner-osx-arm64-2.324.0.tar.gz
tar xzf actions-runner-osx-arm64-2.324.0.tar.gz
```

**Step 2: Configure runner with GitHub**

```bash
cd ~/actions-runner
./config.sh --url https://github.com/philo-meerman/agent-monitor --token YOUR_PAT_TOKEN --name "mac-mini-runner" --labels "self-hosted,macos"
```

Note: You'll generate a registration token from GitHub → Settings → Actions → Runners → New self-hosted runner.

**Step 3: Test runner starts**

```bash
cd ~/actions-runner
./run.sh
```

Expected: Runner appears in GitHub → Settings → Actions → Runners as "idle"

**Step 4: Commit (skip - local setup only)**

---

### Task 2: Configure Runner as Launchd Service

**Files:**
- Create: `~/Library/LaunchAgents/com.github.actions.runner.plist`

**Step 1: Create launchd plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.github.actions.runner</string>
    <key>WorkingDirectory</key>
    <string>/Users/Philo/actions-runner</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/Philo/actions-runner/run.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
```

**Step 2: Load the service**

```bash
launchctl load ~/Library/LaunchAgents/com.github.actions.runner.plist
```

**Step 3: Verify**

```bash
launchctl list | grep actions
ps aux | grep run.sh
```

Expected: Runner process running

**Step 4: Commit (skip - local config only)**

---

### Task 3: Configure GitHub Webhook for Dependabot Alerts

**Files:**
- Modify: (GitHub UI - no local files)

**Step 1: Navigate to GitHub webhook settings**

Go to: https://github.com/philo-meerman/agent-monitor/settings/hooks

**Step 2: Add webhook**

- Payload URL: `https://api.github.com/repos/philo-meerman/agent-monitor/dispatches`
- Content type: `application/json`
- Events: Select "Dependabot alerts" only

**Step 3: Add workflow_dispatch trigger (backup for manual testing)**

The webhook will trigger a `repository_dispatch` event. We'll configure the workflow to respond to that.

**Step 4: Commit (skip - GitHub UI only)**

---

### Task 4: Create GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/upgrade-on-alert.yml`

**Step 1: Write the workflow**

```yaml
name: Upgrade Agent - On Vulnerability Alert

on:
  dependabot_alert:
    types: [created]
  repository_dispatch:
    types: [vulnerability-detected]

jobs:
  upgrade:
    name: Run Upgrade Agent
    runs-on: self-hosted
    timeout-minutes: 30

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run upgrade agent
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPO: ${{ github.repository }}
          LANGFUSE_HOST: ${{ secrets.LANGFUSE_HOST }}
          LANGFUSE_PUBLIC_KEY: ${{ secrets.LANGFUSE_PUBLIC_KEY }}
          LANGFUSE_SECRET_KEY: ${{ secrets.LANGFUSE_SECRET_KEY }}
          TRIGGER_TYPE: ${{ github.event_name == 'dependabot_alert' && 'webhook' || 'manual' }}
        run: |
          python run-upgrade-agent.py

      - name: Report status
        if: always()
        run: |
          echo "Upgrade agent completed"
```

**Step 2: Test workflow syntax**

```bash
# No local test available - will validate on push
```

**Step 3: Commit**

```bash
git add .github/workflows/upgrade-on-alert.yml
git commit -m "feat: add workflow for vulnerability-triggered upgrade agent"
git push origin main
```

---

### Task 5: Enhance LangFuse Tracing

**Files:**
- Modify: `upgrade_agent/tools/langfuse.py`

**Step 1: Add trigger_type to trace initialization**

```python
def get_langfuse_trace_config(trigger_type: str = "manual") -> dict:
    """Get LangFuse trace configuration with trigger metadata."""
    return {
        "metadata": {
            "trigger_type": trigger_type,
            "repository": GITHUB_REPO,
        }
    }
```

**Step 2: Update log_event to use trigger_type**

```python
def log_event(
    event_type: str,
    node: str,
    data: dict,
    trigger_type: str = "manual",
) -> str:
    # ... existing code ...
    trace = client.trace(
        name=trace_name,
        metadata={
            "trigger_type": trigger_type,  # Add this
            "repository": GITHUB_REPO,
            **data,
        }
    )
```

**Step 3: Modify run-upgrade-agent.py to pass trigger_type**

```python
import os

trigger_type = os.getenv("TRIGGER_TYPE", "manual")

# When calling agent, pass trigger_type
result = run_upgrade_agent_sync(trigger_type=trigger_type)
```

**Step 4: Update agent.py to accept trigger_type**

```python
# In run_upgrade_agent(), add:
def run_upgrade_agent(trigger_type: str = "manual"):
    # Pass to LangFuse client initialization
    log_event.invoke(..., trigger_type=trigger_type)
```

**Step 5: Run tests**

```bash
pytest tests/ -v
```

Expected: All tests pass

**Step 6: Commit**

```bash
git add upgrade_agent/tools/langfuse.py run-upgrade-agent.py upgrade_agent/agent.py
git commit -m "feat: add trigger_type tag to LangFuse traces"
git push origin main
```

---

### Task 6: End-to-End Test

**Files:**
- No new files

**Step 1: Manually trigger workflow**

```bash
# Using GitHub CLI
gh api repos/philo-meerman/agent-monitor/dispatches \
  -f event_type=vulnerability-detected \
  --method POST
```

**Step 2: Check runner job**

- GitHub → Actions → Most recent run
- Should show runner picked up job
- Check LangFuse dashboard for new trace with `trigger_type: webhook`

**Step 3: Verify**

Expected:
- Runner shows "busy" then "idle"
- LangFuse shows new trace with `trigger_type: webhook`
- All logs captured

**Step 4: Commit (skip - verification only)**

---

## Summary

| Task | Description | Local/GitHub |
|------|-------------|--------------|
| 1 | Self-hosted runner setup | Local |
| 2 | Runner as launchd service | Local |
| 3 | GitHub webhook config | GitHub UI |
| 4 | Actions workflow | Local (push to GitHub) |
| 5 | LangFuse enhancement | Local (push to GitHub) |
| 6 | End-to-end test | Verification |

## Prerequisites Before Starting

1. ☐ Generate GitHub PAT with `repo` scope
2. ☐ Register runner in GitHub (get token during config)
3. ☐ Ensure `GITHUB_TOKEN` in .env has repo permissions

## Execution Notes

- Task 1-2 are local setup (not in repo)
- Task 3 is GitHub UI only (no local files)
- Tasks 4-6 modify repo files and need commits
- Use a worktree for Tasks 4-6: `git worktree add ../agent-monitor-upgrade -b feat/self-hosted-runner`
