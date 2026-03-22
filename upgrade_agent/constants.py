"""Upgrade Agent - Constants and Boundaries"""

from pathlib import Path

# Paths
AGENT_DIR = Path(__file__).parent
PROJECT_DIR = AGENT_DIR.parent
MEMORY_DIR = PROJECT_DIR / "memory"
MEMORY_DIR.mkdir(exist_ok=True)

# Boundaries
MAX_ATTEMPTS_PER_ISSUE = 5
MAX_RUNTIME_MINUTES = 30
MAX_LLM_CALLS_PER_DAY = 500
MAX_TOKENS_PER_CYCLE = 100_000

# Rate Limits (Gemini Free Tier)
RPM_LIMIT = 10
RPD_LIMIT = 250

# Timeouts
REQUEST_TIMEOUT_SECONDS = 30
LONG_RUNNING_TIMEOUT_SECONDS = 300

# Version Classification
MAJOR_VERSION_BUMP = "major"
MINOR_VERSION_BUMP = "minor"
PATCH_VERSION_BUMP = "patch"

# Dependencies to Monitor
REPOSITORIES = {
    "agent-monitor": {
        "path": str(PROJECT_DIR),
        "files": ["requirements.txt"],
        "type": "python",
    },
    "langfuse": {
        "path": str(PROJECT_DIR.parent / "langfuse"),
        "files": ["docker-compose.v3.yml"],
        "type": "docker",
    },
}

# GitHub
DEFAULT_BRANCH = "main"
UPGRADE_BRANCH_PREFIX = "upgrade/"

# Notification
NEEDS_REVIEW_LABEL = "needs-review"
