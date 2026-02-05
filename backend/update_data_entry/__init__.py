import json
import logging

import azure.functions as func

from .service import update_data_entry_core


def _resolve_user_id(req: func.HttpRequest, body: dict) -> str:
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or body.get("user_id")
    )
    return str(user_id or "default").strip()


def _parse_body(req: func.HttpRequest) -> dict | None:
    try:
        return req.get_json()
    except ValueError:
        return None


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("update_data_entry: Processing HTTP request with user isolation")
    payload = _parse_body(req)
    if payload is None:
        return func.HttpResponse(
            json.dumps({"status": "error", "message": "Invalid JSON format"}),
            mimetype="application/json",
            status_code=400,
        )

    user_id = _resolve_user_id(req, payload)
    target_blob_name = payload.get("target_blob_name")
    find_key = payload.get("find_key")
    find_value = payload.get("find_value")
    update_key = payload.get("update_key")
    update_value = payload.get("update_value")

    logging.info(
        "update_data_entry: user_id=%s file=%s find=%s=%s update=%s=%s",
        user_id,
        target_blob_name,
        find_key,
        find_value,
        update_key,
        update_value,
    )

    try:
        response, status_code = update_data_entry_core(
            user_id=user_id,
            target_blob_name=target_blob_name,
            find_key=find_key,
            find_value=find_value,
            update_key=update_key,
            update_value=update_value,
            raise_on_error=False,
        )
        status_code = status_code if isinstance(status_code, int) else 500
        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False),
            mimetype="application/json",
            status_code=status_code,
        )
    except Exception as exc:
        logging.exception("Error in update_data_entry: %s", exc)
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "error",
                    "message": f"Server error: {str(exc)}",
                    "user_id": user_id,
                },
                ensure_ascii=False,
            ),
            mimetype="application/json",
            status_code=500,
        )
