from manage_files.service import manage_files_core
from shared.manage_files_params import normalize_manage_files_params


def manage_files(args, user_id):
    params = normalize_manage_files_params(args)
    response, _status = manage_files_core(
        user_id=user_id,
        operation=params.get("operation"),
        prefix=params.get("prefix"),
        source_name=params.get("source_name"),
        target_name=params.get("target_name"),
        raise_on_error=False,
    )
    return response
