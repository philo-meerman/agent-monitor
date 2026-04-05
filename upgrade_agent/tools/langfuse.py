"""Upgrade Agent - LangFuse Tracing via OpenTelemetry"""

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
    LANGFUSE_PROJECT_ID,
    LANGFUSE_PUBLIC_KEY,
    LANGFUSE_SECRET_KEY,
)

# Session for HTTP requests
_session = None


def get_session():
    """Get or create requests session."""
    global _session
    if _session is None:
        import requests

        _session = requests.Session()
        _session.auth = (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY)
    return _session


def get_trigger_type() -> str:
    """Get the trigger type from environment or default."""
    return os.getenv("TRIGGER_TYPE", "manual")


def get_langfuse_project_id() -> str:
    """Get the LangFuse project ID from config or environment."""
    # Use configured project ID or default to the one visible in UI
    return LANGFUSE_PROJECT_ID or os.getenv(
        "LANGFUSE_PROJECT_ID", "cmnkonusl000bpk07ckdg20e2"
    )


def create_otel_trace(project_id: str, trace_name: str, metadata: dict) -> str:
    """Create a trace via OpenTelemetry API.

    Args:
        project_id: LangFuse project ID
        trace_name: Name of the trace
        metadata: Trace metadata

    Returns:
        Trace ID
    """
    import uuid

    trace_id = str(uuid.uuid4())
    _timestamp = datetime.utcnow().isoformat() + "Z"

    # Build OTLP trace payload
    trace_payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "langfuse.project_id",
                            "value": {"stringValue": project_id},
                        },
                        {
                            "key": "service.name",
                            "value": {"stringValue": "upgrade-agent"},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": str(uuid.uuid4())[:16],
                                "name": trace_name,
                                "startTimeUnixNano": int(
                                    datetime.utcnow().timestamp() * 1e9
                                ),
                                "endTimeUnixNano": int(
                                    datetime.utcnow().timestamp() * 1e9
                                ),
                                "attributes": [
                                    {"key": k, "value": {"stringValue": str(v)}}
                                    for k, v in metadata.items()
                                ],
                                "kind": "SPAN_KIND_INTERNAL",
                            }
                        ]
                    }
                ],
            }
        ]
    }

    # Send to LangFuse OpenTelemetry endpoint
    session = get_session()
    url = f"{LANGFUSE_HOST}/api/public/otel/v1/traces"

    try:
        _resp = session.post(url, json=trace_payload, timeout=10)
        if _resp.status_code >= 400:
            return f"error: {_resp.status_code} - {_resp.text}"
        return trace_id
    except Exception as e:
        return f"error: {e!s}"


def create_otel_span(
    trace_id: str,
    span_name: str,
    input_data: Optional[dict] = None,
    output_data: Optional[dict] = None,
    metadata: Optional[dict] = None,
    project_id: Optional[str] = None,
) -> str:
    """Create a span via OpenTelemetry API.

    Args:
        trace_id: Parent trace ID
        span_name: Name of the span
        input_data: Input data
        output_data: Output data
        metadata: Span metadata
        project_id: LangFuse project ID

    Returns:
        Span ID or error
    """
    import uuid

    project_id = project_id or get_langfuse_project_id()
    _timestamp = datetime.utcnow().isoformat() + "Z"
    _span_id = str(uuid.uuid4())[:16]

    # Build attributes
    attributes = []
    if input_data:
        attributes.append(
            {"key": "langfuse.input", "value": {"stringValue": json.dumps(input_data)}}
        )
    if output_data:
        attributes.append(
            {
                "key": "langfuse.output",
                "value": {"stringValue": json.dumps(output_data)},
            }
        )
    if metadata:
        for k, v in metadata.items():
            attributes.append({"key": k, "value": {"stringValue": str(v)}})

    # Build OTLP span payload
    span_payload = {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {
                            "key": "langfuse.project_id",
                            "value": {"stringValue": project_id},
                        },
                        {
                            "key": "service.name",
                            "value": {"stringValue": "upgrade-agent"},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": _span_id,
                                "parentSpanId": "",  # Root span
                                "name": span_name,
                                "startTimeUnixNano": int(
                                    datetime.utcnow().timestamp() * 1e9
                                ),
                                "endTimeUnixNano": int(
                                    datetime.utcnow().timestamp() * 1e9
                                ),
                                "attributes": attributes,
                                "kind": "SPAN_KIND_INTERNAL",
                            }
                        ]
                    }
                ],
            }
        ]
    }

    # Send to LangFuse OpenTelemetry endpoint
    session = get_session()
    url = f"{LANGFUSE_HOST}/api/public/otel/v1/traces"

    try:
        _resp = session.post(url, json=span_payload, timeout=10)
        if _resp.status_code >= 400:
            return f"error: {_resp.status_code} - {_resp.text}"
        return _span_id
    except Exception as e:
        return f"error: {e!s}"


