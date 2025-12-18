import datetime
import json
import logging
import os
import time
from typing import Dict, Any, Tuple

try:
    import azure.functions as func
    AZURE_FUNCTIONS_AVAILABLE = True
except ImportError:
    import types
    func = types.SimpleNamespace(HttpResponse=lambda *a, **kw: None)
    AZURE_FUNCTIONS_AVAILABLE = False
import requests
from openai import OpenAI

# Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")
PROXY_URL = os.environ.get("AZURE_PROXY_URL", "")
PROXY_FUNCTION_KEY = os.environ.get("FUNCTION_CODE_PROXY_ROUTER", "")
ENABLE_SAVE_INTERACTION = True  # Hardcoded to always enable saving for now
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID", "")
DEBUG_TOOL_CALL_HANDLER = os.environ.get("DEBUG_TOOL_CALL_HANDLER", "").lower() in ("1", "true", "yes")

logging.info("=== tool_call_handler CONFIG ===")
logging.info(f"OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}")
logging.info(f"OPENAI_ASSISTANT_ID set: {bool(ASSISTANT_ID)}")
logging.info(f"AZURE_PROXY_URL set: {bool(PROXY_URL)}")
logging.info(f"OPENAI_VECTOR_STORE_ID set: {bool(VECTOR_STORE_ID)}")
logging.info("=== END CONFIG ===")


def _parse_json_if_str(value: Any) -> Any:
    """If value is a JSON string, try to parse it; otherwise return as-is."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def normalize_tool_arguments(tool_name: str, tool_arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize arguments coming from the assistant tools to the proxy_router schema.
    """
    args = dict(tool_arguments or {})

    def pop_first(*keys):
        for k in keys:
            if k in args and args[k] not in [None, ""]:
                return args.pop(k)
        return None

    if tool_name == "read_blob_file":
        file_name = pop_first("file_name", "target_blob_name", "blob_name", "name")
        if file_name:
            if "/" in file_name:
                file_name = file_name.split("/")[-1]
            args["file_name"] = file_name

    elif tool_name == "get_filtered_data":
        target_blob_name = pop_first("target_blob_name", "file_name", "blob_name", "name")
        if target_blob_name:
            args["target_blob_name"] = target_blob_name
        find_key = pop_first("find_key", "key_to_find", "key", "match_key")
        if find_key:
            args["find_key"] = find_key
        find_value = pop_first("find_value", "value_to_find", "value", "match_value")
        if find_value is not None:
            args["find_value"] = find_value
        update_key = pop_first("update_key", "set_key")
        if update_key:
            args["update_key"] = update_key
        update_value = pop_first("update_value", "set_value")
        if update_value is not None:
            args["update_value"] = _parse_json_if_str(update_value)

    elif tool_name == "remove_data_entry":
        target_blob_name = pop_first("target_blob_name", "file_name", "blob_name", "name")
        if target_blob_name:
            args["target_blob_name"] = target_blob_name
        key_to_find = pop_first("key_to_find", "find_key", "key")
        if key_to_find:
            args["key_to_find"] = key_to_find
        value_to_find = pop_first("value_to_find", "find_value", "value")
        if value_to_find is not None:
            args["value_to_find"] = value_to_find

    elif tool_name == "upload_data_or_file":
        target_blob_name = pop_first("target_blob_name", "file_name", "blob_name", "name")
        if target_blob_name:
            args["target_blob_name"] = target_blob_name
        file_content = pop_first("file_content", "data", "content", "payload")
        if file_content is not None:
            args["file_content"] = _parse_json_if_str(file_content)

    elif tool_name == "manage_files":
        operation = pop_first("operation", "action", "op")
        if operation:
            args["operation"] = operation
        source_name = pop_first("source_name", "from", "src")
        if source_name:
            if "/" in source_name:
                source_name = source_name.split("/")[-1]
            args["source_name"] = source_name
        target_name = pop_first("target_name", "to", "dest", "destination")
        if target_name:
            if "/" in target_name:
                target_name = target_name.split("/")[-1]
            args["target_name"] = target_name
        prefix = pop_first("prefix")
        if prefix:
            args["prefix"] = prefix

    elif tool_name == "save_interaction":
        user_message = pop_first("user_message", "message")
        if user_message:
            # Add timestamp prefix
            from datetime import datetime
            timestamp = datetime.utcnow().isoformat()
            args["user_message"] = f"{timestamp};\n user: {user_message}"
        assistant_response = pop_first("assistant_response", "response")
        if assistant_response:
            args["assistant_response"] = assistant_response

    return args


