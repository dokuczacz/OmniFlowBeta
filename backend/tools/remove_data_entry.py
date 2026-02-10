# tools/remove_data_entry.py
from remove_data_entry.service import remove_data_entry_core


def _choose_blob_name(args):
    for key in ("target_blob_name", "file_name"):
        candidate = args.get(key)
        if candidate is not None:
            return str(candidate)
    return None


def _choose_find_key(args):
    for key in ("key_to_find", "remove_key", "find_key", "key", "match_key"):
        candidate = args.get(key)
        if candidate is not None:
            return str(candidate)
    return None


def _choose_find_value(args):
    for key in ("value_to_find", "remove_value", "find_value", "value"):
        if key in args:
            return args.get(key)
    return None


def remove_data_entry(args, user_id):
    result, _status = remove_data_entry_core(
        user_id=user_id,
        target_blob_name=_choose_blob_name(args),
        key_to_find=_choose_find_key(args),
        value_to_find=_choose_find_value(args),
        raise_on_error=False,
    )
    return result
