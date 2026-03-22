"""Upgrade Agent - Execution Tools"""
import json
import os
import sys
import subprocess
from pathlib import Path

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from langchain_core.tools import tool

from upgrade_agent.config import PROJECT_DIR


@tool
def run_tests(path: str = None, verbose: bool = True) -> str:
    """Run pytest tests and return results.
    
    Args:
        path: Path to test file or directory (default: PROJECT_DIR/tests)
        verbose: Run pytest in verbose mode
        
    Returns:
        JSON string with test results
    """
    if path is None:
        path = str(PROJECT_DIR / "tests")
    
    test_path = Path(path)
    if not test_path.exists():
        return json.dumps({
            "success": False,
            "error": f"Test path not found: {path}",
        })
    
    cmd = ["python3", "-m", "pytest"]
    if verbose:
        cmd.append("-v")
    cmd.append(str(test_path))
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_DIR),
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        
        return json.dumps({
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "cmd": " ".join(cmd),
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "error": "Tests timed out after 5 minutes",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        })


@tool
def run_command(command: list[str], cwd: str = None, timeout: int = 60) -> str:
    """Run a shell command and return the result.
    
    Args:
        command: Command as list of strings
        cwd: Working directory
        timeout: Command timeout in seconds
        
    Returns:
        JSON string with command result
    """
    if cwd is None:
        cwd = str(PROJECT_DIR)
    
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        
        return json.dumps({
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "error": f"Command timed out after {timeout} seconds",
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        })


@tool
def check_docker_status() -> str:
    """Check status of Docker containers.
    
    Returns:
        JSON string with Docker status
    """
    import subprocess
    
    try:
        # Check if Docker is running
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode != 0:
            return json.dumps({
                "running": False,
                "error": "Docker is not running",
            })
        
        # Get running containers
        ps_result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        containers = []
        if ps_result.returncode == 0:
            for line in ps_result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("\t")
                    containers.append({
                        "name": parts[0] if len(parts) > 0 else "",
                        "status": parts[1] if len(parts) > 1 else "",
                        "image": parts[2] if len(parts) > 2 else "",
                    })
        
        return json.dumps({
            "running": True,
            "containers": containers,
        })
    except Exception as e:
        return json.dumps({
            "running": False,
            "error": str(e),
        })