# Cache for active trace
_active_trace_id = None


def get_active_trace_id() -> Optional[str]:
    """Get the currently active trace ID."""
    return _active_trace_id


def set_active_trace_id(trace_id: str):
    """Set the active trace ID."""
    global _active_trace_id
    _active_trace_id = trace_id


@tool
def log_trace_start(name: str, metadata: Optional[dict] = None) -> str:
    """Start a new LangFuse trace.

    Args:
        name: Trace name
        metadata: Optional metadata

    Returns:
        JSON string with trace ID
    """
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    try:
        project_id = get_langfuse_project_id()
        trigger = get_trigger_type()
        meta = {
            "trigger_type": trigger,
            "repository": GITHUB_REPO,
        }
        if metadata:
            meta.update(metadata)

        trace_id = create_otel_trace(project_id, name, meta)
        set_active_trace_id(trace_id)

        return json.dumps(
            {
                "success": True,
                "trace_id": trace_id,
                "trace_name": name,
                "project_id": project_id,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def log_span(
    name: str,
    input_data: Optional[dict] = None,
    output_data: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Log a span to LangFuse.

    Args:
        name: Span name
        input_data: Input data
        output_data: Output data
        metadata: Optional metadata

    Returns:
        JSON string with success status
    """
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    try:
        trace_id = get_active_trace_id()
        if not trace_id:
            return json.dumps({"success": False, "error": "No active trace"})

        project_id = get_langfuse_project_id()
        _span_id = create_otel_span(
            trace_id=trace_id,
            span_name=name,
            input_data=input_data or {},
            output_data=output_data or {},
            metadata=metadata or {},
            project_id=project_id,
        )

        return json.dumps(
            {
                "success": True,
                "span_id": _span_id,
                "span_name": name,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def log_generation(
    model: str,
    prompt: str,
    completion: str,
    metadata: Optional[dict] = None,
) -> str:
    """Log an LLM generation to LangFuse.

    Args:
        model: Model name
        prompt: Prompt sent
        completion: Completion received
        metadata: Optional metadata

    Returns:
        JSON string with success status
    """
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    try:
        project_id = get_langfuse_project_id()

        # Create a generation span
        import uuid

        trace_id = get_active_trace_id() or str(uuid.uuid4())
        _timestamp = datetime.utcnow().isoformat() + "Z"

        generation_payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "langfuse.project_id",
                                "value": {"stringValue": project_id},
                            },
                            {
                                "key": "service.name",
                                "value": {"stringValue": "upgrade-agent"},
                            },
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": trace_id,
                                    "spanId": str(uuid.uuid4())[:16],
                                    "name": f"generation: {model}",
                                    "startTimeUnixNano": int(
                                        datetime.utcnow().timestamp() * 1e9
                                    ),
                                    "endTimeUnixNano": int(
                                        datetime.utcnow().timestamp() * 1e9
                                    ),
                                    "attributes": [
                                        {
                                            "key": "langfuse.legacy.trace_id",
                                            "value": {"stringValue": trace_id},
                                        },
                                        {
                                            "key": "model",
                                            "value": {"stringValue": model},
                                        },
                                        {
                                            "key": "langfuse.prompt",
                                            "value": {"stringValue": prompt[:1000]},
                                        },
                                        {
                                            "key": "langfuse.completion",
                                            "value": {"stringValue": completion[:1000]},
                                        },
                                        {
                                            "key": "type",
                                            "value": {"stringValue": "generation"},
                                        },
                                    ],
                                    "kind": "SPAN_KIND_CLIENT",
                                }
                            ]
                        }
                    ],
                }
            ]
        }

        session = get_session()
        url = f"{LANGFUSE_HOST}/api/public/otel/v1/traces"
        _resp = session.post(url, json=generation_payload, timeout=10)

        return json.dumps(
            {
                "success": True,
                "model": model,
                "trace_id": trace_id,
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
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    trigger = trigger_type or get_trigger_type()
    project_id = get_langfuse_project_id()

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        trace_name = f"upgrade-agent-{today}"

        meta = {
            "trigger_type": trigger,
            "repository": GITHUB_REPO,
            "node": node,
            "event_type": event_type,
        }

        # Create trace
        trace_id = create_otel_trace(project_id, trace_name, meta)
        set_active_trace_id(trace_id)

        # Create event span
        _span_id = create_otel_span(
            trace_id=trace_id,
            span_name=node,
            input_data={"event": event_type},
            output_data=data,
            metadata=meta,
            project_id=project_id,
        )

        return json.dumps(
            {
                "success": True,
                "trace_id": trace_id,
                "trace_name": trace_name,
                "trigger_type": trigger,
                "project_id": project_id,
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
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    trigger = trigger_type or get_trigger_type()
    project_id = get_langfuse_project_id()

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        trace_name = f"upgrade-agent-{today}"

        meta = {
            "trigger_type": trigger,
            "repository": GITHUB_REPO,
            "dependency": dependency,
            "from_version": from_version,
            "to_version": to_version,
            "success": str(success),
        }
        if error:
            meta["error"] = error

        # Create trace
        trace_id = create_otel_trace(project_id, trace_name, meta)
        set_active_trace_id(trace_id)

        # Create result span
        _span_id = create_otel_span(
            trace_id=trace_id,
            span_name="upgrade-result",
            input_data={
                "dependency": dependency,
                "from": from_version,
                "to": to_version,
            },
            output_data={"success": success, "error": error},
            metadata=meta,
            project_id=project_id,
        )

        return json.dumps(
            {
                "success": True,
                "trigger_type": trigger,
                "trace_id": trace_id,
                "project_id": project_id,
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@tool
def log_test_results(
    test_results: dict,
    trigger_type: Optional[str] = None,
) -> str:
    """Log test results to LangFuse with detailed breakdown.

    Args:
        test_results: Dict with test results (passed, failed, errors, total, stdout, stderr)
        trigger_type: Trigger source (webhook/manual). Defaults to TRIGGER_TYPE env var.

    Returns:
        JSON string with success status
    """
    if not LANGFUSE_PUBLIC_KEY or not LANGFUSE_SECRET_KEY:
        return json.dumps({"success": False, "error": "LangFuse not configured"})

    trigger = trigger_type or get_trigger_type()
    project_id = get_langfuse_project_id()

    try:
        passed = test_results.get("passed", 0)
        failed = test_results.get("failed", 0)
        errors = test_results.get("errors", 0)
        total = test_results.get("total", passed + failed + errors)
        success = test_results.get("success", failed == 0 and errors == 0)

        # Extract key test names from output if available
        test_names = []
        stdout = test_results.get("stdout", "")
        for line in stdout.split("\n"):
            if "::test_" in line and "PASSED" in line:
                test_names.append(line.split("::")[-1].split(" ")[0])
            elif "::test_" in line and "FAILED" in line:
                test_names.append(line.split("::")[-1].split(" ")[0])

        meta = {
            "trigger_type": trigger,
            "repository": GITHUB_REPO,
            "test_type": "pytest",
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "total": total,
            "success": success,
            "test_names": test_names[:20],  # Limit to 20 test names
        }

        today = datetime.now().strftime("%Y-%m-%d")
        trace_name = f"test-results-{today}"

        # Create trace with test results
        trace_id = create_otel_trace(project_id, trace_name, meta)
        set_active_trace_id(trace_id)

        # Create span with detailed test output
        _span_id = create_otel_span(
            trace_id=trace_id,
            span_name="test-execution",
            input_data={
                "test_command": test_results.get("cmd", "pytest"),
            },
            output_data={
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "total": total,
                "success": success,
                "test_names": test_names[:10],
            },
            metadata=meta,
            project_id=project_id,
        )

        # If there are failures, create a separate span for the failure details
        if failed > 0 or errors > 0:
            stderr = test_results.get("stderr", "")
            stdout_tail = "\n".join(stdout.split("\n")[-20:])  # Last 20 lines

            create_otel_span(
                trace_id=trace_id,
                span_name="test-failures",
                input_data={"failed_count": failed, "error_count": errors},
                output_data={
                    "stderr": stderr[-2000:] if stderr else "",
                    "stdout_tail": stdout_tail[-2000:],
                },
                metadata={"test_failures": True},
                project_id=project_id,
            )

        return json.dumps(
            {
                "success": True,
                "trigger_type": trigger,
                "trace_id": trace_id,
                "project_id": project_id,
                "test_summary": {
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "total": total,
                    "success": success,
                },
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
