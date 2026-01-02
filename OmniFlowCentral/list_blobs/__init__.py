import json
import logging
import os
import time

import azure.functions as func
from azure.storage.blob import ContainerClient


def _get_connection_string():
    return os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("list_blobs: start")

    conn_str = _get_connection_string()
    if not conn_str:
        logging.error("Missing Azure storage connection string")
        return func.HttpResponse(
            json.dumps({"error": "Missing storage connection string"}),
            status_code=500,
            mimetype="application/json",
        )

    container_name = os.environ.get("AZURE_BLOB_CONTAINER_NAME")
    if not container_name:
        logging.error("Missing AZURE_BLOB_CONTAINER_NAME env var")
        return func.HttpResponse(
            json.dumps({"error": "Missing AZURE_BLOB_CONTAINER_NAME"}),
            status_code=500,
            mimetype="application/json",
        )

    prefix = req.params.get("prefix")
    if not prefix:
        try:
            req_body = req.get_json()
            prefix = req_body.get("prefix")
        except Exception:
            prefix = None

    max_results = 200
    try:
        max_results = int(req.params.get("max_results") or max_results)
    except Exception:
        max_results = 200
    if max_results < 0:
        max_results = 0
    if max_results > 1000:
        max_results = 1000

    timeout_s = 10
    try:
        timeout_s = int(os.environ.get("AZURE_BLOB_LIST_TIMEOUT_SECONDS") or timeout_s)
    except Exception:
        timeout_s = 10
    if timeout_s < 1:
        timeout_s = 1
    if timeout_s > 60:
        timeout_s = 60

    try:
        client = ContainerClient.from_connection_string(conn_str, container_name)
        blobs = []
        start = time.monotonic()
        for b in client.list_blobs(name_starts_with=prefix, timeout=timeout_s):
            blobs.append({"name": b.name, "size": getattr(b, "size", None)})
            if len(blobs) >= max_results:
                break
            if (time.monotonic() - start) > timeout_s:
                break

        return func.HttpResponse(
            json.dumps({"blobs": blobs}, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.exception("Error listing blobs")
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json",
        )
