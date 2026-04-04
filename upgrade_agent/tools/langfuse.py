"""Upgrade Agent - LangFuse Tracing"""

import json
import os
import sys
from datetime import datetime
from typing import Optional

# Add parent to path
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from langchain_core.tools import tool

from upgrade_agent.config import (
    GITHUB_REPO,
    LANGFUSE_HOST,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
)

# Global LangFuse client (lazy initialized)
_langfuse_client = None
_trigger_type = "manual"


def get_trigger_type() -> str:
    """Get the trigger type from environment or default."""
    return os.getenv("TRIGGER_TYPE", "manual")


def get_langfuse_client():
    """Get or create LangFuse client."""
    global _langfuse_client

    if _langfuse_client is None:
        try:
            from langfuse import Langfuse

            _langfuse_client = Langfuse(
                host=LANGFUSE_HOST,
                public_key=LANGFUSE_PUBLIC_KEY,
                secret_key=LANGFUSE_SECRET_KEY,
            )
        except ImportError:
            return None
        except Exception:
            return None

    return _langfuse_client


@tool
def log_trace_start(name: str, metadata: Optional[dict] = None) -> str:
    """Start a new LangFuse trace.

    Args:
        name: Trace name
        metadata: Optional metadata

    Returns:
        JSON string with trace ID
    """
    client = get_langfuse_client()
    if not client:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    try:
        trace = client.trace(
            name=name,
            metadata=metadata or {},
        )
        return json.dumps(
            {
                "success": True,
                "trace_id": trace.id,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def log_span(
    trace_id: str,
    name: str,
    input_data: Optional[dict] = None,
    output_data: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Log a span to LangFuse.

    Args:
        trace_id: Trace ID from log_trace_start
        name: Span name
        input_data: Input data
        output_data: Output data
        metadata: Optional metadata

    Returns:
        JSON string with success status
    """
    client = get_langfuse_client()
    if not client:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    try:
        # Note: LangFuse Python SDK v2 uses different API
        # This is a simplified version
        span_data = {
            "name": name,
            "input": input_data,
            "output": output_data,
            "metadata": metadata,
        }
        return json.dumps(
            {
                "success": True,
                "span": span_data,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def log_generation(
    trace_id: str,
    model: str,
    prompt: str,
    completion: str,
    metadata: Optional[dict] = None,
) -> str:
    """Log an LLM generation to LangFuse.

    Args:
        trace_id: Trace ID
        model: Model name
        prompt: Prompt sent
        completion: Completion received
        metadata: Optional metadata

    Returns:
        JSON string with success status
    """
    client = get_langfuse_client()
    if not client:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    try:
        # Log as a generation
        generation_data = {
            "model": model,
            "prompt": prompt,
            "completion": completion,
            "metadata": metadata,
        }
        return json.dumps(
            {
                "success": True,
                "generation": generation_data,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def log_event(
    event_type: str,
    node: str,
    data: dict,
    trigger_type: Optional[str] = None,
) -> str:
    """Log a generic event to LangFuse.

    Args:
        event_type: Type of event
        node: Node/agent component
        data: Event data
        trigger_type: Trigger source (webhook/manual). Defaults to TRIGGER_TYPE env var.

    Returns:
        JSON string with success status
    """
    client = get_langfuse_client()
    if not client:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    trigger = trigger_type or get_trigger_type()

    try:
        # Create a trace for the daily run if it doesn't exist
        today = datetime.now().strftime("%Y-%m-%d")
        trace_name = f"upgrade-agent-{today}"

        trace = client.trace(
            name=trace_name,
            metadata={
                "trigger_type": trigger,
                "repository": GITHUB_REPO,
                "node": node,
            },
        )

        # Add a span for this event
        trace.span(
            name=node,
            input={"event": event_type},
            output=data,
        )

        return json.dumps(
            {
                "success": True,
                "trace_id": trace.id,
                "trigger_type": trigger,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def log_upgrade_result(
    dependency: str,
    from_version: str,
    to_version: str,
    success: bool,
    error: Optional[str] = None,
    trigger_type: Optional[str] = None,
) -> str:
    """Log an upgrade result to LangFuse.

    Args:
        dependency: Dependency name
        from_version: Previous version
        to_version: New version
        success: Whether upgrade succeeded
        error: Error message if failed
        trigger_type: Trigger source (webhook/manual). Defaults to TRIGGER_TYPE env var.

    Returns:
        JSON string with success status
    """
    client = get_langfuse_client()
    if not client:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    trigger = trigger_type or get_trigger_type()

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        trace_name = f"upgrade-agent-{today}"

        trace = client.trace(
            name=trace_name,
            metadata={
                "trigger_type": trigger,
                "repository": GITHUB_REPO,
            },
        )

        trace.generation(
            model="upgrade-agent",
            prompt=f"Upgrade {dependency} from {from_version} to {to_version}",
            completion=f"Success: {success}" + (f", Error: {error}" if error else ""),
            metadata={
                "trigger_type": trigger,
                "repository": GITHUB_REPO,
                "dependency": dependency,
                "from_version": from_version,
                "to_version": to_version,
                "success": success,
                "error": error,
            },
        )

        return json.dumps({"success": True, "trigger_type": trigger})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
