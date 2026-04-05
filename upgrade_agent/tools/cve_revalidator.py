"""Upgrade Agent - CVE Re-validation Tools"""

import json
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool


@tool
def verify_vulnerability_fixed(
    package: str,
    version: str,
    cve_ids: str,
) -> str:
    """Verify that the upgrade actually fixed the vulnerability.

    Re-scans the package after upgrade to confirm CVE is resolved.

    Args:
        package: Package name
        version: New version after upgrade
        cve_ids: JSON string of list of CVE IDs to check

    Returns:
        JSON with: {fixed: bool, details: [...]}
    """
    from upgrade_agent.tools.advisory import check_github_advisory, check_pypi_advisory

    try:
        cve_list = json.loads(cve_ids)
        if not isinstance(cve_list, list):
            cve_list = [cve_ids]
    except (json.JSONDecodeError, TypeError):
        cve_list = [cve_ids]

    details = []
    all_fixed = True

    gh_result = check_github_advisory.invoke(package_name=package)  # type: ignore[call-arg]
    gh_data = json.loads(gh_result)
    current_vulns = gh_data.get("vulnerabilities", [])

    pypi_result = check_pypi_advisory.invoke(package=package)  # type: ignore[call-arg]
    pypi_data = json.loads(pypi_result)
    current_advisories = pypi_data.get("advisories", [])

    for cve_id in cve_list:
        found = False

        for vuln in current_vulns:
            if cve_id in [
                vuln.get("cve_id", ""),
                vuln.get("ghsa_id", ""),
                vuln.get("id", ""),
            ]:
                found = True
                all_fixed = False
                details.append(
                    {
                        "cve_id": cve_id,
                        "status": "still_vulnerable",
                        "details": f"CVE {cve_id} still present in {package} {version}",
                    }
                )
                break

        if not found:
            for adv in current_advisories:
                if cve_id in [adv.get("id", ""), adv.get("cve_id", "")]:
                    found = True
                    all_fixed = False
                    details.append(
                        {
                            "cve_id": cve_id,
                            "status": "still_vulnerable",
                            "details": f"Advisory {cve_id} still present in {package} {version}",
                        }
                    )
                    break

        if not found:
            details.append(
                {
                    "cve_id": cve_id,
                    "status": "fixed",
                    "details": f"CVE {cve_id} not found in {package} {version}",
                }
            )

    return json.dumps(
        {
            "fixed": all_fixed,
            "package": package,
            "version": version,
            "cve_checked": cve_list,
            "details": details,
        }
    )


@tool
def check_version_vulnerabilities(
    package: str,
    version: str,
    ecosystem: str = "pip",
) -> str:
    """Check if a specific version of a package has known vulnerabilities.

    Args:
        package: Package name
        version: Version to check
        ecosystem: Package ecosystem (pip, npm, docker)

    Returns:
        JSON with: {has_vulnerabilities, vulnerabilities: [...]}
    """
    from upgrade_agent.tools.advisory import check_github_advisory

    gh_result = check_github_advisory.invoke(package_name=package, ecosystem=ecosystem)  # type: ignore[call-arg]
    gh_data = json.loads(gh_result)

    vulnerabilities = gh_data.get("vulnerabilities", [])

    vulnerabilities_in_version = []
    for vuln in vulnerabilities:
        vuln_versions = vuln.get("vulnerable_versions", [])
        if vuln_versions:
            if version in vuln_versions or "below" in str(vuln_versions).lower():
                vulnerabilities_in_version.append(vuln)
        else:
            vulnerabilities_in_version.append(vuln)

    return json.dumps(
        {
            "has_vulnerabilities": len(vulnerabilities_in_version) > 0,
            "package": package,
            "version": version,
            "vulnerabilities": vulnerabilities_in_version,
            "count": len(vulnerabilities_in_version),
        }
    )
