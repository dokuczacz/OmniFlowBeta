import json
import logging
import os
from typing import Dict, List, Set

import azure.functions as func

from shared.local_logger import LocalLogger, log_request_end, log_request_start
from shared.user_manager import extract_user_id


CUSTOM_GPT_TOOL_SCHEMAS = [
    {
        "name": "add_new_data",
        "description": "Add a new entry to a JSON array stored in a blob.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_blob_name": {
                    "type": "string",
                    "description": "Name of the JSON blob to update (e.g., tasks.json).",
                },
                "new_entry": {
                    "type": "object",
                    "description": "JSON object to append to the array.",
                },
            },
            "required": ["target_blob_name", "new_entry"],
        },
        "required_scopes": [],
    },
    {
        "name": "get_current_time",
        "description": "Return the current UTC timestamp.",
        "parameters": {"type": "object", "properties": {}},
        "required_scopes": [],
    },
    {
        "name": "get_filtered_data",
        "description": "Filter JSON array data in a blob by a key/value pair.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_blob_name": {
                    "type": "string",
                    "description": "Name of the JSON blob to query.",
                },
                "filter_key": {"type": "string", "description": "Field to match."},
                "filter_value": {
                    "type": "string",
                    "description": "Value to match for the field.",
                },
            },
            "required": ["target_blob_name", "filter_key", "filter_value"],
        },
        "required_scopes": [],
    },
    {
        "name": "list_blobs",
        "description": "List blobs available to the current user.",
        "parameters": {
            "type": "object",
            "properties": {
                "prefix": {
                    "type": "string",
                    "description": "Optional prefix filter within the user namespace.",
                }
            },
        },
        "required_scopes": [],
    },
    {
        "name": "read_blob_file",
        "description": "Read the contents of a blob file for the current user.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_name": {
                    "type": "string",
                    "description": "Name of the blob file to read (e.g., tasks.json).",
                }
            },
            "required": ["file_name"],
        },
        "required_scopes": [],
    },
    {
        "name": "remove_data_entry",
        "description": "Remove an entry from a JSON array by key/value match.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_blob_name": {
                    "type": "string",
                    "description": "Name of the JSON blob to update.",
                },
                "key_to_find": {
                    "type": "string",
                    "description": "Field name to match for removal.",
                },
                "value_to_find": {
                    "type": "string",
                    "description": "Value to match for removal.",
                },
            },
            "required": ["target_blob_name", "key_to_find", "value_to_find"],
        },
        "required_scopes": [],
    },
    {
        "name": "update_data_entry",
        "description": "Update an entry in a JSON array by key/value match.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_blob_name": {
                    "type": "string",
                    "description": "Name of the JSON blob to update.",
                },
                "find_key": {
                    "type": "string",
                    "description": "Field name to match for updates.",
                },
                "find_value": {
                    "type": "string",
                    "description": "Value to match for updates.",
                },
                "update_key": {
                    "type": "string",
                    "description": "Field name to update.",
                },
                "update_value": {
                    "type": "string",
                    "description": "New value to set.",
                },
            },
            "required": [
                "target_blob_name",
                "find_key",
                "find_value",
                "update_key",
                "update_value",
            ],
        },
        "required_scopes": [],
    },
    {
        "name": "upload_data_or_file",
        "description": "Upload structured data or plain text to a blob.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_blob_name": {
                    "type": "string",
                    "description": "Name of the blob to create or overwrite.",
                },
                "file_content": {
                    "type": ["string", "object", "array"],
                    "description": "Content to upload to the blob.",
                },
            },
            "required": ["target_blob_name", "file_content"],
        },
        "required_scopes": [],
    },
    {
        "name": "manage_files",
        "description": "List, rename, or delete blob files for the current user.",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "description": "Operation to perform: list, rename, or delete.",
                    "enum": ["list", "rename", "delete"],
                },
                "source_name": {
                    "type": "string",
                    "description": "Source file name for rename/delete.",
                },
                "target_name": {
                    "type": "string",
                    "description": "Target file name for rename operations.",
                },
                "prefix": {
                    "type": "string",
                    "description": "Optional prefix filter for list operations.",
                },
            },
            "required": ["operation"],
        },
        "required_scopes": [],
    },
]

