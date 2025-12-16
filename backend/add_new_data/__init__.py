import logging
import json
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError
import os
from azure.storage.blob import BlobServiceClient


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
    
    # Extract user_id in priority order: header -> query -> body -> default
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or req_body.get("user_id")
        or "default"
    )
    user_id = str(user_id).strip()
    
    # Extract required parameters
    target_blob_name = req_body.get('target_blob_name')
    new_entry = req_body.get('new_entry')
    if isinstance(new_entry, str):
        try:
            new_entry = json.loads(new_entry)
        except Exception:
            # leave as string if not valid JSON
            pass
    
    if not target_blob_name or not new_entry:
        return func.HttpResponse(
            json.dumps({"error": "Missing required fields: 'target_blob_name' or 'new_entry'", "user_id": user_id}),
            status_code=400,
            mimetype="application/json"
        )

    logging.info(f"add_new_data: user_id={user_id}, file_name={target_blob_name}")
    
    try:
        # Storage configuration
        connect_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        container_name = os.environ.get("AZURE_BLOB_CONTAINER_NAME")
        
        if not connect_str or not container_name:
            return func.HttpResponse(
                json.dumps({"error": "Missing Azure Storage configuration", "user_id": user_id}),
                status_code=500,
                mimetype="application/json"
            )
        
        # Namespace the blob path
        namespaced_blob_name = f"users/{user_id}/{target_blob_name}"
        
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
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
        
        response_data = {
            "status": "success",
            "message": f"Entry successfully added to '{target_blob_name}'",
            "entry_count": len(data),
            "user_id": user_id
        }
        
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except AzureError as e:
        logging.error(f"Azure error in add_new_data: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Azure storage error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Unexpected error in add_new_data: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Server error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
