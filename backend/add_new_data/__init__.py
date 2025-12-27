import logging
import json
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError
import os
from azure.storage.blob import BlobServiceClient
from shared.config import AzureConfig


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Add a new entry to a JSON array in blob storage with user isolation.
    
    Parameters (in JSON body):
    - target_blob_name (required): Name of the file to update (e.g., "tasks.json")
    - new_entry (required): JSON object/data to append to the array
    - user_id (optional): User ID (extracted from header/query/body)
    
    Returns:
    - Success response with entry count
    """
    logging.info('add_new_data: Processing HTTP request with user isolation')
    
    # Parse request body
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    
    import time
    start_time = time.time()

    # Extract and validate user_id
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or req_body.get("user_id")
    )
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        return func.HttpResponse(
            json.dumps({"error": "Missing or invalid 'user_id'"}),
            status_code=400,
            mimetype="application/json"
        )
    user_id = user_id.strip()
    if "/" in user_id or ".." in user_id:
        return func.HttpResponse(
            json.dumps({"error": "Invalid user_id: path traversal detected"}),
            status_code=400,
            mimetype="application/json"
        )

    # Extract and validate target_blob_name
    target_blob_name = req_body.get('target_blob_name')
    if not target_blob_name or not isinstance(target_blob_name, str) or not target_blob_name.strip():
        return func.HttpResponse(
            json.dumps({"error": "Missing or invalid 'target_blob_name'", "user_id": user_id}),
            status_code=400,
            mimetype="application/json"
        )
    target_blob_name = target_blob_name.strip()
    if "/" in target_blob_name or ".." in target_blob_name:
        return func.HttpResponse(
            json.dumps({"error": "Invalid target_blob_name: path traversal detected", "user_id": user_id}),
            status_code=400,
            mimetype="application/json"
        )

    # Extract and validate new_entry
    new_entry = req_body.get('new_entry')
    if new_entry is None:
        return func.HttpResponse(
            json.dumps({"error": "Missing required field: 'new_entry'", "user_id": user_id}),
            status_code=400,
            mimetype="application/json"
        )
    if isinstance(new_entry, str):
        try:
            new_entry = json.loads(new_entry)
        except Exception:
            pass

    logging.info(f"add_new_data: user_id={user_id}, file_name={target_blob_name}")
    
    try:
        # Storage configuration
        connect_str = AzureConfig.CONNECTION_STRING
        container_name = AzureConfig.CONTAINER_NAME
        function_name = "add_new_data"
        status = "error"
        entry_count = None
        if not connect_str or not container_name:
            duration_ms = int((time.time() - start_time) * 1000)
            logging.info(json.dumps({
                "user_id": user_id,
                "function_name": function_name,
                "target_blob_name": target_blob_name,
                "status": "error",
                "duration_ms": duration_ms
            }))
            return func.HttpResponse(
                json.dumps({"error": "Missing Azure Storage configuration", "user_id": user_id}),
                status_code=500,
                mimetype="application/json"
            )

        # Namespace the blob path
        namespaced_blob_name = f"users/{user_id}/{target_blob_name}"

        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning(f"add_new_data: container not found ({container_name}); creating")
            try:
                blob_service_client.create_container(container_name)
            except AzureError:
                pass
            container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(namespaced_blob_name)

        # 1. Read existing data or create empty list
        try:
            blob_data = blob_client.download_blob()
            data_str = blob_data.readall().decode('utf-8')
            data = json.loads(data_str)
        except ResourceNotFoundError:
            data = []

        # 2. Ensure data is a list
        if not isinstance(data, list):
            data = [data]

        # 3. Append new entry
        data.append(new_entry)

        # 4. Write updated data back
        upload_data = json.dumps(data, indent=2, ensure_ascii=False)
        blob_client.upload_blob(upload_data.encode('utf-8'), overwrite=True)

        entry_count = len(data)
        status = "success"
        duration_ms = int((time.time() - start_time) * 1000)
        logging.info(json.dumps({
            "user_id": user_id,
            "function_name": function_name,
            "target_blob_name": target_blob_name,
            "status": status,
            "duration_ms": duration_ms
        }))

        response_data = {
            "status": status,
            "message": f"Entry successfully added to '{target_blob_name}'",
            "entry_count": entry_count,
            "user_id": user_id
        }

        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except AzureError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logging.error(f"Azure error in add_new_data: {str(e)}")
        logging.info(json.dumps({
            "user_id": user_id,
            "function_name": "add_new_data",
            "target_blob_name": target_blob_name,
            "status": "error",
            "duration_ms": duration_ms
        }))
        return func.HttpResponse(
            json.dumps({"error": f"Azure storage error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logging.error(f"Unexpected error in add_new_data: {str(e)}")
        logging.info(json.dumps({
            "user_id": user_id,
            "function_name": "add_new_data",
            "target_blob_name": target_blob_name,
            "status": "error",
            "duration_ms": duration_ms
        }))
        return func.HttpResponse(
            json.dumps({"error": f"Server error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
