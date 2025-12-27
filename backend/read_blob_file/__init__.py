import logging
import json
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError
import os
import time
from azure.storage.blob import BlobServiceClient
from shared.config import AzureConfig


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
