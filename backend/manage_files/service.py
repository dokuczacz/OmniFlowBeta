import logging
from typing import Any, Dict, List, Tuple

from azure.core.exceptions import AzureError, ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig

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
        logging.info("manage_files: container missing, creating")
        try:
            service_client.create_container(container_client.container_name)
        except ResourceExistsError:
            pass


def _user_namespace_prefix(user_id: str) -> str:
    return f"{NAMESPACE_PREFIX}/{user_id}"


def _list_operation(
    user_id: str, prefix: str | None, container_client
) -> Dict[str, Any]:
    namespace = _user_namespace_prefix(user_id)
    sanitized_prefix = _normalize_blob_name(prefix)
    full_prefix = f"{namespace}/{sanitized_prefix}" if sanitized_prefix else f"{namespace}/"
    blobs = container_client.list_blobs(name_starts_with=full_prefix)
    files: List[str] = []
    for blob in blobs:
        if isinstance(blob.name, str) and blob.name.startswith(f"{namespace}/"):
            files.append(blob.name[len(namespace) + 1 :])
    response = {
        "status": "success",
        "user_id": user_id,
        "operation": "list",
        "prefix": prefix or "",
        "files": files,
        "count": len(files),
        "message": f"Successfully retrieved list of {len(files)} files.",
    }
    return response


def _delete_operation(user_id: str, source_name: str, container_client) -> Dict[str, Any]:
    namespace = _user_namespace_prefix(user_id)
    sanitized = _normalize_blob_name(source_name)
    if not sanitized:
        raise ValueError("Missing or invalid 'source_name'.")
    full_name = f"{namespace}/{sanitized}"
    blob_client = container_client.get_blob_client(full_name)
    blob_client.delete_blob()
    return {
        "status": "success",
        "user_id": user_id,
        "operation": "delete",
        "source_name": source_name,
        "message": f"Successfully deleted file: {source_name}.",
    }


def _rename_operation(
    user_id: str, source_name: str, target_name: str, container_client
) -> Dict[str, Any]:
    namespace = _user_namespace_prefix(user_id)
    sanitized_source = _normalize_blob_name(source_name)
    sanitized_target = _normalize_blob_name(target_name)
    if not sanitized_source or not sanitized_target:
        raise ValueError("Missing or invalid source/target name.")
    full_source = f"{namespace}/{sanitized_source}"
    full_target = f"{namespace}/{sanitized_target}"
    source_client = container_client.get_blob_client(full_source)
    target_client = container_client.get_blob_client(full_target)
    target_client.start_copy_from_url(source_client.url)
    source_client.delete_blob()
    return {
        "status": "success",
        "user_id": user_id,
        "operation": "rename",
        "source_name": source_name,
        "target_name": target_name,
        "message": f"Successfully renamed file from '{source_name}' to '{target_name}'.",
    }


def manage_files_core(
    user_id: str,
    operation: str | None,
    prefix: str | None = None,
    source_name: str | None = None,
    target_name: str | None = None,
    raise_on_error: bool = True,
) -> Tuple[Dict[str, Any], int]:
    if not operation:
        return (
            {
                "status": "error",
                "message": "Missing required field 'operation'.",
                "user_id": user_id,
            },
            400,
        )

    user_id = _normalize_user_id(user_id)
    op = str(operation).strip().lower()
    try:
        service_client, container_client = _get_clients()
        _ensure_container(service_client, container_client)

        if op == "list":
            response = _list_operation(user_id, prefix, container_client)
            return response, 200
        if op == "delete":
            if not source_name:
                return (
                    {
                        "status": "error",
                        "message": "Missing 'source_name' for delete operation.",
                        "user_id": user_id,
                    },
                    400,
                )
            response = _delete_operation(user_id, source_name, container_client)
            return response, 200
        if op == "rename":
            if not source_name or not target_name:
                return (
                    {
                        "status": "error",
                        "message": "Missing 'source_name' or 'target_name' for rename operation.",
                        "user_id": user_id,
                    },
                    400,
                )
            response = _rename_operation(user_id, source_name, target_name, container_client)
            return response, 200
        return (
            {
                "status": "error",
                "message": f"Unsupported operation: {operation}.",
                "user_id": user_id,
            },
            400,
        )
    except ResourceNotFoundError:
        return (
            {
                "status": "error",
                "message": f"File '{source_name or target_name or ''}' not found.",
                "user_id": user_id,
            },
            404,
        )
    except ValueError as exc:
        return (
            {
                "status": "error",
                "message": str(exc),
                "user_id": user_id,
            },
            400,
        )
    except (AzureError, RuntimeError) as exc:
        logging.error("manage_files: storage failure %s", exc)
        if raise_on_error:
            raise
        payload = {
            "status": "error",
            "message": f"Error during Blob Storage operation: {str(exc)}",
            "user_id": user_id,
        }
        return payload, 500
    except Exception as exc:
        logging.exception("manage_files: unexpected error")
        if raise_on_error:
            raise
        payload = {
            "status": "error",
            "message": f"Internal error: {str(exc)}",
            "user_id": user_id,
        }
        return payload, 500
