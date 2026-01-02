import json
import logging
import os

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

    try:
        client = ContainerClient.from_connection_string(conn_str, container_name)
        blobs = []
        for b in client.list_blobs(name_starts_with=prefix):
            blobs.append({"name": b.name, "size": getattr(b, "size", None)})

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
