import datetime
import json
import logging
import os
import time
from typing import Dict, Any, Tuple

import azure.functions as func
import requests
from openai import OpenAI, BadRequestError

# Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")
PROXY_URL = os.environ.get("AZURE_PROXY_URL", "")
PROXY_FUNCTION_KEY = os.environ.get("FUNCTION_CODE_PROXY_ROUTER", "")
ENABLE_SAVE_INTERACTION = os.environ.get("ENABLE_SAVE_INTERACTION", "false").lower() == "true"
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID", "")

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
        key = pop_first("key_to_find", "key", "find_key", "filter_key")
        if key:
            args["key_to_find"] = key
            args["filter_key"] = key
        value = pop_first("value_to_find", "value", "find_value", "filter_value")
        if value is not None:
            args["value_to_find"] = value
            args["filter_value"] = value

    elif tool_name == "add_new_data":
        target_blob_name = pop_first("target_blob_name", "file_name", "blob_name", "name")
        if target_blob_name:
            args["target_blob_name"] = target_blob_name
        new_entry = pop_first("new_entry", "entry", "data", "payload")
        if new_entry is not None:
            args["new_entry"] = _parse_json_if_str(new_entry)

    elif tool_name == "update_data_entry":
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
            args["user_message"] = user_message
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

    # Fallback: HTTP proxy_router
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
        resp = requests.post(PROXY_URL, json={"action": tool_name, "params": params_with_user}, headers=headers, timeout=45)
        resp.raise_for_status()
        try:
            result = resp.json()
        except ValueError:
            result = {"raw_response": resp.text}
        duration_ms = (time.time() - start_time) * 1000
        info = {"tool_name": tool_name, "arguments": normalized_args, "result": result, "status": "success", "duration_ms": duration_ms}
        logging.info(f"Tool {tool_name} OK via proxy_router in {duration_ms:.1f}ms")
        return json.dumps(result), info
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
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
        return func.HttpResponse(json.dumps({"error": "Invalid JSON payload"}), status_code=400, mimetype="application/json")

    user_message = body.get("message", "")
    user_id = body.get("user_id", "default")
    thread_id = body.get("thread_id")
    time_only = bool(body.get("time_only", False))

    if not user_message:
        return func.HttpResponse(json.dumps({"error": "Missing 'message' field"}), status_code=400, mimetype="application/json")

    # Fast path: local time only
    if time_only:
        current_time = datetime.datetime.utcnow().isoformat() + "Z"
        return func.HttpResponse(
            json.dumps({"status": "success", "response": current_time, "thread_id": thread_id, "user_id": user_id, "tool_calls_count": 0}),
            status_code=200,
            mimetype="application/json",
        )

    # Config check
    if not (OPENAI_API_KEY and ASSISTANT_ID and PROXY_URL):
        missing = []
        if not OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not ASSISTANT_ID:
            missing.append("OPENAI_ASSISTANT_ID")
        if not PROXY_URL:
            missing.append("AZURE_PROXY_URL")
        return func.HttpResponse(
            json.dumps({"error": f"Missing env vars: {', '.join(missing)}", "status": "not_configured"}),
            status_code=503,
            mimetype="application/json",
        )

    # OpenAI client
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=60.0, max_retries=2)
    except Exception as e:
        return func.HttpResponse(json.dumps({"error": f"Failed to init OpenAI: {e}"}), status_code=503, mimetype="application/json")

    try:
        request_start = time.time()
        all_tool_calls = []


        # Feature flag: only wait for open runs if DEBUG_WAIT_FOR_OPEN_RUNS is set
        DEBUG_WAIT_FOR_OPEN_RUNS = os.environ.get("DEBUG_WAIT_FOR_OPEN_RUNS", "false").lower() == "true"

        def wait_for_open_runs(th_id: str, max_wait_s: float = 6.0, interval_s: float = 0.5) -> bool:
            """Return True if thread is clear for new message, False if still blocked."""
            deadline = time.time() + max_wait_s
            while time.time() < deadline:
                runs = openai_client.beta.threads.runs.list(thread_id=th_id, limit=1)
                if not runs.data:
                    return True
                status = runs.data[0].status
                if status in ["in_progress", "queued", "requires_action"]:
                    time.sleep(interval_s)
                    continue
                return True
            return False

        # Thread
        if not thread_id:
            thread = openai_client.beta.threads.create()
            thread_id = thread.id
        else:
            if DEBUG_WAIT_FOR_OPEN_RUNS:
                # If previous run still active, wait briefly; if still blocked, start new thread
                if not wait_for_open_runs(thread_id):
                    logging.warning(f"Thread {thread_id} still has active run; starting new thread.")
                    thread = openai_client.beta.threads.create()
                    thread_id = thread.id
            # In normal flow, skip waiting and always try to add message

        # Add user message (retry once if blocked by active run)
        try:
            openai_client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
        except BadRequestError as e:
            if "run" in str(e) and "is active" in str(e):
                if wait_for_open_runs(thread_id):
                    openai_client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
                else:
                    logging.warning(f"Still blocked on thread {thread_id}, creating new thread for message.")
                    thread = openai_client.beta.threads.create()
                    thread_id = thread.id
                    openai_client.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_message)
            else:
                raise

        # Run
        run = None
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
                return func.HttpResponse(json.dumps({"error": str(run.last_error)}), status_code=500, mimetype="application/json")
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
                    return func.HttpResponse(json.dumps({"error": str(run.last_error)}), status_code=500, mimetype="application/json")
                # If still requires_action, continue loop (should be rare)
                continue
            # break if polling takes too long (fail fast)
            if (time.time() - poll_start) > max_poll_s:
                return func.HttpResponse(json.dumps({"error": "Polling timed out"}), status_code=504, mimetype="application/json")
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

        save_interaction_log(user_id, user_message, assistant_response, thread_id, all_tool_calls)

        total_ms = (time.time() - request_start) * 1000
        tools_ms = sum(call.get("duration_ms", 0) for call in all_tool_calls)

        return func.HttpResponse(
            json.dumps(
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
                ensure_ascii=False,
            ),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as e:
        logging.error(f"Critical error: {e}", exc_info=True)
        return func.HttpResponse(json.dumps({"error": str(e)}), status_code=500, mimetype="application/json")