def _safe_load_json(text: str) -> Dict[str, Any]:
    """
    Best-effort JSON loader for tool arguments. On failure, returns {} to avoid crashing the run.
    Tries to extract the first {...} block if extra data is present.
    """
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(text[start : end + 1])
        except Exception:
            pass
    logging.error(f"Failed to parse tool arguments as JSON: {text}")
    return {}


def _redact_sensitive(obj: Any) -> Any:
    """Redact common sensitive keys in dict-like objects for safe logging."""
    if not isinstance(obj, dict):
        return obj
    redacted = {}
    sensitive_keys = {"openai_api_key", "authorization", "api_key", "access_token", "x-functions-key", "code", "password"}
    for k, v in obj.items():
        if k and k.lower() in sensitive_keys:
            redacted[k] = "REDACTED"
        else:
            # avoid logging very large blobs
            try:
                if isinstance(v, (str, bytes)) and len(str(v)) > 1000:
                    redacted[k] = str(v)[:1000] + "...[truncated]"
                else:
                    redacted[k] = v
            except Exception:
                redacted[k] = "<unserializable>"
    return redacted


def _make_response(body: Any, status_code: int = 200):
    """Return a tuple (body, status, headers) which the Functions worker accepts for HTTP output."""
    if isinstance(body, (dict, list)):
        body_text = json.dumps(body, ensure_ascii=False)
    else:
        body_text = str(body)
    # When running under the Functions worker, return a proper HttpResponse
    if AZURE_FUNCTIONS_AVAILABLE:
        try:
            return func.HttpResponse(body_text, status_code=status_code, mimetype="application/json")
        except Exception:
            # Fallback to tuple if HttpResponse construction fails for some reason
            return body_text, status_code, {"Content-Type": "application/json"}
    return body_text, status_code, {"Content-Type": "application/json"}


