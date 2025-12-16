import json
import logging
import azure.functions as func
from azure.storage.blob import BlobServiceClient
import os


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    List blobs in the user's namespace.
    
    Parameters:
    - prefix (optional): Additional prefix filter within user's namespace
    - user_id (optional): User ID (extracted from header/query/body)
    
    Returns:
    - JSON array of blob names (relative to user's namespace)
    """
    # Extract user_id in priority order
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
    )
    if not user_id:
        try:
            body = req.get_json()
            user_id = body.get("user_id")
        except (ValueError, AttributeError):
            pass
    user_id = user_id or "default"
    user_id = str(user_id).strip()
    
    prefix = req.params.get("prefix", "")
    
    logging.info(f"list_blobs: user_id={user_id}, prefix={prefix}")
    
    try:
        connect_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        container_name = os.environ.get("AZURE_BLOB_CONTAINER_NAME")
        
        if not connect_str or not container_name:
            return func.HttpResponse(
                json.dumps({"error": "Missing Azure Storage configuration", "user_id": user_id}),
                status_code=500,
                mimetype="application/json"
            )
        
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_client = blob_service_client.get_container_client(container_name)
        
        # Build full prefix: users/{user_id}/{optional_prefix}
        user_namespace_prefix = f"users/{user_id}/"
        full_prefix = user_namespace_prefix + prefix if prefix else user_namespace_prefix
        
        # List blobs in user's namespace
        blob_list = []
        blobs = container_client.list_blobs(name_starts_with=full_prefix)
        for blob in blobs:
            # Return blob name relative to user's namespace (strip users/{user_id}/)
            relative_name = blob.name[len(user_namespace_prefix):]
            blob_list.append(relative_name)
        
        response = {
            "status": "success",
            "user_id": user_id,
            "blobs": blob_list,
            "count": len(blob_list)
        }
        
        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"Error listing blobs: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Error listing blobs: {str(e)}", "user_id": user_id}),
            status_code=500,
            mimetype="application/json"
        )
