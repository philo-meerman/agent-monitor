"""Upgrade Agent - Node.js Package Tools (npm/yarn)"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

from upgrade_agent.state import UpdateType


@tool
def scan_package_json(path: str) -> str:
    """Scan a package.json file and extract dependencies.

    Args:
        path: Path to package.json file

    Returns:
        JSON string of list of dependencies with name, version, and type
    """
    pkg_path = Path(path)
    if not pkg_path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        with open(pkg_path) as f:
            data = json.load(f)

        dependencies = []

        # Parse regular dependencies
        for name, version in data.get("dependencies", {}).items():
            dependencies.append(
                {
                    "name": name,
                    "current_version": version.lstrip("^~"),
                    "version_constraint": version,
                    "repo": pkg_path.parent.name,
                    "file_path": str(pkg_path),
                    "update_type": UpdateType.NODE_NPM,
                }
            )

        # Parse dev dependencies
        for name, version in data.get("devDependencies", {}).items():
            dependencies.append(
                {
                    "name": name,
                    "current_version": version.lstrip("^~"),
                    "version_constraint": version,
                    "repo": pkg_path.parent.name,
                    "file_path": str(pkg_path),
                    "update_type": UpdateType.NODE_NPM,
                    "is_dev": True,
                }
            )

        return json.dumps(dependencies)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def check_npm_version(package: str) -> str:
    """Check the latest version of an npm package.

    Args:
        package: Name of the npm package

    Returns:
        JSON string with latest version and info
    """
    import httpx

    try:
        response = httpx.get(
            f"https://registry.npmjs.org/{package}/latest",
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return json.dumps(
                {
                    "package": package,
                    "latest_version": data.get("version", "unknown"),
                    "dist_tags": data.get("dist-tags", {}),
                }
            )
        else:
            return json.dumps({"error": f"Package not found: {package}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def check_yarn_version(package: str) -> str:
    """Check the latest version of a package using yarn info.

    This is an alias for npm version checking since yarn uses the same registry.

    Args:
        package: Name of the package

    Returns:
        JSON string with latest version
    """
    result: str = check_npm_version.invoke({"package": package})
    return result


@tool
def install_npm_dependencies(path: str, lock_file: str = "package-lock.json") -> str:
    """Install npm dependencies after version update.

    Args:
        path: Path to package.json directory
        lock_file: Lock file to use (package-lock.json or yarn.lock)

    Returns:
        JSON with success status
    """
    import subprocess

    pkg_dir = Path(path)
    if not pkg_dir.exists():
        return json.dumps({"success": False, "error": f"Directory not found: {path}"})

    try:
        # Check for yarn.lock vs package-lock.json
        if (pkg_dir / "yarn.lock").exists():
            result = subprocess.run(
                ["yarn", "install"],
                cwd=pkg_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            cmd = "yarn install"
        else:
            result = subprocess.run(
                ["npm", "install"],
                cwd=pkg_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            cmd = "npm install"

        return json.dumps(
            {
                "success": result.returncode == 0,
                "cmd": cmd,
                "stdout": result.stdout[:2000] if result.stdout else "",
                "stderr": result.stderr[:2000] if result.stderr else "",
                "return_code": result.returncode,
            }
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "Timeout (5 min)"})
    except FileNotFoundError:
        return json.dumps({"success": False, "error": "npm or yarn not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def update_npm_package(package: str, version: str, file_path: str) -> str:
    """Update a specific package version in package.json.

    Args:
        package: Package name
        version: Target version
        file_path: Path to package.json

    Returns:
        JSON with success status and changes
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
        deps_pattern = rf'"{package}":\s*"[^"]*"'
        match = re.search(deps_pattern, content)
        if match:
            old = match.group(0)
            new = f'"{package}": "^{version}"'
            content = content.replace(old, new)
            changes.append({"old": old, "new": new})

        # Update in devDependencies
        dev_pattern = rf'"({package})":\s*"[^"]*"'
        for m in re.finditer(dev_pattern, content):
            old = m.group(0)
            if '"dependencies"' not in content[: m.start()]:
                new = f'"{package}": "^{version}"'
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
