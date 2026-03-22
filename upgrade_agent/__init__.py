"""Upgrade Agent - Main package"""
__version__ = "0.1.0"

from .state import AgentState, Dependency, AvailableUpdate, UpdateAttempt
from .constants import *
from .config import validate_config

__all__ = [
    "AgentState",
    "Dependency",
    "AvailableUpdate", 
    "UpdateAttempt",
    "validate_config",
]
