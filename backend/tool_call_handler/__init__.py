import datetime
import json
import logging
import os
import sys
import time
from typing import Dict, Any, Tuple
import uuid

try:
    import azure.functions as func
    AZURE_FUNCTIONS_AVAILABLE = True
except ImportError:
    import types as _types
    # Minimal fallback shim so annotations and simple usages don't fail when
    # `azure.functions` is not available in the local environment.
    class _DummyHttpRequest:
        def __init__(self, *a, **kw):
            self.headers = {}
            self.params = {}
        def get_json(self):
            return {}

    func = _types.SimpleNamespace(HttpResponse=lambda *a, **kw: None, HttpRequest=_DummyHttpRequest)
    AZURE_FUNCTIONS_AVAILABLE = False
import requests
import threading
from openai import OpenAI
import inspect
from types import SimpleNamespace
import types as _types
import threading
import random

# Allow importing shared helpers when running as a Functions app or locally
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from shared.file_logger import attach_file_handler, detach_file_handler
except Exception:
    # Best-effort import; if it fails, we will continue without file logging
    attach_file_handler = None
    detach_file_handler = None

# Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")
OPENAI_PROMPT_ID = os.environ.get("OPENAI_PROMPT_ID", "")
LLM_RUNTIME_DEFAULT = os.environ.get("LLM_RUNTIME", "assistants")
HANDLES_CACHE_TTL_SECONDS = int(os.environ.get("HANDLES_CACHE_TTL_SECONDS", "60") or 60)
PROXY_URL = os.environ.get("AZURE_PROXY_URL", "")
PROXY_FUNCTION_KEY = os.environ.get("FUNCTION_CODE_PROXY_ROUTER", "")
ENABLE_SAVE_INTERACTION = True  # Hardcoded to always enable saving for now
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID", "")
DEBUG_TOOL_CALL_HANDLER = os.environ.get("DEBUG_TOOL_CALL_HANDLER", "").lower() in ("1", "true", "yes")
OPENAI_MAX_REQUESTS = int(os.environ.get("OPENAI_MAX_REQUESTS", "0") or 0)
# runtime counter for outbound OpenAI HTTP calls (best-effort)
_openai_lock = threading.Lock()
_openai_count = 0
_handles_cache: Dict[str, Dict[str, Any]] = {}

# Optional global (cross-process) limit for tests. If set (>0), this will be
# enforced by a simple file-based counter in `backend/logs/openai_global_counter.json`.
OPENAI_GLOBAL_MAX_REQUESTS = int(os.environ.get("OPENAI_GLOBAL_MAX_REQUESTS", "0") or 0)
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLOBAL_COUNTER_PATH = os.path.join(BACKEND_ROOT, "logs", "openai_global_counter.json")
GLOBAL_LOCK_PATH = GLOBAL_COUNTER_PATH + ".lock"

def _acquire_file_lock(lock_path, timeout=10.0):
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            if (time.time() - start) > timeout:
                raise RuntimeError("Timeout acquiring lock")
            time.sleep(0.05)

def _release_file_lock(lock_path):
    try:
        os.remove(lock_path)
    except Exception:
        pass

