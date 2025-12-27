import logging
import json
import azure.functions as func
import os
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
from shared.config import AzureConfig

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('manage_files: Processing file management request')

    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON payload."}),
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
    
    operation = req_body.get('operation')
    source_name = req_body.get('source_name')
    target_name = req_body.get('target_name')
    prefix = req_body.get('prefix', '')

    if not operation:
        return func.HttpResponse("Missing required field 'operation'.", status_code=400)

    try:
        connect_str = AzureConfig.CONNECTION_STRING
        container_name = AzureConfig.CONTAINER_NAME
        if not connect_str or not container_name:
            return func.HttpResponse(
                json.dumps({"error": "Missing Azure Storage configuration.", "user_id": user_id}),
                mimetype="application/json",
                status_code=500,
            )
        
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning(f"manage_files: container not found ({container_name}); creating")
            try:
                blob_service_client.create_container(container_name)
            except ResourceExistsError:
                pass
            container_client = blob_service_client.get_container_client(container_name)
        
        result_message = ""
        
        if operation == 'list':
            # List operation - namespace to user
            user_namespace_prefix = f"users/{user_id}/"
            full_prefix = user_namespace_prefix + prefix if prefix else user_namespace_prefix
            
            logging.info(f"Listing blobs for user '{user_id}' with prefix: {full_prefix}")
            blob_list = container_client.list_blobs(name_starts_with=full_prefix)
            
            file_names = []
            for blob in blob_list:
                # Return relative to user namespace
                relative_name = blob.name[len(user_namespace_prefix):]
                file_names.append(relative_name)
            
            result_message = f"Successfully retrieved list of {len(file_names)} files."
            response_data = {
                "status": "success",
                "user_id": user_id,
                "operation": "list",
                "prefix": prefix,
                "files": file_names,
                "count": len(file_names),
                "message": result_message
            }
        
        elif operation == 'delete':
            if not source_name:
                return func.HttpResponse(
                    json.dumps({"error": "Missing 'source_name' for delete operation.", "user_id": user_id}),
                    mimetype="application/json",
                    status_code=400
                )
            
            # Namespace to user
            full_source_name = f"users/{user_id}/{source_name}"
            blob_client = container_client.get_blob_client(full_source_name)
            blob_client.delete_blob()
            
            result_message = f"Successfully deleted file: {source_name}."
            response_data = {
                "status": "success",
                "user_id": user_id,
                "operation": "delete",
                "source_name": source_name,
                "message": result_message
            }
            
        elif operation == 'rename':
            if not source_name or not target_name:
                return func.HttpResponse(
                    json.dumps({"error": "Missing 'source_name' or 'target_name' for rename operation.", "user_id": user_id}),
                    mimetype="application/json",
                    status_code=400
                )
            
            # Namespace both source and target to user
            full_source_name = f"users/{user_id}/{source_name}"
            full_target_name = f"users/{user_id}/{target_name}"
            
            source_blob_client = container_client.get_blob_client(full_source_name)
            target_blob_client = container_client.get_blob_client(full_target_name)
            
            target_blob_client.start_copy_from_url(source_blob_client.url)
            source_blob_client.delete_blob()
            
            result_message = f"Successfully renamed file from '{source_name}' to '{target_name}'."
            response_data = {
                "status": "success",
                "user_id": user_id,
                "operation": "rename",
                "source_name": source_name,
                "target_name": target_name,
                "message": result_message
            }

        else:
            return func.HttpResponse(
                json.dumps({"error": f"Unsupported operation: {operation}.", "user_id": user_id}),
                mimetype="application/json",
                status_code=400
            )
        
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        error_status = 500
        if "BlobNotFound" in str(e):
            error_status = 404
             
        logging.error(f"Error in manage_files: {e}")
        
        return func.HttpResponse(
            json.dumps({
                "error": f"Error during Blob Storage operation: {str(e)}",
                "user_id": user_id if 'user_id' in locals() else "unknown"
            }),
            mimetype="application/json",
            status_code=error_status
        )
