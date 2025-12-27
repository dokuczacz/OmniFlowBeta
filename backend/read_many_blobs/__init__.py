import json
import logging
import time

import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig


def _parse_bool(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _read_tail_lines(blob_client, *, tail_lines: int, tail_bytes: int) -> tuple[str, bool, int]:
    """
    Return (text, truncated, bytes_read).
    Best-effort tail for text/JSONL; reads up to `tail_bytes` from the end.
    """
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
    return "\n".join(lines), (offset > 0), len(raw)


def _read_prefix(blob_client, *, max_bytes: int) -> tuple[bytes, bool]:
    props = blob_client.get_blob_properties()
    size = int(getattr(props, "size", 0) or 0)
    if size <= 0:
        return b"", False
    if max_bytes <= 0 or size <= max_bytes:
        return blob_client.download_blob().readall(), False
    data = blob_client.download_blob(offset=0, length=max_bytes).readall()
    return data, True


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Bulk read many blobs from the user's namespace with safety limits.

    POST body:
    {
      "files": ["TM.json", "LO.json", "interactions/semantic/index.jsonl"],
      "tail_lines": 0,
      "tail_bytes": 65536,
      "max_bytes_per_file": 262144,
      "parse_json": true,
      "user_id": "default"
    }
    """
    start_t = time.perf_counter()
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json",
        )

    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or body.get("user_id")
        or "default"
    )
    user_id = str(user_id).strip() or "default"

    files = body.get("files") or body.get("file_names") or []
    if not isinstance(files, list) or not all(isinstance(f, str) and f.strip() for f in files):
        return func.HttpResponse(
            json.dumps({"error": "Field 'files' must be a non-empty array of strings", "user_id": user_id}),
            status_code=400,
            mimetype="application/json",
        )

    max_files = _safe_int(body.get("max_files"), 25)
    if len(files) > max_files:
        return func.HttpResponse(
            json.dumps({"error": f"Too many files (max {max_files})", "user_id": user_id}),
            status_code=400,
            mimetype="application/json",
        )

    tail_lines = _safe_int(body.get("tail_lines"), 0)
    tail_bytes = _safe_int(body.get("tail_bytes"), 65536)
    max_bytes_per_file = _safe_int(body.get("max_bytes_per_file"), 262144)
    parse_json = _parse_bool(body.get("parse_json", True))

    logging.info(
        "read_many_blobs: user_id=%s count=%s tail_lines=%s max_bytes_per_file=%s",
        user_id,
        len(files),
        tail_lines,
        max_bytes_per_file,
    )

    try:
        connect_str = AzureConfig.CONNECTION_STRING
        container_name = AzureConfig.CONTAINER_NAME
        if not connect_str or not container_name:
            return func.HttpResponse(
                json.dumps({"error": "Missing Azure Storage configuration", "user_id": user_id}),
                status_code=500,
                mimetype="application/json",
            )

        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning(f"read_many_blobs: container not found ({container_name}); creating")
            try:
                blob_service_client.create_container(container_name)
            except AzureError:
                pass
            container_client = blob_service_client.get_container_client(container_name)

        items = []
        errors = 0
        total_bytes = 0
        for file_name in files:
            file_name = str(file_name).strip()
            namespaced = f"users/{user_id}/{file_name}"
            blob_client = container_client.get_blob_client(namespaced)
            try:
                if tail_lines > 0:
                    text, truncated, bytes_read = _read_tail_lines(
                        blob_client, tail_lines=tail_lines, tail_bytes=tail_bytes
                    )
                    total_bytes += bytes_read
                    entry = {
                        "file_name": file_name,
                        "content_type": "text",
                        "data": text,
                        "bytes": bytes_read,
                        "truncated": bool(truncated),
                        "mode": "tail",
                    }
                    items.append(entry)
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
            except AzureError as e:
                errors += 1
                items.append({"file_name": file_name, "error": f"azure_error: {str(e)}"})
            except Exception as e:
                errors += 1
                items.append({"file_name": file_name, "error": f"unexpected_error: {str(e)}"})

        dur_ms = int((time.perf_counter() - start_t) * 1000)
        logging.info(
            "read_many_blobs: OK user_id=%s count=%s errors=%s total_bytes=%s dur_ms=%s",
            user_id,
            len(files),
            errors,
            total_bytes,
            dur_ms,
        )

        return func.HttpResponse(
            json.dumps(
                {
                    "status": "success",
                    "user_id": user_id,
                    "count": len(items),
                    "errors": errors,
                    "items": items,
                },
                ensure_ascii=False,
            ),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        logging.error(f"Unexpected error in read_many_blobs: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Server error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json",
        )

