import json
import logging
import time
from typing import Dict, List, Tuple, Any

from azure.core.exceptions import AzureError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig


DEFAULT_TAIL_LINES = 0
DEFAULT_TAIL_BYTES = 65536
DEFAULT_MAX_BYTES_PER_FILE = 262144
DEFAULT_MAX_FILES = 25


def _get_container_client() -> Tuple[BlobServiceClient, object]:
    connection_string = AzureConfig.CONNECTION_STRING
    container_name = AzureConfig.CONTAINER_NAME
    if not connection_string or not container_name:
        raise RuntimeError("Missing Azure Storage configuration.")
    service_client = BlobServiceClient.from_connection_string(connection_string)
    container_client = service_client.get_container_client(container_name)
    return service_client, container_client


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _read_tail_lines(blob_client, *, tail_lines: int, tail_bytes: int) -> Tuple[str, bool, int]:
    props = blob_client.get_blob_properties()
    size = int(getattr(props, "size", 0) or 0)
    if size <= 0:
        return "", False, 0
    length = min(size, max(1, tail_bytes))
    offset = max(0, size - length)
    raw = blob_client.download_blob(offset=offset, length=length).readall()
    text = raw.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if tail_lines > 0:
        lines = lines[-tail_lines:]
    return "\n".join(lines), offset > 0, len(raw)


def _read_prefix(blob_client, *, max_bytes: int) -> Tuple[bytes, bool]:
    props = blob_client.get_blob_properties()
    size = int(getattr(props, "size", 0) or 0)
    if size <= 0:
        return b"", False
    if max_bytes <= 0 or size <= max_bytes:
        return blob_client.download_blob().readall(), False
    data = blob_client.download_blob(offset=0, length=max_bytes).readall()
    return data, True


def _validate_files(files: Any, max_files: int) -> Tuple[List[str], Dict[str, Any]]:
    if not isinstance(files, list):
        return [], {"status": "error", "error": "Field 'files' must be a non-empty array of strings"}
    trimmed = []
    for raw in files:
        if not isinstance(raw, str):
            continue
        value = raw.strip()
        if value:
            trimmed.append(value)
    if not trimmed:
        return [], {"status": "error", "error": "Field 'files' must be a non-empty array of strings"}
    if len(trimmed) > max_files:
        return [], {"status": "error", "error": f"Too many files (max {max_files})"}
    return trimmed, {}


def read_many_blobs_core(
    user_id: str,
    files: List[str],
    tail_lines: int = DEFAULT_TAIL_LINES,
    tail_bytes: int = DEFAULT_TAIL_BYTES,
    max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE,
    parse_json: bool = True,
    max_files: int = DEFAULT_MAX_FILES,
    raise_on_error: bool = True,
) -> Tuple[Dict[str, Any], int]:
    tail_lines = _safe_int(tail_lines, DEFAULT_TAIL_LINES)
    tail_bytes = _safe_int(tail_bytes, DEFAULT_TAIL_BYTES)
    max_bytes_per_file = _safe_int(max_bytes_per_file, DEFAULT_MAX_BYTES_PER_FILE)
    max_files = max(DEFAULT_MAX_FILES, _safe_int(max_files, DEFAULT_MAX_FILES))
    parse_json = _coerce_bool(parse_json, True)

    files, validation_error = _validate_files(files, max_files)
    if validation_error:
        status_code = 400
        if raise_on_error:
            raise ValueError(validation_error["error"])
        return {**validation_error, "user_id": user_id}, status_code

    start = time.perf_counter()
    try:
        service_client, container_client = _get_container_client()
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning("read_many_blobs: container missing, creating")
            try:
                service_client.create_container(container_client.container_name)
            except AzureError:
                pass
            _, container_client = _get_container_client()

        items = []
        errors = 0
        total_bytes = 0
        namespace_prefix = f"users/{user_id}/"
        for file_name in files:
            namespaced = f"{namespace_prefix}{file_name}"
            blob_client = container_client.get_blob_client(namespaced)
            try:
                if tail_lines > 0:
                    text, truncated, bytes_read = _read_tail_lines(
                        blob_client, tail_lines=tail_lines, tail_bytes=tail_bytes
                    )
                    total_bytes += bytes_read
                    items.append(
                        {
                            "file_name": file_name,
                            "content_type": "text",
                            "data": text,
                            "bytes": bytes_read,
                            "truncated": bool(truncated),
                            "mode": "tail",
                        }
                    )
                    continue

                data, truncated = _read_prefix(blob_client, max_bytes=max_bytes_per_file)
                total_bytes += len(data)
                if parse_json:
                    try:
                        parsed = json.loads(data.decode("utf-8"))
                        items.append(
                            {
                                "file_name": file_name,
                                "content_type": "json",
                                "data": parsed,
                                "bytes": len(data),
                                "truncated": bool(truncated),
                                "mode": "read",
                            }
                        )
                        continue
                    except Exception:
                        pass

                items.append(
                    {
                        "file_name": file_name,
                        "content_type": "text",
                        "data": data.decode("utf-8", errors="replace"),
                        "bytes": len(data),
                        "truncated": bool(truncated),
                        "mode": "read",
                    }
                )
            except ResourceNotFoundError:
                errors += 1
                items.append({"file_name": file_name, "error": "not_found"})
            except AzureError as exc:
                errors += 1
                items.append({"file_name": file_name, "error": f"azure_error: {str(exc)}"})
            except Exception as exc:
                errors += 1
                items.append({"file_name": file_name, "error": f"unexpected_error: {str(exc)}"})

        duration_ms = int((time.perf_counter() - start) * 1000)
        logging.info(
            "read_many_blobs: user_id=%s count=%s errors=%s total_bytes=%s dur_ms=%s",
            user_id,
            len(files),
            errors,
            total_bytes,
            duration_ms,
        )

        payload = {
            "status": "success",
            "user_id": user_id,
            "count": len(items),
            "errors": errors,
            "items": items,
        }
        return payload, 200
    except (AzureError, ResourceNotFoundError) as exc:
        payload = {"status": "error", "user_id": user_id, "error": str(exc)}
        if raise_on_error:
            raise
        return payload, 500
    except Exception as exc:
        payload = {"status": "error", "user_id": user_id, "error": str(exc)}
        if raise_on_error:
            raise
        return payload, 500
