import json
import logging

import azure.functions as func

from .service import read_many_blobs_core


def _resolve_user_id(req: func.HttpRequest, body: dict) -> str:
    user_id = req.headers.get("x-user-id") or req.params.get("user_id") or body.get("user_id")
    return str(user_id or "default").strip() or "default"


def _merge_params(body: dict) -> dict:
    return {
        "files": body.get("files") or body.get("file_names") or [],
        "tail_lines": body.get("tail_lines"),
        "tail_bytes": body.get("tail_bytes"),
        "max_bytes_per_file": body.get("max_bytes_per_file"),
        "parse_json": body.get("parse_json"),
        "max_files": body.get("max_files"),
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

    params = _merge_params(body)
    user_id = _resolve_user_id(req, body)
    response, status_code = read_many_blobs_core(user_id=user_id, **params, raise_on_error=False)
    return func.HttpResponse(
        json.dumps(response, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )
