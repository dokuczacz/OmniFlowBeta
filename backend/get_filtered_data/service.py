import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig
from shared.artifact_envelope import extract_items


def _get_container_client():
    connection_string = AzureConfig.CONNECTION_STRING
    container_name = AzureConfig.CONTAINER_NAME
    if not connection_string or not container_name:
        raise RuntimeError("Missing Azure Storage configuration.")
    service_client = BlobServiceClient.from_connection_string(connection_string)
    return service_client, service_client.get_container_client(container_name)


def _normalize_entries(raw_data: Any) -> List[Any]:
    envelope, items = extract_items(raw_data, items_key="items")
    data = items if isinstance(items, list) else [items]
    if isinstance(data, list):
        normalized = []
        for entry in data:
            if isinstance(entry, str):
                try:
                    normalized.append(json.loads(entry))
                except Exception:
                    normalized.append({"_raw": entry})
            else:
                normalized.append(entry)
        return normalized
    return [raw_data] if raw_data is not None else []


def get_filtered_data_core(
    user_id: str,
    target_blob_name: str,
    filter_key: Optional[str] = None,
    filter_value: Optional[str] = None,
    raise_on_error: bool = True,
) -> Tuple[Dict[str, Any], int]:
    start = time.perf_counter()
    namespaced = f"users/{user_id}/{target_blob_name}"
    try:
        service_client, container_client = _get_container_client()
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning("get_filtered_data: container missing, creating")
            try:
                service_client.create_container(container_client.container_name)
            except AzureError:
                pass
            _, container_client = _get_container_client()

        blob_client = container_client.get_blob_client(namespaced)
        raw = blob_client.download_blob().readall().decode("utf-8")
        parsed = json.loads(raw)
        data = _normalize_entries(parsed)

        filtered = data
        if filter_key and filter_value is not None and isinstance(data, list):
            filtered = [
                entry
                for entry in data
                if isinstance(entry, dict) and str(entry.get(filter_key)) == str(filter_value)
            ]

        payload = {
            "status": "success",
            "user_id": user_id,
            "file": target_blob_name,
            "filter": {"key": filter_key, "value": filter_value} if filter_key and filter_value is not None else None,
            "data": filtered,
            "count": len(filtered),
            "total": len(data),
        }
        dur_ms = int((time.perf_counter() - start) * 1000)
        logging.info(
            "get_filtered_data: user_id=%s file=%s filter=%s total=%d dur=%dms",
            user_id,
            target_blob_name,
            f"{filter_key}={filter_value}" if filter_key else "none",
            len(data),
            dur_ms,
        )
        return payload, 200
    except ResourceNotFoundError:
        message = f"File '{target_blob_name}' not found"
        logging.warning("get_filtered_data: %s", message)
        payload = {"status": "error", "user_id": user_id, "error": message}
        return payload, 404
    except json.JSONDecodeError as exc:
        message = f"Invalid JSON format: {exc}"
        logging.error("get_filtered_data: %s", message)
        payload = {"status": "error", "user_id": user_id, "error": message}
        return payload, 500
    except AzureError as exc:
        payload = {"status": "error", "user_id": user_id, "error": f"Azure storage error: {exc}"}
        return payload, 500
    except Exception as exc:
        payload = {"status": "error", "user_id": user_id, "error": f"Server error: {exc}"}
        if raise_on_error:
            raise
        return payload, 500
