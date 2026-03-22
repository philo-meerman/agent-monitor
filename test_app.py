"""
Unit tests for agent-monitor
"""

import os
import unittest

from app import app, check_langfuse_status


class TestLangfuseIntegration(unittest.TestCase):
    """Test Langfuse-related functionality."""

    def test_langfuse_logo_exists(self):
        """Test that the Langfuse logo file exists in static folder."""
        logo_path = os.path.join(
            os.path.dirname(__file__), "static", "assets", "logos", "langfuse.png"
        )
        self.assertTrue(
            os.path.exists(logo_path), f"Langfuse logo should exist at {logo_path}"
        )

    def test_langfuse_status_check(self):
        """Test that Langfuse status check returns a valid status."""
        status = check_langfuse_status()
        valid_statuses = ["running", "stopped", "unknown"]
        self.assertIn(
            status,
            valid_statuses,
            f"Status should be one of {valid_statuses}, got {status}",
        )


class TestFlaskApp(unittest.TestCase):
    """Test Flask app endpoints."""

    def setUp(self):
        self.app = app.test_client()

    def test_home_page(self):
        """Test that home page loads."""
        response = self.app.get("/")
        self.assertEqual(response.status_code, 200)

    def test_logs_page(self):
        """Test that logs page loads."""
        response = self.app.get("/logs")
        self.assertEqual(response.status_code, 200)

    def test_api_agents(self):
        """Test /api/agents endpoint."""
        response = self.app.get("/api/agents")
        self.assertEqual(response.status_code, 200)
        import json

        data = json.loads(response.data)
        self.assertIsInstance(data, list)
        # Should have at least Brew Maintenance and Langfuse
        self.assertGreaterEqual(len(data), 2)

    def test_api_logs(self):
        """Test /api/logs endpoint."""
        response = self.app.get("/api/logs")
        self.assertEqual(response.status_code, 200)
        import json

        data = json.loads(response.data)
        self.assertIn("events", data)


class TestLangfuseStatusIntegration(unittest.TestCase):
    """Integration tests for Langfuse status - catches bugs in server context."""

    def setUp(self):
        self.app = app.test_client()

    @unittest.skipIf(os.environ.get("CI") == "true", "Requires Docker/Langfuse running")
    def test_langfuse_status_in_api_response(self):
        """
        Integration test: When /api/agents is called, Langfuse status should be 'running'.

        This test catches the bug where Docker is not accessible in the server context,
        causing the status to return 'unknown' instead of 'running'.
        """
        response = self.app.get("/api/agents")
        self.assertEqual(response.status_code, 200)

        import json

        agents = json.loads(response.data)

        # Find Langfuse agent
        langfuse_agent = None
        for agent in agents:
            if agent.get("name") == "Langfuse":
                langfuse_agent = agent
                break

        self.assertIsNotNone(
            langfuse_agent, "Langfuse agent should exist in API response"
        )

        # This is the key assertion - it will FAIL if status is 'unknown'
        self.assertEqual(
            langfuse_agent.get("status"),
            "running",
            f"Langfuse status should be 'running' when Docker is running, got '{langfuse_agent.get('status')}'",
        )


if __name__ == "__main__":
    unittest.main()
