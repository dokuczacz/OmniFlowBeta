import json

import azure.functions as func

from .service import upload_data_or_file_core


def _resolve_user_id(req: func.HttpRequest, body: dict) -> str:
    user_id = req.headers.get("x-user-id") or req.params.get("user_id") or body.get("user_id")
    return str(user_id or "default").strip() or "default"


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "Invalid JSON payload"}),
            status_code=400,
            mimetype="application/json",
        )
    target = body.get("target_blob_name")
    file_content = body.get("file_content")
    if target is None or file_content is None:
        return func.HttpResponse(
            json.dumps({"status": "error", "error": "Missing required fields", "user_id": _resolve_user_id(req, body)}),
            status_code=400,
            mimetype="application/json",
        )
    user_id = _resolve_user_id(req, body)
    response, status_code = upload_data_or_file_core(
        user_id=user_id,
        target_blob_name=target,
        file_content=file_content,
        raise_on_error=False,
    )
    return func.HttpResponse(
        json.dumps(response, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )
