"""Upgrade Agent - Configuration"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Paths
AGENT_DIR = Path(__file__).parent
PROJECT_DIR = AGENT_DIR.parent

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO", "philo-meerman/agent-monitor")

# LangFuse
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")

# Local paths
LANGFUSE_REPO_PATH = str(PROJECT_DIR.parent / "langfuse")

# Validation
REQUIRED_ENV_VARS = ["GEMINI_API_KEY", "GITHUB_TOKEN"]


def validate_config() -> list[str]:
    """Validate required configuration."""
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.getenv(var):
            missing.append(var)
    return missing
