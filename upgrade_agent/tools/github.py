"""Upgrade Agent - GitHub Tools"""
import json
import os
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.tools import tool

from upgrade_agent.config import GITHUB_TOKEN, GITHUB_REPO
from upgrade_agent.constants import DEFAULT_BRANCH, UPGRADE_BRANCH_PREFIX


def get_headers() -> dict:
    """Get GitHub API headers."""
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


@tool
def github_get_default_branch() -> str:
    """Get the default branch name for the configured repository.
    
    Returns:
        JSON string with branch name
    """
    import httpx
    
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{GITHUB_REPO}",
            headers=get_headers(),
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return json.dumps({"branch": data.get("default_branch", "main")})
        return json.dumps({"error": f"Failed to get repo info: {response.status_code}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def github_create_branch(branch_name: str, base_branch: str = DEFAULT_BRANCH) -> str:
    """Create a new branch in the GitHub repository.
    
    Args:
        branch_name: Name of the branch to create
        base_branch: Branch to create from (default: main)
        
    Returns:
        JSON string with success status
    """
    import httpx
    
    try:
        # First get the commit SHA for the base branch
        ref_response = httpx.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/git/ref/heads/{base_branch}",
            headers=get_headers(),
            timeout=10,
        )
        if ref_response.status_code != 200:
            return json.dumps({"error": f"Base branch not found: {base_branch}"})
        
        commit_sha = ref_response.json().get("object", {}).get("sha")
        
        # Create the branch
        create_response = httpx.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/git/refs",
            headers=get_headers(),
            json={
                "ref": f"refs/heads/{branch_name}",
                "sha": commit_sha,
            },
            timeout=10,
        )
        
        if create_response.status_code in [200, 201]:
            return json.dumps({
                "success": True,
                "branch": branch_name,
                "sha": commit_sha,
            })
        else:
            error = create_response.json()
            return json.dumps({
                "success": False,
                "error": error.get("message", "Unknown error"),
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def github_get_file_content(path: str, branch: str = DEFAULT_BRANCH) -> str:
    """Get the content of a file from the repository.
    
    Args:
        path: Path to the file in the repo
        branch: Branch name
        
    Returns:
        JSON string with file content (base64 encoded)
    """
    import httpx
    
    try:
        response = httpx.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}",
            params={"ref": branch},
            headers=get_headers(),
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            return json.dumps({
                "content": data.get("content", ""),
                "encoding": data.get("encoding", "base64"),
                "sha": data.get("sha", ""),
            })
        return json.dumps({"error": f"File not found: {path}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def github_update_file(
    path: str,
    content: str,
    message: str,
    branch: str,
    sha: str = None,
) -> str:
    """Update or create a file in the repository.
    
    Args:
        path: Path to the file in the repo
        content: New content (will be base64 encoded)
        message: Commit message
        branch: Branch name
        sha: File SHA (required if updating existing file)
        
    Returns:
        JSON string with commit info
    """
    import httpx
    import base64
    
    try:
        # Encode content to base64
        encoded_content = base64.b64encode(content.encode()).decode()
        
        data = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }
        if sha:
            data["sha"] = sha
        
        response = httpx.put(
            f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}",
            headers=get_headers(),
            json=data,
            timeout=10,
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            return json.dumps({
                "success": True,
                "commit_sha": result.get("commit", {}).get("sha", ""),
                "file_path": result.get("content", {}).get("path", ""),
            })
        else:
            error = response.json()
            return json.dumps({
                "success": False,
                "error": error.get("message", "Unknown error"),
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def github_create_pr(
    title: str,
    body: str,
    branch: str,
    base: str = DEFAULT_BRANCH,
) -> str:
    """Create a pull request.
    
    Args:
        title: PR title
        body: PR body description
        branch: Branch to merge
        base: Target branch
        
    Returns:
        JSON string with PR URL
    """
    import httpx
    
    try:
        response = httpx.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/pulls",
            headers=get_headers(),
            json={
                "title": title,
                "body": body,
                "head": branch,
                "base": base,
            },
            timeout=10,
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            return json.dumps({
                "success": True,
                "pr_number": data.get("number"),
                "pr_url": data.get("html_url"),
                "pr_state": data.get("state"),
            })
        else:
            error = response.json()
            return json.dumps({
                "success": False,
                "error": error.get("message", "Unknown error"),
            })
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def github_add_label(pr_number: int, labels: list[str]) -> str:
    """Add labels to a pull request.
    
    Args:
        pr_number: PR number
        labels: List of label names
        
    Returns:
        JSON string with success status
    """
    import httpx
    
    try:
        response = httpx.post(
            f"https://api.github.com/repos/{GITHUB_REPO}/issues/{pr_number}/labels",
            headers=get_headers(),
            json={"labels": labels},
            timeout=10,
        )
        
        if response.status_code in [200, 201]:
            return json.dumps({"success": True, "labels": labels})
        else:
            error = response.json()
            return json.dumps({"success": False, "error": error.get("message")})
    except Exception as e:
        return json.dumps({"error": str(e)})
