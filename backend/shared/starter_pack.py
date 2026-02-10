"""
Starter pack initialization for new users.

Requirements:
- Idempotent: safe to call on every request/tool call.
- Creates minimal PA-core artifacts for new users so prompts/tools have a stable base.
- Uses envelope format (schema_version + timestamps + items) for new files,
  while staying backward compatible with legacy list artifacts already present.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Tuple

from azure.core.exceptions import ResourceNotFoundError

from .azure_client import AzureBlobClient


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _blob_exists(blob_client) -> bool:
    try:
        # exists() is not present in all azure sdk versions; fall back to get_blob_properties.
        if hasattr(blob_client, "exists"):
            return bool(blob_client.exists())
        blob_client.get_blob_properties()
        return True
    except ResourceNotFoundError:
        return False
    except Exception:
        # Best-effort: do not block runtime on transient errors here.
        return False


def _write_json(blob_client, payload: Any) -> None:
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    blob_client.upload_blob(data, overwrite=True)


def _enveloped(schema_version: str, *, items_key: str, items: list, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    now = _utc_now_iso()
    out: Dict[str, Any] = {
        "schema_version": schema_version,
        "created_utc": now,
        "updated_utc": now,
        items_key: items,
    }
    if extra:
        out.update(extra)
    return out


def starter_pack_spec() -> List[Tuple[str, Any]]:
    """
    Returns list of (relative_blob_name, initial_json_payload) within user's namespace.
    """
    return [
        ("TM.json", _enveloped("omniflow.pa.tm.v1", items_key="items", items=[], extra={"kind": "tasks"})),
        ("PS.json", _enveloped("omniflow.pa.ps.v1", items_key="items", items=[], extra={"kind": "goals"})),
        ("LO.json", _enveloped("omniflow.pa.lo.v1", items_key="items", items=[], extra={"kind": "time_plans"})),
        ("GEN.json", _enveloped("omniflow.pa.gen.v1", items_key="items", items=[], extra={"kind": "notes"})),
        ("SYS.json", _enveloped("omniflow.pa.sys.v1", items_key="events", items=[], extra={"kind": "system"})),
        (
            "semantics/preferences.json",
            {
                "schema_version": "omniflow.wp6.preferences.v1",
                "updated_utc": _utc_now_iso(),
                "brevity": "medium",
                "fast_mode": False,
                "allowed_reads": [],
                "disable_history_reads": False,
            },
        ),
    ]


def ensure_starter_pack(user_id: str) -> Dict[str, Any]:
    """
    Ensure starter pack exists for user. Returns a short status dict.

    Notes:
    - Intentionally best-effort; does not raise on failure.
    - We consider SYS.json as the "sentinel" for initialization.
    """
    uid = str(user_id or "").strip() or "default"
    try:
        container = AzureBlobClient.get_container_client()
    except Exception as exc:
        return {"status": "error", "error": f"container_unavailable:{type(exc).__name__}"}

    created: List[str] = []
    existed: List[str] = []

    # Fast sentinel check: if SYS.json exists, assume pack is present.
    try:
        sentinel = AzureBlobClient.get_blob_client("SYS.json", uid)
        if _blob_exists(sentinel):
            return {"status": "ok", "created": [], "existed": ["SYS.json"], "user_id": uid}
    except Exception:
        # Fall through to full ensure.
        pass

    for rel_name, payload in starter_pack_spec():
        try:
            bc = AzureBlobClient.get_blob_client(rel_name, uid)
            if _blob_exists(bc):
                existed.append(rel_name)
                continue
            _write_json(bc, payload)
            created.append(rel_name)
        except Exception:
            # Best-effort: continue so we create as much as possible.
            continue

    return {"status": "ok", "created": created, "existed": existed, "user_id": uid}

