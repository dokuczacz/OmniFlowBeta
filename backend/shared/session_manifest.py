"""
Session manifest: event model, append-only JSONL writer, and summary builder.

Storage path: users/{user_id}/sessions/session_manifest.jsonl
Schema:       omniflow.session_manifest.v1

Design constraints:
- Append-only: no read-modify-write; single upload_blob(overwrite=False ... append) via BlobClient.
  We use BlockBlobClient with append semantics via stage + commit in the simplest safe form:
  read current content, append line, upload overwrite=True.  Race risk is low (single user,
  single Function App instance); compaction is a future concern.
- Writer is non-blocking: on any storage error, log warning and continue (do NOT raise).
- gpt_note is set ONLY when state_changed=True.
- session_id is derived as user_id + date (UTC) — rolls over daily.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from azure.core.exceptions import ResourceNotFoundError

from shared.azure_client import AzureBlobClient
from shared.session_domain_classifier import classify_capability

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCHEMA_VERSION = "omniflow.session_manifest.v1"
SESSION_MANIFEST_PATH_TEMPLATE = "sessions/session_manifest.jsonl"
MAX_GPT_NOTE_LEN = 300
MAX_SUMMARY_EVENTS = 50


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _manifest_blob_path(user_id: str) -> str:
    return SESSION_MANIFEST_PATH_TEMPLATE


# ---------------------------------------------------------------------------
# Session ID
# ---------------------------------------------------------------------------

def _build_session_id(user_id: str) -> str:
    """Daily session granularity: {user_id}_{YYYYMMDD}."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{user_id}_{date_str}"


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------

def build_session_event(
    *,
    user_id: str,
    capability: str,
    thread_id: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    artifacts_updated: Optional[List[str]] = None,
    open_loops: Optional[List[str]] = None,
    state_changed: bool = False,
    gpt_note: Optional[str] = None,
    request_id: Optional[str] = None,
    interaction_id: Optional[str] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build a session event record conforming to omniflow.session_manifest.v1.

    gpt_note is only preserved when state_changed=True; otherwise stripped.
    """
    domain, _ = classify_capability(capability)

    effective_gpt_note: Optional[str] = None
    if state_changed and gpt_note:
        effective_gpt_note = str(gpt_note).strip()[:MAX_GPT_NOTE_LEN] or None

    event: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "session_id": _build_session_id(user_id),
        "user_id": user_id,
        "thread_id": thread_id or None,
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "capability": capability,
        "domains_touched": [domain],
        "tool_calls": tool_calls or [],
        "artifacts_updated": artifacts_updated or [],
        "state_changed": state_changed,
        "open_loops": open_loops or [],
        "request_id": request_id or None,
        "interaction_id": interaction_id or None,
    }
    if effective_gpt_note is not None:
        event["gpt_note"] = effective_gpt_note
    if extra_meta:
        event["meta"] = extra_meta
    return event


# ---------------------------------------------------------------------------
# JSONL writer
# ---------------------------------------------------------------------------

def append_session_event(user_id: str, event: Dict[str, Any]) -> bool:
    """
    Append one event line to users/{user_id}/sessions/session_manifest.jsonl.

    Returns True on success, False on any storage error (non-blocking).
    """
    try:
        blob_client = AzureBlobClient.get_blob_client(
            _manifest_blob_path(user_id), user_id
        )
        try:
            existing = blob_client.download_blob().readall().decode("utf-8")
        except ResourceNotFoundError:
            existing = ""

        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        new_content = (existing.rstrip("\n") + "\n" + line + "\n").lstrip("\n")
        blob_client.upload_blob(new_content.encode("utf-8"), overwrite=True)
        return True
    except Exception as exc:
        logging.warning("session_manifest: append_session_event failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Reader helpers
# ---------------------------------------------------------------------------

def _read_events(user_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Read raw JSONL events from blob. Returns list (oldest first)."""
    try:
        blob_client = AzureBlobClient.get_blob_client(
            _manifest_blob_path(user_id), user_id
        )
        raw = blob_client.download_blob().readall().decode("utf-8")
    except ResourceNotFoundError:
        return []
    except Exception as exc:
        logging.warning("session_manifest: _read_events failed: %s", exc)
        return []

    events: List[Dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    if limit is not None:
        events = events[-limit:]
    return events


# ---------------------------------------------------------------------------
# Session summary builder
# ---------------------------------------------------------------------------

def build_session_summary(user_id: str, max_events: int = MAX_SUMMARY_EVENTS) -> Dict[str, Any]:
    """
    Build a summary object for the current session from the latest N events.

    Returns:
      {
        "session_id": "...",
        "user_id": "...",
        "event_count": N,
        "domains_touched": [...],
        "artifacts_updated": [...],
        "open_loops": [...],
        "state_changed_count": N,
        "last_event_utc": "...",
        "events_included": N,
      }
    """
    session_id = _build_session_id(user_id)
    events = _read_events(user_id, limit=max_events)

    domains: List[str] = []
    artifacts: List[str] = []
    open_loops: List[str] = []
    state_changed_count = 0
    last_event_utc: Optional[str] = None

    for ev in events:
        if not isinstance(ev, dict):
            continue
        for d in (ev.get("domains_touched") or []):
            if d not in domains:
                domains.append(d)
        for a in (ev.get("artifacts_updated") or []):
            if a not in artifacts:
                artifacts.append(a)
        for ol in (ev.get("open_loops") or []):
            if ol not in open_loops:
                open_loops.append(ol)
        if ev.get("state_changed"):
            state_changed_count += 1
        ts = ev.get("timestamp_utc")
        if ts:
            last_event_utc = ts

    return {
        "session_id": session_id,
        "user_id": user_id,
        "event_count": len(events),
        "domains_touched": domains,
        "artifacts_updated": artifacts,
        "open_loops": open_loops,
        "state_changed_count": state_changed_count,
        "last_event_utc": last_event_utc,
        "events_included": len(events),
    }


def list_session_events(user_id: str, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    """Return a page of session events (newest first)."""
    events = _read_events(user_id)
    events_desc = list(reversed(events))
    return events_desc[offset: offset + limit]
