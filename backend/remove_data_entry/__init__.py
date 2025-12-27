import logging
import json
import azure.functions as func
import os
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError
from azure.core.exceptions import ResourceExistsError
from shared.config import AzureConfig

def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Remove data entries from a JSON file with user isolation.
    
    Parameters (in JSON body):
    - target_blob_name (required): Name of the file
    - key_to_find (required): Key to search by
    - value_to_find (required): Value to match for deletion
    - user_id (optional): User ID (extracted from header/query/body)
    """
    logging.info('remove_data_entry: Processing HTTP request with user isolation')
    
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

    target_blob_name = req_body.get('target_blob_name')
    key_to_find = req_body.get('key_to_find')
    value_to_find = req_body.get('value_to_find')

    if not all([target_blob_name, key_to_find, value_to_find]):
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "message": "Missing required fields: 'target_blob_name', 'key_to_find', or 'value_to_find'",
                "user_id": user_id
            }),
            mimetype="application/json",
            status_code=400
        )

    logging.info(f"remove_data_entry: user_id={user_id}, file={target_blob_name}, remove={key_to_find}={value_to_find}")

    try:
        connect_str = AzureConfig.CONNECTION_STRING
        container_name = AzureConfig.CONTAINER_NAME
        
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
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning(f"remove_data_entry: container not found ({container_name}); creating")
            try:
                blob_service_client.create_container(container_name)
            except ResourceExistsError:
                pass
            container_client = blob_service_client.get_container_client(container_name)
        blob_client = container_client.get_blob_client(namespaced_blob_name)
        
        # Read existing data
        try:
            blob_data = blob_client.download_blob()
            data_str = blob_data.readall().decode('utf-8')
            raw_list = json.loads(data_str)
        except ResourceNotFoundError:
            return func.HttpResponse(
                json.dumps({"status": "error", "message": f"File '{target_blob_name}' not found", "user_id": user_id}),
                mimetype="application/json",
                status_code=404
            )
        
        if not isinstance(raw_list, list):
            return func.HttpResponse(
                json.dumps({"status": "error", "message": "Target file is not a list", "user_id": user_id}),
                mimetype="application/json",
                status_code=500
            )

        # Normalize entries (parse JSON strings)
        data_list = []
        for entry in raw_list:
            if isinstance(entry, str):
                try:
                    entry = json.loads(entry)
                except Exception:
                    entry = {"_raw": entry}
            data_list.append(entry)

        # Remove matching entries
        initial_count = len(data_list)
        
        modified_data_list = [
            entry for entry in data_list 
            if not (isinstance(entry, dict) and str(entry.get(key_to_find)) == str(value_to_find))
        ]
        
        deleted_count = initial_count - len(modified_data_list)

        if deleted_count == 0:
            return func.HttpResponse(
                json.dumps({
                    "status": "not_found",
                    "message": f"No entries found matching {key_to_find}={value_to_find}",
                    "user_id": user_id
                }),
                mimetype="application/json",
                status_code=404
            )

        # Write modified list
        upload_data = json.dumps(modified_data_list, indent=2, ensure_ascii=False)
        blob_client.upload_blob(upload_data.encode('utf-8'), overwrite=True)

        response_data = {
            "status": "success",
            "message": f"Successfully removed {deleted_count} entries matching {key_to_find}={value_to_find}",
            "deleted_count": deleted_count,
            "user_id": user_id
        }
        
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"Error in remove_data_entry: {e}")
        return func.HttpResponse(
            json.dumps({"status": "error", "message": f"Server error: {str(e)}", "user_id": user_id}),
            mimetype="application/json",
            status_code=500
        )
