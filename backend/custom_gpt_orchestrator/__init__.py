import json
import logging
import os
import re
import time
from typing import Any, Dict, List

import azure.functions as func
import requests

PROXY_URL = os.environ.get("AZURE_PROXY_URL", "")
PROXY_FUNCTION_KEY = os.environ.get("FUNCTION_CODE_PROXY_ROUTER", "")

ALLOWED_TOOLS = {"list_blobs", "read_blob_file"}
PLACEHOLDER_PATTERN = re.compile(r"^\$prev\[(\d+)\](.*)$")
PATH_TOKEN_PATTERN = re.compile(r"(\.[A-Za-z0-9_\-]+|\[\d+\])")


def _make_response(body: Any, status_code: int = 200) -> func.HttpResponse:
    if isinstance(body, (dict, list)):
        payload = json.dumps(body, ensure_ascii=False)
    else:
        payload = str(body)
    return func.HttpResponse(payload, status_code=status_code, mimetype="application/json")


def _extract_user_id(req: func.HttpRequest, data: Dict[str, Any]) -> str:
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or (data or {}).get("user_id")
        or "default"
    )
    return str(user_id).strip() or "default"


def _resolve_path(value: Any, path: str) -> Any:
    if not path:
        return value
    tokens = PATH_TOKEN_PATTERN.findall(path)
    if "".join(tokens) != path:
        raise ValueError(f"Invalid placeholder path: {path}")
    current = value
    for token in tokens:
        if token.startswith("."):
            key = token[1:]
            if not isinstance(current, dict) or key not in current:
                raise ValueError(f"Missing key '{key}' in placeholder path")
            current = current[key]
        elif token.startswith("["):
            index = int(token[1:-1])
            if not isinstance(current, list) or index >= len(current):
                raise ValueError(f"Index {index} out of range in placeholder path")
            current = current[index]
    return current


def _resolve_placeholders(value: Any, previous_results: List[Any]) -> Any:
    if isinstance(value, str):
        match = PLACEHOLDER_PATTERN.match(value)
        if not match:
            return value
        index = int(match.group(1))
        if index >= len(previous_results):
            raise ValueError(f"Placeholder index {index} out of range")
        path = match.group(2) or ""
        return _resolve_path(previous_results[index], path)
    if isinstance(value, list):
        return [_resolve_placeholders(item, previous_results) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_placeholders(val, previous_results) for key, val in value.items()}
    return value


def _validate_chain(tool_chain: Any) -> List[Dict[str, Any]]:
    if not isinstance(tool_chain, list) or not tool_chain:
        raise ValueError("tool_chain must be a non-empty list")
    if len(tool_chain) < 2:
        raise ValueError("tool_chain must include at least list_blobs and read_blob_file")
    for idx, step in enumerate(tool_chain):
        if not isinstance(step, dict):
            raise ValueError(f"tool_chain[{idx}] must be an object")
        tool = step.get("tool")
        if not isinstance(tool, str) or not tool:
            raise ValueError(f"tool_chain[{idx}].tool must be a non-empty string")
        if tool not in ALLOWED_TOOLS:
            raise ValueError(f"Unsupported tool '{tool}' in tool_chain")
        if idx == 0 and tool != "list_blobs":
            raise ValueError("First tool must be list_blobs")
        if idx > 0 and tool != "read_blob_file":
            raise ValueError("Only read_blob_file can follow list_blobs in the tool_chain")
        params = step.get("params", {})
        if params is None:
            step["params"] = {}
        elif not isinstance(params, dict):
            raise ValueError(f"tool_chain[{idx}].params must be an object")
    return tool_chain


def _call_proxy(action: str, params: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    if not PROXY_URL:
        raise RuntimeError("AZURE_PROXY_URL not configured")
    headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
    if PROXY_FUNCTION_KEY:
        headers["x-functions-key"] = PROXY_FUNCTION_KEY
    payload = {"action": action, "params": params}
    response = requests.post(PROXY_URL, json=payload, headers=headers, timeout=45)
    try:
        body = response.json()
    except ValueError:
        body = {"raw_response": response.text}
    return {
        "status_code": response.status_code,
        "body": body,
    }


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("custom_gpt_orchestrator triggered")
    try:
        data = req.get_json()
    except ValueError:
        return _make_response({"error": "Invalid JSON payload"}, status_code=400)

    user_id = _extract_user_id(req, data)
    try:
        tool_chain = _validate_chain(data.get("tool_chain"))
    except ValueError as exc:
        return _make_response({"error": str(exc), "user_id": user_id}, status_code=400)

    trace: List[Dict[str, Any]] = []
    previous_results: List[Any] = []

    for index, step in enumerate(tool_chain):
        tool = step["tool"]
        try:
            resolved_params = _resolve_placeholders(step.get("params", {}), previous_results)
        except ValueError as exc:
            return _make_response({
                "error": str(exc),
                "user_id": user_id,
                "trace": trace,
            }, status_code=400)

        if tool == "read_blob_file" and not resolved_params.get("file_name"):
            return _make_response({
                "error": "read_blob_file requires file_name",
                "user_id": user_id,
                "trace": trace,
            }, status_code=400)

        params_with_user = {**resolved_params, "user_id": user_id}
        start_time = time.time()
        try:
            result = _call_proxy(tool, params_with_user, user_id)
        except Exception as exc:
            trace.append({
                "step": index,
                "tool": tool,
                "params": resolved_params,
                "status": "failed",
                "error": str(exc),
                "duration_ms": (time.time() - start_time) * 1000,
            })
            return _make_response({
                "status": "failed",
                "user_id": user_id,
                "error": str(exc),
                "trace": trace,
            }, status_code=500)

        duration_ms = (time.time() - start_time) * 1000
        step_entry = {
            "step": index,
            "tool": tool,
            "params": resolved_params,
            "status_code": result["status_code"],
            "duration_ms": duration_ms,
            "response": result["body"],
        }
        trace.append(step_entry)

        if result["status_code"] >= 400:
            return _make_response({
                "status": "failed",
                "user_id": user_id,
                "error": "Downstream tool call failed",
                "downstream_response": result["body"],
                "trace": trace,
            }, status_code=result["status_code"])

        previous_results.append(result["body"])

    final_result = previous_results[-1] if previous_results else None
    return _make_response({
        "status": "success",
        "user_id": user_id,
        "result": final_result,
        "trace": trace,
    })
