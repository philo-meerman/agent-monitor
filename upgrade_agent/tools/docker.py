"""Upgrade Agent - Docker & Health Check Tools"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from typing import Any, Optional

from langchain_core.tools import tool


@tool
def restart_docker_compose(path: str, services: Optional[list[Any]] = None) -> str:
    """Restart docker-compose services.

    Args:
        path: Path to docker-compose.yml file
        services: Optional list of specific services to restart (default: all)

    Returns:
        JSON with success status and container status
    """
    compose_path = Path(path)
    if not compose_path.exists():
        return json.dumps({"success": False, "error": f"File not found: {path}"})

    compose_dir = compose_path.parent

    try:
        # Stop services
        stop_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "down"],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Start services
        start_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "up", "-d"],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )

        # Wait for containers to start
        time.sleep(5)

        # Get container status
        ps_result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "ps", "--format", "json"],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        container_status = []
        if ps_result.returncode == 0 and ps_result.stdout:
            for line in ps_result.stdout.strip().split("\n"):
                if line:
                    try:
                        container_status.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

        return json.dumps(
            {
                "success": start_result.returncode == 0,
                "stop_output": stop_result.stdout[:500],
                "start_output": start_result.stdout[:500],
                "containers": container_status,
                "return_codes": {
                    "stop": stop_result.returncode,
                    "start": start_result.returncode,
                },
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "Timeout"})
    except FileNotFoundError:
        return json.dumps({"success": False, "error": "docker not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def check_container_health(container_name: str) -> str:
    """Check if a Docker container is healthy.

    Args:
        container_name: Name of the container

    Returns:
        JSON with health status
    """
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Health.Status}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            status = result.stdout.strip()
            return json.dumps(
                {
                    "container": container_name,
                    "health": status if status else "none",
                    "has_health_check": status != "none",
                }
            )
        else:
            return json.dumps({"error": f"Container not found: {container_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def check_container_status(container_name: str) -> str:
    """Get the status of a Docker container.

    Args:
        container_name: Name of the container

    Returns:
        JSON with status info
    """
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            status = result.stdout.strip()
            return json.dumps(
                {
                    "container": container_name,
                    "status": status,
                    "running": status == "running",
                }
            )
        else:
            return json.dumps({"error": f"Container not found: {container_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def check_service_health(
    url: str, expected_status: int = 200, timeout: int = 10
) -> str:
    """Check if a service is healthy via HTTP.

    Args:
        url: Health check URL
        expected_status: Expected HTTP status code
        timeout: Request timeout in seconds

    Returns:
        JSON with health status
    """
    import httpx

    try:
        response = httpx.get(url, timeout=timeout)
        healthy = response.status_code == expected_status

        return json.dumps(
            {
                "url": url,
                "healthy": healthy,
                "status_code": response.status_code,
                "expected_status": expected_status,
                "response_time_ms": response.elapsed.total_seconds() * 1000,
            }
        )
    except httpx.TimeoutException:
        return json.dumps(
            {
                "url": url,
                "healthy": False,
                "error": "timeout",
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


@tool
def wait_for_service_health(
    url: str, expected_status: int = 200, max_wait: int = 60, interval: int = 2
) -> str:
    """Wait for a service to become healthy.

    Args:
        url: Health check URL
        expected_status: Expected HTTP status code
        max_wait: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        JSON with final health status
    """
    import httpx

    start_time = time.time()
    last_error = None

    while time.time() - start_time < max_wait:
        try:
            response = httpx.get(url, timeout=10)
            if response.status_code == expected_status:
                elapsed = time.time() - start_time
                return json.dumps(
                    {
                        "url": url,
                        "healthy": True,
                        "status_code": response.status_code,
                        "wait_time_seconds": round(elapsed, 1),
                        "attempts": int(elapsed / interval),
                    }
                )
            last_error = f"status {response.status_code}"
        except Exception as e:
            last_error = str(e)

        time.sleep(interval)

    return json.dumps(
        {
            "url": url,
            "healthy": False,
            "error": last_error or "timeout",
            "max_wait_seconds": max_wait,
        }
    )


@tool
def get_compose_services(path: str) -> str:
    """Get list of services in docker-compose file.

    Args:
        path: Path to docker-compose.yml

    Returns:
        JSON with list of services
    """
    compose_path = Path(path)
    if not compose_path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    compose_dir = compose_path.parent

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "config", "--services"],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            services = [s.strip() for s in result.stdout.split("\n") if s.strip()]
            return json.dumps({"services": services})
        else:
            return json.dumps({"error": result.stderr})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def docker_pull_image(image: str, tag: str = "latest") -> str:
    """Pull a Docker image to verify it exists.

    Args:
        image: Image name
        tag: Image tag

    Returns:
        JSON string with success status
    """
    full_image = f"{image}:{tag}"

    try:
        result = subprocess.run(
            ["docker", "pull", full_image],
            capture_output=True,
            text=True,
            timeout=300,
        )

        return json.dumps(
            {
                "success": result.returncode == 0,
                "image": full_image,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:1000],
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
