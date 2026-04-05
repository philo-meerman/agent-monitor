"""Upgrade Agent - Poetry Tools"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

from upgrade_agent.state import UpdateType


@tool
def scan_pyproject_toml(path: str) -> str:
    """Scan a pyproject.toml file and extract Poetry dependencies.

    Args:
        path: Path to pyproject.toml file

    Returns:
        JSON string of list of dependencies with name, version
    """
    pkg_path = Path(path)
    if not pkg_path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        with open(pkg_path) as f:
            content = f.read()

        dependencies = []

        # Parse [tool.poetry.dependencies] section
        deps_match = re.search(
            r"\[tool\.poetry\.dependencies\](.+?)(?:\n\[|$)",
            content,
            re.DOTALL,
        )
        if deps_match:
            deps_content = deps_match.group(1)
            for line in deps_content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Match: package = "version" or package = "^version"
                match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"', line)
                if match:
                    name = match.group(1)
                    # Skip python version
                    if name.lower() == "python":
                        continue
                    version = match.group(2)
                    dependencies.append(
                        {
                            "name": name,
                            "current_version": version.lstrip("^~"),
                            "version_constraint": version,
                            "repo": pkg_path.parent.name,
                            "file_path": str(pkg_path),
                            "update_type": UpdateType.PYTHON_POETRY,
                        }
                    )

        # Parse [tool.poetry.dev-dependencies] section
        dev_deps_match = re.search(
            r"\[tool\.poetry\.dev-dependencies\](.+?)(?:\n\[|$)",
            content,
            re.DOTALL,
        )
        if dev_deps_match:
            deps_content = dev_deps_match.group(1)
            for line in deps_content.split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                match = re.match(r'^([a-zA-Z0-9_-]+)\s*=\s*"([^"]*)"', line)
                if match:
                    name = match.group(1)
                    version = match.group(2)
                    dependencies.append(
                        {
                            "name": name,
                            "current_version": version.lstrip("^~"),
                            "version_constraint": version,
                            "repo": pkg_path.parent.name,
                            "file_path": str(pkg_path),
                            "update_type": UpdateType.PYTHON_POETRY,
                            "is_dev": True,
                        }
                    )

        return json.dumps(dependencies)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def check_poetry_version(package: str) -> str:
    """Check the latest version of a package on PyPI.

    Poetry uses PyPI, so we can use the same approach as pip.

    Args:
        package: Name of the PyPI package

    Returns:
        JSON string with latest version
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
                }
            )
        else:
            return json.dumps({"error": f"Package not found: {package}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def update_pyproject_toml(package: str, version: str, file_path: str) -> str:
    """Update a package version in pyproject.toml.

    Args:
        package: Package name
        version: Target version
        file_path: Path to pyproject.toml

    Returns:
        JSON with success and changes
    """
    import re

    target_path = Path(file_path)
    if not target_path.exists():
        return json.dumps({"success": False, "error": f"File not found: {file_path}"})

    try:
        with open(target_path) as f:
            content = f.read()

        original = content
        changes = []

        # Update in dependencies
        pattern = rf'({re.escape(package)})\s*=\s*"[^"]*"'
        for match in re.finditer(pattern, content):
            old = match.group(0)
            new = f'{package} = "^{version}"'
            content = content.replace(old, new)
            changes.append({"old": old, "new": new})

        if content != original:
            with open(target_path, "w") as f:
                f.write(content)

        return json.dumps(
            {
                "success": True,
                "changes": changes,
                "package": package,
                "version": version,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def run_poetry_lock(path: str) -> str:
    """Run poetry lock to update lock file after version change.

    Args:
        path: Path to pyproject.toml directory

    Returns:
        JSON with success status
    """
    import subprocess

    pkg_dir = Path(path)
    if not pkg_dir.exists():
        return json.dumps({"success": False, "error": f"Directory not found: {path}"})

    try:
        result = subprocess.run(
            ["poetry", "lock", "--no-update"],
            cwd=pkg_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )

        return json.dumps(
            {
                "success": result.returncode == 0,
                "cmd": "poetry lock --no-update",
                "stdout": result.stdout[:2000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
                "return_code": result.returncode,
            }
        )
    except FileNotFoundError:
        return json.dumps({"success": False, "error": "poetry not found"})
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "Timeout (5 min)"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
