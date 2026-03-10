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
        interactions = []
        source = "interactions/index.jsonl"

        # Primary source (current architecture): interactions/index.jsonl.
        index_blob_client = AzureBlobClient.get_blob_client("interactions/index.jsonl", user_id)
        try:
            index_raw = index_blob_client.download_blob().readall().decode("utf-8")
            for line in index_raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict):
                    interactions.append(entry)
        except ResourceNotFoundError:
            # Backward-compatible fallback for older users.
            source = "interaction_logs.json"
            legacy_blob = AzureBlobClient.get_blob_client("interaction_logs.json", user_id)
            try:
                legacy_raw = legacy_blob.download_blob().readall().decode("utf-8")
                legacy = json.loads(legacy_raw)
                if isinstance(legacy, list):
                    interactions = [it for it in legacy if isinstance(it, dict)]
            except ResourceNotFoundError:
                interactions = []

        if thread_id:
            filtered_logs = [log for log in interactions if str(log.get("thread_id") or "") == thread_id]
        else:
            filtered_logs = interactions

        filtered_logs.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
        total_count = len(filtered_logs)
        paginated_logs = filtered_logs[offset:offset + limit]

        response_data = {
            "status": "success",
            "interactions": paginated_logs,
            "total_count": total_count,
            "returned_count": len(paginated_logs),
            "offset": offset,
            "limit": limit,
            "user_id": user_id,
            "thread_id": thread_id,
            "source": source,
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
