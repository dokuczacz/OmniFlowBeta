from add_new_data.service import add_new_data_core


def add_new_data(args, user_id):
    payload = {
        'target_blob_name': args.get('target_blob_name') or args.get('file_name'),
        'new_entry': args.get('new_entry'),
    }
    if not payload['target_blob_name'] or payload['new_entry'] is None:
        return {'status': 'error', 'error': 'Missing required fields'}
    result, _ = add_new_data_core(user_id=user_id, raise_on_error=False, **payload)
    return result