def execute_tool_call(tool_name: str, tool_arguments: Dict[str, Any], user_id: str) -> Tuple[str, Dict[str, Any]]:
    """Call proxy_router for a given tool."""
    start_time = time.time()
    normalized_args = normalize_tool_arguments(tool_name, tool_arguments)
    params_with_user = {**(normalized_args or {}), "user_id": user_id}
    logging.debug(f"Dispatching tool={tool_name} with params={params_with_user}")

    # Try in-process dispatch first
    try:
        from tools import dispatch_tool
        result = dispatch_tool(tool_name, normalized_args, user_id)
        duration_ms = (time.time() - start_time) * 1000
        info = {"tool_name": tool_name, "arguments": normalized_args, "result": result, "status": "success", "duration_ms": duration_ms}
        logging.info(f"Tool {tool_name} OK in-process in {duration_ms:.1f}ms")
        return json.dumps(result), info
    except ImportError as e:
        logging.warning(f"tools module not available for in-process dispatch: {e}")
    except Exception as e:
        logging.warning(f"In-process dispatch failed for {tool_name}: {e}. Falling back to proxy_router.")
        # Only include required fields for each function (per DATA_EXTRACTION_FUNCTIONS_REFERENCE.md)
        DATA_EXTRACTION_REQUIRED = {
            "add_new_data": ["target_blob_name", "new_entry"],
            "get_filtered_data": ["target_blob_name", "filter_key", "filter_value"],
            "get_interaction_history": ["thread_id", "limit", "offset"],
            "list_blobs": ["prefix"],
            "manage_files": ["operation", "source_name", "target_name", "prefix"],
            "proxy_router": ["action", "params"],
            "read_blob_file": ["file_name"],
            "remove_data_entry": ["target_blob_name", "key_to_find", "value_to_find"],
            "save_interaction": ["user_message", "assistant_response", "thread_id", "tool_calls", "metadata"],
            "update_data_entry": ["target_blob_name", "find_key", "find_value", "update_key", "update_value"],
            "upload_data_or_file": ["target_blob_name", "file_content"],
        }

        # Only include user_id for tool_call_handler (if enforced)
        include_user_id = tool_name == "tool_call_handler"

        # Filter out user_id for all other functions
        if tool_name in DATA_EXTRACTION_REQUIRED:
            required_fields = DATA_EXTRACTION_REQUIRED[tool_name]
            filtered_args = {k: v for k, v in (normalized_args or {}).items() if k in required_fields and v is not None}
        else:
            filtered_args = dict(normalized_args or {})
        if include_user_id:
            filtered_args["user_id"] = user_id

        logging.debug(f"Dispatching tool={tool_name} with params={filtered_args}")
    headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
    if PROXY_FUNCTION_KEY:
        headers["x-functions-key"] = PROXY_FUNCTION_KEY

    # Hard validation for manage_files to avoid bad requests
    if tool_name == "manage_files":
        op = params_with_user.get("operation")
        src = params_with_user.get("source_name")
        tgt = params_with_user.get("target_name")
        if op is None:
            err = "manage_files requires 'operation' (rename/delete)"
            info = {"tool_name": tool_name, "arguments": normalized_args, "error": err, "status": "failed", "duration_ms": 0}
            return json.dumps({"error": err}), info
        if op not in ["rename", "delete"]:
            err = f"manage_files operation '{op}' is not supported. Use list_blobs for listing."
            info = {"tool_name": tool_name, "arguments": normalized_args, "error": err, "status": "failed", "duration_ms": 0}
            return json.dumps({"error": err}), info
        if not src:
            err = "manage_files requires 'source_name'"
            info = {"tool_name": tool_name, "arguments": normalized_args, "error": err, "status": "failed", "duration_ms": 0}
            return json.dumps({"error": err}), info
        if op == "rename" and not tgt:
            err = "manage_files rename requires 'target_name'"
            info = {"tool_name": tool_name, "arguments": normalized_args, "error": err, "status": "failed", "duration_ms": 0}
            return json.dumps({"error": err}), info

    try:
        # Some backend functions expect GET (e.g. get_interaction_history).
        # When calling via proxy_router we POST to the proxy, which may in turn POST
        # to the target function and cause a method mismatch. For known GET-style
        # endpoints, call the function URL directly with GET to preserve method.
        # Validate proxy configuration for POST-style dispatch
        if tool_name == "get_interaction_history":
            function_base = os.getenv("FUNCTION_URL_BASE", "http://localhost:7071").rstrip("/")
            func_url = f"{function_base}/api/{tool_name}"
            if DEBUG_TOOL_CALL_HANDLER:
                logging.info(f"[DEBUG] GET {func_url} params={_redact_sensitive(dict(params_with_user))} headers={_redact_sensitive(dict(headers))}")
            try:
                resp = requests.get(func_url, params=params_with_user, headers=headers, timeout=45)
                resp.raise_for_status()
                try:
                    result = resp.json()
                except ValueError:
                    result = {"raw_response": resp.text}
            except requests.RequestException as e:
                duration_ms = (time.time() - start_time) * 1000
                logging.warning(f"GET {func_url} failed: {e}")
                info = {"tool_name": tool_name, "arguments": normalized_args, "error": str(e), "status": "failed", "duration_ms": duration_ms}
                return json.dumps({"error": str(e)}), info
        else:
            if not PROXY_URL:
                err = "AZURE_PROXY_URL not configured"
                duration_ms = (time.time() - start_time) * 1000
                info = {"tool_name": tool_name, "arguments": normalized_args, "error": err, "status": "failed", "duration_ms": duration_ms}
                logging.error(err)
                return json.dumps({"error": err}), info
            payload = {"action": tool_name, "params": params_with_user}
            if DEBUG_TOOL_CALL_HANDLER:
                logging.info(f"[DEBUG] POST {PROXY_URL} json={_redact_sensitive(payload)} headers={_redact_sensitive(dict(headers))}")
            try:
                resp = requests.post(PROXY_URL, json=payload, headers=headers, timeout=45)
                resp.raise_for_status()
            except requests.RequestException as e:
                duration_ms = (time.time() - start_time) * 1000
                logging.warning(f"POST to proxy failed: {e}")
                info = {"tool_name": tool_name, "arguments": normalized_args, "error": str(e), "status": "failed", "duration_ms": duration_ms}
                # Include response body if available
                body_text = None
                try:
                    body_text = resp.text
                except Exception:
                    pass
                return json.dumps({"error": str(e), "proxy_body": (body_text or "")}), info
            try:
                parsed = resp.json()
            except ValueError:
                parsed = {"raw_response": resp.text}
            # Normalize non-dict responses
            if not isinstance(parsed, (dict, list)):
                parsed = {"raw": parsed}
            result = parsed
        if DEBUG_TOOL_CALL_HANDLER:
            try:
                body_snippet = result if isinstance(result, (dict, list)) else (resp.text[:2000] + "...[truncated]" if len(resp.text) > 2000 else resp.text)
            except Exception:
                body_snippet = "<unserializable>"
            logging.info(f"[DEBUG] Response status={getattr(resp, 'status_code', 'n/a')} body={_redact_sensitive(body_snippet if isinstance(body_snippet, dict) else {'raw': body_snippet})}")
        duration_ms = (time.time() - start_time) * 1000
        info = {"tool_name": tool_name, "arguments": normalized_args, "result": result, "status": "success", "duration_ms": duration_ms}
        logging.info(f"Tool {tool_name} OK via proxy_router in {duration_ms:.1f}ms")
        return json.dumps(result), info
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        if DEBUG_TOOL_CALL_HANDLER:
            logging.exception(f"Tool {tool_name} failed in {duration_ms:.1f}ms: {e}")
        else:
            logging.error(f"Tool {tool_name} failed in {duration_ms:.1f}ms: {e}")
        info = {"tool_name": tool_name, "arguments": normalized_args, "error": str(e), "status": "failed", "duration_ms": duration_ms}
        return json.dumps({"error": str(e)}), info

