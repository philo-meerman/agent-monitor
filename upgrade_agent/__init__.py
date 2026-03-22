"""Upgrade Agent - Main package"""

__version__ = "0.1.0"

from .config import validate_config
from .constants import *
from .state import AgentState, AvailableUpdate, Dependency, UpdateAttempt

__all__ = [
    "AgentState",
    "Dependency",
    "AvailableUpdate",
    "UpdateAttempt",
    "validate_config",
]
