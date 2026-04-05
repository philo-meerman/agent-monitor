"""Upgrade Agent - Execution Tools"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Add parent to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

from upgrade_agent.config import PROJECT_DIR


@tool
def run_tests(path: Optional[str] = None, verbose: bool = True) -> str:
    """Run pytest tests and return results.

    Args:
        path: Path to test file or directory (default: PROJECT_DIR/tests)
        verbose: Run pytest in verbose mode

    Returns:
        JSON string with test results including passed/failed counts
    """
    import re

    if path is None:
        path = str(PROJECT_DIR / "tests")

    test_path = Path(path)
    if not test_path.exists():
        return json.dumps(
            {
                "success": False,
                "error": f"Test path not found: {path}",
            }
        )

    cmd = ["python3", "-m", "pytest"]
    if verbose:
        cmd.append("-v")
    cmd.extend(["--tb=short", "--no-header"])
    cmd.append(str(test_path))

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        # Parse test results from output
        stdout = result.stdout
        stderr = result.stderr

        # Extract test counts from pytest output
        passed = 0
        failed = 0
        errors = 0

        # Match patterns like "18 passed" or "2 failed, 1 error"
        passed_match = re.search(r"(\d+) passed", stdout)
        failed_match = re.search(r"(\d+) failed", stdout)
        error_match = re.search(r"(\d+) error", stdout)

        if passed_match:
            passed = int(passed_match.group(1))
        if failed_match:
            failed = int(failed_match.group(1))
        if error_match:
            errors = int(error_match.group(1))

        # Also check for "X passed" in summary line
        summary_match = re.search(r"(\d+) passed", stdout)
        if summary_match and passed == 0:
            passed = int(summary_match.group(1))

        return json.dumps(
            {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "total": passed + failed + errors,
                "stdout": stdout[-5000:] if len(stdout) > 5000 else stdout,
                "stderr": stderr[-2000:] if len(stderr) > 2000 else stderr,
                "cmd": " ".join(cmd),
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "success": False,
                "error": "Tests timed out after 5 minutes",
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
            }
        )


@tool
def run_command(
    command: list[str], cwd: Optional[str] = None, timeout: int = 60
) -> str:
    """Run a shell command and return the result.

    Args:
        command: Command as list of strings
        cwd: Working directory
        timeout: Command timeout in seconds

    Returns:
        JSON string with command result
    """
    if cwd is None:
        cwd = str(PROJECT_DIR)

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return json.dumps(
            {
                "success": result.returncode == 0,
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "success": False,
                "error": f"Command timed out after {timeout} seconds",
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
            }
        )


@tool
def check_docker_status() -> str:
    """Check status of Docker containers.

    Returns:
        JSON string with Docker status
    """
    import subprocess

    try:
        # Check if Docker is running
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return json.dumps(
                {
                    "running": False,
                    "error": "Docker is not running",
                }
            )

        # Get running containers
        ps_result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        containers = []
        if ps_result.returncode == 0:
            for line in ps_result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("\t")
                    containers.append(
                        {
                            "name": parts[0] if len(parts) > 0 else "",
                            "status": parts[1] if len(parts) > 1 else "",
                            "image": parts[2] if len(parts) > 2 else "",
                        }
                    )

        return json.dumps(
            {
                "running": True,
                "containers": containers,
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "running": False,
                "error": str(e),
            }
        )


@tool
def start_app_and_verify(
    app_module: str = "app",
    port: Optional[int] = None,
    health_endpoint: str = "/",
    timeout: int = 10,
) -> str:
    """Start a Flask/Python app and verify it responds to requests.

    Args:
        app_module: Python module to run (e.g., 'app' for 'python -m app')
        port: Port to run on (auto-detect if in use)
        health_endpoint: Endpoint to check for health
        timeout: How long to wait for startup

    Returns:
        JSON with startup success and health check result
    """
    import time

    import requests as httpx

    # Find an available port
    if port is None:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            port = s.getsockname()[1]

    app_path = PROJECT_DIR / f"{app_module}.py"
    if not app_path.exists():
        return json.dumps(
            {"success": False, "error": f"App file not found: {app_module}.py"}
        )

    try:
        # Start the app in background
        proc = subprocess.Popen(
            ["python3", "-m", app_module],
            cwd=str(PROJECT_DIR),
            env={**os.environ, "FLASK_RUN_PORT": str(port)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait for startup
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                resp = httpx.get(f"http://localhost:{port}{health_endpoint}", timeout=2)
                if resp.status_code < 500:
                    return json.dumps(
                        {
                            "success": True,
                            "app_started": True,
                            "port": port,
                            "health_endpoint": health_endpoint,
                            "health_status": resp.status_code,
                            "pid": proc.pid,
                        }
                    )
            except Exception:
                time.sleep(0.5)
                continue

            time.sleep(0.5)

        # Timeout - kill the process
        proc.terminate()
        return json.dumps(
            {
                "success": False,
                "error": f"App did not respond within {timeout}s",
                "pid": proc.pid,
            }
        )

    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "error": str(e),
            }
        )


@tool
def check_app_health(url: str, expected_status: int = 200) -> str:
    """Check if a Python/Flask app is responding.

    Args:
        url: Full URL to check (e.g., http://localhost:5000/)
        expected_status: Expected HTTP status

    Returns:
        JSON with health status
    """
    import requests as httpx

    try:
        resp = httpx.get(url, timeout=10)
        return json.dumps(
            {
                "url": url,
                "healthy": resp.status_code == expected_status,
                "status_code": resp.status_code,
                "expected_status": expected_status,
            }
        )
    except Exception as e:
        return json.dumps(
            {
                "url": url,
                "healthy": False,
                "error": str(e),
            }
        )
