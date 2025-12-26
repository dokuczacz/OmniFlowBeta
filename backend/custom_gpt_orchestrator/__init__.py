import json
import logging
import re
import time
from typing import Any, Dict, List

import azure.functions as func
import requests

from proxy_router import ACTION_MAP

ALLOWED_TOOLS = set(ACTION_MAP.keys())
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


def _normalize_tool_chain(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    tool_chain = data.get("tool_chain")
    if tool_chain is None:
        tool = data.get("tool")
        params = data.get("params", {})
        if tool is None:
            raise ValueError("Provide either tool_chain or tool")
        tool_chain = [{"tool": tool, "params": params}]
    elif data.get("tool") is not None:
        raise ValueError("Provide tool_chain or tool, not both")
    if not isinstance(tool_chain, list) or not tool_chain:
        raise ValueError("tool_chain must be a non-empty list")
    return tool_chain


def _validate_chain(tool_chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for idx, step in enumerate(tool_chain):
        if not isinstance(step, dict):
            raise ValueError(f"tool_chain[{idx}] must be an object")
        tool = step.get("tool")
        if not isinstance(tool, str) or not tool:
            raise ValueError(f"tool_chain[{idx}].tool must be a non-empty string")
        if ALLOWED_TOOLS and tool not in ALLOWED_TOOLS:
            raise ValueError(f"Unsupported tool '{tool}' in tool_chain")
        params = step.get("params", {})
        if params is None:
            step["params"] = {}
        elif not isinstance(params, dict):
            raise ValueError(f"tool_chain[{idx}].params must be an object")
    return tool_chain


def _call_direct(action: str, params: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    if action not in ACTION_MAP:
        raise RuntimeError(f"Unsupported action '{action}' for direct dispatch")
    endpoint = ACTION_MAP[action]
    url = endpoint["url"]
    code = endpoint["code"]
    headers = {"X-User-Id": user_id}
    if endpoint["method"] == "GET":
        query = {**params}
        if code:
            query["code"] = code
        response = requests.get(url, params=query, headers=headers, timeout=45)
    elif endpoint["method"] == "POST":
        full_url = f"{url}?code={code}" if code else url
        response = requests.post(full_url, json=params, headers=headers, timeout=45)
    else:
        raise RuntimeError(f"Unsupported method {endpoint['method']} for action {action}")
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
        tool_chain = _normalize_tool_chain(data)
        tool_chain = _validate_chain(tool_chain)
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

        params_with_user = {**resolved_params, "user_id": user_id}
        start_time = time.time()
        try:
            result = _call_direct(tool, params_with_user, user_id)
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
