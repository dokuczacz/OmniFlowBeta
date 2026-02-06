import logging
import json
import sys
import os
import azure.functions as func
from azure.core.exceptions import AzureError

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.tool_handler_config import DEFAULT_TOOL_HANDLER_CONFIG as TOOL_HANDLER_CONFIG
from shared.user_manager import extract_user_id
from shared.wp7_indexer import QueueThresholds, append_queue_item, build_queue_item
from .service import save_interaction_entry

CONFIG = TOOL_HANDLER_CONFIG


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
        result = save_interaction_entry(
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_response,
            thread_id=thread_id,
            tool_calls=tool_calls,
            metadata=metadata,
        )
        if result.get("duplicate"):
            response_data = {
                "success": True,
                "message": "Duplicate interaction skipped",
                "code": "duplicate_skipped",
                "interaction_id": result["interaction_entry"]["interaction_id"],
                "timestamp": result["interaction_entry"]["timestamp"],
                "total_interactions": result.get("total_interactions", 0),
                "user_id": user_id,
                "storage_location": result.get("interaction_blob"),
            }
            return func.HttpResponse(
                json.dumps(response_data, ensure_ascii=False),
                mimetype="application/json",
                status_code=200,
            )

        interaction_entry = result["interaction_entry"]
        total_interactions = result.get("total_interactions", 1)
        storage_location = result.get("interaction_blob")

        try:
            batch_multiplier = max(1, CONFIG.wp7_batch_size_multiplier)
            thresholds = QueueThresholds(
                target_tokens=CONFIG.wp7_target_batch_tokens * batch_multiplier,
                hard_min_tokens=CONFIG.wp7_hard_min_batch_tokens * batch_multiplier,
                max_wait_seconds=CONFIG.wp7_max_wait_seconds,
                max_items_per_run=min(CONFIG.wp7_max_items_per_run, 25),
            )
            queue_item = build_queue_item(interaction_entry, user_id=user_id, thresholds=thresholds)
            append_queue_item(user_id, queue_item)
        except Exception as enqueue_exc:
            logging.warning(f"WP7 queue enqueue failed (non-fatal): {enqueue_exc}")

        response_data = {
            "success": True,
            "message": "Interaction successfully saved",
            "code": "ok",
            "interaction_id": interaction_entry["interaction_id"],
            "timestamp": interaction_entry["timestamp"],
            "total_interactions": total_interactions,
            "user_id": user_id,
            "storage_location": storage_location,
        }
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
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
