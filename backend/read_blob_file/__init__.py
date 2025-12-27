import logging
import json
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError
import os
import time
from azure.storage.blob import BlobServiceClient
from shared.config import AzureConfig


def _safe_str(value) -> str:
    return str(value or "").strip()


def _is_basename_only(file_name: str) -> bool:
    value = _safe_str(file_name)
    return bool(value) and ("/" not in value) and ("\\" not in value)


def _try_unique_suffix_resolve(container_client, *, user_id: str, file_name: str, max_scan: int = 2000) -> tuple[str | None, list[str]]:
    """
    Best-effort resolver for cases where the caller passes only a basename (e.g. 'index.jsonl')
    even though the real blob is nested (e.g. 'interactions/semantic/index.jsonl').

    Returns (resolved_relative_name|None, candidates_relative_names[]).
    """
    user_namespace_prefix = f"users/{user_id}/"
    suffix = f"/{file_name}"
    candidates: list[str] = []
    scanned = 0
    for blob in container_client.list_blobs(name_starts_with=user_namespace_prefix):
        scanned += 1
        if scanned > max_scan:
            break
        name = getattr(blob, "name", "") or ""
        if not name.endswith(suffix):
            continue
        rel = name[len(user_namespace_prefix) :]
        if rel:
            candidates.append(rel)
            if len(candidates) > 25:
                break
    if len(candidates) == 1:
        return candidates[0], candidates
    return None, candidates


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Read blob file with user isolation.
    
    Parameters:
    - file_name (required): Name of the file to read (e.g., "tasks.json")
    - user_id (optional): User ID from header X-User-Id, query param, or body (default: "default")
    
    Returns:
    - JSON file contents with metadata
    """
    # Extract user_id in priority order: header -> query -> body -> default
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
    )
    if not user_id:
        try:
            body = req.get_json()
            user_id = body.get("user_id")
        except ValueError:
            pass
    user_id = user_id or "default"
    user_id = str(user_id).strip()
    
    file_name = req.params.get("file_name")
    if not file_name:
        return func.HttpResponse(
            json.dumps({"error": "Missing 'file_name' parameter", "user_id": user_id}),
            status_code=400,
            mimetype="application/json"
        )
    
    start_t = time.perf_counter()
    file_name = _safe_str(file_name)
    logging.info(f"read_blob_file: user_id={user_id}, file_name={file_name}")
    
    try:
        connect_str = AzureConfig.CONNECTION_STRING
        container_name = AzureConfig.CONTAINER_NAME
        
        if not connect_str or not container_name:
            return func.HttpResponse(
                json.dumps({"error": "Missing Azure Storage configuration", "user_id": user_id}),
                status_code=500,
                mimetype="application/json"
            )
        
        # Namespace the blob path to user
        namespaced_blob_name = f"users/{user_id}/{file_name}"
        
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning(f"read_blob_file: container not found ({container_name}); creating")
            try:
                blob_service_client.create_container(container_name)
            except AzureError:
                pass
            container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(namespaced_blob_name)

        # Download blob data
        blob_data = blob_client.download_blob().readall()
        blob_text = blob_data.decode('utf-8')
        # Try to parse as JSON, else return as plain text
        try:
            parsed_data = json.loads(blob_text)
            response = {
                "status": "success",
                "user_id": user_id,
                "file_name": file_name,
                "data": parsed_data,
                "content_type": "json"
            }
            dur_ms = int((time.perf_counter() - start_t) * 1000)
            logging.info(f"read_blob_file: OK user_id={user_id} file_name={file_name} content_type=json bytes={len(blob_data)} dur_ms={dur_ms}")
        except Exception:
            response = {
                "status": "success",
                "user_id": user_id,
                "file_name": file_name,
                "data": blob_text,
                "content_type": "text"
            }
            dur_ms = int((time.perf_counter() - start_t) * 1000)
            logging.info(f"read_blob_file: OK user_id={user_id} file_name={file_name} content_type=text bytes={len(blob_data)} dur_ms={dur_ms}")
        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False),
            mimetype="application/json"
        )

    except ResourceNotFoundError:
        # If caller passed only basename (no '/'), try to resolve uniquely within user's namespace.
        if _is_basename_only(file_name):
            try:
                blob_service_client = BlobServiceClient.from_connection_string(AzureConfig.CONNECTION_STRING)
                container_client = blob_service_client.get_container_client(AzureConfig.CONTAINER_NAME)
                resolved, candidates = _try_unique_suffix_resolve(
                    container_client, user_id=user_id, file_name=file_name
                )
                if resolved:
                    logging.warning(
                        f"read_blob_file: resolved basename user_id={user_id} file_name={file_name} -> {resolved}"
                    )
                    namespaced_blob_name = f"users/{user_id}/{resolved}"
                    blob_client = container_client.get_blob_client(namespaced_blob_name)
                    blob_data = blob_client.download_blob().readall()
                    blob_text = blob_data.decode("utf-8", errors="replace")
                    try:
                        parsed_data = json.loads(blob_text)
                        response = {
                            "status": "success",
                            "user_id": user_id,
                            "file_name": resolved,
                            "requested_file_name": file_name,
                            "resolved": True,
                            "data": parsed_data,
                            "content_type": "json",
                        }
                    except Exception:
                        response = {
                            "status": "success",
                            "user_id": user_id,
                            "file_name": resolved,
                            "requested_file_name": file_name,
                            "resolved": True,
                            "data": blob_text,
                            "content_type": "text",
                        }
                    dur_ms = int((time.perf_counter() - start_t) * 1000)
                    logging.info(
                        "read_blob_file: OK user_id=%s file_name=%s resolved_from=%s bytes=%s dur_ms=%s",
                        user_id,
                        resolved,
                        file_name,
                        len(blob_data),
                        dur_ms,
                    )
                    return func.HttpResponse(
                        json.dumps(response, ensure_ascii=False),
                        mimetype="application/json",
                        status_code=200,
                    )
                if candidates:
                    logging.warning(
                        f"read_blob_file: basename ambiguous user_id={user_id} file_name={file_name} matches={len(candidates)}"
                    )
                    return func.HttpResponse(
                        json.dumps(
                            {
                                "error": f"File '{file_name}' not found as a direct path; multiple candidates exist.",
                                "user_id": user_id,
                                "file_name": file_name,
                                "candidates": candidates[:10],
                            },
                            ensure_ascii=False,
                        ),
                        status_code=404,
                        mimetype="application/json",
                    )
            except Exception as e:
                logging.warning(f"read_blob_file: basename resolve failed user_id={user_id} file_name={file_name}: {e}")

        logging.warning(f"File not found: users/{user_id}/{file_name}")
        return func.HttpResponse(
            json.dumps({"error": f"File '{file_name}' not found", "user_id": user_id}),
            status_code=404,
            mimetype="application/json"
        )
    except AzureError as e:
        logging.error(f"Azure error reading users/{user_id}/{file_name}: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Error reading file: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Unexpected error in read_blob_file: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Unexpected error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
