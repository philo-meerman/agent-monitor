"""Upgrade Agent - State Recovery Tools"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

from upgrade_agent.tools.memory import read_memory


@tool
def restore_working_state() -> str:
    """Restore application to last known good state.

    Returns:
        JSON with: {success, state_restored}
    """

    memory_result = read_memory.invoke("last_known_good")
    memory_data = json.loads(memory_result)

    if not memory_data:
        return json.dumps(
            {
                "success": False,
                "error": "No last known good state found in memory",
            }
        )

    state_restored = True
    details = []

    last_state = memory_data[-1] if isinstance(memory_data, list) else memory_data

    files_to_restore = last_state.get("files", [])
    for file_info in files_to_restore:
        file_path = file_info.get("path")
        original_content = file_info.get("content")

        if not file_path:
            continue

        try:
            target = Path(file_path)
            if target.exists():
                target.write_text(original_content)
                details.append(f"Restored: {file_path}")
            else:
                details.append(f"File not found, skipped: {file_path}")
        except Exception as e:
            details.append(f"Failed to restore {file_path}: {e!s}")
            state_restored = False

    return json.dumps(
        {
            "success": state_restored,
            "state_restored": state_restored,
            "details": details,
        }
    )


@tool
def save_working_state(branch: str) -> str:
    """Save current working state before making changes.

    Args:
        branch: Branch name being worked on

    Returns:
        JSON with: {success, saved}
    """
    from upgrade_agent.config import PROJECT_DIR
    from upgrade_agent.tools.memory import append_memory

    state_to_save: dict = {
        "branch": branch,
        "files": [],
    }

    important_files = [
        PROJECT_DIR / "requirements.txt",
        PROJECT_DIR / "pyproject.toml",
    ]

    for file_path in important_files:
        if file_path.exists():
            try:
                state_to_save["files"].append(
                    {
                        "path": str(file_path),
                        "content": file_path.read_text(),
                    }
                )
            except Exception:
                continue

    append_memory.invoke("last_known_good", state_to_save)  # type: ignore[arg-type]

    return json.dumps(
        {
            "success": True,
            "saved": True,
            "files_saved": len(state_to_save["files"]),
            "branch": branch,
        }
    )


@tool
def get_last_successful_upgrade() -> str:
    """Get the last successful upgrade from memory.

    Returns:
        JSON with: {success, upgrade}
    """
    memory_result = read_memory.invoke("upgrades")
    upgrades = json.loads(memory_result)

    if not upgrades:
        return json.dumps(
            {
                "success": False,
                "error": "No upgrade history found",
            }
        )

    successful = [u for u in upgrades if u.get("success", False)]

    if not successful:
        return json.dumps(
            {
                "success": False,
                "error": "No successful upgrades found",
            }
        )

    last_success = successful[-1]
    return json.dumps(
        {
            "success": True,
            "upgrade": last_success,
        }
    )
