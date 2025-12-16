import logging
import json
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError
import os
from azure.storage.blob import BlobServiceClient


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
    
    logging.info(f"read_blob_file: user_id={user_id}, file_name={file_name}")
    
    try:
        connect_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        container_name = os.environ.get("AZURE_BLOB_CONTAINER_NAME")
        
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
        except Exception:
            response = {
                "status": "success",
                "user_id": user_id,
                "file_name": file_name,
                "data": blob_text,
                "content_type": "text"
            }
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
