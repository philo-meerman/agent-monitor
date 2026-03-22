"""Tests for upgrade agent."""

from upgrade_agent.constants import MAX_ATTEMPTS_PER_ISSUE, RPM_LIMIT
from upgrade_agent.rate_limiter import RateLimiter
from upgrade_agent.state import (
    AgentState,
    AvailableUpdate,
    Dependency,
    UpdateType,
    VersionBump,
)


class TestState:
    """Test state models."""

    def test_agent_state_empty(self):
        """Test empty agent state."""
        state = AgentState()
        assert state.dependencies == []
        assert state.available_updates == []
        assert state.completed_updates == []

    def test_dependency_creation(self):
        """Test creating a dependency."""
        dep = Dependency(
            name="flask",
            current_version="2.0",
            repo="agent-monitor",
            file_path="/path/to/requirements.txt",
            update_type=UpdateType.PYTHON_PACKAGE,
        )
        assert dep.name == "flask"
        assert dep.current_version == "2.0"

    def test_available_update(self):
        """Test creating an available update."""
        dep = Dependency(
            name="flask",
            current_version="2.0",
            repo="agent-monitor",
            file_path="/path/to/requirements.txt",
            update_type=UpdateType.PYTHON_PACKAGE,
        )
        update = AvailableUpdate(
            dependency=dep.dict(),
            latest_version="3.0",
            version_bump=VersionBump.MAJOR,
        )
        assert update.version_bump == VersionBump.MAJOR
        assert update.latest_version == "3.0"


class TestConstants:
    """Test constants."""

    def test_max_attempts(self):
        """Test max attempts constant."""
        assert MAX_ATTEMPTS_PER_ISSUE == 5

    def test_rpm_limit(self):
        """Test RPM limit."""
        assert RPM_LIMIT == 10


class TestRateLimiter:
    """Test rate limiter."""

    def test_rate_limiter_initialization(self):
        """Test rate limiter initializes correctly."""
        limiter = RateLimiter(rpm=5, max_daily=100)
        assert limiter.rpm == 5
        assert limiter.max_daily == 100

    def test_acquire_first_request(self):
        """Test first request is allowed."""
        limiter = RateLimiter(rpm=5, max_daily=100)
        assert limiter.acquire()

    def test_rpm_limit_enforced(self):
        """Test RPM limit is enforced."""
        limiter = RateLimiter(rpm=2, max_daily=100)

        # First two should succeed
        assert limiter.acquire()
        assert limiter.acquire()

        # Third should fail (rate limited)
        assert not limiter.acquire()

    def test_daily_limit_enforced(self):
        """Test daily limit is enforced."""
        limiter = RateLimiter(rpm=10, max_daily=2)

        # First two should succeed
        assert limiter.acquire()
        assert limiter.acquire()

        # Third should fail (daily limit)
        assert not limiter.acquire()

    def test_status(self):
        """Test getting status."""
        limiter = RateLimiter(rpm=10, max_daily=100)
        limiter.acquire()

        status = limiter.get_status()
        assert status["rpm_used"] == 1
        assert status["rpm_limit"] == 10
        assert status["daily_used"] == 1


class TestTools:
    """Test tools (basic import tests)."""

    def test_dependencies_tools_import(self):
        """Test dependency tools can be imported."""
        from upgrade_agent.tools.dependencies import (
            scan_requirements,
        )

        assert scan_requirements is not None

    def test_github_tools_import(self):
        """Test GitHub tools can be imported."""
        from upgrade_agent.tools.github import (
            github_create_branch,
        )

        assert github_create_branch is not None

    def test_memory_tools_import(self):
        """Test memory tools can be imported."""
        from upgrade_agent.tools.memory import (
            read_memory,
        )

        assert read_memory is not None


class TestSkills:
    """Test skills."""

    def test_skills_import(self):
        """Test skills can be imported."""
        from upgrade_agent.skills.base import (
            SKILL_BASE,
        )

        assert "upgrade" in SKILL_BASE.lower()

    def test_get_skill_for_major(self):
        """Test getting major upgrade skill."""
        from upgrade_agent.skills.base import get_skill_for_update_type

        skill = get_skill_for_update_type("major")
        assert "human review" in skill.lower()

    def test_get_skill_for_minor(self):
        """Test getting minor upgrade skill."""
        from upgrade_agent.skills.base import get_skill_for_update_type

        skill = get_skill_for_update_type("minor")
        assert "safe" in skill.lower()


class TestPrompts:
    """Test prompts."""

    def test_prompts_import(self):
        """Test prompts can be imported."""
        from upgrade_agent.prompts.reason import (
            REASONING_PROMPT,
        )

        assert "dependency" in REASONING_PROMPT.lower()

    def test_build_reasoning_prompt(self):
        """Test building reasoning prompt."""
        from upgrade_agent.prompts.reason import build_reasoning_prompt

        prompt = build_reasoning_prompt(
            name="flask",
            current_version="2.0",
            latest_version="3.0",
            version_bump="major",
        )
        assert "flask" in prompt
        assert "2.0" in prompt
        assert "3.0" in prompt
