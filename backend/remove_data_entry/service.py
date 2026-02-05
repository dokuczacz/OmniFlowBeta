import json
import logging
from typing import Any, Dict, List, Tuple

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig
from shared.manifest_helper import remove_manifest_entry

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
        logging.info("remove_data_entry: container missing, creating")
        try:
            service_client.create_container(container_client.container_name)
        except ResourceExistsError:
            pass


def _namespaced_path(user_id: str, blob_name: str) -> str:
    return f"{NAMESPACE_PREFIX}/{user_id}/{blob_name}"


def _load_entries(blob_client) -> List[Any]:
    payload = blob_client.download_blob().readall().decode("utf-8")
    raw_list = json.loads(payload)
    if isinstance(raw_list, list):
        candidates = raw_list
    else:
        candidates = [raw_list]
    normalized: List[Any] = []
    for entry in candidates:
        if isinstance(entry, str):
            try:
                entry = json.loads(entry)
            except Exception:
                entry = {"_raw": entry}
        normalized.append(entry)
    return normalized


def _matches(entry: Any, key: str, value: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    return str(entry.get(key) or "").lower() == str(value or "").lower()


def remove_data_entry_core(
    user_id: str,
    target_blob_name: str,
    key_to_find: str,
    value_to_find: Any,
    raise_on_error: bool = True,
) -> Tuple[Dict[str, Any], int]:
    if not all([target_blob_name, key_to_find, value_to_find]):
        payload = {
            "status": "error",
            "message": "Missing required fields: 'target_blob_name', 'key_to_find', or 'value_to_find'",
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
        entries = _load_entries(blob_client)
        initial_count = len(entries)
        filtered = [entry for entry in entries if not _matches(entry, key_to_find, value_to_find)]
        deleted_count = initial_count - len(filtered)

        if deleted_count == 0:
            payload = {
                "status": "not_found",
                "message": f"No entries found matching {key_to_find}={value_to_find}",
                "user_id": user_id,
            }
            return payload, 404

        serialized = json.dumps(filtered, indent=2, ensure_ascii=False).encode("utf-8")
        blob_client.upload_blob(serialized, overwrite=True)
        payload = {
            "status": "success",
            "message": f"Successfully removed {deleted_count} entries matching {key_to_find}={value_to_find}",
            "deleted_count": deleted_count,
            "user_id": user_id,
        }
        try:
            removed = remove_manifest_entry(container_client, user_id, namespaced)
            payload["manifest_status"] = "removed" if removed else "missing"
        except Exception as exc:
            logging.warning("remove_data_entry: manifest update failed: %s", exc)
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
        logging.error("remove_data_entry: storage failure %s", exc)
        if raise_on_error:
            raise
        payload = {
            "status": "error",
            "message": f"Server error: {str(exc)}",
            "user_id": user_id,
        }
        return payload, 500
    except Exception as exc:
        logging.exception("remove_data_entry: unexpected error")
        if raise_on_error:
            raise
        payload = {
            "status": "error",
            "message": f"Server error: {str(exc)}",
            "user_id": user_id,
        }
        return payload, 500
