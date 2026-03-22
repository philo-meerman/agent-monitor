"""Upgrade Agent - Memory Tools"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

from upgrade_agent.constants import MEMORY_DIR


def get_memory_file(filename: str) -> Path:
    """Get path to memory file."""
    return MEMORY_DIR / filename


@tool
def read_memory(key: str = "upgrades") -> str:
    """Read from agent memory.

    Args:
        key: Memory key to read (upgrades, errors, decisions, metrics)

    Returns:
        JSON string with memory data
    """
    memory_file = get_memory_file(f"{key}.json")

    if not memory_file.exists():
        return json.dumps({})

    try:
        with open(memory_file) as f:
            data = json.load(f)
        return json.dumps(data)
    except Exception as e:
        return json.dumps({"error": str(e)})


@tool
def write_memory(key: str, data: dict) -> str:
    """Write to agent memory.

    Args:
        key: Memory key (upgrades, errors, decisions, metrics)
        data: Data to store

    Returns:
        JSON string with success status
    """
    memory_file = get_memory_file(f"{key}.json")

    # Load existing data
    existing = {}
    if memory_file.exists():
        try:
            with open(memory_file) as f:
                existing = json.load(f)
        except:
            pass

    # Merge data
    if isinstance(existing, dict) and isinstance(data, dict):
        existing.update(data)
    else:
        existing = data

    # Write back
    try:
        with open(memory_file, "w") as f:
            json.dump(existing, f, indent=2, default=str)
        return json.dumps({"success": True, "file": str(memory_file)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def append_memory(key: str, data: dict) -> str:
    """Append to a list in memory.

    Args:
        key: Memory key
        data: Data to append (must have an 'id' or 'timestamp' field)

    Returns:
        JSON string with success status
    """
    memory_file = get_memory_file(f"{key}.json")

    # Load existing
    existing = []
    if memory_file.exists():
        try:
            with open(memory_file) as f:
                existing = json.load(f)
                if not isinstance(existing, list):
                    existing = [existing]
        except:
            existing = []

    # Add timestamp if not present
    if "timestamp" not in data:
        data["timestamp"] = datetime.now().isoformat()

    # Generate ID if not present
    if "id" not in data:
        data["id"] = f"{key}-{len(existing)}"

    # Append
    existing.append(data)

    # Write back
    try:
        with open(memory_file, "w") as f:
            json.dump(existing, f, indent=2, default=str)
        return json.dumps({"success": True, "id": data["id"]})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def get_memory_metrics() -> str:
    """Get aggregated metrics from memory.

    Returns:
        JSON string with metrics
    """
    metrics = {
        "total_upgrades": 0,
        "successful": 0,
        "failed": 0,
        "needs_review": 0,
    }

    # Read upgrades
    upgrades_json = read_memory.invoke("upgrades")
    try:
        upgrades = json.loads(upgrades_json)
        if isinstance(upgrades, list):
            metrics["total_upgrades"] = len(upgrades)
            metrics["successful"] = sum(1 for u in upgrades if u.get("success"))
            metrics["failed"] = sum(1 for u in upgrades if not u.get("success"))
    except:
        pass

    return json.dumps(metrics)
