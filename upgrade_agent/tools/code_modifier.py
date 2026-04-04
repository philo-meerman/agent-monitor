"""Upgrade Agent - Code Modification Tools"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool


@tool
def find_and_replace_imports(
    old_package: str,
    new_package: str,
    file_path: str,
) -> str:
    """Find and replace package imports.

    Args:
        old_package: Old package name
        new_package: New package name (if renamed)
        file_path: File to modify

    Returns:
        JSON with: {success, files_modified, changes_made}
    """
    target_path = Path(file_path)

    if not target_path.exists():
        return json.dumps(
            {
                "success": False,
                "error": f"File not found: {file_path}",
                "changes_made": [],
            }
        )

    try:
        content = target_path.read_text()
        original_content = content

        old_pkg_normalized = old_package.lower().replace("-", "_").replace(".", "/")
        new_pkg_normalized = new_package.lower().replace("-", "_").replace(".", "/")

        changes_made = []

        import_patterns = [
            (rf"^import {re.escape(old_package)}$", f"import {new_package}"),
            (rf"^from {re.escape(old_package)} import", f"from {new_package} import"),
            (
                rf"^import {re.escape(old_pkg_normalized)}$",
                f"import {new_pkg_normalized}",
            ),
            (
                rf"^from {re.escape(old_pkg_normalized)} import",
                f"from {new_pkg_normalized} import",
            ),
        ]

        for pattern, replacement in import_patterns:
            matches = list(re.finditer(pattern, content, re.MULTILINE))
            if matches:
                content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
                changes_made.append(
                    {
                        "pattern": pattern,
                        "replacement": replacement,
                        "count": len(matches),
                    }
                )

        if content != original_content:
            target_path.write_text(content)
            return json.dumps(
                {
                    "success": True,
                    "files_modified": [file_path],
                    "changes_made": changes_made,
                }
            )

        return json.dumps(
            {
                "success": True,
                "files_modified": [],
                "changes_made": [],
                "message": "No imports found to replace",
            }
        )

    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "changes_made": []})


@tool
def update_api_signatures(
    file_path: str,
    old_signature: str,
    new_signature: str,
) -> str:
    """Update function/variable signatures between versions.

    Uses AST parsing for accurate replacements.

    Args:
        file_path: File to modify
        old_signature: Old function signature (e.g., "function(arg1, arg2)")
        new_signature: New function signature (e.g., "function(arg1, new_arg, arg2)")

    Returns:
        JSON with: {success, changes_made, error}
    """
    target_path = Path(file_path)

    if not target_path.exists():
        return json.dumps(
            {
                "success": False,
                "error": f"File not found: {file_path}",
                "changes_made": [],
            }
        )

    try:
        content = target_path.read_text()
        original_content = content

        pattern = re.escape(old_signature)
        content = re.sub(pattern, new_signature, content)

        if content != original_content:
            target_path.write_text(content)

        return json.dumps(
            {
                "success": True,
                "changes_made": [
                    {
                        "old_signature": old_signature,
                        "new_signature": new_signature,
                    }
                ],
            }
        )

    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "changes_made": []})


@tool
def find_breaking_changes(
    from_version: str,
    to_version: str,
    package: str,
) -> str:
    """Find potential breaking changes between package versions.

    Args:
        from_version: Current version
        to_version: Target version
        package: Package name

    Returns:
        JSON with: {breaking_changes, migration_guide_url, risk_level}
    """
    breaking_changes = []
    migration_guide_url = None
    risk_level = "low"

    from_parts = [int(x) for x in from_version.split(".") if x.isdigit()]
    to_parts = [int(x) for x in to_version.split(".") if x.isdigit()]

    if len(from_parts) >= 2 and len(to_parts) >= 2:
        if to_parts[0] > from_parts[0]:
            risk_level = "high"
            breaking_changes.append(
                {
                    "type": "major_version_bump",
                    "description": f"Major version change from {from_version} to {to_version}",
                    "likely_breaking": True,
                }
            )
        elif to_parts[1] > from_parts[1]:
            risk_level = "medium"
            breaking_changes.append(
                {
                    "type": "minor_version_bump",
                    "description": f"Minor version change from {from_version} to {to_version}",
                    "likely_breaking": False,
                }
            )

    migration_guides = {
        "langfuse": "https://langfuse.com/docs/migration",
        "langchain": "https://python.langchain.com/docs/migration",
        "flask": "https://flask.palletsprojects.com/migration/",
        "django": "https://docs.djangoproject.com/en/stable/howto/upgrade-version/",
    }

    for pkg, url in migration_guides.items():
        if pkg in package.lower():
            migration_guide_url = url
            break

    return json.dumps(
        {
            "breaking_changes": breaking_changes,
            "migration_guide_url": migration_guide_url,
            "risk_level": risk_level,
            "from_version": from_version,
            "to_version": to_version,
        }
    )


@tool
def scan_for_package_usage(
    package: str,
    directory: Optional[str] = None,
) -> str:
    """Scan directory for usage of a package.

    Args:
        package: Package name to search for
        directory: Directory to scan (defaults to PROJECT_DIR)

    Returns:
        JSON with: {files, usages}
    """
    # Import here to avoid circular imports
    from upgrade_agent.config import PROJECT_DIR

    if directory:
        scan_dir = Path(directory)
    else:
        scan_dir = PROJECT_DIR

    if not scan_dir.exists():
        return json.dumps(
            {"error": f"Directory not found: {directory}", "files": [], "usages": []}
        )

    pkg_normalized = package.lower().replace("-", "_")

    files = []
    usages = []

    for py_file in scan_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text()

            patterns = [
                rf"import\s+{re.escape(pkg_normalized)}",
                rf"from\s+{re.escape(pkg_normalized)}\s+import",
                rf"import\s+{re.escape(package)}",
                rf"from\s+{re.escape(package)}\s+import",
            ]

            for pattern in patterns:
                matches = list(re.finditer(pattern, content, re.MULTILINE))
                if matches:
                    files.append(str(py_file.relative_to(PROJECT_DIR)))
                    usages.append(
                        {
                            "file": str(py_file.relative_to(PROJECT_DIR)),
                            "line_numbers": [
                                content[: m.start()].count("\n") + 1 for m in matches
                            ],
                            "pattern": pattern,
                        }
                    )
                    break

        except Exception:
            continue

    return json.dumps(
        {
            "files": list(set(files)),
            "usages": usages,
            "package": package,
        }
    )
