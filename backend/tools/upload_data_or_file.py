from upload_data_or_file.service import upload_data_or_file_core


def upload_data_or_file(args, user_id):
    target = args.get("target_blob_name")
    file_content = args.get("file_content")
    result, _ = upload_data_or_file_core(
        user_id=user_id,
        target_blob_name=target,
        file_content=file_content,
        raise_on_error=False,
    )
    return result
