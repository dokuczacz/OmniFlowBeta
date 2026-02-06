import json
import logging
import time
import azure.functions as func

from .service import list_blobs_core


def _resolve_user_id(req: func.HttpRequest) -> str:
    user_id = req.headers.get("x-user-id") or req.params.get("user_id")
    if not user_id:
        try:
            body = req.get_json()
            user_id = body.get("user_id")
        except ValueError:
            pass
    return str(user_id or "default").strip()


def _parse_include_meta(req: func.HttpRequest) -> bool:
    value = str(req.params.get("include_meta") or "").strip().lower()
    return value in ("1", "true", "yes", "y", "on")


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("list_blobs: received request")
    user_id = _resolve_user_id(req)
    prefix = req.params.get("prefix", "")
    include_meta = _parse_include_meta(req)
    response = list_blobs_core(user_id, prefix=prefix, include_meta=include_meta, raise_on_error=True)
    status_code = 200 if response.get("status") == "success" else 500
    return func.HttpResponse(
        json.dumps(response, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )
