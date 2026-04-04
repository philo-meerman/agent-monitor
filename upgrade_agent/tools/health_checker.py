"""Upgrade Agent - Health Check Tools"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool


@tool
def verify_app_health() -> str:
    """Verify the application is running correctly after upgrade.

    Checks:
    - Flask app starts without errors
    - /api/agents endpoint responds
    - Home page renders

    Returns:
        JSON with: {success, checks: {...}, details: [...]}
    """
    from upgrade_agent.config import PROJECT_DIR

    checks = {
        "app_starts": False,
        "api_responds": False,
        "templates_render": False,
    }
    details = []

    app_path = PROJECT_DIR / "app.py"
    if not app_path.exists():
        return json.dumps(
            {
                "success": False,
                "error": "app.py not found",
                "checks": checks,
                "details": ["app.py not found in PROJECT_DIR"],
            }
        )

    try:
        import app as flask_app

        with flask_app.app.test_client() as client:
            try:
                response = client.get("/api/agents")
                if response.status_code == 200:
                    checks["api_responds"] = True
                    details.append("API /api/agents responded 200")
                else:
                    details.append(f"API returned status {response.status_code}")
            except Exception as e:
                details.append(f"API check failed: {e!s}")

            try:
                response = client.get("/")
                if response.status_code == 200:
                    checks["templates_render"] = True
                    details.append("Home page rendered successfully")
                else:
                    details.append(f"Home page returned status {response.status_code}")
            except Exception as e:
                details.append(f"Template check failed: {e!s}")

        checks["app_starts"] = True
        details.append("Flask app started successfully")

    except Exception as e:
        details.append(f"App health check failed: {e!s}")

    all_passed = all(checks.values())
    return json.dumps(
        {
            "success": all_passed,
            "checks": checks,
            "details": details,
        }
    )


@tool
def verify_docker_services() -> str:
    """Verify Docker services are healthy.

    Returns:
        JSON with: {success, services: {...}}
    """
    import subprocess

    services = {}

    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("\t")
                if len(parts) >= 2:
                    name = parts[0]
                    status = parts[1]
                    services[name] = {
                        "status": status,
                        "healthy": "Up" in status or "running" in status.lower(),
                    }

            return json.dumps(
                {
                    "success": True,
                    "services": services,
                    "details": [f"Found {len(services)} Docker services"],
                }
            )

        return json.dumps(
            {
                "success": False,
                "error": "Docker not available or not running",
                "services": {},
            }
        )

    except FileNotFoundError:
        return json.dumps(
            {
                "success": False,
                "error": "Docker command not found",
                "services": {},
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
                "services": {},
            }
        )


@tool
def run_health_check_suite() -> str:
    """Run comprehensive health check suite after upgrade.

    Checks:
    - Unit tests pass
    - App starts
    - API responds

    Returns:
        JSON with: {success, results: {...}}
    """
    results = {
        "tests_passed": False,
        "app_healthy": False,
        "api_responsive": False,
    }
    details = []

    import subprocess

    try:
        test_result = subprocess.run(
            ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=Path(__file__).parent.parent.parent,
        )

        if test_result.returncode == 0:
            results["tests_passed"] = True
            details.append("All unit tests passed")
        else:
            details.append(f"Tests failed: {test_result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        details.append("Test suite timed out")
    except Exception as e:
        details.append(f"Test execution failed: {e!s}")

    try:
        import app as flask_app

        with flask_app.app.test_client() as client:
            try:
                response = client.get("/api/agents")
                if response.status_code == 200:
                    results["api_responsive"] = True
                    details.append("API responded successfully")
            except Exception as e:
                details.append(f"API check failed: {e!s}")

        results["app_healthy"] = True

    except Exception as e:
        details.append(f"App health check failed: {e!s}")

    all_passed = all(results.values())
    return json.dumps(
        {
            "success": all_passed,
            "results": results,
            "details": details,
        }
    )
