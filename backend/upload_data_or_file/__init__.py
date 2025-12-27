import logging
import json
import azure.functions as func
import os
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
from shared.config import AzureConfig


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('upload_data_or_file: Processing HTTP request.')
    
    # --- 1. Parsowanie JSON ---
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON payload."}, ensure_ascii=False),
            mimetype="application/json",
            status_code=400
        )

    # --- 1B. Extract user_id for namespace ---
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or req_body.get("user_id")
        or "default"
    )
    user_id = str(user_id).strip()

    target_blob_name = req_body.get('target_blob_name')
    file_content = req_body.get('file_content')

    if not target_blob_name or file_content is None:
        return func.HttpResponse(
            json.dumps({
                "error": "Missing required fields: 'target_blob_name' or 'file_content'."
            }, ensure_ascii=False),
            mimetype="application/json",
            status_code=400
        )

    # --- 2. Konfiguracja środowiska ---
    connect_str = AzureConfig.CONNECTION_STRING
    container_name = AzureConfig.CONTAINER_NAME
    if not connect_str or not container_name:
        return func.HttpResponse(
            json.dumps({"error": "Missing Azure Storage configuration."}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )

    try:
        blob_service_client = BlobServiceClient.from_connection_string(connect_str)
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            logging.warning(f"upload_data_or_file: container not found ({container_name}); creating")
            try:
                blob_service_client.create_container(container_name)
            except ResourceExistsError:
                pass
            container_client = blob_service_client.get_container_client(container_name)

        # --- 3. Przygotowanie danych do uploadu ---
        # Automatyczne wykrycie content_type
        if isinstance(file_content, (dict, list)):
            upload_data = json.dumps(file_content, indent=2, ensure_ascii=False)
            content_type = "application/json"
        else:
            upload_data = str(file_content)
            content_type = "text/plain"

        content_settings = ContentSettings(content_type=content_type)

        # Namespace the blob path
        namespaced_blob_name = f"users/{user_id}/{target_blob_name}"
        blob_client = container_client.get_blob_client(namespaced_blob_name)

        # --- 4. Zapis do Azure Blob (PRODUCTION SAFE) ---
        blob_client.upload_blob(
            upload_data.encode("utf-8"),
            overwrite=True,
            content_settings=content_settings
        )

        # --- 5. Odpowiedź ---
        response_data = {
            "message": "File uploaded successfully.",
            "blob_name": target_blob_name,
            "user_id": user_id,
            "storage_location": namespaced_blob_name,
            "content_type": content_type,
            "size_bytes": len(upload_data.encode("utf-8")),
        }

        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except Exception as e:
        logging.error(f"Critical error in upload_data_or_file: {e}")
        return func.HttpResponse(
            json.dumps({
                "error": "Internal server error while writing to Blob Storage.",
                "details": str(e)
            }, ensure_ascii=False),
            mimetype="application/json",
            status_code=500
        )
