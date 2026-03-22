"""Upgrade Agent - State Models"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UpdateType(str, Enum):
    """Type of dependency update."""

    PYTHON_PACKAGE = "python_package"
    DOCKER_IMAGE = "docker_image"


class VersionBump(str, Enum):
    """Type of version bump."""

    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    UNKNOWN = "unknown"


class UpdateStatus(str, Enum):
    """Status of an update attempt."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"


class Dependency(BaseModel):
    """A dependency to track."""

    name: str
    current_version: str
    repo: str
    file_path: str
    update_type: UpdateType


class AvailableUpdate(BaseModel):
    """An available update for a dependency."""

    dependency: Dependency
    latest_version: str
    version_bump: VersionBump
    breaking_changes: bool = False
    migration_guide_url: Optional[str] = None


class UpdateAttempt(BaseModel):
    """An attempt to upgrade a dependency."""

    update: AvailableUpdate
    attempt_number: int = 0
    status: UpdateStatus = UpdateStatus.PENDING
    plan: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    error_analysis: Optional[dict] = None
    test_results: Optional[dict] = None
    pr_url: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class Decision(BaseModel):
    """A decision made by the agent."""

    decision: str
    reasoning: str
    approved_by_human: Optional[bool] = None
    human_comment: Optional[str] = None


class TraceEvent(BaseModel):
    """An event for LangFuse tracing."""

    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: str
    node: str
    data: dict[str, Any]


class Memory(BaseModel):
    """Agent memory of past upgrades."""

    past_upgrades: dict[str, dict] = Field(default_factory=dict)
    known_errors: dict[str, dict] = Field(default_factory=dict)
    decisions: dict[str, dict] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    """Main state for the LangGraph agent."""

    # Scan results
    dependencies: list[Dependency] = Field(default_factory=list)
    available_updates: list[AvailableUpdate] = Field(default_factory=list)

    # Current processing
    current_update: Optional[UpdateAttempt] = None
    completed_updates: list[UpdateAttempt] = Field(default_factory=list)

    # Reasoning
    reasoning: str = ""
    decision: Optional[Decision] = None

    # Execution tracking
    attempts: int = 0
    max_attempts_reached: bool = False
    needs_human_help: bool = False

    # Runtime
    started_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)

    # Tracing
    traces: list[TraceEvent] = Field(default_factory=list)

    # Memory reference
    memory: Memory = Field(default_factory=Memory)

    # Configuration
    dry_run: bool = False
    force: bool = False

    class Config:
        arbitrary_types_allowed = True
