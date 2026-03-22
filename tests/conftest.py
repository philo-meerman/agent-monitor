"""Pytest configuration and fixtures."""
import os
import sys
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for testing."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
    monkeypatch.setenv("GITHUB_REPO", "test/repo")


@pytest.fixture
def temp_memory_dir(tmp_path, monkeypatch):
    """Set up temporary memory directory."""
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    monkeypatch.setattr("upgrade_agent.constants.MEMORY_DIR", memory_dir)
    return memory_dir
