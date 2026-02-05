import json

import azure.functions as func

from .service import get_filtered_data_core


def _resolve_user_id(req: func.HttpRequest, body: dict) -> str:
    user_id = req.headers.get("x-user-id") or req.params.get("user_id") or body.get("user_id")
    return str(user_id or "default").strip() or "default"


def _extract_payload(body: dict) -> dict:
    return {
        "target_blob_name": body.get("target_blob_name") or body.get("file_name"),
        "filter_key": body.get("filter_key"),
        "filter_value": body.get("filter_value"),
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "Invalid JSON in request body"}),
            status_code=400,
            mimetype="application/json",
        )

    user_id = _resolve_user_id(req, body)
    params = _extract_payload(body)
    if not params["target_blob_name"]:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "Missing required field 'target_blob_name'", "user_id": user_id}),
            status_code=400,
            mimetype="application/json",
        )

    response, status_code = get_filtered_data_core(user_id=user_id, raise_on_error=False, **params)
    return func.HttpResponse(
        json.dumps(response, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )
