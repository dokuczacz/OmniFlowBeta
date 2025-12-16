import logging
import json
import os
import azure.functions as func
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Update a data entry in a JSON file with user isolation.
    
    Parameters (in JSON body):
    - target_blob_name (required): Name of the file to update
    - find_key (required): Key to search by (e.g., "id")
    - find_value (required): Value to match
    - update_key (required): Key to update
    - update_value (required): New value
    - user_id (optional): User ID (extracted from header/query/body)
    """
    logging.info('update_data_entry: Processing HTTP request with user isolation')

    # Parse request body
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Invalid JSON format"}),
            mimetype="application/json",
            status_code=400
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
    find_key = req_body.get('find_key')
    find_value = req_body.get('find_value')
    update_key = req_body.get('update_key')
    update_value = req_body.get('update_value')

    if not all([target_blob_name, find_key, find_value, update_key, update_value]):
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": "Missing required fields",
                "user_id": user_id
            }),
            mimetype="application/json",
            status_code=400
        )

    logging.info(f"update_data_entry: user_id={user_id}, file={target_blob_name}, find={find_key}={find_value}, update={update_key}={update_value}")

    try:
        # Storage configuration
        connect_str = os.environ.get('AZURE_STORAGE_CONNECTION_STRING')
        container_name = os.environ.get('AZURE_BLOB_CONTAINER_NAME')
        
        if not connect_str or not container_name:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Missing Azure Storage configuration", "user_id": user_id}),
                mimetype="application/json",
                status_code=500
            )

        # Namespace the blob path
        namespaced_blob_name = f"users/{user_id}/{target_blob_name}"
        
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(namespaced_blob_name)

        # Read current file
        download_stream = blob_client.download_blob()
        raw_list = json.loads(download_stream.readall().decode('utf-8'))

        # Normalize entries: convert JSON strings to dicts if needed
        data_list = []
        for entry in raw_list if isinstance(raw_list, list) else [raw_list]:
            if isinstance(entry, str):
                try:
                    entry = json.loads(entry)
                except Exception:
                    entry = {"_raw": entry}
            data_list.append(entry)
        
        entry_updated = False
        
        # Find and update entry
        for item in data_list:
            if not isinstance(item, dict):
                continue
            if str(item.get(find_key)).lower() == str(find_value).lower():
                item[update_key] = update_value
                entry_updated = True
                logging.info(f"Updated record {find_key}={find_value}: set {update_key}={update_value}")
                break

        if not entry_updated:
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "message": f"Record not found: {find_key}={find_value}",
                    "user_id": user_id
                }),
                mimetype="application/json",
                status_code=404
            )

        # Write updated data
        modified_data = json.dumps(data_list, indent=2, ensure_ascii=False)
        blob_client.upload_blob(modified_data, overwrite=True)

        return func.HttpResponse(
            json.dumps({
                "status": "success",
                "message": f"Successfully updated {find_key}={find_value} in '{target_blob_name}'",
                "updated_key": update_key,
                "updated_value": update_value,
                "user_id": user_id
            }, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except ResourceNotFoundError:
        logging.warning(f"File not found: {namespaced_blob_name}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": f"File '{target_blob_name}' not found", "user_id": user_id}),
            mimetype="application/json",
            status_code=404
        )
    except Exception as e:
        logging.error(f"Error in update_data_entry: {e}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": f"Server error: {str(e)}", "user_id": user_id}),
            mimetype="application/json",
            status_code=500
        )
