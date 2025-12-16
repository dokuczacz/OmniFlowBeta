import logging
import json
import sys
import os
import azure.functions as func
from azure.core.exceptions import ResourceNotFoundError, AzureError

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.azure_client import AzureBlobClient
from shared.user_manager import extract_user_id


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    Retrieve interaction history for analysis with user isolation.
    
    Parameters (query params or JSON body):
    - thread_id (optional): Filter by specific thread
    - limit (optional): Maximum number of interactions to return (default: 50)
    - offset (optional): Number of interactions to skip (default: 0)
    - user_id (optional): User ID (extracted from header/query/body)
    
    Returns:
    - List of interactions with metadata
    """
    logging.info('get_interaction_history: Processing HTTP request with user isolation')
    
    # Extract parameters from query or body
    thread_id = req.params.get('thread_id')
    
    try:
        limit = int(req.params.get('limit', 50))
        offset = int(req.params.get('offset', 0))
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Invalid limit or offset value"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Try to get from body if not in query params
    try:
        req_body = req.get_json()
        if not thread_id:
            thread_id = req_body.get('thread_id')
        if req.params.get('limit') is None:
            limit = int(req_body.get('limit', 50))
        if req.params.get('offset') is None:
            offset = int(req_body.get('offset', 0))
    except (ValueError, AttributeError):
        pass
    
    # Validate parameters
    if limit < 1 or limit > 1000:
        return func.HttpResponse(
            json.dumps({"error": "Limit must be between 1 and 1000"}),
            status_code=400,
            mimetype="application/json"
        )
    
    if offset < 0:
        return func.HttpResponse(
            json.dumps({"error": "Offset must be non-negative"}),
            status_code=400,
            mimetype="application/json"
        )
    
    # Extract user ID from request
    user_id = extract_user_id(req)
    logging.info(f"get_interaction_history: user_id={user_id}, thread_id={thread_id}, limit={limit}, offset={offset}")
    
    try:
        # Use the same dedicated file for interaction logs
        target_blob_name = "interaction_logs.json"
        
        # Get blob client with user isolation
        blob_client = AzureBlobClient.get_blob_client(target_blob_name, user_id)
        
        # 1. Read existing logs
        try:
            blob_data = blob_client.download_blob()
            data_str = blob_data.readall().decode('utf-8')
            logs = json.loads(data_str)
        except ResourceNotFoundError:
            logs = []
        
        # 2. Ensure logs is a list
        if not isinstance(logs, list):
            logs = []
        
        # 3. Filter by thread_id if specified
        if thread_id:
            filtered_logs = [log for log in logs if log.get('thread_id') == thread_id]
        else:
            filtered_logs = logs
        
        # 4. Apply pagination
        total_count = len(filtered_logs)
        
        # Sort by timestamp (most recent first)
        filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Apply offset and limit
        paginated_logs = filtered_logs[offset:offset + limit]
        
        response_data = {
            "status": "success",
            "interactions": paginated_logs,
            "total_count": total_count,
            "returned_count": len(paginated_logs),
            "offset": offset,
            "limit": limit,
            "user_id": user_id,
            "thread_id": thread_id
        }
        
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )

    except AzureError as e:
        logging.error(f"Azure error in get_interaction_history: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Azure storage error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )
    except Exception as e:
        logging.error(f"Unexpected error in get_interaction_history: {str(e)}")
        return func.HttpResponse(
            json.dumps({"error": f"Server error: {str(e)}"}),
            status_code=500,
            mimetype="application/json"
        )
