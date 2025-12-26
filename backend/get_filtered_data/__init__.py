import logging
import json
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError
import os
from azure.storage.blob import BlobServiceClient


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Get and optionally filter data from a JSON file with user isolation.
    
    Parameters (in JSON body):
    - target_blob_name (required): Name of the file to read (e.g., "tasks.json")
    - filter_key (optional): Field name to filter by (e.g., "status")
    - filter_value (optional): Value to match (e.g., "open")
    - user_id (optional): User ID (extracted from header/query/body)
    
    Returns:
    - JSON data (filtered if filter_key/filter_value provided, otherwise full data)
    """
    logging.info('get_filtered_data: Processing HTTP request with user isolation')
    
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Extract user_id in priority order
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or req_body.get("user_id")
        or "default"
    )
    user_id = str(user_id).strip()
    
    # Extract parameters
    target_blob_name = req_body.get('target_blob_name')
    filter_key = req_body.get('filter_key')
    filter_value = req_body.get('filter_value')
    
    if not target_blob_name:
        return func.HttpResponse(
            json.dumps({"error": "Missing required field 'target_blob_name'", "user_id": user_id}),
            status_code=400,
            mimetype="application/json"
        )

    logging.info(f"get_filtered_data: user_id={user_id}, file={target_blob_name}, filter={filter_key}={filter_value if filter_key else 'none'}")
    
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
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning(f"get_filtered_data: container not found ({container_name}); creating")
            try:
                blob_service_client.create_container(container_name)
            except AzureError:
                pass
            container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(namespaced_blob_name)
        
        # Read blob data
        blob_data = blob_client.download_blob()
        data_str = blob_data.readall().decode('utf-8')
        raw_data = json.loads(data_str)

        # Normalize entries if list contains JSON strings
        if isinstance(raw_data, list):
            data = []
            for entry in raw_data:
                if isinstance(entry, str):
                    try:
                        entry = json.loads(entry)
                    except Exception:
                        entry = {"_raw": entry}
                data.append(entry)
        else:
            data = raw_data
        
        # Apply filter if provided
        if filter_key and filter_value is not None:
            filtered_data = [entry for entry in data if isinstance(entry, dict) and str(entry.get(filter_key)) == str(filter_value)]
            
            response = {
                "status": "success",
                "user_id": user_id,
                "file": target_blob_name,
                "filter": {"key": filter_key, "value": filter_value},
                "data": filtered_data,
                "count": len(filtered_data),
                "total": len(data)
            }
        else:
            response = {
                "status": "success",
                "user_id": user_id,
                "file": target_blob_name,
                "filter": None,
                "data": data,
                "count": len(data),
                "total": len(data)
            }
        
        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except ResourceNotFoundError:
        logging.warning(f"File not found: {namespaced_blob_name}")
        return func.HttpResponse(
            json.dumps({"error": f"File '{target_blob_name}' not found", "user_id": user_id}),
            status_code=404,
            mimetype="application/json"
        )
    except json.JSONDecodeError as e:
        logging.error(f"JSON parsing error in {target_blob_name}: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Invalid JSON format in file: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
    except AzureError as e:
        logging.error(f"Azure error in get_filtered_data: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Azure storage error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Unexpected error in get_filtered_data: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Server error: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
