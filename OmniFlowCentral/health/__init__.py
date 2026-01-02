import json
import logging

import azure.functions as func


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("health: ok")
    return func.HttpResponse(
        json.dumps({"status": "ok"}, ensure_ascii=False),
        mimetype="application/json",
        status_code=200,
    )
