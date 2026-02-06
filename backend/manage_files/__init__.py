import json
import logging

import azure.functions as func

from .service import manage_files_core


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
    logging.info("manage_files: Processing file management request")
    payload = _parse_body(req)
    if payload is None:
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON payload."}),
            mimetype="application/json",
            status_code=400,
        )

    user_id = _resolve_user_id(req, payload)
    operation = payload.get("operation")
    source_name = payload.get("source_name")
    target_name = payload.get("target_name")
    prefix = payload.get("prefix")

    logging.info(
        "manage_files: user_id=%s operation=%s source=%s target=%s prefix=%s",
        user_id,
        operation,
        source_name,
        target_name,
        prefix,
    )

    try:
        response, status_code = manage_files_core(
            user_id=user_id,
            operation=operation,
            prefix=prefix,
            source_name=source_name,
            target_name=target_name,
            raise_on_error=False,
        )
        status_code = status_code if isinstance(status_code, int) else 500
        return func.HttpResponse(
            json.dumps(response, ensure_ascii=False),
            mimetype="application/json",
            status_code=status_code,
        )
    except Exception as exc:
        logging.exception("Error in manage_files: %s", exc)
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "error",
                    "message": f"Error during Blob Storage operation: {str(exc)}",
                    "user_id": user_id,
                },
                ensure_ascii=False,
            ),
            mimetype="application/json",
            status_code=500,
        )
