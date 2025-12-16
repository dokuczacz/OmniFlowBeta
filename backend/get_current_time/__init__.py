import logging
import json
import azure.functions as func
from datetime import datetime, timezone

def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('get_current_time: Processing HTTP request.')
    
    try:
        # Get current time in UTC (ISO 8601 format with 'Z')
        now_utc = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        response_data = {
            "current_time_utc": now_utc,
            "message": "Successfully retrieved current UTC time."
        }
        
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200
        )
    except Exception as e:
        logging.error(f"Error in get_current_time: {e}")
        return func.HttpResponse(
             json.dumps({"error": f"Server error: {str(e)}"}),
             mimetype="application/json",
             status_code=500
        )