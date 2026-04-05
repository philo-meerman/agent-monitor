"""Upgrade Agent - Advisory Database Tools"""

import json
import os
import sys

import httpx

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

GITHUB_ADVISORY_API = "https://api.github.com/advisories"


@tool
def check_github_advisory(package_name: str, ecosystem: str = "pip") -> str:
    """Check GitHub Advisory Database for vulnerabilities.

    Args:
        package_name: Name of package (e.g., "flask", "langfuse")
        ecosystem: Package ecosystem (pip, npm, docker, etc.)

    Returns:
        JSON string with list of CVEs affecting this package
    """
    normalized_name = package_name.lower().replace("_", "-")

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.getenv('GITHUB_TOKEN')}"

    try:
        response = httpx.get(
            GITHUB_ADVISORY_API,
            params={
                "affects": normalized_name,
                "ecosystem": ecosystem,
            },
            headers=headers,
            timeout=30,
        )

        if response.status_code == 200:
            advisories = response.json()
            vulnerabilities = []

            for adv in advisories:
                cve_id = adv.get("cve_id", "N/A")
                ghsa_id = adv.get("ghsa_id", "")
                severity = adv.get("severity", "unknown").upper()
                summary = adv.get("description", "")
                published_at = adv.get("published_at", "")
                vulnerabilities_fixed_in = adv.get("vulnerabilities_fixed_in", [])

                vulnerabilities.append(
                    {
                        "id": ghsa_id or cve_id,
                        "cve_id": cve_id,
                        "ghsa_id": ghsa_id,
                        "severity": severity,
                        "summary": summary[:500] if summary else "",
                        "published_at": published_at,
                        "vulnerable_versions": vulnerabilities_fixed_in,
                        "source": "github_advisory",
                    }
                )

            return json.dumps(
                {
                    "package": package_name,
                    "ecosystem": ecosystem,
                    "vulnerabilities": vulnerabilities,
                    "count": len(vulnerabilities),
                }
            )
        elif response.status_code == 403:
            return json.dumps(
                {
                    "error": "Rate limited or unauthenticated. Add GITHUB_TOKEN for higher limits.",
                    "package": package_name,
                    "vulnerabilities": [],
                }
            )
        else:
            return json.dumps(
                {
                    "error": f"API returned {response.status_code}",
                    "package": package_name,
                    "vulnerabilities": [],
                }
            )

    except Exception as e:
        return json.dumps(
            {
                "error": str(e),
                "package": package_name,
                "vulnerabilities": [],
            }
        )


@tool
def check_pypi_advisory(package: str) -> str:
    """Check PyPI security advisories.

    Uses PyPI JSON API to get security metadata.

    Args:
        package: Name of the PyPI package

    Returns:
        JSON string with list of advisories
    """
    normalized_name = package.lower().replace("_", "-")

    try:
        response = httpx.get(
            f"https://pypi.org/pypi/{normalized_name}/json",
            timeout=10,
        )

        if response.status_code != 200:
            return json.dumps(
                {
                    "error": f"Package not found: {package}",
                    "package": package,
                    "advisories": [],
                }
            )

        data = response.json()
        info = data.get("info", {})

        vulnerabilities = []

        if info.get("yanked", False):
            yanked_reason = info.get("yanked_reason", "")
            if (
                "security" in yanked_reason.lower()
                or "vulnerability" in yanked_reason.lower()
            ):
                vulnerabilities.append(
                    {
                        "id": f"pypi-{normalized_name}",
                        "severity": "HIGH",
                        "summary": yanked_reason[:500],
                        "vulnerable_versions": [info.get("version", "")],
                        "source": "pypi_yanked",
                    }
                )

        return json.dumps(
            {
                "package": package,
                "latest_version": info.get("release_version", "unknown"),
                "advisories": vulnerabilities,
                "count": len(vulnerabilities),
            }
        )

    except Exception as e:
        return json.dumps(
            {
                "error": str(e),
                "package": package,
                "advisories": [],
            }
        )


@tool
def get_vulnerability_scan() -> str:
    """Scan all project dependencies for vulnerabilities.

    Combines GitHub Advisory + PyPI Advisory results.

    Returns:
        JSON string with aggregated vulnerabilities sorted by severity
    """
    # This will need to be completed after implementing the other tools
    from upgrade_agent.tools.dependencies import get_all_dependencies

    deps_json = get_all_dependencies.invoke({})
    deps = json.loads(deps_json)

    if isinstance(deps, dict) and "error" in deps:
        return json.dumps({"error": deps.get("error"), "vulnerabilities": []})

    if not isinstance(deps, list):
        return json.dumps(
            {"error": "Failed to get dependencies", "vulnerabilities": []}
        )

    all_vulnerabilities = []

    for dep in deps:
        package_name = dep.get("name", "")
        if not package_name:
            continue

        ecosystem = "pip"
        if dep.get("update_type") == "docker_image":
            ecosystem = "docker"

        gh_result = check_github_advisory.invoke(  # type: ignore[call-arg]
            package_name=package_name, ecosystem=ecosystem
        )
        gh_data = json.loads(gh_result)
        vulns = gh_data.get("vulnerabilities", [])
        for v in vulns:
            v["package"] = package_name
            v["dependency_type"] = dep.get("update_type", "unknown")
            v["is_direct"] = True
        all_vulnerabilities.extend(vulns)

        pypi_result = check_pypi_advisory.invoke(package=package_name)  # type: ignore[call-arg]
        pypi_data = json.loads(pypi_result)
        advisories = pypi_data.get("advisories", [])
        for a in advisories:
            a["package"] = package_name
            a["dependency_type"] = dep.get("update_type", "unknown")
            a["is_direct"] = True
        all_vulnerabilities.extend(advisories)

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}

    all_vulnerabilities.sort(
        key=lambda x: (
            severity_order.get(x.get("severity", "UNKNOWN"), 5),
            x.get("published_at", ""),
        ),
        reverse=True,
    )

    return json.dumps(
        {
            "vulnerabilities": all_vulnerabilities,
            "total_count": len(all_vulnerabilities),
            "by_severity": {
                "critical": sum(
                    1 for v in all_vulnerabilities if v.get("severity") == "CRITICAL"
                ),
                "high": sum(
                    1 for v in all_vulnerabilities if v.get("severity") == "HIGH"
                ),
                "medium": sum(
                    1 for v in all_vulnerabilities if v.get("severity") == "MEDIUM"
                ),
                "low": sum(
                    1 for v in all_vulnerabilities if v.get("severity") == "LOW"
                ),
            },
        }
    )
