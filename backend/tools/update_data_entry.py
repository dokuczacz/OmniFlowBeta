# tools/update_data_entry.py
from update_data_entry.service import update_data_entry_core


def _choose_blob_name(args):
    for key in ("target_blob_name", "file_name"):
        candidate = args.get(key)
        if candidate is not None:
            return str(candidate)
    return None


def update_data_entry(args, user_id):
    result, _status = update_data_entry_core(
        user_id=user_id,
        target_blob_name=_choose_blob_name(args),
        find_key=args.get("find_key"),
        find_value=args.get("find_value"),
        update_key=args.get("update_key"),
        update_value=args.get("update_value"),
        raise_on_error=False,
    )
    return result
