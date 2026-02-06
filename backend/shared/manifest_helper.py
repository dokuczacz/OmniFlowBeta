import json
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from azure.core.exceptions import ResourceNotFoundError


def _current_iso_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _normalize_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    candidate = str(value).strip()
    return [candidate.lower()] if candidate else []


def manifest_blob_path(user_id: str) -> str:
    return f"manifests/{user_id}/manifest.json"


def _extract_manifest_entries(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        entries = payload.get("entries")
        if isinstance(entries, list):
            return entries
        if payload.get("blob_name"):
            return [payload]
        return []
    if isinstance(payload, list):
        return payload
    return []


def load_manifest(container_client, user_id: str) -> Dict[str, Any]:
    blob_client = container_client.get_blob_client(manifest_blob_path(user_id))
    try:
        raw_manifest = blob_client.download_blob().readall().decode("utf-8")
    except ResourceNotFoundError:
        return {
            "manifest_version": 1,
            "updated_at": _current_iso_timestamp(),
            "entries": [],
        }
    try:
        manifest = json.loads(raw_manifest)
    except json.JSONDecodeError as exc:
        logging.warning("load_manifest: parse error %s", exc)
        return {
            "manifest_version": 1,
            "updated_at": _current_iso_timestamp(),
            "entries": [],
        }
    return {
        "manifest_version": manifest.get("manifest_version", 1),
        "updated_at": manifest.get("updated_at", _current_iso_timestamp()),
        "entries": _extract_manifest_entries(manifest),
    }


def write_manifest(container_client, user_id: str, manifest: Dict[str, Any]) -> None:
    blob_client = container_client.get_blob_client(manifest_blob_path(user_id))
    payload = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    blob_client.upload_blob(payload, overwrite=True)


def build_manifest_entry(
    namespaced: str,
    target_blob_name: str,
    payload: Dict[str, Any],
    content_type: str,
    size: int,
) -> Dict[str, Any]:
    now = _current_iso_timestamp()
    display_name = str(payload.get("display_name") or target_blob_name).strip()
    summary = str(payload.get("summary") or "").strip()
    tags = _normalize_string_list(payload.get("tags"))
    manifest_tags = _normalize_string_list(payload.get("manifest_tags"))
    category = str(payload.get("category") or "dataset").strip()
    source = str(payload.get("source") or "custom_gpt_api").strip()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    entry: Dict[str, Any] = {
        "blob_name": namespaced,
        "display_name": display_name,
        "summary": summary,
        "tags": tags,
        "category": category,
        "source": source,
        "size": size,
        "content_type": content_type,
        "updated_at": now,
        "created_at": now,
        "manifest_tags": manifest_tags,
        "metadata": metadata,
    }
    version = payload.get("version")
    if version:
        entry["version"] = str(version)
    return entry


def upsert_manifest_entry(container_client, user_id: str, entry: Dict[str, Any]) -> None:
    manifest = load_manifest(container_client, user_id)
    entries = manifest.get("entries", [])
    for index, existing in enumerate(entries):
        if existing.get("blob_name") == entry["blob_name"]:
            created_at = existing.get("created_at") or entry["created_at"]
            merged = {**existing, **entry}
            merged["created_at"] = created_at
            entries[index] = merged
            break
    else:
        entries.append(entry)
    manifest["entries"] = entries
    manifest["updated_at"] = entry["updated_at"]
    manifest["manifest_version"] = manifest.get("manifest_version", 1)
    write_manifest(container_client, user_id, manifest)


def remove_manifest_entry(container_client, user_id: str, blob_name: str) -> bool:
    manifest = load_manifest(container_client, user_id)
    entries = manifest.get("entries", [])
    filtered = [entry for entry in entries if entry.get("blob_name") != blob_name]
    if len(filtered) == len(entries):
        return False
    manifest["entries"] = filtered
    manifest["updated_at"] = _current_iso_timestamp()
    write_manifest(container_client, user_id, manifest)
    return True


def rename_manifest_entry(
    container_client,
    user_id: str,
    old_blob_name: str,
    new_blob_name: str,
    display_name: Optional[str] = None,
) -> bool:
    manifest = load_manifest(container_client, user_id)
    updated = False
    for entry in manifest.get("entries", []):
        if entry.get("blob_name") == old_blob_name:
            entry["blob_name"] = new_blob_name
            if display_name:
                entry["display_name"] = display_name
            entry["updated_at"] = _current_iso_timestamp()
            updated = True
            break
    if not updated:
        return False
    manifest["updated_at"] = _current_iso_timestamp()
    write_manifest(container_client, user_id, manifest)
    return True


def get_manifest_entry(container_client, user_id: str, blob_name: str) -> Optional[Dict[str, Any]]:
    manifest = load_manifest(container_client, user_id)
    for entry in manifest.get("entries", []):
        if entry.get("blob_name") == blob_name:
            return entry
    return None