def save_interaction_log(user_id: str, user_message: str, assistant_response: str, thread_id: str, tool_calls_info: list):
    if not ENABLE_SAVE_INTERACTION:
        return
    try:
        base = os.getenv("FUNCTION_URL_BASE", "")
        code = os.getenv("FUNCTION_CODE_SAVE_INTERACTION", "")
        if not base or not code:
            return
        url = f"{base}/api/save_interaction?code={code}"
        payload = {
            "user_message": user_message,
            "assistant_response": assistant_response,
            "thread_id": thread_id,
            "tool_calls": tool_calls_info,
            "metadata": {"assistant_id": ASSISTANT_ID, "source": "tool_call_handler"},
        }
        headers = {"Content-Type": "application/json", "X-User-Id": user_id}
        requests.post(url, json=payload, headers=headers, timeout=10)
    except Exception as e:
        logging.warning(f"save_interaction_log failed: {e}")


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("=" * 60)
    logging.info("TOOL_CALL_HANDLER start")
    try:
        body = req.get_json()
    except Exception:
        return _make_response({"error": "Invalid JSON payload"}, status_code=400)

    user_message = body.get("message", "")
    user_id = body.get("user_id")  # Do not default to 'default' for save/get actions
    thread_id = body.get("thread_id")
    time_only = bool(body.get("time_only", False))
    action = body.get("action")
    params = body.get("params", {})

    # Config check (move here so it's always checked before main logic)
    if not (OPENAI_API_KEY and ASSISTANT_ID and PROXY_URL):
        missing = []
        if not OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not ASSISTANT_ID:
            missing.append("OPENAI_ASSISTANT_ID")
        if not PROXY_URL:
            missing.append("AZURE_PROXY_URL")
        return _make_response({"error": f"Missing env vars: {', '.join(missing)}", "status": "not_configured"}, status_code=503)

    # Direct save/get actions bypass agent
    if action in ["save_interaction", "get_interaction_history"]:
        # Enforce user_id presence
        user_message = body.get("message", "")
        user_id = body.get("user_id")  # Do not default to 'default' for save/get actions
        thread_id = body.get("thread_id")
        time_only = bool(body.get("time_only", False))
        action = body.get("action")
        params = body.get("params", {})
        if not user_id:
            return _make_response({"error": "user_id is required for save/get actions"}, status_code=400)
        headers = {"X-User-Id": str(user_id), "Content-Type": "application/json"}
        params = params if params is not None else {}
        # Build target function URL
        base = os.getenv("FUNCTION_URL_BASE", "http://localhost:7071").rstrip("/")
        url = f"{base}/api/{action}"
        # Pass through function key if present
        function_code_env = f"FUNCTION_CODE_{action.upper()}"
        function_code = os.getenv(function_code_env)
        if function_code:
            url = f"{url}?code={function_code}"
        resp = None
        try:
            if DEBUG_TOOL_CALL_HANDLER:
                logging.info(f"[DEBUG] Direct call {action} URL={url} params={_redact_sensitive(dict(params))} headers={_redact_sensitive(dict(headers))}")
            # Use GET for get_interaction_history, POST for save_interaction
            if action == "get_interaction_history":
                resp = requests.get(url, params=params, headers=headers, timeout=45)
            else:
                resp = requests.post(url, json=params, headers=headers, timeout=45)
            resp.raise_for_status()
            try:
                result = resp.json()
            except ValueError:
                result = {"raw_response": resp.text}
            if DEBUG_TOOL_CALL_HANDLER:
                try:
                    snippet = result if isinstance(result, (dict, list)) else (resp.text[:1000] + "...[truncated]" if len(resp.text) > 1000 else resp.text)
                except Exception:
                    snippet = "<unserializable>"
                logging.info(f"[DEBUG] Direct response status={resp.status_code} body={_redact_sensitive(snippet if isinstance(snippet, dict) else {'raw': snippet})}")
            return _make_response({"status": "success", "result": result}, status_code=resp.status_code)
        except requests.HTTPError as exc:
            if resp is not None:
                return _make_response(resp.text, status_code=resp.status_code)
            else:
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.exception(f"Direct {action} call failed: {exc}")
                return _make_response({"error": str(exc)}, status_code=500)

        # Run
        run = None
        all_tool_calls = []
        request_start = time.time()
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        if VECTOR_STORE_ID:
            try:
                run = openai_client.beta.threads.runs.create(
                    thread_id=thread_id,
                    assistant_id=ASSISTANT_ID,
                    tool_resources={"file_search": {"vector_store_ids": [VECTOR_STORE_ID]}},
                )
                logging.info(f"Vector store attached OK: tool_resources sent with vector_store_id={VECTOR_STORE_ID}")
            except TypeError:
                logging.warning("OpenAI client does not support tool_resources in runs.create; falling back without vector store.")
        if run is None:
            run = openai_client.beta.threads.runs.create(thread_id=thread_id, assistant_id=ASSISTANT_ID)
    
        # Remove static sleeps/backoff: poll as fast as possible until run is no longer actionable
        poll_start = time.time()
        max_poll_s = 30  # hard timeout for polling
        while True:
            run = openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run.status == "completed":
                break
            if run.status == "failed":
                return _make_response({"error": str(run.last_error)}, status_code=500)
            if run.status == "requires_action":
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                outputs = []
                for call in tool_calls:
                    name = call.function.name
                    args = _safe_load_json(call.function.arguments or "{}")
                    # map legacy manage_files(list) to list_blobs
                    if name == "manage_files" and args.get("operation") == "list":
                        name = "list_blobs"
                        args = {"prefix": args.get("prefix")}
                    result, info = execute_tool_call(name, args, user_id)
                    all_tool_calls.append(info)
                    outputs.append({"tool_call_id": call.id, "output": result})
                openai_client.beta.threads.runs.submit_tool_outputs(thread_id=thread_id, run_id=run.id, tool_outputs=outputs)
                # Immediately re-fetch run status after submitting tool outputs
                run = openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
                if run.status == "completed":
                    break
                if run.status == "failed":
                    return _make_response({"error": str(run.last_error)}, status_code=500)
                # If still requires_action, continue loop (should be rare)
                continue
            # break if polling takes too long (fail fast)
            if (time.time() - poll_start) > max_poll_s:
                return _make_response({"error": "Polling timed out"}, status_code=504)
            # minimal delay to avoid hammering API (e.g., 50ms)
            time.sleep(0.05)
    
        # Response
        messages = openai_client.beta.threads.messages.list(thread_id=thread_id)
        assistant_response = "No response from assistant."
        for msg in messages.data:
            if msg.role == "assistant":
                for content in msg.content:
                    if hasattr(content, "text"):
                        assistant_response = content.text.value
                        break
                if assistant_response:
                    break
    
        # Always save interaction history at the end, with all required fields
        save_interaction_log(
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_response,
            thread_id=thread_id,
            tool_calls_info=all_tool_calls
        )
    
        total_ms = (time.time() - request_start) * 1000
        tools_ms = sum(call.get("duration_ms", 0) for call in all_tool_calls)
    
        return _make_response(
            {
                "status": "success",
                "response": assistant_response,
                "thread_id": thread_id,
                "user_id": user_id,
                "tool_calls_count": len(all_tool_calls),
                "timings": {
                    "total_ms": total_ms,
                    "tools_ms": tools_ms,
                },
            },
            status_code=200,
        )
    # Note: exceptions will propagate for local debugging; the Functions worker
    # will catch and log them when running under the runtime.

