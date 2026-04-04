"""Upgrade Agent - Test Coverage Analysis"""

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

from upgrade_agent.config import PROJECT_DIR


def find_test_files(project_dir: Path) -> list[Path]:
    """Find all test files in the project."""
    test_files: list[Path] = []

    for pattern in ["tests/**/*.py", "test_*.py", "*_test.py"]:
        test_files.extend(project_dir.glob(pattern))

    test_files = [f for f in test_files if f.name != "__pycache__"]
    return test_files


def check_imports_in_file(file_path: Path, packages: list[str]) -> dict:
    """Check if a file imports any of the given packages."""
    if not file_path.exists():
        return {"imports": [], "is_affected": False}

    try:
        content = file_path.read_text()
    except Exception:
        return {"imports": [], "is_affected": False}

    imports = []
    for pkg in packages:
        pkg_normalized = pkg.lower().replace("-", "_")

        import_patterns = [
            rf"^import {re.escape(pkg_normalized)}$",
            rf"^from {re.escape(pkg_normalized)} import",
            rf"^import {re.escape(pkg)}$",
            rf"^from {re.escape(pkg)} import",
        ]

        for pattern in import_patterns:
            if re.search(pattern, content, re.MULTILINE):
                imports.append(pkg)
                break

    return {
        "imports": list(set(imports)),
        "is_affected": len(imports) > 0,
    }


def calculate_coverage_score(
    affected_packages: list[str], test_dir: Optional[Path] = None
) -> dict:
    """Calculate test coverage for affected packages."""
    if test_dir is None:
        test_dir = PROJECT_DIR / "tests"

    if not test_dir.exists():
        return {
            "coverage_score": 0.0,
            "has_tests": False,
            "test_files_affected": [],
            "confidence": "low",
        }

    test_files = find_test_files(PROJECT_DIR)

    if not test_files:
        return {
            "coverage_score": 0.0,
            "has_tests": False,
            "test_files_affected": [],
            "confidence": "low",
        }

    affected_test_files = []

    for test_file in test_files:
        result = check_imports_in_file(test_file, affected_packages)
        if result["is_affected"]:
            affected_test_files.append(str(test_file.relative_to(PROJECT_DIR)))

    total_test_files = len(test_files)
    affected_count = len(affected_test_files)

    coverage_score = affected_count / total_test_files if total_test_files > 0 else 0.0

    if coverage_score >= 0.8:
        confidence = "high"
    elif coverage_score >= 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "coverage_score": coverage_score,
        "has_tests": affected_count > 0,
        "test_files_affected": affected_test_files,
        "total_test_files": total_test_files,
        "confidence": confidence,
    }


@tool
def check_test_coverage(affected_packages: str) -> str:
    """Check test coverage for affected packages.

    Args:
        affected_packages: JSON string of list of package names

    Returns:
        JSON string with coverage analysis
    """
    try:
        packages = json.loads(affected_packages)
        if not isinstance(packages, list):
            packages = [packages]
    except (json.JSONDecodeError, TypeError):
        packages = [affected_packages]

    result = calculate_coverage_score(packages)
    return json.dumps(result)


@tool
def get_test_coverage_for_vulnerabilities(vulnerabilities: str) -> str:
    """Get test coverage for packages with vulnerabilities.

    Args:
        vulnerabilities: JSON string of vulnerability list

    Returns:
        JSON string with vulnerabilities enriched with coverage data
    """
    try:
        vulns = json.loads(vulnerabilities)
        if not isinstance(vulns, list):
            vulns = [vulns]
    except (json.JSONDecodeError, TypeError):
        return json.dumps(
            {"error": "Invalid vulnerability data", "vulnerabilities": []}
        )

    packages = list({v.get("package", "") for v in vulns if v.get("package")})

    if not packages:
        return json.dumps({"error": "No packages found", "vulnerabilities": []})

    coverage = calculate_coverage_score(packages)

    for vuln in vulns:
        vuln["test_coverage"] = coverage["coverage_score"]
        vuln["has_test_coverage"] = coverage["has_tests"]
        vuln["test_files_affected"] = coverage["test_files_affected"]

    return json.dumps(
        {
            "vulnerabilities": vulns,
            "coverage": coverage,
        }
    )
