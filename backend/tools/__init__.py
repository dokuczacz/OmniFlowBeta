# tools/__init__.py
# Tool dispatch registry and loader for in-process tool calls

import os

from .add_new_data import add_new_data
from .get_current_time import get_current_time
from .get_filtered_data import get_filtered_data
from .list_blobs import list_blobs
from .read_blob_file import read_blob_file
from .read_many_blobs import read_many_blobs
from .remove_data_entry import remove_data_entry
from .update_data_entry import update_data_entry
from .upload_data_or_file import upload_data_or_file
from .manage_files import manage_files
from .gmail_action import gmail_action

tool_registry = {
    "add_new_data": add_new_data,
    "get_current_time": get_current_time,
    "get_filtered_data": get_filtered_data,
    "list_blobs": list_blobs,
    "read_blob_file": read_blob_file,
    "read_many_blobs": read_many_blobs,
    "remove_data_entry": remove_data_entry,
    "update_data_entry": update_data_entry,
    "upload_data_or_file": upload_data_or_file,
    "manage_files": manage_files,
    "gmail_action": gmail_action,
}

def dispatch_tool(tool_name, args, user_id):
    if tool_name not in tool_registry:
        raise ValueError(f"Unknown tool: {tool_name}")
    # Starter pack must be explicit (`action=pa_init`) in tool_call_handler.
    # For tool-level tests we can force initialization via OMNIFLOW_STARTER_PACK_FORCE=1.
    if os.environ.get("OMNIFLOW_STARTER_PACK_FORCE") in ("1", "true", "yes"):
        from shared.starter_pack import ensure_starter_pack

        ensure_starter_pack(user_id)
    return tool_registry[tool_name](args, user_id)
