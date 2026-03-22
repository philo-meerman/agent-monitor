"""Upgrade Agent - Dependency Tools"""

import json
import os
import re
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

from upgrade_agent.config import LANGFUSE_REPO_PATH, PROJECT_DIR
from upgrade_agent.state import UpdateType


@tool
def scan_requirements(path: str) -> str:
    """Scan a requirements.txt file and extract dependencies with versions.

    Args:
        path: Path to requirements.txt file

    Returns:
        JSON string of list of dependencies with name, version, and file path
    """
    req_path = Path(path)
    if not req_path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    dependencies = []

    with open(req_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            # Handle various formats: package==version, package>=version, package
            match = re.match(r"^([a-zA-Z0-9_-]+)([=<>!]+)?(.+)?$", line)
            if match:
                name = match.group(1).lower()
                # Normalize name (replace underscores with hyphens)
                name = name.replace("_", "-")
                version = match.group(3).strip() if match.group(3) else "latest"

                dependencies.append(
                    {
                        "name": name,
                        "current_version": version,
                        "repo": "agent-monitor",
                        "file_path": str(req_path),
                        "update_type": UpdateType.PYTHON_PACKAGE,
                    }
                )

    return json.dumps(dependencies)


@tool
def scan_docker_compose(path: str) -> str:
    """Scan a docker-compose.yml file and extract image versions.

    Args:
        path: Path to docker-compose.yml file

    Returns:
        JSON string of list of Docker images with current tags
    """
    compose_path = Path(path)
    if not compose_path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    dependencies = []

    with open(compose_path) as f:
        content = f.read()

        # Find all image: lines
        # Simple regex - for production, use a proper YAML parser
        image_pattern = re.compile(r"^\s*image:\s*([^\s#]+)", re.MULTILINE)

        for match in image_pattern.finditer(content):
            image = match.group(1)

            # Split image and tag
            if ":" in image:
                name, tag = image.rsplit(":", 1)
            else:
                name = image
                tag = "latest"

            # Extract service name (look backward for "services:" section)
            # This is simplified - real implementation would parse YAML properly
            service_name = name.split("/")[-1] if "/" in name else name

            dependencies.append(
                {
                    "name": name,
                    "current_version": tag,
                    "repo": "langfuse",
                    "file_path": str(compose_path),
                    "service": service_name,
                    "update_type": UpdateType.DOCKER_IMAGE,
                }
            )

    return json.dumps(dependencies)


@tool
def check_pypi_version(package: str) -> str:
    """Check the latest version of a package on PyPI.

    Args:
        package: Name of the PyPI package

    Returns:
        JSON string with latest version and info
    """
    import httpx

    try:
        response = httpx.get(
            f"https://pypi.org/pypi/{package}/json",
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            info = data.get("info", {})
            return json.dumps(
                {
                    "package": package,
                    "latest_version": info.get("release_version", "unknown"),
                    "pypi_url": info.get("package_url", ""),
                    "summary": info.get("summary", ""),
                }
            )
        else:
            return json.dumps({"error": f"Package not found: {package}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def check_dockerhub_version(image: str) -> str:
    """Check the latest tag for a Docker image on Docker Hub.

    Args:
        image: Name of the Docker image (e.g., 'postgres', 'nginx')

    Returns:
        JSON string with latest tag info
    """
    import httpx

    # For official images, use library/ prefix
    if "/" not in image:
        image = f"library/{image}"

    try:
        # Get tags from Docker Hub API
        response = httpx.get(
            f"https://hub.docker.com/v2/repositories/{image}/tags",
            params={"page_size": 10},
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results:
                latest = results[0]
                return json.dumps(
                    {
                        "image": image,
                        "latest_tag": latest.get("name", "unknown"),
                        "tag_count": data.get("count", 0),
                    }
                )
        return json.dumps({"error": f"Could not fetch tags for {image}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def get_all_dependencies() -> str:
    """Get all dependencies to monitor from configured repositories.

    Returns:
        JSON string of all dependencies found
    """
    all_deps = []

    # Scan agent-monitor requirements.txt
    agent_monitor_req = PROJECT_DIR / "requirements.txt"
    if agent_monitor_req.exists():
        deps_json = scan_requirements.invoke(str(agent_monitor_req))
        deps = json.loads(deps_json)
        if isinstance(deps, list):
            all_deps.extend(deps)

    # Scan langfuse docker-compose
    langfuse_compose = Path(LANGFUSE_REPO_PATH) / "docker-compose.v3.yml"
    if langfuse_compose.exists():
        deps_json = scan_docker_compose.invoke(str(langfuse_compose))
        deps = json.loads(deps_json)
        if isinstance(deps, list):
            all_deps.extend(deps)

    return json.dumps(all_deps)
