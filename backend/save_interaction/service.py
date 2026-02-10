import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from azure.core.exceptions import ResourceNotFoundError

from shared.azure_client import AzureBlobClient

INTERACTIONS_DIR = "interactions"
INDEX_FILE = f"{INTERACTIONS_DIR}/index.jsonl"
MAX_DUPLICATE_AGE_SECONDS = 30


def _current_timestamp() -> str:
    return datetime.utcnow().isoformat()


def _interaction_blob_name(interaction_id: str) -> str:
    return f"{INTERACTIONS_DIR}/{interaction_id}.json"


def _index_blob_client(user_id: str):
    return AzureBlobClient.get_blob_client(INDEX_FILE, user_id)


def _read_index_lines(user_id: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    blob_client = _index_blob_client(user_id)
    try:
        raw = blob_client.download_blob().readall().decode("utf-8")
    except ResourceNotFoundError:
        return [], []
    lines = [line for line in raw.splitlines() if line.strip()]
    entries: List[Dict[str, Any]] = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return lines, entries


def _write_index_lines(user_id: str, lines: List[str]) -> None:
    blob_client = _index_blob_client(user_id)
    content = "\n".join(lines) + ("\n" if lines else "")
    blob_client.upload_blob(content.encode("utf-8"), overwrite=True)


def _is_duplicate_interaction(existing_logs: List[Dict[str, Any]], candidate: Dict[str, Any], *, max_age_seconds: int = MAX_DUPLICATE_AGE_SECONDS) -> bool:
    if not existing_logs:
        return False
    last = existing_logs[-1]
    if not isinstance(last, dict):
        return False
    same_thread = (last.get("thread_id") or None) == (candidate.get("thread_id") or None)
    same_user_msg = (last.get("user_message") or "") == (candidate.get("user_message") or "")
    same_assistant = (last.get("assistant_response") or "") == (candidate.get("assistant_response") or "")
    if not (same_thread and same_user_msg and same_assistant):
        return False
    last_ts = last.get("timestamp")
    cand_ts = candidate.get("timestamp")
    if not (last_ts and cand_ts):
        return True
    try:
        last_dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
        cand_dt = datetime.fromisoformat(str(cand_ts).replace("Z", "+00:00"))
        return abs((cand_dt - last_dt).total_seconds()) <= max_age_seconds
    except Exception:
        return True


def save_interaction_entry(
    user_id: str,
    user_message: str,
    assistant_response: str,
    thread_id: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    interaction_id = f"INT_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
    timestamp = _current_timestamp()
    entry = {
        "interaction_id": interaction_id,
        "timestamp": timestamp,
        "user_id": user_id,
        "thread_id": thread_id,
        "user_message": user_message,
        "assistant_response": assistant_response,
        "tool_calls": tool_calls or [],
        "metadata": metadata or {},
    }

    index_lines, existing_entries = _read_index_lines(user_id)
    last_index_entry = existing_entries[-1] if existing_entries else None
    if _is_duplicate_interaction(existing_entries, entry):
        return {
            "duplicate": True,
            "interaction_entry": entry,
            "total_interactions": len(existing_entries),
            "interaction_blob": last_index_entry.get("storage_path") if last_index_entry else None,
        }

    interaction_blob_name = _interaction_blob_name(interaction_id)
    blob_client = AzureBlobClient.get_blob_client(interaction_blob_name, user_id)
    blob_client.upload_blob(json.dumps(entry, ensure_ascii=False, indent=2).encode("utf-8"), overwrite=True)

    sanitized_index_entry = {
        "interaction_id": interaction_id,
        "timestamp": timestamp,
        "thread_id": thread_id,
        "storage_path": AzureBlobClient.get_blob_client(interaction_blob_name, user_id).blob_name,
        "user_message": user_message,
        "assistant_response": assistant_response,
        "tool_calls": tool_calls or [],
        "metadata": metadata or {},
    }
    index_lines.append(json.dumps(sanitized_index_entry, ensure_ascii=False))
    _write_index_lines(user_id, index_lines)

    return {
        "duplicate": False,
        "interaction_entry": entry,
        "total_interactions": len(existing_entries) + 1,
        "interaction_blob": AzureBlobClient.get_blob_client(interaction_blob_name, user_id).blob_name,
    }


def rebuild_interactions_index(user_id: str, *, max_scan: int = 5000) -> Dict[str, Any]:
    """
    Rebuild `interactions/index.jsonl` by scanning existing `interactions/INT_*.json` blobs.

    This is intended for import/merge recovery where index.jsonl may be incomplete.
    Deterministic and idempotent: overwrites index.jsonl from current blobs.
    """
    uid = str(user_id or "").strip()
    if not uid:
        raise ValueError("user_id is required")
    try:
        names = AzureBlobClient.list_user_blobs(uid, prefix=f"{INTERACTIONS_DIR}/")
    except Exception as exc:
        return {"status": "error", "error": f"list_failed:{type(exc).__name__}"}

    candidates = [n for n in names if isinstance(n, str) and n.startswith(f"{INTERACTIONS_DIR}/INT_") and n.endswith(".json")]
    candidates = sorted(candidates)[: int(max_scan or 5000)]

    rebuilt: List[Dict[str, Any]] = []
    skipped = 0
    for rel_name in candidates:
        try:
            bc = AzureBlobClient.get_blob_client(rel_name, uid)
            raw = bc.download_blob().readall().decode("utf-8")
            entry = json.loads(raw)
            if not isinstance(entry, dict):
                skipped += 1
                continue
            ts = entry.get("timestamp") or ""
            iid = entry.get("interaction_id") or ""
            rebuilt.append(
                {
                    "interaction_id": iid,
                    "timestamp": ts,
                    "thread_id": entry.get("thread_id"),
                    "storage_path": bc.blob_name,
                    "user_message": entry.get("user_message") or "",
                    "assistant_response": entry.get("assistant_response") or "",
                    "tool_calls": entry.get("tool_calls") or [],
                    "metadata": entry.get("metadata") or {},
                }
            )
        except Exception:
            skipped += 1
            continue

    rebuilt.sort(key=lambda e: str(e.get("timestamp") or ""))
    lines = [json.dumps(e, ensure_ascii=False) for e in rebuilt]
    _write_index_lines(uid, lines)
    return {
        "status": "ok",
        "user_id": uid,
        "scanned": len(candidates),
        "rebuilt": len(rebuilt),
        "skipped": skipped,
    }
