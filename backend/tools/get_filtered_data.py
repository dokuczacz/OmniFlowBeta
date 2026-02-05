from get_filtered_data.service import get_filtered_data_core


def get_filtered_data(args, user_id):
    payload = {
        "target_blob_name": args.get("target_blob_name") or args.get("file_name"),
        "filter_key": args.get("filter_key"),
        "filter_value": args.get("filter_value"),
    }
    result, _ = get_filtered_data_core(user_id=user_id, raise_on_error=False, **payload)
    return result