def _global_openai_call(fn, *args, **kwargs):
    """Enforce a cross-process global request counter for OpenAI calls.
    This uses a file-based counter with a lock; intended only for local testing.
    """
    if OPENAI_GLOBAL_MAX_REQUESTS <= 0:
        return fn(*args, **kwargs)
    # ensure logs dir exists
    try:
        os.makedirs(os.path.dirname(GLOBAL_COUNTER_PATH), exist_ok=True)
    except Exception:
        pass
    # acquire lock
    _acquire_file_lock(GLOBAL_LOCK_PATH, timeout=10.0)
    try:
        if os.path.exists(GLOBAL_COUNTER_PATH):
            try:
                with open(GLOBAL_COUNTER_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {"count": 0}
        else:
            data = {"count": 0}
        if data.get("count", 0) >= OPENAI_GLOBAL_MAX_REQUESTS:
            raise RuntimeError(f"OPENAI_GLOBAL_MAX_REQUESTS limit reached ({OPENAI_GLOBAL_MAX_REQUESTS})")
        data["count"] = data.get("count", 0) + 1
        try:
            with open(GLOBAL_COUNTER_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass
    finally:
        _release_file_lock(GLOBAL_LOCK_PATH)
    return fn(*args, **kwargs)

def _openai_call(fn, *args, **kwargs):
    """Call an OpenAI SDK function but enforce an optional max-requests limit.
    If `OPENAI_MAX_REQUESTS` is 0, no limit is enforced. After the limit is
    reached, raise RuntimeError to stop further network calls.
    """
    global _openai_count
    # If a global cross-process limit is configured, use that wrapper.
    if OPENAI_GLOBAL_MAX_REQUESTS > 0:
        return _global_openai_call(fn, *args, **kwargs)
    if OPENAI_MAX_REQUESTS <= 0:
        return fn(*args, **kwargs)
    with _openai_lock:
        if _openai_count >= OPENAI_MAX_REQUESTS:
            raise RuntimeError(f"OPENAI_MAX_REQUESTS limit reached ({OPENAI_MAX_REQUESTS})")
        _openai_count += 1
    return fn(*args, **kwargs)

logging.info("=== tool_call_handler CONFIG ===")
logging.info(f"OPENAI_API_KEY set: {bool(OPENAI_API_KEY)}")
logging.info(f"OPENAI_ASSISTANT_ID set: {bool(ASSISTANT_ID)}")
logging.info(f"OPENAI_PROMPT_ID set: {bool(OPENAI_PROMPT_ID)}")
logging.info(f"LLM_RUNTIME default: {LLM_RUNTIME_DEFAULT}")
logging.info(f"HANDLES_CACHE_TTL_SECONDS: {HANDLES_CACHE_TTL_SECONDS}")
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
            args["filter_key"] = find_key
        find_value = pop_first("find_value", "value_to_find", "value", "match_value")
        if find_value is not None:
            args["filter_value"] = find_value
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


def _supports_tool_resources(openai_client: OpenAI) -> bool:
    """Return True if the OpenAI client appears to support the `tool_resources` parameter
    on `beta.threads.runs.create`. Uses introspection to avoid making a network call.
    Falls back to conservative False on any error.
    """
    try:
        create_fn = getattr(openai_client.beta.threads.runs, "create", None)
        if create_fn is None:
            return False
        sig = inspect.signature(create_fn)
        # Parameters may include **kwargs; prefer explicit 'tool_resources' if present
        if "tool_resources" in sig.parameters:
            return True
        # If **kwargs present, assume it may accept tool_resources at runtime
        for p in sig.parameters.values():
            if p.kind == inspect.Parameter.VAR_KEYWORD:
                return True
        return False
    except Exception:
        return False


def resolve_user_id(req, body: Dict[str, Any]) -> Tuple[Any, str]:
    """Resolve user_id from request headers, then body, then query params.
    Returns (user_id, source) where source is one of 'header', 'body', 'params', or 'none'.
    """
    try:
        # Header priority
        if req is not None:
            try:
                hdrs = getattr(req, 'headers', None) or {}
                # Support both capitalized and lowercase keys
                for hk in ('X-User-Id', 'x-user-id', 'X-User-Id'.lower()):
                    if isinstance(hdrs, dict) and hk in hdrs and hdrs.get(hk):
                        return str(hdrs.get(hk)), 'header'
                    # Some HttpRequest implementations use a case-insensitive mapping
                # Fallback: try get with case-insensitive search
                if isinstance(hdrs, dict):
                    for k, v in hdrs.items():
                        if k and k.lower() == 'x-user-id' and v:
                            return str(v), 'header'
            except Exception:
                pass
        # Body
        if isinstance(body, dict) and body.get('user_id'):
            return body.get('user_id'), 'body'
        # Query params on the request object
        try:
            params = getattr(req, 'params', None) or {}
            if isinstance(params, dict) and params.get('user_id'):
                return params.get('user_id'), 'params'
        except Exception:
            pass
    except Exception:
        pass
    return (None, 'none')


def resolve_runtime(body: Dict[str, Any]) -> str:
    """Resolve requested runtime from request body or env default."""
    runtime = (body or {}).get("runtime") or LLM_RUNTIME_DEFAULT or "assistants"
    runtime = str(runtime).strip().lower()
    if runtime not in ("assistants", "responses", "auto"):
        raise ValueError("Invalid runtime. Allowed: assistants|responses|auto")
    return runtime


def _missing_env_vars_for_runtime(runtime: str) -> list:
    runtime = (runtime or "").strip().lower()
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not PROXY_URL:
        missing.append("AZURE_PROXY_URL")
    if runtime == "assistants":
        if not ASSISTANT_ID:
            missing.append("OPENAI_ASSISTANT_ID")
    elif runtime == "responses":
        if not OPENAI_PROMPT_ID:
            missing.append("OPENAI_PROMPT_ID")
    return missing


def _load_handles(user_id: str) -> Dict[str, Any]:
    """Load `handles.json` from the user's blob namespace (best-effort)."""
    if HANDLES_CACHE_TTL_SECONDS > 0:
        cached = _handles_cache.get(str(user_id))
        if cached:
            age = time.time() - cached.get("ts", 0)
            if age <= HANDLES_CACHE_TTL_SECONDS:
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.info(f"[DEBUG] handles cache hit user_id={user_id} age_s={age:.2f}")
                return cached.get("data", {}) or {}
            if DEBUG_TOOL_CALL_HANDLER:
                logging.info(f"[DEBUG] handles cache expired user_id={user_id} age_s={age:.2f}")
        elif DEBUG_TOOL_CALL_HANDLER:
            logging.info(f"[DEBUG] handles cache miss user_id={user_id}")
    elif DEBUG_TOOL_CALL_HANDLER:
        logging.info("[DEBUG] handles cache disabled (TTL=0)")
    try:
        result_str, _info = execute_tool_call("read_blob_file", {"file_name": "handles.json"}, user_id)
        payload = json.loads(result_str) if isinstance(result_str, str) else {}
        if isinstance(payload, dict) and payload.get("status") == "success":
            data = payload.get("data")
            if isinstance(data, dict):
                if HANDLES_CACHE_TTL_SECONDS > 0:
                    _handles_cache[str(user_id)] = {"data": data, "ts": time.time()}
                    if DEBUG_TOOL_CALL_HANDLER:
                        logging.info(f"[DEBUG] handles cache set user_id={user_id} entries={len(data)}")
                return data
            if isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        if HANDLES_CACHE_TTL_SECONDS > 0:
                            _handles_cache[str(user_id)] = {"data": parsed, "ts": time.time()}
                            if DEBUG_TOOL_CALL_HANDLER:
                                logging.info(f"[DEBUG] handles cache set user_id={user_id} entries={len(parsed)}")
                        return parsed
                except Exception:
                    return {}
        if isinstance(payload, dict) and payload.get("error"):
            error_text = str(payload.get("error") or "")
            if "not found" in error_text.lower() or "blobnotfound" in error_text.lower():
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.info(f"[DEBUG] handles.json missing; initializing user_id={user_id}")
                _save_handles(user_id, {}, async_save=True)
        return {}
    except Exception:
        return {}


def _save_handles(user_id: str, handles: Dict[str, Any], async_save: bool = False) -> None:
    """Persist `handles.json` to the user's blob namespace (best-effort)."""
    def _do_save():
        try:
            execute_tool_call(
                "upload_data_or_file",
                {"target_blob_name": "handles.json", "file_content": handles or {}},
                user_id,
            )
            if HANDLES_CACHE_TTL_SECONDS > 0:
                _handles_cache[str(user_id)] = {"data": handles or {}, "ts": time.time()}
            if DEBUG_TOOL_CALL_HANDLER:
                logging.info(f"[DEBUG] handles async save done user_id={user_id}")
        except Exception as exc:
            if DEBUG_TOOL_CALL_HANDLER:
                logging.info(f"[DEBUG] handles async save failed user_id={user_id} error={exc}")

    if async_save:
        if DEBUG_TOOL_CALL_HANDLER:
            logging.info(f"[DEBUG] handles async save queued user_id={user_id}")
        threading.Thread(target=_do_save, daemon=True).start()
        return

    try:
        _do_save()
    except Exception:
        pass


def _extract_response_function_calls(response: Any) -> list:
    calls = []
    for item in (getattr(response, "output", None) or []):
        item_type = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
        if item_type != "function_call":
            continue
        call_id = item.get("call_id") if isinstance(item, dict) else getattr(item, "call_id", None)
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
        arguments = item.get("arguments") if isinstance(item, dict) else getattr(item, "arguments", None)
        if call_id and name:
            calls.append({"call_id": str(call_id), "name": str(name), "arguments": str(arguments or "")})
    return calls


def _coerce_conversation_id(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("id", "conversation_id"):
            if value.get(key):
                return str(value.get(key))
    # Last resort: stringify object (may already be a typed mapping)
    try:
        return str(value)
    except Exception:
        return ""


def run_responses(openai_client: OpenAI, user_id: str, user_message: str, thread_id: str) -> Tuple[str, list, Dict[str, Any], str]:
    """Responses API deterministic tool loop using a Prompt ID (dual-runtime mode)."""
    if not thread_id:
        thread_id = f"handle_{uuid.uuid4().hex[:12]}"

    handles = _load_handles(user_id)
    state = handles.get(thread_id, {}) if isinstance(handles, dict) else {}

    conversation_id = _coerce_conversation_id(state.get("responses_conversation_id"))
    previous_response_id = str(state.get("responses_last_response_id") or "").strip()

    all_tool_calls = []
    current_input: Any = user_message or ""
    retried_without_previous = False

    for _ in range(25):
        create_kwargs: Dict[str, Any] = {
            "prompt": {"id": OPENAI_PROMPT_ID},
            "input": current_input,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            "metadata": {"user_id": str(user_id), "thread_id": str(thread_id), "runtime": "responses"},
        }
        if conversation_id:
            create_kwargs["conversation"] = conversation_id
        if previous_response_id:
            create_kwargs["previous_response_id"] = previous_response_id

        try:
            response = _openai_call(openai_client.responses.create, **create_kwargs)
        except Exception as exc:
            # If the last persisted `previous_response_id` points to a response that had pending tool calls
            # (e.g., crash before tool outputs were submitted), OpenAI rejects new input with:
            # "No tool output found for function call call_...". We can safely self-heal by retrying once
            # without previous_response_id (conversation id may still be kept).
            msg = str(exc)
            if (
                (not retried_without_previous)
                and previous_response_id
                and isinstance(current_input, (str, bytes))
                and ("No tool output found for function call" in msg)
            ):
                retried_without_previous = True
                logging.warning(
                    "Responses loop detected pending tool-call state for previous_response_id; retrying without previous_response_id "
                    f"user_id={user_id} thread_id={thread_id}"
                )
                previous_response_id = ""
                # Best-effort: clear persisted last_response_id to avoid repeated failures on next calls.
                try:
                    if isinstance(handles, dict):
                        handles[thread_id] = {
                            **(state if isinstance(state, dict) else {}),
                            "responses_conversation_id": conversation_id,
                            "responses_last_response_id": "",
                            "active_runtime": "responses",
                            "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
                        }
                        _save_handles(user_id, handles, async_save=True)
                except Exception:
                    pass
                continue
            raise
        previous_response_id = str(getattr(response, "id", "") or previous_response_id)
        conversation_id = _coerce_conversation_id(getattr(response, "conversation", None) or conversation_id)

        function_calls = _extract_response_function_calls(response)
        if not function_calls:
            final_text = getattr(response, "output_text", None) or ""
            if not final_text:
                final_text = "No response from assistant."
            meta = {"responses_conversation_id": conversation_id, "responses_last_response_id": previous_response_id}
            # Persist only after reaching a "final" response to avoid saving a response id with pending tool calls.
            try:
                if isinstance(handles, dict):
                    handles[thread_id] = {
                        **(state if isinstance(state, dict) else {}),
                        "responses_conversation_id": conversation_id,
                        "responses_last_response_id": previous_response_id,
                        "active_runtime": "responses",
                        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
                    }
                    _save_handles(user_id, handles, async_save=True)
            except Exception:
                pass
            return final_text, all_tool_calls, meta, thread_id

        tool_outputs = []
        for call in function_calls:
            name = call.get("name") or ""
            args = _safe_load_json(call.get("arguments") or "")
            result_str, info = execute_tool_call(name, args, user_id)
            info = dict(info or {})
            info["call_id"] = call.get("call_id")
            info["runtime"] = "responses"
            all_tool_calls.append(info)
            tool_outputs.append(
                {"type": "function_call_output", "call_id": call.get("call_id"), "output": str(result_str)}
            )

        current_input = tool_outputs

    raise RuntimeError("Responses tool loop exceeded max iterations")


def restore_or_create_thread(openai_client: OpenAI, user_id: str, thread_id: str) -> str:
    """Attempt to restore a thread_id for the user from blob storage; if not found,
    create a new thread via the OpenAI SDK or REST fallback. Returns thread_id.
    Raises RuntimeError on unrecoverable failure.
    """
    # Try restore from blob storage if no thread_id provided
    if thread_id:
        return thread_id
    try:
        if user_id:
            logging.info(f"Attempting to restore thread_id for user {user_id} from blob")
            try:
                from backend.read_blob_file import main as read_blob_main

                class _Req:
                    def __init__(self, file_name, user_id):
                        self.headers = {"x-user-id": str(user_id)}
                        self.params = {"file_name": file_name}

                    def get_json(self):
                        return {"user_id": str(user_id), "file_name": file_name}

                req_obj = _Req("current_thread.json", user_id)
                resp = read_blob_main(req_obj)
                try:
                    resp_text = resp.get_body() if hasattr(resp, 'get_body') else getattr(resp, 'body', None)
                except Exception:
                    resp_text = getattr(resp, 'body', None)
                try:
                    res = json.loads(resp_text) if isinstance(resp_text, (str, bytes)) else resp_text
                except Exception:
                    res = resp_text
            except Exception:
                # Fall back to the generic execute_tool_call which may proxy
                res_str, info = execute_tool_call("read_blob_file", {"file_name": "current_thread.json"}, user_id)
                try:
                    res = json.loads(res_str) if isinstance(res_str, str) else res_str
                except Exception:
                    res = res_str
            # Normalize and extract thread id
            tid = None
            if isinstance(res, dict):
                data = res.get('data')
                if isinstance(data, dict) and 'thread_id' in data:
                    tid = data.get('thread_id')
            if tid:
                logging.info(f"Restored thread_id={tid} from blob for user {user_id}")
                return tid
            logging.info("No valid thread id found in current_thread.json; attempting fallback to interaction_logs.json")
            # Fallback: try to recover last thread_id from interaction_logs.json
            try:
                res_str, info = execute_tool_call("read_blob_file", {"file_name": "interaction_logs.json"}, user_id)
                try:
                    rb = json.loads(res_str) if isinstance(res_str, str) else res_str
                except Exception:
                    rb = res_str
                candidate = None
                if isinstance(rb, dict) and 'data' in rb:
                    data_blob = rb.get('data')
                    try:
                        candidate = json.loads(data_blob) if isinstance(data_blob, str) else data_blob
                    except Exception:
                        candidate = data_blob
                elif isinstance(rb, (list, dict)):
                    candidate = rb
                recovered = None
                if isinstance(candidate, list) and len(candidate) > 0:
                    for entry in reversed(candidate):
                        try:
                            if isinstance(entry, dict) and 'thread_id' in entry and entry.get('thread_id'):
                                recovered = entry.get('thread_id')
                                break
                        except Exception:
                            continue
                elif isinstance(candidate, dict) and candidate.get('thread_id'):
                    recovered = candidate.get('thread_id')
                if recovered:
                    logging.info(f"Recovered thread_id={recovered} from interaction_logs.json for user {user_id}")
                    return recovered
                logging.info("No thread_id found in interaction_logs.json; will create new thread")
            except Exception as fb_ex:
                logging.info(f"Fallback restore from interaction_logs.json failed: {fb_ex}")
    except Exception as e:
        logging.info(f"Restore from blob failed or no file present: {e}")

    logging.info("No thread_id provided; attempting to create a new thread via OpenAI SDK")
    # Create via SDK (simplified single path)
    try:
        created = _openai_call(openai_client.beta.threads.create)
        thread_id = getattr(created, "id", None) or getattr(created, "thread_id", None)
        if not thread_id and isinstance(created, dict):
            thread_id = created.get("id") or created.get("thread_id")
        if not thread_id:
            logging.warning(f"SDK thread create returned unexpected payload: {type(created)}")
            raise RuntimeError("SDK thread creation returned no thread id")
        logging.info(f"Created new thread_id={thread_id} via SDK")
        # Persist the new thread id to blob storage for future restores
        try:
            if user_id:
                logging.info(f"Saving new thread_id for user {user_id} to blob")
                payload = {"thread_id": thread_id}
                execute_tool_call("upload_data_or_file", {"target_blob_name": "current_thread.json", "file_content": json.dumps(payload)}, user_id)
        except Exception:
            logging.warning("Failed to persist new thread id to blob storage")
        return thread_id
    except Exception as sdk_exc:
        logging.warning(f"SDK-based thread creation failed: {sdk_exc}; falling back to REST create")
        # REST fallback
        try:
            openai_api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com").rstrip("/")
            create_url = f"{openai_api_base}/v1/beta/threads"
            headers = _openai_rest_headers()
            payload = {"assistant_id": ASSISTANT_ID}
            try:
                use_rest_tr = os.environ.get("OPENAI_USE_REST_TOOLRESOURCES", "").lower() in ("1", "true", "yes")
            except Exception:
                use_rest_tr = False
            if use_rest_tr and VECTOR_STORE_ID:
                payload["tool_resources"] = {"vector_store": VECTOR_STORE_ID}
            resp = requests.post(create_url, json=payload, headers=headers, timeout=15)
            try:
                resp.raise_for_status()
            except requests.RequestException as exc:
                body_snip = (resp.text[:1000] + "...[truncated]") if hasattr(resp, "text") else ""
                logging.warning(f"Thread creation REST call failed: {exc} status={getattr(resp, 'status_code', 'n/a')} body={body_snip}")
                raise RuntimeError("failed to create thread")
            try:
                thread_json = resp.json()
            except ValueError:
                raise RuntimeError("invalid response creating thread")
            thread_id = thread_json.get("id") or thread_json.get("thread_id")
            if not thread_id:
                raise RuntimeError("thread creation returned no id")
            logging.info(f"Created new thread_id={thread_id} via REST")
            try:
                if user_id:
                    logging.info(f"Saving new thread_id for user {user_id} to blob (REST-created)")
                    payload = {"thread_id": thread_id}
                    execute_tool_call("upload_data_or_file", {"target_blob_name": "current_thread.json", "file_content": json.dumps(payload)}, user_id)
            except Exception:
                logging.warning("Failed to persist new thread id to blob storage (REST-created)")
            return thread_id
        except Exception as e:
            logging.exception(f"Unexpected error while creating thread via REST: {e}")
            raise RuntimeError(f"failed to create thread: {e}")


def append_user_message(openai_client: OpenAI, thread_id: str, user_message: str):
    """Append user's message to the given thread. Uses SDK when possible, otherwise REST fallback."""
    if not user_message:
        return
    try:
        logging.info(f"Posting user message to thread {thread_id} via SDK")
        _openai_call(
            openai_client.beta.threads.messages.create,
            thread_id=thread_id,
            role="user",
            content=[{"type": "text", "text": user_message}],
        )
    except Exception as msg_sdk_exc:
        try:
            logging.info(f"SDK message create failed ({msg_sdk_exc}); falling back to REST POST for thread {thread_id}")
            openai_api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com").rstrip("/")
            candidate_urls = [
                f"{openai_api_base}/v1/threads/{thread_id}/messages",
                f"{openai_api_base}/v1/beta/threads/{thread_id}/messages",
            ]
            headers = _openai_rest_headers()
            payload = {"role": "user", "content": [{"type": "text", "text": user_message}]}
            resp_msg = None
            success = False
            for msg_url in candidate_urls:
                try:
                    if DEBUG_TOOL_CALL_HANDLER:
                        logging.info(f"[DEBUG] REST POST {msg_url} headers={_redact_sensitive(dict(headers))} payload={_redact_sensitive(payload)}")
                    resp_msg = requests.post(msg_url, json=payload, headers=headers, timeout=10)
                    resp_msg.raise_for_status()
                    logging.info(f"Posted user message to thread {thread_id} via REST; status={resp_msg.status_code} url={msg_url}")
                    success = True
                    break
                except requests.RequestException as rme:
                    try:
                        body_text = resp_msg.text[:1000] if resp_msg is not None and hasattr(resp_msg, 'text') else ''
                    except Exception:
                        body_text = '<unserializable>'
                    logging.warning(
                        f"Failed to POST message to thread {thread_id} via REST: status={getattr(resp_msg, 'status_code', 'n/a')} url={msg_url} error={rme} body={body_text} headers={_redact_sensitive(dict(headers))} payload_trunc={_redact_sensitive(payload)}"
                    )
            if not success:
                logging.warning(f"REST fallback for posting message failed for all candidate URLs for thread {thread_id}")
        except Exception as rest_exc:
            logging.warning(f"REST fallback for posting message failed: {rest_exc}")


def handle_direct_actions(req, body: Dict[str, Any], action: str, user_id: str):
    """Handle direct actions `save_interaction` and `get_interaction_history`.
    Returns an _make_response(...) tuple if handled, otherwise None.
    """
    # Enforce user_id presence
    user_message = body.get("message", "")
    user_id_local = user_id
    thread_id = body.get("thread_id")
    params = body.get("params", {}) or {}
    if not user_id_local:
        return _make_response({"error": "user_id is required for save/get actions"}, status_code=400)
    headers = {"X-User-Id": str(user_id_local), "Content-Type": "application/json"}
    base = os.getenv("FUNCTION_URL_BASE", "http://localhost:7071").rstrip("/")
    url = f"{base}/api/{action}"
    function_code_env = f"FUNCTION_CODE_{action.upper()}"
    function_code = os.getenv(function_code_env)
    if function_code:
        url = f"{url}?code={function_code}"
    try:
        if DEBUG_TOOL_CALL_HANDLER:
            logging.info(f"[DEBUG] Direct call {action} URL={url} params={_redact_sensitive(dict(params))} headers={_redact_sensitive(dict(headers))}")
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


def create_run_and_poll(openai_client: OpenAI, thread_id: str, user_id: str):
    """Create a run and poll until completion. Returns (run, all_tool_calls, tool_outputs_struct, run_summary).
    Raises exceptions on unrecoverable failures.
    """
    run = None
    all_tool_calls = []
    tool_outputs_struct = []
    run_summary = {"timestamps": {}, "steps": []}

    # Create a normal run (no tool_resources attachment)
    try:
        try:
            run = _openai_call(openai_client.beta.threads.runs.create, thread_id=thread_id, assistant_id=ASSISTANT_ID)
        except TypeError:
            try:
                run = _openai_call(openai_client.beta.threads.runs.create, thread_id=thread_id, assistant=ASSISTANT_ID)
            except TypeError:
                run = _openai_call(openai_client.beta.threads.runs.create, thread_id=thread_id)
    except Exception as exc:
        logging.warning(f"SDK runs.create failed: {exc}; attempting REST fallback for run creation")
        try:
            openai_api_base = os.environ.get("OPENAI_API_BASE", "https://api.openai.com").rstrip("/")
            runs_url = f"{openai_api_base}/v1/beta/threads/{thread_id}/runs"
            headers = _openai_rest_headers()
            payload = {"assistant_id": ASSISTANT_ID}
            try:
                use_rest_tr = os.environ.get("OPENAI_USE_REST_TOOLRESOURCES", "").lower() in ("1", "true", "yes")
            except Exception:
                use_rest_tr = False
            if use_rest_tr and VECTOR_STORE_ID:
                payload["tool_resources"] = {"vector_store": VECTOR_STORE_ID}
            resp = requests.post(runs_url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            try:
                run_json = resp.json()
            except ValueError:
                logging.warning("REST runs.create returned non-JSON response")
                raise RuntimeError("REST runs.create returned non-JSON response")
            else:
                run_id = run_json.get("id") or run_json.get("run_id")
                if run_id:
                    run = _types.SimpleNamespace(id=run_id)
                    logging.info("Created run via REST fallback")
                else:
                    logging.warning("REST runs.create returned no run id")
                    raise RuntimeError("REST runs.create returned no run id")
        except Exception as e:
            logging.exception(f"REST fallback for runs.create failed: {e}")
            raise

    # Polling with progressive backoff+jitter to avoid hammering the API.
    poll_start = time.time()
    max_poll_s = 30  # hard timeout for polling
    poll_delay = 0.15
    max_delay = 1.0
    backoff_factor = 1.5
    prev_status = None
    while True:
        run = _openai_call(openai_client.beta.threads.runs.retrieve, thread_id=thread_id, run_id=run.id)
        run_summary["timestamps"]["last_poll"] = time.time()
        try:
            rs = getattr(run, 'status', None)
            logging.info(f"run_status={rs}")
        except Exception:
            logging.debug("Unable to read run.status for logging")
        if prev_status is None or rs != prev_status:
            poll_delay = 0.15
        prev_status = rs
        if run.status == "completed":
            run_summary["timestamps"]["completed"] = time.time()
            break
        if run.status == "failed":
            if DEBUG_TOOL_CALL_HANDLER:
                logging.error(f"Run failed: {getattr(run, 'last_error', None)}")
            raise RuntimeError(str(getattr(run, 'last_error', 'run failed')))
        if run.status == "requires_action":
            # Log required tool calls summary (name + arguments) for quick visibility
            try:
                tool_calls_tmp = getattr(getattr(run, 'required_action', _types.SimpleNamespace()), 'submit_tool_outputs', _types.SimpleNamespace())
                tool_calls_list = getattr(tool_calls_tmp, 'tool_calls', [])
                brief_calls = []
                for c in tool_calls_list:
                    nm = getattr(c.function, 'name', None) or getattr(c.function, 'function_name', None)
                    raw_args = getattr(c.function, 'arguments', None) or "{}"
                    args_parsed = _safe_load_json(raw_args or "{}")
                    brief_calls.append({"name": nm, "args": _redact_sensitive(args_parsed)})
                logging.info(f"requires_action_tool_calls={brief_calls}")
            except Exception:
                logging.debug("Failed to log required action tool calls summary")

            # Execute required tool calls
            tool_calls = getattr(getattr(run, 'required_action', _types.SimpleNamespace()), 'submit_tool_outputs', _types.SimpleNamespace())
            tool_calls = getattr(tool_calls, 'tool_calls', [])
            outputs = []
            run_summary["timestamps"]["tools_start"] = time.time()
            for call in tool_calls:
                try:
                    name = getattr(call.function, 'name', None) or getattr(call.function, 'function_name', None)
                    raw_args = getattr(call.function, 'arguments', None) or "{}"
                    args = _safe_load_json(raw_args or "{}")
                    if name == "manage_files" and args.get("operation") == "list":
                        name = "list_blobs"
                        args = {"prefix": args.get("prefix")}
                    call_start = time.time()
                    try:
                        if not isinstance(args, dict):
                            args = dict(args or {})
                    except Exception:
                        args = args or {}
                    if args.get("user_id") and args.get("user_id") != user_id:
                        logging.info(f"Overriding tool arg user_id={args.get('user_id')} -> {user_id}")
                    args["user_id"] = user_id
                    if "thread_id" in args and args.get("thread_id") != thread_id:
                        logging.info(f"Overriding tool arg thread_id={args.get('thread_id')} -> {thread_id}")
                    if thread_id:
                        args["thread_id"] = thread_id

                    result_str, info = execute_tool_call(name, args, user_id)
                    call_end = time.time()
                    all_tool_calls.append(info)
                    try:
                        parsed_output = json.loads(result_str)
                    except Exception:
                        parsed_output = result_str
                    outputs.append({
                        "tool_call_id": getattr(call, 'id', None),
                        "name": name,
                        "arguments": args,
                        "output": parsed_output,
                        "info": info,
                        "duration_ms": (call_end - call_start) * 1000,
                    })
                    tool_outputs_struct.append(outputs[-1])
                except Exception as call_exc:
                    if DEBUG_TOOL_CALL_HANDLER:
                        logging.exception(f"Error executing tool call {name}: {call_exc}")
                    outputs.append({"tool_call_id": getattr(call, 'id', None), "name": name, "error": str(call_exc)})
            run_summary["timestamps"]["tools_end"] = time.time()
            run_summary["steps"].append({"step": "tools", "count": len(outputs), "outputs": outputs})
            try:
                _openai_call(openai_client.beta.threads.runs.submit_tool_outputs, thread_id=thread_id, run_id=run.id, tool_outputs=[{"tool_call_id": o.get('tool_call_id'), "output": json.dumps(o.get('output')) if not isinstance(o.get('output'), str) else o.get('output')} for o in outputs])
            except Exception as submit_exc:
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.exception(f"Failed to submit tool outputs: {submit_exc}")
            run = _openai_call(openai_client.beta.threads.runs.retrieve, thread_id=thread_id, run_id=run.id)
            if run.status == "completed":
                run_summary["timestamps"]["completed_after_tools"] = time.time()
                break
            if run.status == "failed":
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.error(f"Run failed after submitting tool outputs: {getattr(run, 'last_error', None)}")
                raise RuntimeError(str(getattr(run, 'last_error', 'run failed after tools')))
            continue
        if (time.time() - poll_start) > max_poll_s:
            raise RuntimeError("Polling timed out")
        jitter = random.uniform(0, min(0.1, poll_delay * 0.2))
        time.sleep(poll_delay + jitter)
        poll_delay = min(max_delay, poll_delay * backoff_factor)

    return run, all_tool_calls, tool_outputs_struct, run_summary


def finalize_response(
    openai_client: OpenAI,
    thread_id: str,
    user_id: str,
    user_message: str,
    all_tool_calls: list,
    vector_store_attached: bool,
    total_ms: float = 0,
    log_interaction: bool = True,
    assistant_response_override: str = "",
    runtime_used: str = "assistants",
    responses_meta: Dict[str, Any] = None,
):
    """Collect assistant response, save interaction, and return final HttpResponse."""
    messages = None
    if not assistant_response_override and runtime_used == "assistants":
        # Request a limited number of messages to reduce payload and latency.
        # Use limit=10 conservatively.
        try:
            messages = _openai_call(openai_client.beta.threads.messages.list, thread_id=thread_id, limit=10)
        except TypeError:
            # Some SDK versions may not accept 'limit' as a kwarg; fall back to call without it.
            messages = _openai_call(openai_client.beta.threads.messages.list, thread_id=thread_id)

    def _get_attr(msg: Any, key: str):
        if isinstance(msg, dict):
            return msg.get(key)
        return getattr(msg, key, None)

    def _get_role(msg: Any) -> str:
        return str(_get_attr(msg, "role") or "")

    def _created_at_int(msg: Any):
        created_at = _get_attr(msg, "created_at")
        if created_at is None:
            return None
        try:
            return int(created_at)
        except Exception:
            return None

    def _extract_text_from_message(msg: Any):
        contents = _get_attr(msg, "content") or []
        for item in contents:
            # SDK object shape: item.text.value
            try:
                if hasattr(item, "text") and getattr(item.text, "value", None):
                    return item.text.value
            except Exception:
                pass
            # REST/dict shape: {"type":"text","text":{"value":"..."}}
            if isinstance(item, dict):
                if item.get("type") == "text":
                    text_obj = item.get("text")
                    if isinstance(text_obj, dict):
                        if text_obj.get("value"):
                            return text_obj.get("value")
                    elif isinstance(text_obj, str) and text_obj:
                        return text_obj
        return None

    assistant_response = assistant_response_override or None
    if not assistant_response:
        assistant_response = None
        if runtime_used == "assistants" and messages is not None:
            try:
                data_iter = list(getattr(messages, "data", []) or [])
                assistant_msgs = [m for m in data_iter if _get_role(m) == "assistant"]
                if assistant_msgs:
                    if any(_created_at_int(m) is not None for m in assistant_msgs):
                        chosen = max(assistant_msgs, key=lambda m: (_created_at_int(m) or -1))
                    else:
                        chosen = assistant_msgs[-1]
                    assistant_response = _extract_text_from_message(chosen)
            except Exception:
                assistant_response = None

    if not assistant_response:
        assistant_response = "No response from assistant."

    try:
        user_snip = (user_message or "")[:120]
        assistant_snip = (assistant_response or "")[:120]
        logging.info("--- interaction summary ---\n" + f"user_id={user_id} thread_id={thread_id}\n" + f"user_message={user_snip}\n" + f"assistant_message={assistant_snip}\n" + "--- end summary ---")
    except Exception:
        logging.debug("Failed to emit concise interaction summary")

    if log_interaction:
        save_interaction_log(
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_response,
            thread_id=thread_id,
            tool_calls_info=all_tool_calls,
        )

    # `total_ms` can be supplied by caller; default to 0 if not provided.
    tools_ms = sum(call.get("duration_ms", 0) for call in all_tool_calls)

    body = {
        "status": "success",
        "response": assistant_response,
        "thread_id": thread_id,
        "user_id": user_id,
        "runtime_used": runtime_used,
        "vector_store_attached": vector_store_attached,
        "tool_calls_count": len(all_tool_calls),
        "timings": {
            "total_ms": total_ms,
            "tools_ms": tools_ms,
        },
    }
    if responses_meta:
        body["responses"] = responses_meta
    return _make_response(body, status_code=200)


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


def _openai_rest_headers(include_beta: bool = True) -> Dict[str, str]:
    """Build standard headers for OpenAI REST requests, including the
    OpenAI-Beta header required for the Assistants API when requested.
    """
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    try:
        if include_beta:
            headers["OpenAI-Beta"] = "assistants=v2"
    except Exception:
        pass
    return headers


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
            "read_many_blobs": ["files", "tail_lines", "tail_bytes", "max_bytes_per_file", "parse_json", "max_files"],
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
                logging.info(f"[DEBUG] GET {func_url} params={_redact_sensitive(dict(filtered_args if 'filtered_args' in locals() else params_with_user))} headers={_redact_sensitive(dict(headers))}")
            try:
                # Use filtered_args to avoid sending assistant-supplied extras when available
                get_params = filtered_args if 'filtered_args' in locals() else params_with_user
                resp = requests.get(func_url, params=get_params, headers=headers, timeout=45)
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
            # When dispatching via proxy, prefer the filtered argument set constructed
            # above to avoid leaking assistant-supplied or extraneous fields.
            payload = {"action": tool_name, "params": filtered_args if 'filtered_args' in locals() else params_with_user}
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
        base = str(base or "").strip().rstrip("/")

        # Local/dev fast path: avoid HTTP + function keys and call the function in-process.
        # This also makes the save visible in local `func` logs.
        if not base or base.startswith("http://localhost") or base.startswith("http://127.0.0.1"):
            try:
                from save_interaction import main as save_interaction_main

                class _Req:
                    def __init__(self, _payload, _user_id):
                        self.headers = {"x-user-id": str(_user_id), "X-User-Id": str(_user_id)}
                        self.params = {}
                        self._payload = _payload

                    def get_json(self):
                        return dict(self._payload)

                payload_local = {
                    "user_message": user_message,
                    "assistant_response": assistant_response,
                    "thread_id": thread_id,
                    "tool_calls": tool_calls_info,
                    "metadata": {"assistant_id": ASSISTANT_ID, "source": "tool_call_handler"},
                    "user_id": user_id,
                }
                resp = save_interaction_main(_Req(payload_local, user_id))
                if DEBUG_TOOL_CALL_HANDLER:
                    try:
                        body_text = resp.get_body().decode("utf-8") if hasattr(resp, "get_body") else str(resp)
                    except Exception:
                        body_text = "<unreadable>"
                    logging.info(f"[DEBUG] save_interaction in-process done body={body_text[:500]}")
                try:
                    body_text = resp.get_body().decode("utf-8") if hasattr(resp, "get_body") else ""
                    parsed = json.loads(body_text) if body_text else {}
                    if isinstance(parsed, dict) and parsed.get("success") is False:
                        logging.warning(f"save_interaction failed: {parsed.get('details') or parsed}")
                except Exception:
                    pass
                return
            except Exception as inproc_exc:
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.warning(f"[DEBUG] save_interaction in-process failed: {inproc_exc}; falling back to HTTP")

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
        def _fire_and_forget():
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=(1, 10))
                if DEBUG_TOOL_CALL_HANDLER:
                    try:
                        snippet = (r.text or "")[:500]
                    except Exception:
                        snippet = "<unreadable>"
                    logging.info(f"[DEBUG] save_interaction http status={getattr(r,'status_code','n/a')} body={snippet}")
            except Exception as post_exc:
                logging.warning(f"save_interaction_log failed: {post_exc}")

        threading.Thread(target=_fire_and_forget, daemon=True).start()
    except Exception as e:
        logging.warning(f"save_interaction_log failed: {e}")


def main(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("=" * 60)
    logging.info("TOOL_CALL_HANDLER start")
    file_handler = None
    if attach_file_handler:
        try:
            file_handler = attach_file_handler("tool_call_handler")
            logging.info("Attached per-invocation file log handler")
        except Exception:
            logging.warning("Failed to attach file log handler")
    try:
        try:
            body = req.get_json()
        except Exception:
            return _make_response({"error": "Invalid JSON payload"}, status_code=400)

        user_message = body.get("message", "")
        user_id, _user_id_source = resolve_user_id(req, body)
        thread_id = body.get("thread_id")
        time_only = bool(body.get("time_only", False))
        action = body.get("action")
        params = body.get("params", {})
        log_interaction = bool(body.get("log_interaction", True))

        # Direct save/get actions bypass agent
        if action in ["save_interaction", "get_interaction_history"]:
            resp_direct = handle_direct_actions(req, body, action, user_id)
            if resp_direct is not None:
                return resp_direct

        # Runtime selection (dual runtime: assistants|responses|auto)
        try:
            runtime_requested = resolve_runtime(body)
        except ValueError as vex:
            return _make_response({"error": str(vex)}, status_code=400)

        if runtime_requested == "auto":
            if not _missing_env_vars_for_runtime("responses"):
                runtime_used = "responses"
            elif not _missing_env_vars_for_runtime("assistants"):
                runtime_used = "assistants"
            else:
                # Prefer listing everything required for both runtimes to aid setup.
                missing = sorted(set(_missing_env_vars_for_runtime("responses") + _missing_env_vars_for_runtime("assistants")))
                return _make_response({"error": f"Missing env vars: {', '.join(missing)}", "status": "not_configured"}, status_code=503)
        else:
            runtime_used = runtime_requested

        # Config check (after direct actions so save/get can work without proxy config)
        missing = _missing_env_vars_for_runtime(runtime_used)
        if missing:
            return _make_response({"error": f"Missing env vars: {', '.join(missing)}", "status": "not_configured", "runtime": runtime_used}, status_code=503)

        # Run
        # Initialize OpenAI client and detect SDK capabilities early so we
        # can attempt SDK-based thread creation before falling back to REST.
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        # Note: SDK tool_resources support is detectable via _supports_tool_resources(),
        # but the value is not used in this handler; keep function available for future use.

        # Responses runtime (Prompt ID + deterministic tool loop)
        if runtime_used == "responses":
            request_start = time.time()
            try:
                assistant_response, all_tool_calls, responses_meta, thread_id = run_responses(
                    openai_client=openai_client,
                    user_id=user_id,
                    user_message=user_message,
                    thread_id=thread_id,
                )
            except RuntimeError as rexc:
                return _make_response({"error": str(rexc), "runtime": "responses"}, status_code=500)
            except Exception as exc:
                logging.exception(f"Failed during responses loop: {exc}")
                return _make_response({"error": "Internal server error", "details": str(exc), "runtime": "responses"}, status_code=500)

            total_ms = (time.time() - request_start) * 1000
            return finalize_response(
                openai_client=openai_client,
                thread_id=thread_id,
                user_id=user_id,
                user_message=user_message,
                all_tool_calls=all_tool_calls,
                vector_store_attached=False,
                total_ms=total_ms,
                log_interaction=log_interaction,
                assistant_response_override=assistant_response,
                runtime_used="responses",
                responses_meta=responses_meta,
            )

        # If the caller didn't supply a thread identifier, attempt to restore
        # a previously saved thread for this user from blob storage. If restore
        # fails, create a new thread via the installed OpenAI SDK (preferred).
        # If the SDK-based creation fails (or is unavailable), fall back to
        # a REST call. This avoids routing issues where a hardcoded REST
        # endpoint may be intercepted by a local proxy returning HTML.
        if not thread_id:
            try:
                thread_id = restore_or_create_thread(openai_client, user_id, thread_id)
            except RuntimeError as rexc:
                msg = str(rexc)
                if 'failed to create thread' in msg or 'invalid response' in msg or 'thread creation returned no id' in msg:
                    return _make_response({"error": msg}, status_code=502)
                return _make_response({"error": msg}, status_code=500)

        # --- Synchronization: always append the user's message to the thread ---
        # Use SDK when available, otherwise fall back to REST so the thread
        # contains the user's message before creating a run.
        try:
            append_user_message(openai_client, thread_id, user_message)
        except Exception:
            logging.exception("Unexpected error while appending user message to thread")

        run = None
        all_tool_calls = []
        tool_outputs_struct = []
        request_start = time.time()
        # Vector store support removed per configuration: we no longer attach
        # OpenAI-managed vector stores to runs. This simplifies runtime
        # behavior and avoids SDK/proxy compatibility issues.
        vector_store_attached = False
        # Run summary and per-step timestamps
        run_summary = {"timestamps": {}, "steps": []}

        # Optional pre-run restore (caller may request state restore)
        do_restore = bool(body.get("do_restore", False))
        if do_restore:
            try:
                run_summary["timestamps"]["restore_start"] = time.time()
                base = os.getenv("FUNCTION_URL_BASE", "http://localhost:7071").rstrip("/")
                restore_url = f"{base}/api/restore_session"
                function_code_env = os.getenv("FUNCTION_CODE_RESTORE_SESSION", "")
                if function_code_env:
                    restore_url = f"{restore_url}?code={function_code_env}"
                headers = {"X-User-Id": str(user_id), "Content-Type": "application/json"}
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.info(f"[DEBUG] Calling restore_session {restore_url} user_id={user_id}")
                try:
                    r = requests.post(restore_url, json={"user_id": user_id, "thread_id": thread_id}, headers=headers, timeout=30)
                    r.raise_for_status()
                    try:
                        restore_result = r.json()
                    except Exception:
                        restore_result = {"raw": r.text}
                except Exception as e:
                    restore_result = {"error": str(e)}
                    if DEBUG_TOOL_CALL_HANDLER:
                        logging.exception("Restore session failed")
                run_summary["timestamps"]["restore_end"] = time.time()
                run_summary["steps"].append({"step": "restore", "result": restore_result})
            except Exception as e:
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.exception(f"Unexpected error during restore: {e}")

        # Create run and poll via helper (encapsulates run creation, polling,
        # required-action tool execution and submit outputs). Any runtime
        # failures in that flow are converted into appropriate HTTP responses.
        try:
            run, all_tool_calls, tool_outputs_struct, run_summary = create_run_and_poll(openai_client, thread_id, user_id)
        except RuntimeError as rexc:
            return _make_response({"error": str(rexc)}, status_code=500)
        except Exception as exc:
            logging.exception(f"Failed during run creation/polling: {exc}")
            return _make_response({"error": "Internal server error", "details": str(exc)}, status_code=500)

        # Build final response and return
        total_ms = (time.time() - request_start) * 1000
        return finalize_response(
            openai_client,
            thread_id,
            user_id,
            user_message,
            all_tool_calls,
            vector_store_attached,
            total_ms=total_ms,
            log_interaction=log_interaction,
            runtime_used=runtime_used,
        )
    # Ensure any uncaught exception returns a Functions-compatible HttpResponse
    except Exception as e:
        logging.exception(f"Unhandled exception in tool_call_handler.main: {e}")
        try:
            return _make_response({"error": "Internal server error", "details": str(e)}, status_code=500)
        except Exception:
            # Fallback: construct HttpResponse directly to avoid worker encoding issues
            try:
                return func.HttpResponse(json.dumps({"error": "Internal server error"}), status_code=500, mimetype="application/json")
            except Exception:
                # As a last resort, return a plain tuple (the worker may still handle it)
                return json.dumps({"error": "Internal server error"}), 500, {"Content-Type": "application/json"}
    finally:
        if file_handler is not None and detach_file_handler:
            try:
                detach_file_handler(file_handler)
            except Exception:
                logging.warning("Failed to detach file log handler")

