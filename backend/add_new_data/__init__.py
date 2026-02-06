import json

import azure.functions as func

from .service import add_new_data_core


def _resolve_user_id(req: func.HttpRequest, body: dict) -> str:
    user_id = req.headers.get('x-user-id') or req.params.get('user_id') or body.get('user_id')
    return str(user_id or 'default').strip() or 'default'


def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({'status': 'error', 'error': 'Invalid JSON in request body'}),
            status_code=400,
            mimetype='application/json',
        )
    user_id = _resolve_user_id(req, body)
    payload = {
        'target_blob_name': body.get('target_blob_name') or body.get('file_name'),
        'new_entry': body.get('new_entry'),
    }
    if not payload['target_blob_name'] or payload['new_entry'] is None:
        return func.HttpResponse(
            json.dumps({'status': 'error', 'error': 'Missing required fields', 'user_id': user_id}),
            status_code=400,
            mimetype='application/json',
        )
    response, status_code = add_new_data_core(
        user_id=user_id, raise_on_error=False, **payload
    )
    return func.HttpResponse(
        json.dumps(response, ensure_ascii=False),
        status_code=status_code,
        mimetype='application/json',
    )
