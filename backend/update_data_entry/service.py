import json
import logging
from typing import Any, Dict, List, Tuple

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig
from shared.manifest_helper import build_manifest_entry, upsert_manifest_entry
from shared.artifact_envelope import extract_items, merge_items_back

DEFAULT_USER_ID = "default"
NAMESPACE_PREFIX = "users"


def _normalize_user_id(user_id: str | None) -> str:
    candidate = str(user_id or "").strip()
    return candidate or DEFAULT_USER_ID


def _normalize_blob_name(blob_name: str | None) -> str:
    return str(blob_name or "").strip().lstrip("/")


def _get_clients() -> Tuple[BlobServiceClient, Any]:
    connection_string = AzureConfig.CONNECTION_STRING
    container_name = AzureConfig.CONTAINER_NAME
    if not connection_string or not container_name:
        raise RuntimeError("Missing Azure Storage configuration.")
    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container_name)
    return service_client, container_client


def _ensure_container(service_client: BlobServiceClient, container_client) -> None:
    try:
        container_client.get_container_properties()
    except ResourceNotFoundError:
        logging.info("update_data_entry: container missing, creating")
        try:
            service_client.create_container(container_client.container_name)
        except ResourceExistsError:
            pass


def _namespaced_path(user_id: str, blob_name: str) -> str:
    return f"{NAMESPACE_PREFIX}/{user_id}/{blob_name}"


def _load_entries(blob_client) -> List[Any]:
    payload = blob_client.download_blob().readall().decode("utf-8")
    raw_payload = json.loads(payload)
    envelope, raw_list = extract_items(raw_payload, items_key="items")
    candidates = raw_list if isinstance(raw_list, list) else [raw_list]
    normalized: List[Any] = []
    for entry in candidates:
        if isinstance(entry, str):
            try:
                entry = json.loads(entry)
            except Exception:
                entry = {"_raw": entry}
        normalized.append(entry)
    return normalized


def _find_entry(
    entries: List[Any], find_key: str, find_value: Any
) -> Dict[str, Any] | None:
    target_value = str(find_value or "").lower()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get(find_key) or "").lower() == target_value:
            return entry
    return None


def update_data_entry_core(
    user_id: str,
    target_blob_name: str,
    find_key: str,
    find_value: Any,
    update_key: str,
    update_value: Any,
    raise_on_error: bool = True,
) -> Tuple[Dict[str, Any], int]:
    if not all([target_blob_name, find_key, find_value, update_key, update_value]):
        payload = {
            "status": "error",
            "message": "Missing required fields",
            "user_id": user_id,
        }
        return payload, 400

    user_id = _normalize_user_id(user_id)
    target_name = _normalize_blob_name(target_blob_name)
    namespaced = _namespaced_path(user_id, target_name)
    try:
        service_client, container_client = _get_clients()
        _ensure_container(service_client, container_client)
        blob_client = container_client.get_blob_client(namespaced)
        # Load full payload so we can preserve envelope fields if present.
        raw_text = blob_client.download_blob().readall().decode("utf-8")
        raw_payload = json.loads(raw_text)
        envelope, entries = extract_items(raw_payload, items_key="items")
        # Normalize entries to list[dict|...]
        entries = entries if isinstance(entries, list) else [entries]
        entry = _find_entry(entries, find_key, find_value)
        if not entry:
            payload = {
                "status": "error",
                "message": f"Record not found: {find_key}={find_value}",
                "user_id": user_id,
            }
            return payload, 404
        entry[update_key] = update_value
        out_payload = merge_items_back(envelope, entries, items_key="items")
        serialized = json.dumps(out_payload, indent=2, ensure_ascii=False).encode("utf-8")
        blob_client.upload_blob(serialized, overwrite=True)
        message = (
            f"Successfully updated {find_key}={find_value} in '{target_blob_name}'"
        )
        payload = {
            "status": "success",
            "message": message,
            "updated_key": update_key,
            "updated_value": update_value,
            "user_id": user_id,
        }
        try:
            entry = build_manifest_entry(
                namespaced=namespaced,
                target_blob_name=target_blob_name,
                payload={
                    "target_blob_name": target_blob_name,
                    "updated_key": update_key,
                    "updated_value": update_value,
                },
                content_type="application/json",
                size=len(serialized),
            )
            upsert_manifest_entry(container_client, user_id, entry)
            payload["manifest_status"] = "updated"
        except Exception as exc:
            logging.warning("update_data_entry: manifest update failed: %s", exc)
            payload["manifest_status"] = "failed"
            payload["manifest_error"] = str(exc)
        return payload, 200
    except ResourceNotFoundError:
        payload = {
            "status": "error",
            "message": f"File '{target_blob_name}' not found",
            "user_id": user_id,
        }
        return payload, 404
    except (AzureError, RuntimeError) as exc:
        logging.error("update_data_entry: storage failure %s", exc)
        if raise_on_error:
            raise
        payload = {
            "status": "error",
            "message": f"Server error: {str(exc)}",
            "user_id": user_id,
        }
        return payload, 500
    except Exception as exc:
        logging.exception("update_data_entry: unexpected error")
        if raise_on_error:
            raise
        payload = {
            "status": "error",
            "message": f"Server error: {str(exc)}",
            "user_id": user_id,
        }
        return payload, 500
