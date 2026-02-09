"""
Retrieve intent classification artifacts (ML training dataset) from blob storage.
Supports pagination and filtering by date range.
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import ResourceNotFoundError


def main(req) -> str:
    """
    GET /api/get_intent_artifacts
    
    Query params:
    - limit: Max number of entries to return (default 100, max 10000)
    - offset: Skip N entries (for pagination)
    - since: ISO datetime (return entries after this time)
    - stage: Filter by PA stage (e.g., EMAIL_WRITE)
    - min_confidence: Filter by min confidence (0.0-1.0)
    
    Response:
    {
        "entries": [...],
        "total_count": N,
        "offset": X,
        "limit": Y,
        "next": "..." (if more entries available)
    }
    """
    try:
        # Parse query parameters
        limit = int(req.params.get("limit", 100))
        offset = int(req.params.get("offset", 0))
        since = req.params.get("since", None)
        stage_filter = req.params.get("stage", None)
        min_confidence = float(req.params.get("min_confidence", 0.0))
        
        # Validate
        limit = min(max(1, limit), 10000)
        offset = max(0, offset)
        
        # Get logs from blob storage
        entries = _get_intent_artifacts_from_blob(
            limit=limit,
            offset=offset,
            since=since,
            stage=stage_filter,
            min_confidence=min_confidence
        )
        
        response = {
            "entries": entries["items"],
            "total_count": entries["total"],
            "offset": offset,
            "limit": limit,
            "next": entries.get("next_offset", None),
        }
        
        return json.dumps(response), 200, {"Content-Type": "application/json"}
        
    except Exception as e:
        logging.error(f"get_intent_artifacts error: {e}")
        return json.dumps({"error": str(e)}), 500, {"Content-Type": "application/json"}


def _get_intent_artifacts_from_blob(
    limit: int = 100,
    offset: int = 0,
    since: str | None = None,
    stage: str | None = None,
    min_confidence: float = 0.0,
) -> Dict[str, Any]:
    """
    Fetch intent classification logs from blob storage (JSONL format).
    Supports pagination and filtering.
    
    Returns:
    {
        "items": [...JSON entries...],
        "total": N,
        "next_offset": M (if more)
    }
    """
    try:
        from datetime import datetime as dt
        
        container_name = os.environ.get("INTENT_CLASSIFIER_LOG_BLOB_CONTAINER", "training-data")
        blob_name = os.environ.get("INTENT_CLASSIFIER_LOG_BLOB_NAME", "analytics/intent_classifications.jsonl")
        connection_string = os.environ.get("AzureWebJobsStorage") or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        
        if not connection_string:
            logging.warning("Blob storage not configured")
            return {"items": [], "total": 0}
        
        service_client = BlobServiceClient.from_connection_string(connection_string)
        blob_client = service_client.get_blob_client(container=container_name, blob=blob_name)
        
        # Read blob content
        try:
            content = blob_client.download_blob().readall().decode("utf-8")
        except ResourceNotFoundError:
            return {"items": [], "total": 0}
        
        # Parse JSONL lines
        lines = content.strip().split("\n")
        entries = []
        
        for line in lines:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                
                # Apply filters
                if since:
                    try:
                        since_dt = dt.fromisoformat(since.replace("Z", "+00:00"))
                        entry_dt = dt.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
                        if entry_dt < since_dt:
                            continue
                    except Exception:
                        pass
                
                if stage and entry.get("stage") != stage:
                    continue
                
                if entry.get("confidence", 1.0) < min_confidence:
                    continue
                
                entries.append(entry)
            except json.JSONDecodeError:
                continue
        
        # Pagination
        total = len(entries)
        paginated = entries[offset:offset + limit]
        
        next_offset = None
        if offset + limit < total:
            next_offset = offset + limit
        
        return {
            "items": paginated,
            "total": total,
            "next_offset": next_offset,
        }
        
    except Exception as e:
        logging.error(f"_get_intent_artifacts_from_blob error: {e}")
        return {"items": [], "total": 0}
