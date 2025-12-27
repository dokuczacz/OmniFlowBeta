"""
WP7 (Semantic Post-Processing / Indexer) shared helpers.

This module defines:
- Append-only queue in Blob Storage: interactions/indexer_queue.jsonl
- Cursor/state file: interactions/indexer_state.json
- Helper functions for token estimation and sanitization

Design goals:
- Deterministic, minimal payloads (no large tool outputs)
- Append without downloading the whole queue (Append Blob)
- Local-dev friendly (Azurite) via AzureConfig.CONNECTION_STRING
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from azure.core.exceptions import (
    AzureError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from azure.storage.blob import BlobClient

from .azure_client import AzureBlobClient
from .config import AzureConfig, UserNamespace


WP7_QUEUE_BLOB_NAME = "interactions/indexer_queue.jsonl"
WP7_STATE_BLOB_NAME = "interactions/indexer_state.json"
WP7_SEMANTIC_PREFIX = "interactions/semantic/"
WP7_SEMANTIC_INDEX_BLOB_NAME = "interactions/semantic/index.jsonl"
WP7_UNCATEGORIZED_PORTFOLIO_BLOB_NAME = "interactions/portfolio/uncategorized.jsonl"

WP7_QUEUE_SCHEMA_V1 = "omniflow.wp7.queue.v1"
WP7_STATE_SCHEMA_V1 = "omniflow.wp7.state.v1"
WP7_SEMANTIC_SCHEMA_V1 = "omniflow.wp7.semantic.v1"
WP7_SEMANTIC_INDEX_SCHEMA_V1 = "omniflow.wp7.semantic_index.v1"
WP7_UNCATEGORIZED_SCHEMA_V1 = "omniflow.wp7.uncategorized.v1"


def utc_now_iso() -> str:
    return _dt.datetime.utcnow().replace(tzinfo=_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _truncate(text: str, max_chars: int) -> str:
    value = str(text or "")
    if max_chars <= 0:
        return value
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 1] + "…"


def estimate_tokens_chars(text: str) -> Tuple[int, int]:
    """Estimate tokens for text using two heuristics: chars/4 (low) and chars/3 (high)."""
    s = str(text or "")
    n = len(s)
    low = (n + 3) // 4
    high = (n + 2) // 3
    return max(0, int(low)), max(0, int(high))


def derive_signal_level(artifact: Dict[str, Any]) -> str:
    """
    Return a deterministic signal level for a semantic artifact.

    Allowed values: low | medium | high
    - If artifact already contains a valid `signal_level`, keep it.
    - Otherwise, derive from `confidence`:
      - high: >= 0.85
      - medium: >= 0.65
      - low: < 0.65
    """
    raw = str((artifact or {}).get("signal_level") or "").strip().lower()
    if raw in ("low", "medium", "high"):
        return raw
    try:
        conf = float((artifact or {}).get("confidence"))
    except Exception:
        conf = 0.0
    if conf >= 0.85:
        return "high"
    if conf >= 0.65:
        return "medium"
    return "low"


def build_semantic_index_item(
    artifact: Dict[str, Any],
    *,
    user_id: str,
    interaction_id: str,
    semantic_blob_path: str,
) -> Dict[str, Any]:
    tags = artifact.get("tags") if isinstance(artifact.get("tags"), list) else []
    tags_clean: List[str] = []
    for t in tags:
        if isinstance(t, str) and t.strip():
            tags_clean.append(t.strip())
    summary = str(artifact.get("summary") or "").strip()
    summary_short = summary[:400]
    return {
        "schema_version": WP7_SEMANTIC_INDEX_SCHEMA_V1,
        "timestamp_utc": str(artifact.get("timestamp_utc") or utc_now_iso()),
        "user_id": str(user_id),
        "interaction_id": str(interaction_id),
        "category": str(artifact.get("category") or "").strip(),
        "signal_level": str(artifact.get("signal_level") or derive_signal_level(artifact)),
        "confidence": float(artifact.get("confidence") or 0.0),
        "tags": tags_clean[:12],
        "summary_short": summary_short,
        "semantic_blob_path": semantic_blob_path,
    }


def append_semantic_index_item(user_id: str, item: Dict[str, Any]) -> None:
    """Append a single JSONL line to the per-user semantic manifest index.jsonl."""
    line = json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not line.endswith("\n"):
        line += "\n"

    client = _get_append_blob_client(user_id, WP7_SEMANTIC_INDEX_BLOB_NAME)
    try:
        _append_jsonl_line(client, line)
    except AzureError as e:
        logging.error(f"WP7 append_semantic_index_item failed: {e}")
        raise


def extract_tools_used(tool_calls: Any, *, max_items: int = 25) -> List[str]:
    """Extract a compact list of tool names used in an interaction."""
    names: List[str] = []
    if not tool_calls:
        return names
    if not isinstance(tool_calls, list):
        return names
    for item in tool_calls:
        if len(names) >= max_items:
            break
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("tool_name") or item.get("function") or item.get("operationId")
        if name:
            names.append(str(name))
    # de-dup while keeping order
    seen = set()
    out: List[str] = []
    for n in names:
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


@dataclass(frozen=True)
class QueueThresholds:
    target_tokens: int = 1000
    hard_min_tokens: int = 600
    max_wait_seconds: int = 300
    max_items_per_run: int = 25
    max_user_chars: int = 2000
    max_assistant_chars: int = 4000


def build_queue_item(
    interaction_entry: Dict[str, Any],
    *,
    user_id: str,
    thresholds: QueueThresholds,
) -> Dict[str, Any]:
    """Create a sanitized queue item from a raw interaction entry."""
    interaction_id = str(interaction_entry.get("interaction_id") or "").strip()
    timestamp = str(interaction_entry.get("timestamp") or interaction_entry.get("timestamp_utc") or "").strip()
    thread_id = str(interaction_entry.get("thread_id") or "").strip() or None

    user_msg = _truncate(interaction_entry.get("user_message") or "", thresholds.max_user_chars)
    asst_msg = _truncate(interaction_entry.get("assistant_response") or "", thresholds.max_assistant_chars)

    tools_used = extract_tools_used(interaction_entry.get("tool_calls"))

    low, high = estimate_tokens_chars(user_msg + asst_msg)

    return {
        "schema_version": WP7_QUEUE_SCHEMA_V1,
        "interaction_id": interaction_id,
        "timestamp_utc": timestamp,
        "user_id": str(user_id),
        "thread_id": thread_id,
        "language": "mixed",
        "user_message": user_msg,
        "assistant_response": asst_msg,
        "tools_used": tools_used,
        "estimated_tokens": low,
        "estimated_tokens_hi": high,
    }


def _get_append_blob_client(user_id: str, blob_name: str) -> BlobClient:
    """Return a BlobClient for a user-namespaced blob name (used as Append Blob)."""
    # Ensure container exists (and is cached)
    AzureBlobClient.get_container_client()
    namespaced = UserNamespace.get_user_blob_name(user_id, blob_name)
    return BlobClient.from_connection_string(
        AzureConfig.CONNECTION_STRING,
        container_name=AzureConfig.CONTAINER_NAME,
        blob_name=namespaced,
    )


def append_queue_item(user_id: str, item: Dict[str, Any]) -> None:
    """Append a single JSONL line to the per-user WP7 queue (Append Blob)."""
    line = json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not line.endswith("\n"):
        line += "\n"

    client = _get_append_blob_client(user_id, WP7_QUEUE_BLOB_NAME)
    try:
        _append_jsonl_line(client, line)
    except AzureError as e:
        logging.error(f"WP7 append_queue_item failed: {e}")
        raise


def append_uncategorized_portfolio_item(user_id: str, item: Dict[str, Any]) -> None:
    """Append a single JSONL line to the per-user UNCATEGORIZED portfolio."""
    line = json.dumps(item, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not line.endswith("\n"):
        line += "\n"

    client = _get_append_blob_client(user_id, WP7_UNCATEGORIZED_PORTFOLIO_BLOB_NAME)
    try:
        _append_jsonl_line(client, line)
    except AzureError as e:
        logging.error(f"WP7 append_uncategorized_portfolio_item failed: {e}")
        raise


def _append_jsonl_line(client: BlobClient, line: str) -> None:
    """Append a JSONL line using Append Blob operations; migrate if blob exists as Block Blob."""
    data = line.encode("utf-8")

    # Create append blob if missing
    try:
        client.get_blob_properties()
    except ResourceNotFoundError:
        try:
            client.create_append_blob()
        except ResourceExistsError:
            pass

    try:
        client.append_block(data)
        return
    except HttpResponseError as e:
        # If the blob exists but is not an append blob (e.g. created earlier via upload_blob),
        # fall back to overwrite-with-appended-text once (migration path).
        msg = str(getattr(e, "message", "") or str(e))
        if "AppendBlob" not in msg and "append" not in msg.lower():
            raise

    existing = b""
    try:
        existing = client.download_blob().readall()
    except ResourceNotFoundError:
        existing = b""

    merged = existing + data
    client.upload_blob(merged, overwrite=True)


def load_indexer_state(user_id: str) -> Dict[str, Any]:
    """Load per-user indexer state; returns defaults if missing."""
    blob_client = AzureBlobClient.get_blob_client(WP7_STATE_BLOB_NAME, user_id)
    try:
        raw = blob_client.download_blob().readall()
    except ResourceNotFoundError:
        return {
            "schema_version": WP7_STATE_SCHEMA_V1,
            "user_id": str(user_id),
            "byte_offset": 0,
            "first_pending_at_utc": None,
            "updated_at_utc": utc_now_iso(),
        }
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("state is not an object")
        payload.setdefault("schema_version", WP7_STATE_SCHEMA_V1)
        payload.setdefault("user_id", str(user_id))
        payload.setdefault("byte_offset", 0)
        payload.setdefault("first_pending_at_utc", None)
        payload.setdefault("updated_at_utc", utc_now_iso())
        return payload
    except Exception:
        # If state is corrupted, do not crash indexing; reset safely.
        return {
            "schema_version": WP7_STATE_SCHEMA_V1,
            "user_id": str(user_id),
            "byte_offset": 0,
            "first_pending_at_utc": None,
            "updated_at_utc": utc_now_iso(),
        }


def save_indexer_state(user_id: str, state: Dict[str, Any]) -> None:
    blob_client = AzureBlobClient.get_blob_client(WP7_STATE_BLOB_NAME, user_id)
    payload = dict(state or {})
    payload["schema_version"] = WP7_STATE_SCHEMA_V1
    payload["user_id"] = str(user_id)
    payload["updated_at_utc"] = utc_now_iso()
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    blob_client.upload_blob(data.encode("utf-8"), overwrite=True)


def download_queue_tail(user_id: str, *, offset: int) -> Tuple[bytes, int]:
    """Download queue bytes from offset to end. Returns (data, total_length_bytes)."""
    # Use a Block/Append blob client (download works for both). We use the standard blob client here.
    blob_client = AzureBlobClient.get_blob_client(WP7_QUEUE_BLOB_NAME, user_id)
    try:
        props = blob_client.get_blob_properties()
        total = int(getattr(props, "size", 0) or 0)
    except ResourceNotFoundError:
        return b"", 0

    if offset < 0:
        offset = 0
    if offset >= total:
        return b"", total
    downloader = blob_client.download_blob(offset=offset)
    return downloader.readall(), total
