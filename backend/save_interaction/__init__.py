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
from shared.user_manager import extract_user_id


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
    logging.info(f"save_interaction: user_id={user_id}, thread_id={thread_id}")
    
    try:
        # Use a dedicated file for interaction logs
        target_blob_name = "interaction_logs.json"
        
        # Get blob client with user isolation
        blob_client = AzureBlobClient.get_blob_client(target_blob_name, user_id)
        
        # 1. Read existing logs or create empty list
        try:
            blob_data = blob_client.download_blob()
            data_str = blob_data.readall().decode('utf-8')
            logs = json.loads(data_str)
        except ResourceNotFoundError:
            logs = []
        
        # 2. Ensure logs is a list
        if not isinstance(logs, list):
            logs = []
        
        # 3. Create new interaction entry
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
        
        # 4. Append new interaction
        logs.append(interaction_entry)
        
        # 5. Write updated logs back
        upload_data = json.dumps(logs, indent=2, ensure_ascii=False)
        blob_client.upload_blob(upload_data.encode('utf-8'), overwrite=True)
        
        response_data = {
            "status": "success",
            "message": "Interaction successfully saved",
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

    except AzureError as e:
        logging.error(f"Azure error in save_interaction: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Azure storage error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Unexpected error in save_interaction: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Server error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )
