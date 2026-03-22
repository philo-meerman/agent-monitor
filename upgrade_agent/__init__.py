"""Upgrade Agent - Main package"""

__version__ = "0.1.0"

from .config import validate_config
from .constants import (
    DEFAULT_BRANCH,
    MAX_ATTEMPTS_PER_ISSUE,
    MAX_LLM_CALLS_PER_DAY,
    MAX_RUNTIME_MINUTES,
    MAX_TOKENS_PER_CYCLE,
    MEMORY_DIR,
    PROJECT_DIR,
    REPOSITORIES,
    REQUEST_TIMEOUT_SECONDS,
    RPD_LIMIT,
    RPM_LIMIT,
    UPGRADE_BRANCH_PREFIX,
)
from .state import AgentState, AvailableUpdate, Dependency, UpdateAttempt

__all__ = [
    "DEFAULT_BRANCH",
    "MAX_ATTEMPTS_PER_ISSUE",
    "MAX_LLM_CALLS_PER_DAY",
    "MAX_RUNTIME_MINUTES",
    "MAX_TOKENS_PER_CYCLE",
    "MEMORY_DIR",
    "PROJECT_DIR",
    "REPOSITORIES",
    "REQUEST_TIMEOUT_SECONDS",
    "RPD_LIMIT",
    "RPM_LIMIT",
    "UPGRADE_BRANCH_PREFIX",
    "AgentState",
    "AvailableUpdate",
    "Dependency",
    "UpdateAttempt",
    "validate_config",
]
