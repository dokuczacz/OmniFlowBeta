import logging
import json
import sys
import os
from datetime import datetime
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.azure_client import AzureBlobClient
from shared.config import AzureConfig
from shared.user_manager import extract_user_id


def _is_duplicate_interaction(existing_logs: list, candidate: dict, *, max_age_seconds: int = 30) -> bool:
    if not existing_logs:
        return False
    try:
        last = existing_logs[-1] if isinstance(existing_logs, list) else None
        if not isinstance(last, dict):
            return False
        same_thread = (last.get("thread_id") or None) == (candidate.get("thread_id") or None)
        same_user_msg = (last.get("user_message") or "") == (candidate.get("user_message") or "")
        same_assistant = (last.get("assistant_response") or "") == (candidate.get("assistant_response") or "")
        if not (same_thread and same_user_msg and same_assistant):
            return False
        last_ts = last.get("timestamp")
        cand_ts = candidate.get("timestamp")
        if not (last_ts and cand_ts):
            return True
        last_dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
        cand_dt = datetime.fromisoformat(str(cand_ts).replace("Z", "+00:00"))
        return abs((cand_dt - last_dt).total_seconds()) <= max_age_seconds
    except Exception:
        return False


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Save interaction data for future analysis with user isolation.
    
    Parameters (in JSON body):
    - user_message (required): The user's input message
    - assistant_response (required): The assistant's response
    - thread_id (optional): Thread ID for conversation tracking
    - tool_calls (optional): List of tool calls made during interaction
    - metadata (optional): Additional metadata about the interaction
    - user_id (optional): User ID (extracted from header/query/body)
    
    Returns:
    - Success response with interaction ID and storage location
    """
    logging.info('save_interaction: Processing HTTP request with user isolation')
    
    # Parse request body
    try:
        req_body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Extract required parameters
    user_message = req_body.get('user_message')
    assistant_response = req_body.get('assistant_response')
    
    if not user_message or not assistant_response:
        return func.HttpResponse(
            json.dumps({"error": "Missing required fields: 'user_message' or 'assistant_response'"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Extract optional parameters
    thread_id = req_body.get('thread_id')
    tool_calls = req_body.get('tool_calls', [])
    metadata = req_body.get('metadata', {})
    
    # Extract user ID from request

    user_id = extract_user_id(req)
    if not user_id or not str(user_id).strip():
        return func.HttpResponse(
            json.dumps({"error": "Missing or invalid 'user_id' in request."}),
            status_code=400,
            mimetype="application/json"
        )
    logging.info(f"save_interaction: user_id={user_id}, thread_id={thread_id}")
    
    try:
        # Save-only approach: do not attempt to GET existing blob contents.
        # Build a new logs list containing the single new interaction and upload it.
        target_blob_name = "interaction_logs.json"
        blob_client = AzureBlobClient.get_blob_client(target_blob_name, user_id)

        now = datetime.utcnow()
        interaction_entry = {
            "interaction_id": f"INT_{now.strftime('%Y%m%d_%H%M%S_%f')}",
            "timestamp": now.isoformat(),
            "user_id": user_id,
            "thread_id": thread_id,
            "user_message": user_message,
            "assistant_response": assistant_response,
            "tool_calls": tool_calls,
            "metadata": metadata
        }

        # Read existing logs (if any) and append the new interaction to preserve history
        try:
            existing_logs = []
            try:
                # Try to download existing blob; if not found, we'll create a new list
                if AzureBlobClient.blob_exists(target_blob_name, user_id):
                    downloader = blob_client.download_blob()
                    raw = downloader.readall()
                    try:
                        existing_logs = json.loads(raw.decode('utf-8'))
                        if not isinstance(existing_logs, list):
                            existing_logs = [existing_logs]
                    except Exception:
                        existing_logs = []
                else:
                    existing_logs = []
            except ResourceNotFoundError:
                existing_logs = []

            if _is_duplicate_interaction(existing_logs, interaction_entry):
                response_data = {
                    "success": True,
                    "message": "Duplicate interaction skipped",
                    "code": "duplicate_skipped",
                    "interaction_id": interaction_entry["interaction_id"],
                    "timestamp": interaction_entry["timestamp"],
                    "total_interactions": len(existing_logs),
                    "user_id": user_id,
                    "storage_location": blob_client.blob_name,
                }
                return func.HttpResponse(
                    json.dumps(response_data, ensure_ascii=False),
                    mimetype="application/json",
                    status_code=200,
                )

            logs = list(existing_logs) + [interaction_entry]
            upload_data = json.dumps(logs, indent=2, ensure_ascii=False)

            # Try upload, on container-not-found attempt to create container then retry
            upload_success = False
            try:
                blob_client.upload_blob(upload_data.encode('utf-8'), overwrite=True)
                upload_success = True
            except ResourceNotFoundError as e:
                logging.warning(f"Upload failed with ResourceNotFoundError; attempting to create container: {e}")
                try:
                    service = AzureBlobClient.get_service_client()
                    service.create_container(AzureConfig.CONTAINER_NAME)
                    logging.info(f"Created missing container: {AzureConfig.CONTAINER_NAME}")
                    # Re-acquire blob client and retry upload once
                    blob_client = AzureBlobClient.get_blob_client(target_blob_name, user_id)
                    blob_client.upload_blob(upload_data.encode('utf-8'), overwrite=True)
                    upload_success = True
                except Exception as create_exc:
                    logging.error(f"Failed to create container: {create_exc}")
                    return func.HttpResponse(
                        json.dumps({
                            "success": False,
                            "message": "Failed to create container for user interaction log.",
                            "code": "container_create_failed",
                            "details": str(create_exc)[:200]
                        }),
                        status_code=500,
                        mimetype="application/json"
                    )
            except AzureError as e:
                logging.error(f"Azure error in save_interaction: {str(e)}")
                return func.HttpResponse(
                    json.dumps({
                        "success": False,
                        "message": "Azure storage error during save_interaction.",
                        "code": "azure_error",
                        "details": str(e)[:200]
                    }),
                    status_code=500,
                    mimetype="application/json"
                )
        except Exception as e:
            logging.error(f"Unexpected error preparing upload data: {e}")
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "message": "Server error preparing interaction log.",
                    "code": "server_error",
                    "details": str(e)[:200]
                }),
                status_code=500,
                mimetype="application/json"
            )

        if upload_success:
            response_data = {
                "success": True,
                "message": "Interaction successfully saved",
                "code": "ok",
                "interaction_id": interaction_entry["interaction_id"],
                "timestamp": interaction_entry["timestamp"],
                "total_interactions": len(logs),
                "user_id": user_id,
                "storage_location": blob_client.blob_name
            }
            return func.HttpResponse(
                json.dumps(response_data, ensure_ascii=False),
                mimetype="application/json",
                status_code=200
            )
        else:
            return func.HttpResponse(
                json.dumps({
                    "success": False,
                    "message": "Unknown error: upload did not succeed.",
                    "code": "unknown_error",
                    "details": "Upload did not complete successfully."
                }),
                status_code=500,
                mimetype="application/json"
            )
    except Exception as e:
        logging.error(f"Unexpected error in save_interaction: {str(e)}")
        return func.HttpResponse(
            json.dumps({
                "success": False,
                "message": "Server error during save_interaction.",
                "code": "server_error",
                "details": str(e)[:200]
            }),
            status_code=500,
            mimetype="application/json"
        )
