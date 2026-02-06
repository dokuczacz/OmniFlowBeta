import logging
import time
from typing import Dict, Any

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError, AzureError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig


def _get_client():
    connection_string = AzureConfig.CONNECTION_STRING
    container_name = AzureConfig.CONTAINER_NAME
    if not connection_string or not container_name:
        raise RuntimeError("Missing Azure Storage configuration.")
    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container_name)
    return service_client, container_client


def list_blobs_core(
    user_id: str,
    prefix: str = "",
    include_meta: bool = False,
    raise_on_error: bool = True,
) -> Dict[str, Any]:
    prefix = str(prefix or "").strip()
    include_meta = bool(include_meta)
    start = time.perf_counter()

    def handle_error(exc: Exception) -> Dict[str, Any]:
        logging.error("list_blobs:error user_id=%s prefix=%s exc=%s", user_id, prefix, exc)
        if raise_on_error:
            raise
        return {
            "status": "error",
            "user_id": user_id,
            "error": str(exc),
        }

    try:
        service_client, container_client = _get_client()
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning("list_blobs: container missing, creating")
            try:
                service_client.create_container(container_client.container_name)
            except ResourceExistsError:
                pass
            _, container_client = _get_client()

        namespace_prefix = f"users/{user_id}/"
        full_prefix = namespace_prefix + prefix if prefix else namespace_prefix
        blobs = list(container_client.list_blobs(name_starts_with=full_prefix))
        blob_names = []
        blob_meta = []
        for blob in blobs:
            relative = blob.name[len(namespace_prefix) :]
            blob_names.append(relative)
            if include_meta:
                blob_meta.append(
                    {
                        "name": relative,
                        "size": int(getattr(blob, "size", 0) or 0),
                        "last_modified": getattr(blob, "last_modified", None).isoformat()
                        if getattr(blob, "last_modified", None)
                        else None,
                    }
                )

        response = {
            "status": "success",
            "user_id": user_id,
            "blobs": blob_names,
            "count": len(blob_names),
            "blobs_meta": blob_meta if include_meta else None,
        }
        duration_ms = int((time.perf_counter() - start) * 1000)
        logging.info(
            "list_blobs: user_id=%s prefix=%s count=%d dur_ms=%d include_meta=%s",
            user_id,
            prefix,
            len(blob_names),
            duration_ms,
            include_meta,
        )
        return response
    except (ResourceNotFoundError, AzureError, RuntimeError) as exc:
        return handle_error(exc)
    except Exception as exc:
        return handle_error(exc)
