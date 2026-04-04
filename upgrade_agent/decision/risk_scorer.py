"""Upgrade Agent - Risk Scoring System"""

import json
from enum import Enum

from langchain_core.tools import tool

RiskLevel = Enum("RiskLevel", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
Recommendation = Enum("Recommendation", ["AUTO_UPGRADE", "REQUEST_REVIEW", "BLOCK"])


def calculate_risk_score(
    cve_severity: str,
    version_bump: str,
    test_coverage: float,
    is_direct_dependency: bool,
    has_known_fix: bool = True,
) -> dict:
    """Calculate risk score for an upgrade.

    Args:
        cve_severity: CVE severity (Critical/High/Medium/Low)
        version_bump: Type of version bump (major/minor/patch)
        test_coverage: Test coverage score (0.0 - 1.0)
        is_direct_dependency: Whether this is a direct dependency
        has_known_fix: Whether we have a known fix (default True, since we're upgrading)

    Returns:
        dict with score, risk_level, and recommendation
    """
    score = 0
    reasoning = []

    cve_severity_upper = cve_severity.upper() if cve_severity else "UNKNOWN"
    if cve_severity_upper == "CRITICAL":
        score += 40
        reasoning.append("Critical CVE (+40)")
    elif cve_severity_upper == "HIGH":
        score += 30
        reasoning.append("High CVE (+30)")
    elif cve_severity_upper == "MEDIUM":
        score += 15
        reasoning.append("Medium CVE (+15)")

    version_bump_lower = version_bump.lower() if version_bump else "patch"
    if version_bump_lower == "major":
        score += 20
        reasoning.append("Major version bump (+20)")
    elif version_bump_lower == "minor":
        score += 10
        reasoning.append("Minor version bump (+10)")

    if test_coverage < 0.3:
        score += 30
        reasoning.append("Low test coverage (+30)")
    elif test_coverage < 0.6:
        score += 15
        reasoning.append("Medium test coverage (+15)")

    if is_direct_dependency:
        score += 10
        reasoning.append("Direct dependency (+10)")

    if has_known_fix:
        score -= 20
        reasoning.append("Known fix available (-20)")

    score = max(0, min(score, 100))

    if score >= 70:
        risk_level = "CRITICAL"
        recommendation = "BLOCK"
    elif score >= 40:
        risk_level = "HIGH"
        recommendation = "REQUEST_REVIEW"
    else:
        risk_level = "LOW"
        recommendation = "AUTO_UPGRADE"

    return {
        "score": score,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "reasoning": "; ".join(reasoning),
    }


@tool
def risk_score_for_vulnerability(
    cve_severity: str,
    version_bump: str = "minor",
    test_coverage: float = 0.5,
    is_direct_dependency: bool = True,
    has_known_fix: bool = True,
) -> str:
    """Calculate risk score for upgrading a vulnerable package.

    Args:
        cve_severity: CVE severity level (Critical, High, Medium, Low)
        version_bump: Type of version bump needed (major, minor, patch)
        test_coverage: Test coverage for the package (0.0 to 1.0)
        is_direct_dependency: Whether this is a direct dependency
        has_known_fix: Whether a fix is available (default True)

    Returns:
        JSON string with score, risk_level, recommendation, and reasoning
    """
    result = calculate_risk_score(
        cve_severity=cve_severity,
        version_bump=version_bump,
        test_coverage=test_coverage,
        is_direct_dependency=is_direct_dependency,
        has_known_fix=has_known_fix,
    )
    return json.dumps(result)