FUNCTION_URL_BASE = os.getenv("FUNCTION_URL_BASE", "https://agentbackendservice.azurewebsites.net").rstrip("/")
FUNCTION_HTTP_METHODS: Dict[str, List[str]] = {
    "add_new_data": ["POST"],
    "get_current_time": ["GET"],
    "get_filtered_data": ["GET", "POST"],
    "list_blobs": ["GET"],
    "read_blob_file": ["GET"],
    "remove_data_entry": ["POST"],
    "update_data_entry": ["POST"],
    "upload_data_or_file": ["POST"],
    "manage_files": ["POST"],
}
FUNCTION_CODE_ENV_MAP: Dict[str, List[str]] = {
    "add_new_data": ["FUNCTION_CODE_ADD_NEW_DATA", "FUNCTION_CODE_ADD_DATA"],
    "get_current_time": ["FUNCTION_CODE_GET_TIME"],
    "get_filtered_data": ["FUNCTION_CODE_GET_FILTERED_DATA", "FUNCTION_CODE_GET_DATA"],
    "list_blobs": ["FUNCTION_CODE_LIST_BLOBS"],
    "read_blob_file": ["FUNCTION_CODE_READ_BLOB_FILE", "FUNCTION_CODE_READ_BLOB"],
    "remove_data_entry": ["FUNCTION_CODE_REMOVE_DATA_ENTRY", "FUNCTION_CODE_REMOVE_DATA"],
    "update_data_entry": ["FUNCTION_CODE_UPDATE_DATA_ENTRY", "FUNCTION_CODE_UPDATE_DATA"],
    "upload_data_or_file": ["FUNCTION_CODE_UPLOAD_DATA_OR_FILE", "FUNCTION_CODE_UPLOAD"],
    "manage_files": ["FUNCTION_CODE_MANAGE_FILES"],
}

def _get_function_url(tool_name: str) -> str:
    if not FUNCTION_URL_BASE:
        return f"/api/{tool_name}"
    return f"{FUNCTION_URL_BASE}/api/{tool_name}"

def _get_function_methods(tool_name: str) -> List[str]:
    return FUNCTION_HTTP_METHODS.get(tool_name, ["POST"])

def _get_function_code(tool_name: str) -> str:
    for env_key in FUNCTION_CODE_ENV_MAP.get(tool_name, []):
        code_value = os.getenv(env_key, "").strip()
        if code_value:
            return code_value
    return ""


def _parse_scopes(req: func.HttpRequest) -> Set[str]:
    raw_scopes = (
        req.headers.get("X-OAuth-Scopes")
        or req.headers.get("X-OAuth-Scope")
        or req.headers.get("X-Scopes")
        or req.params.get("scopes")
        or ""
    )
    scopes: Set[str] = set()
    for chunk in raw_scopes.replace(",", " ").split():
        scope = chunk.strip()
        if scope:
            scopes.add(scope)
    return scopes


def _filter_tools_for_scopes(scopes: Set[str]) -> List[Dict[str, object]]:
    filtered_tools: List[Dict[str, object]] = []
    for tool in CUSTOM_GPT_TOOL_SCHEMAS:
        required_scopes = set(tool.get("required_scopes", []))
        if required_scopes and not required_scopes.issubset(scopes):
            continue
        filtered_tools.append(tool)
    return filtered_tools


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("custom_gpt_tools: Processing tool catalog request.")

    user_id = extract_user_id(req)
    start_time = log_request_start("custom_gpt_tools", user_id, endpoint="custom_gpt_tools")

    try:
        scopes = _parse_scopes(req)
        filtered_tools = _filter_tools_for_scopes(scopes)
        tools_payload = []
        for tool in filtered_tools:
            function_entry = {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "methods": _get_function_methods(tool["name"]),
                "code": _get_function_code(tool["name"]),
                "url": _get_function_url(tool["name"]),
            }
            tools_payload.append(
                {
                    "type": "function",
                    "function": function_entry,
                }
            )

        LocalLogger.log_to_file(
            function_name="custom_gpt_tools",
            action="catalog_request",
            status="success",
            user_id=user_id,
            metadata={
                "tool_count": len(tools_payload),
                "scopes_provided": sorted(scopes),
            },
        )

        log_request_end(
            function_name="custom_gpt_tools",
            start_time=start_time,
            user_id=user_id,
            status="success",
            metadata={"tool_count": len(tools_payload)},
        )

        response_data = {
            "status": "success",
            "tools": tools_payload,
            "count": len(tools_payload),
        }
        return func.HttpResponse(
            json.dumps(response_data, ensure_ascii=False),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as exc:
        logging.error(f"custom_gpt_tools: {exc}")
        LocalLogger.log_to_file(
            function_name="custom_gpt_tools",
            action="catalog_request",
            status="error",
            user_id=user_id,
            error=str(exc),
        )
        log_request_end(
            function_name="custom_gpt_tools",
            start_time=start_time,
            user_id=user_id,
            status="error",
            error=str(exc),
        )
        return func.HttpResponse(
            json.dumps({"error": f"Server error: {exc}"}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500,
        )
