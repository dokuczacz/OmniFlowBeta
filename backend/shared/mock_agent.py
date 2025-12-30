import os
import time
from typing import Any, Dict


def _parse_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def mock_enabled() -> bool:
    return _parse_bool(os.environ.get("OMNIFLOW_MOCK_AGENT", "0"))


def mock_user_id(default: str = "tester") -> str:
    return str(os.environ.get("OMNIFLOW_MOCK_USER_ID", default) or default).strip() or default


def mock_marker(agent: str, default: str = ":::test:::") -> str:
    agent_norm = str(agent or "").strip().lower()
    if agent_norm in ("wp6", "wp6_agent", "tool_call_handler"):
        return str(os.environ.get("OMNIFLOW_MOCK_MARKER_WP6", ":::WP6 TEST:::") or ":::WP6 TEST:::").strip()
    if agent_norm in ("wp7", "wp7_indexer", "wp7_indexer_run", "wp7_indexer_timer"):
        return str(os.environ.get("OMNIFLOW_MOCK_MARKER_WP7", ":::WP7 TEST:::") or ":::WP7 TEST:::").strip()
    return str(os.environ.get("OMNIFLOW_MOCK_MARKER", default) or default).strip()


def build_mock_agent_response(
    *,
    agent: str,
    user_id: str,
    thread_id: str,
    user_message: str,
    marker: str = "",
) -> Dict[str, Any]:
    """
    Deterministic mock response for debugging/testing.

    Contract intentionally mirrors `tool_call_handler.finalize_response()` output shape.
    """
    marker_eff = str(marker or mock_marker(agent) or ":::test:::").strip() or ":::test:::"
    return {
        "status": "success",
        "response": marker_eff,
        "thread_id": thread_id,
        "user_id": user_id,
        "runtime_used": "mock",
        "vector_store_attached": False,
        "tool_calls_count": 0,
        "timings": {"total_ms": 0, "tools_ms": 0},
        "mock": {
            "enabled": True,
            "agent": str(agent or ""),
            "marker": marker_eff,
            "echo": {
                "user_message_chars": len(user_message or ""),
                "user_message_snip": (user_message or "")[:120],
            },
            "created_ts": time.time(),
        },
    }
