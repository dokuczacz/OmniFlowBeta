import datetime
import json
import logging
import os
import sys
import time
import hashlib
from typing import Dict, Any, Tuple, List
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

try:
    from jsonschema import Draft202012Validator
except Exception:  # pragma: no cover
    Draft202012Validator = None

# Allow importing shared helpers when running as a Functions app or locally
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from shared.local_logger import attach_file_handler, detach_file_handler
except Exception:
    # Best-effort import; if it fails, we will continue without file logging
    attach_file_handler = None
    detach_file_handler = None
from shared.http_client import requests_get, requests_post
from shared.mock_agent import build_mock_agent_response, mock_marker, mock_user_id

# Phase 2: Import registry-driven dispatch pipeline
try:
    from tool_call_handler.dispatch import dispatch_tool_call as registry_dispatch
    REGISTRY_DISPATCH_AVAILABLE = True
except ImportError:
    REGISTRY_DISPATCH_AVAILABLE = False

# Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")
OPENAI_PROMPT_ID = os.environ.get("OPENAI_PROMPT_ID", "")
LLM_RUNTIME_DEFAULT = os.environ.get("LLM_RUNTIME", "assistants")
# Cache `handles.json` in-memory to avoid repeated blob reads.
# Default TTL is 10 minutes to tolerate long responses/tool loops without frequent cache refresh.
HANDLES_CACHE_TTL_SECONDS = int(os.environ.get("HANDLES_CACHE_TTL_SECONDS", "600") or 600)
PROXY_URL = os.environ.get("AZURE_PROXY_URL", "")
PROXY_FUNCTION_KEY = os.environ.get("FUNCTION_CODE_PROXY_ROUTER", "")
ENABLE_SAVE_INTERACTION = True  # Hardcoded to always enable saving for now
VECTOR_STORE_ID = os.environ.get("OPENAI_VECTOR_STORE_ID", "")
DEBUG_TOOL_CALL_HANDLER = os.environ.get("DEBUG_TOOL_CALL_HANDLER", "").lower() in ("1", "true", "yes")
OMNIFLOW_DEBUG = os.environ.get("OMNIFLOW_DEBUG", "").lower() in ("1", "true", "yes")
DEBUG_TOOL_CALL_HANDLER = bool(DEBUG_TOOL_CALL_HANDLER or OMNIFLOW_DEBUG)
OMNIFLOW_MOCK_AGENT = os.environ.get("OMNIFLOW_MOCK_AGENT", "").lower() in ("1", "true", "yes")
OPENAI_MAX_REQUESTS = int(os.environ.get("OPENAI_MAX_REQUESTS", "0") or 0)
# WP6 routing: when UI does not send `context_mode`, fall back to this default.
# Values: AUTO | FAST | DEEP
WP6_DEFAULT_CONTEXT_MODE = (os.environ.get("WP6_DEFAULT_CONTEXT_MODE", "AUTO") or "AUTO").strip().upper()
WP6_TOPIC_CHANGE_ENABLED = False
WP6_TOPIC_CHANGE_WINDOW_SECONDS = 0
WP6_RESPONSES_STATELESS = os.environ.get("WP6_RESPONSES_STATELESS", "").lower() in ("1", "true", "yes")
WP6_RECENT_TURNS_MAX = int(os.environ.get("WP6_RECENT_TURNS_MAX", "8") or 8)
WP6_RECENT_TURNS_MAX_CHARS = int(os.environ.get("WP6_RECENT_TURNS_MAX_CHARS", "320") or 320)
WP6_FAST_AUDIT_ENABLED = str(os.environ.get("WP6_FAST_AUDIT_ENABLED", "0") or "").strip().lower() in ("1", "true", "yes", "y", "on")
WP6_FAST_AUDIT_MAX_CHARS = int(os.environ.get("WP6_FAST_AUDIT_MAX_CHARS", "16000") or 16000)
WP6_AUDIT_DEFAULT_MODEL = str(os.environ.get("WP6_AUDIT_DEFAULT_MODEL") or os.environ.get("OPENAI_WP6_AUDIT_MODEL") or "gpt-5-mini").strip()
WP6_AUDIT_DEFAULT_REASONING_EFFORT = str(os.environ.get("WP6_AUDIT_DEFAULT_REASONING_EFFORT") or os.environ.get("OPENAI_WP6_AUDIT_REASONING_EFFORT") or "medium").strip().lower()
WP7_AUDIT_DEFAULT_MODEL = str(os.environ.get("WP7_AUDIT_DEFAULT_MODEL", "gpt-5-mini") or "gpt-5-mini").strip()
WP7_AUDIT_DEFAULT_REASONING_EFFORT = str(os.environ.get("WP7_AUDIT_DEFAULT_REASONING_EFFORT", "medium") or "medium").strip().lower()
# runtime counter for outbound OpenAI HTTP calls (best-effort)
_openai_lock = threading.Lock()
_openai_count = 0
CACHE_LOCK = threading.Lock()
_handles_cache: Dict[str, Dict[str, Any]] = {}

# WP6.M1: preferences cache (best-effort; no hard dependency)
_prefs_cache: Dict[str, Dict[str, Any]] = {}
PREFERENCES_CACHE_TTL_SECONDS = int(os.environ.get("PREFERENCES_CACHE_TTL_SECONDS", "600") or 600)
WP6_PREFERENCES_AUTO_CREATE = str(os.environ.get("WP6_PREFERENCES_AUTO_CREATE", "1") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
    "on",
)
_prefs_loading = threading.local()

WP6_FAST_MAX_INPUT_TOKENS = int(os.environ.get("WP6_FAST_MAX_INPUT_TOKENS", "2000") or 2000)
WP6_FAST_MAX_SOURCES = int(os.environ.get("WP6_FAST_MAX_SOURCES", "4") or 4)
WP6_FAST_MAX_RAW_BYTES = int(os.environ.get("WP6_FAST_MAX_RAW_BYTES", "64000") or 64000)
WP6_DEEP_MAX_PACK_TOKENS = int(os.environ.get("WP6_DEEP_MAX_PACK_TOKENS", "16000") or 16000)
WP6_DEEP_MAX_CANDIDATE_SOURCES = int(os.environ.get("WP6_DEEP_MAX_CANDIDATE_SOURCES", "12") or 12)
WP6_DEEP_MIN_SEMANTIC_SELECTED = int(os.environ.get("WP6_DEEP_MIN_SEMANTIC_SELECTED", "3") or 3)
WP6_DEEP_MIN_SEMANTIC_CANDIDATES = int(os.environ.get("WP6_DEEP_MIN_SEMANTIC_CANDIDATES", "6") or 6)
WP6_CONTEXT_PACK_TTL_SECONDS = int(os.environ.get("WP6_CONTEXT_PACK_TTL_SECONDS", "300") or 300)
WP6_DEEP_COOLDOWN_SECONDS = int(os.environ.get("WP6_DEEP_COOLDOWN_SECONDS", "600") or 600)
OPENAI_CONTEXT_BUILDER_PROMPT_ID = os.environ.get("OPENAI_CONTEXT_BUILDER_PROMPT_ID", "")

PA_INTENT_STAGES = (
    "CALENDAR_QUERY",
    "CALENDAR_WRITE",
    "EMAIL_QUERY",
    "EMAIL_WRITE",
    "TASKS_MANAGE",
    "DAILY_PLAN",
    "NOTES_KB",
    "DECISION_SUPPORT",
    "DOC_ANALYSIS",
    "REPORTING",
    "TRAVEL_PLANNING",
)
PA_WRITE_STAGES = {"CALENDAR_WRITE", "EMAIL_WRITE", "TASKS_MANAGE"}


def _pa_intent_router(user_text: str) -> Dict[str, Any]:
    text = str(user_text or "").lower()
    stage_scores = {stage: 0.0 for stage in PA_INTENT_STAGES}
    evidence: list[str] = []

    def _add(stage: str, keyword: str, weight: float = 1.0):
        if keyword and keyword in text:
            stage_scores[stage] += weight
            evidence.append(f"{stage}:{keyword}")

    email_terms = ["email", "mail", "inbox", "gmail", "outlook"]
    email_write_terms = ["send", "draft", "write", "reply", "respond", "compose", "forward"]
    email_query_terms = ["check", "read", "show", "find", "search", "unread", "latest", "last"]
    calendar_terms = ["calendar", "meeting", "event", "appointment", "schedule"]
    calendar_write_terms = ["schedule", "book", "reschedule", "move", "cancel", "create", "add", "invite"]
    calendar_query_terms = ["when", "next", "upcoming", "availability", "free", "busy"]
    tasks_terms = ["task", "todo", "to-do", "remind", "reminder", "follow up", "follow-up"]
    plan_terms = ["plan my day", "daily plan", "agenda", "day plan", "schedule my day"]
    notes_terms = ["note", "remember", "save", "store", "knowledge base", "kb", "notes"]
    decision_terms = ["decide", "choose", "recommend", "compare", "pros and cons", "tradeoff", "advice"]
    doc_terms = ["document", "pdf", "summarize", "analyze", "extract", "review", "report"]
    reporting_terms = ["report", "metrics", "status update", "weekly summary", "kpi"]
    travel_terms = ["travel", "trip", "flight", "hotel", "itinerary", "booking"]

    for term in email_terms:
        _add("EMAIL_QUERY", term, 0.5)
        _add("EMAIL_WRITE", term, 0.5)
    for term in email_write_terms:
        _add("EMAIL_WRITE", term, 2.0)
    for term in email_query_terms:
        _add("EMAIL_QUERY", term, 1.5)

    for term in calendar_terms:
        _add("CALENDAR_QUERY", term, 0.5)
        _add("CALENDAR_WRITE", term, 0.5)
    for term in calendar_write_terms:
        _add("CALENDAR_WRITE", term, 2.0)
    for term in calendar_query_terms:
        _add("CALENDAR_QUERY", term, 1.5)

    for term in tasks_terms:
        _add("TASKS_MANAGE", term, 1.5)
    for term in plan_terms:
        _add("DAILY_PLAN", term, 2.0)
    for term in notes_terms:
        _add("NOTES_KB", term, 1.5)
    for term in decision_terms:
        _add("DECISION_SUPPORT", term, 1.5)
    for term in doc_terms:
        _add("DOC_ANALYSIS", term, 1.5)
    for term in reporting_terms:
        _add("REPORTING", term, 1.5)
    for term in travel_terms:
        _add("TRAVEL_PLANNING", term, 1.5)

    sorted_intents = sorted(stage_scores.items(), key=lambda item: item[1], reverse=True)
    top_stage, top_score = sorted_intents[0]
    second_score = sorted_intents[1][1] if len(sorted_intents) > 1 else 0.0
    total_score = sum(stage_scores.values())

    if total_score <= 0:
        top_stage = "DECISION_SUPPORT"
        top_score = 1.0
        total_score = 1.0

    top_intents = [
        {"stage": stage, "p": round(score / total_score, 3)}
        for stage, score in sorted_intents
        if score > 0
    ][:5]
    if not top_intents:
        top_intents = [{"stage": top_stage, "p": 1.0}]

    need_clarification = top_score < 2.0 or (top_score - second_score) <= 1.0
    clarify_questions = []
    if need_clarification:
        clarify_questions = [
            "Czy chodzi o odczyt (QUERY), czy wykonanie akcji (WRITE)?",
            "Podaj proszę dokładny zakres i oczekiwany rezultat.",
        ]

    return {
        "top_intents": top_intents,
        "recommended_stage": top_stage,
        "recommended_phase": "DISCOVERY",
        "need_clarification": need_clarification,
        "clarify_questions": clarify_questions,
        "evidence": evidence[:5],
    }

def _best_effort_debug(code: str, *, user_id: str = "", thread_id: str = "", error: Exception | None = None, **ctx: Any) -> None:
    logger = logging.getLogger()
    if not (DEBUG_TOOL_CALL_HANDLER or logger.isEnabledFor(logging.DEBUG)):
        return
    try:
        extras = " ".join([f"{k}={str(v)[:200]}" for k, v in (ctx or {}).items() if v is not None])
        err = f"{type(error).__name__}: {error}" if error else ""
        logging.debug(f"[BEST_EFFORT] code={code} user_id={user_id} thread_id={thread_id} {extras} error={err}".strip())
    except Exception:
        return


def _inprocess_call_function_main(main_fn, user_id: str, *, params: Dict[str, Any] | None = None, body: Dict[str, Any] | None = None):
    """
    Call an Azure Functions `main(req)` handler in-process without going through `execute_tool_call()`.

    Purpose: avoid recursion (e.g. preferences loading calling execute_tool_call calling preferences loading).
    """
    class _Req:
        def __init__(self, _params: Dict[str, Any] | None, _body: Dict[str, Any] | None, _user_id: str):
            self.headers = {"x-user-id": str(_user_id), "X-User-Id": str(_user_id)}
            self.params = dict(_params or {})
            self._body = dict(_body or {})

        def get_json(self):
            return dict(self._body)

    return main_fn(_Req(params, body, user_id))


def _inprocess_read_blob_file(user_id: str, file_name: str) -> Dict[str, Any]:
    from read_blob_file import main as read_blob_file_main
    resp = _inprocess_call_function_main(read_blob_file_main, user_id, params={"file_name": file_name})
    try:
        body_text = resp.get_body().decode("utf-8") if hasattr(resp, "get_body") else str(resp)
        return json.loads(body_text) if body_text else {}
    except Exception as exc:
        _best_effort_debug("inprocess_read_blob_parse_failed", user_id=str(user_id), error=exc, file_name=file_name)
        return {}


def _inprocess_upload_data_or_file(user_id: str, target_blob_name: str, file_content: Any) -> Dict[str, Any]:
    from upload_data_or_file import main as upload_main
    resp = _inprocess_call_function_main(
        upload_main,
        user_id,
        body={"target_blob_name": target_blob_name, "file_content": file_content, "user_id": user_id},
    )
    try:
        body_text = resp.get_body().decode("utf-8") if hasattr(resp, "get_body") else str(resp)
        return json.loads(body_text) if body_text else {}
    except Exception as exc:
        _best_effort_debug(
            "inprocess_upload_parse_failed",
            user_id=str(user_id),
            error=exc,
            target_blob_name=target_blob_name,
        )
        return {}


_WP6_PREFERENCES_SCHEMA_FALLBACK: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "omniflow.wp6.preferences.v1",
    "type": "object",
    "additionalProperties": True,
    "required": ["schema_version", "updated_utc"],
    "properties": {
        "schema_version": {"type": "string", "const": "omniflow.wp6.preferences.v1"},
        "updated_utc": {"type": "string"},
    },
}

_WP6_CONTEXT_PACK_SCHEMA_LEGACY: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "omniflow.wp6.context_pack.legacy.v0",
    "type": "object",
    # Keep permissive for forward-compatibility with prompt iterations.
    "additionalProperties": True,
    "required": [
        "mode",
        "summary",
        "bullets",
        "top_sources",
        "pack_tokens_est",
        "coverage",
        "need_more_sources",
        "created_utc",
    ],
    "properties": {
        "mode": {"type": "string"},
        "summary": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}},
        "top_sources": {"type": "array"},
        "pack_tokens_est": {"type": "integer", "minimum": 0},
        "coverage": {},
        "need_more_sources": {"type": "boolean"},
        "created_utc": {"type": "string"},
    },
}

_WP6_CONTEXT_BUILDER_INPUT_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "omniflow.wp6.context_builder_input.v1",
    "type": "object",
    "additionalProperties": True,
    "required": ["request", "candidate_sources", "constraints"],
    "properties": {
        "request": {
            "type": "object",
            "additionalProperties": True,
            "required": ["user_prompt"],
            "properties": {"user_prompt": {"type": "string"}},
        },
        "candidate_sources": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": True,
                "required": ["path"],
                "properties": {
                    "path": {"type": "string"},
                    "excerpt_or_snippet": {"type": "string"},
                },
            },
        },
        "constraints": {"type": "object", "additionalProperties": True},
    },
}

_wp6_prefs_validator = None
_wp6_pack_legacy_validator = None
_wp6_builder_input_validator = None


def _repo_root_dir() -> str:
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(os.path.join(backend_dir, ".."))


def _load_schema_file(relative_path: str) -> Dict[str, Any]:
    try:
        schema_path = os.path.join(_repo_root_dir(), relative_path)
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        return schema if isinstance(schema, dict) else {}
    except Exception:
        return {}


def _ensure_validator(schema: Dict[str, Any] | None):
    if Draft202012Validator is None or not isinstance(schema, dict) or not schema:
        return None
    try:
        return Draft202012Validator(schema)
    except Exception:
        return None


def _validate_schema(validator, payload: Any) -> Tuple[bool, str]:
    if validator is None:
        # Best-effort fallback when jsonschema is unavailable.
        return True, ""
    try:
        errors = sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    except Exception as exc:
        return False, f"validator_failed:{type(exc).__name__}"
    if not errors:
        return True, ""
    err = errors[0]
    try:
        path = ".".join([str(x) for x in err.path]) if getattr(err, "path", None) else ""
    except Exception:
        path = ""
    return False, f"{path}:{getattr(err, 'message', 'schema_validation_failed')}"


def _wp6_preferences_validator():
    global _wp6_prefs_validator
    if _wp6_prefs_validator is not None:
        return _wp6_prefs_validator
    schema = _load_schema_file(
        os.path.join("docs", "workflow", "wp6_context_builder", "preferences.schema.v1.json")
    )
    _wp6_prefs_validator = _ensure_validator(schema or _WP6_PREFERENCES_SCHEMA_FALLBACK)
    return _wp6_prefs_validator


def _wp6_context_pack_legacy_validator():
    global _wp6_pack_legacy_validator
    if _wp6_pack_legacy_validator is not None:
        return _wp6_pack_legacy_validator
    _wp6_pack_legacy_validator = _ensure_validator(_WP6_CONTEXT_PACK_SCHEMA_LEGACY)
    return _wp6_pack_legacy_validator


def _wp6_context_builder_input_validator():
    global _wp6_builder_input_validator
    if _wp6_builder_input_validator is not None:
        return _wp6_builder_input_validator
    _wp6_builder_input_validator = _ensure_validator(_WP6_CONTEXT_BUILDER_INPUT_SCHEMA)
    return _wp6_builder_input_validator


def _wp6_default_preferences() -> Dict[str, Any]:
    return {
        "schema_version": "omniflow.wp6.preferences.v1",
        "updated_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "brevity": "medium",
        "fast_mode": False,
        "allowed_reads": [],
        "disable_history_reads": False,
    }


def _wp6_validate_preferences(prefs: Any) -> Tuple[bool, str]:
    if not isinstance(prefs, dict):
        return False, "not_an_object"
    # Validate against the published schema (or fallback).
    return _validate_schema(_wp6_preferences_validator(), prefs)


def _wp6_validate_context_pack(pack: Any) -> Tuple[bool, str]:
    if not isinstance(pack, dict):
        return False, "not_an_object"
    return _validate_schema(_wp6_context_pack_legacy_validator(), pack)


def _wp6_validate_context_builder_input(cb_input: Any) -> Tuple[bool, str]:
    if not isinstance(cb_input, dict):
        return False, "not_an_object"
    return _validate_schema(_wp6_context_builder_input_validator(), cb_input)


def _load_preferences(user_id: str) -> Dict[str, Any]:
    """
    Load users/{user_id}/semantics/preferences.json (best-effort).

    Behavior:
    - If missing/invalid, returns {}.
    - Cached in-memory for PREFERENCES_CACHE_TTL_SECONDS.
    """
    uid = str(user_id or "default").strip() or "default"
    if PREFERENCES_CACHE_TTL_SECONDS > 0:
        with CACHE_LOCK:
            cached = _prefs_cache.get(uid)
        if cached:
            age = time.time() - cached.get("ts", 0)
            if age <= PREFERENCES_CACHE_TTL_SECONDS:
                return cached.get("data", {}) or {}
    try:
        setattr(_prefs_loading, "active", True)
        payload = _inprocess_read_blob_file(uid, "semantics/preferences.json")
        if isinstance(payload, dict) and payload.get("status") == "success":
            prefs = payload.get("data")
            if isinstance(prefs, str):
                try:
                    prefs = json.loads(prefs)
                except Exception as exc:
                    _best_effort_debug("prefs_json_parse_failed", user_id=uid, error=exc)
                    prefs = {}
            if isinstance(prefs, dict):
                ok, reason = _wp6_validate_preferences(prefs)
                if not ok:
                    _best_effort_debug(
                        "prefs_schema_invalid",
                        user_id=uid,
                        reason=reason,
                    )
                    if WP6_PREFERENCES_AUTO_CREATE:
                        default_prefs = _wp6_default_preferences()
                        try:
                            _inprocess_upload_data_or_file(
                                uid, "semantics/preferences.json", default_prefs
                            )
                            if PREFERENCES_CACHE_TTL_SECONDS > 0:
                                with CACHE_LOCK:
                                    _prefs_cache[uid] = {
                                        "data": default_prefs,
                                        "ts": time.time(),
                                    }
                            return default_prefs
                        except Exception as exc:
                            _best_effort_debug(
                                "prefs_autocreate_failed",
                                user_id=uid,
                                error=exc,
                            )
                    return {}

                if PREFERENCES_CACHE_TTL_SECONDS > 0:
                    with CACHE_LOCK:
                        _prefs_cache[uid] = {"data": prefs, "ts": time.time()}
                return prefs

        if WP6_PREFERENCES_AUTO_CREATE and isinstance(payload, dict) and payload.get("error"):
            err_text = str(payload.get("error") or "").lower()
            if "not found" in err_text or "blobnotfound" in err_text:
                default_prefs = _wp6_default_preferences()
                try:
                    _inprocess_upload_data_or_file(uid, "semantics/preferences.json", default_prefs)
                    if PREFERENCES_CACHE_TTL_SECONDS > 0:
                        with CACHE_LOCK:
                            _prefs_cache[uid] = {"data": default_prefs, "ts": time.time()}
                    return default_prefs
                except Exception as exc:
                    _best_effort_debug("prefs_autocreate_failed", user_id=uid, error=exc)
        return {}
    except Exception as exc:
        _best_effort_debug("prefs_load_failed", user_id=uid, error=exc)
        return {}
    finally:
        try:
            setattr(_prefs_loading, "active", False)
        except Exception:
            pass


def _bool_pref(prefs: Dict[str, Any], key: str, default: bool = False) -> bool:
    try:
        if key in (prefs or {}):
            return str(prefs.get(key) or "").strip().lower() in ("1", "true", "yes", "y", "on")
    except Exception:
        pass
    return default


def _list_pref(prefs: Dict[str, Any], key: str) -> list:
    v = (prefs or {}).get(key)
    if isinstance(v, list):
        out = []
        for item in v:
            s = str(item or "").strip()
            if s:
                out.append(s)
        return out
    return []


def _wp6_is_history_path(file_name: str) -> bool:
    fn = str(file_name or "").strip().lower()
    return fn == "interaction_logs.json" or fn.startswith("interactions/")


def _wp6_is_semantic_ok(file_name: str) -> bool:
    fn = str(file_name or "").strip().lower()
    # WP7 semantic artifacts are the intended source for cheap context rebuild.
    return fn.startswith("interactions/semantic/") or fn.startswith("interactions/portfolio/")


def _wp6_allowed_to_read(tool_name: str, normalized_args: Dict[str, Any], prefs: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Enforce WP6.M1 preferences on read-style tools.

    - disable_history_reads blocks: get_interaction_history and interaction_logs/interactions reads (except semantic/portfolio).
    - allowed_reads (if non-empty) restricts read targets to the allowlist (plus always-needed system files).
    """
    tool = str(tool_name or "").strip()
    args = dict(normalized_args or {})

    disable_history = _bool_pref(prefs, "disable_history_reads", False)
    allowed_reads = set([s.strip() for s in _list_pref(prefs, "allowed_reads") if str(s).strip()])

    always_allowed_files = {
        "handles.json",
        "current_thread.json",
        "semantics/preferences.json",
        "agent_exchange/agent_exchange.jsonl",
    }

    # If allowlist is active, block list_blobs to prevent broad browsing.
    if tool == "list_blobs" and allowed_reads:
        return False, "Blocked by preferences: allowed_reads is set; prefer read_blob_file/read_many_blobs on allowlisted files."

    if tool == "get_interaction_history" and disable_history:
        return False, "Blocked by preferences: disable_history_reads=true (use semantic index instead)."

    # Determine read targets by tool
    targets: list[str] = []
    if tool == "read_blob_file":
        targets = [str(args.get("file_name") or "").strip()]
    elif tool == "read_many_blobs":
        files = args.get("files")
        if isinstance(files, list):
            targets = [str(x or "").strip() for x in files]
    elif tool == "get_filtered_data":
        targets = [str(args.get("target_blob_name") or "").strip()]

    targets = [t for t in targets if t]
    if not targets:
        return True, ""

    # History gating
    if disable_history:
        for t in targets:
            if _wp6_is_history_path(t) and not _wp6_is_semantic_ok(t):
                return False, f"Blocked by preferences: disable_history_reads=true (target={t})."

    # Allowlist gating (if present)
    if allowed_reads:
        for t in targets:
            if t in always_allowed_files:
                continue
            if _wp6_is_semantic_ok(t):
                continue
            if t not in allowed_reads:
                return False, f"Blocked by preferences: target not in allowed_reads (target={t})."

    return True, ""


def _wp6_est_tokens_from_text(text: str) -> int:
    return int((len(text or "") + 3) // 4)


def _wp6_norm_intent_key(user_message: str) -> str:
    raw = str(user_message or "").strip().lower()
    raw = " ".join(raw.split())
    raw = raw[:256]
    return hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _wp6_parse_need_deep_signal(text: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse the WP6 "need_deep" signal from a FAST response.

    Preferred contract: the first line is a single-line JSON object:
      {"need_deep":false,"missing":[],"why":"","confidence":0.0,"deep_plan":[]}

    Fallback contract: if the JSON is missing/unparseable, treat the presence of
    "__ROUTE_DEEP__" anywhere in the text as need_deep=True.

    Returns: (signal, cleaned_text) where cleaned_text has the first-line JSON stripped
    when successfully parsed via JSON.
    """

    signal: Dict[str, Any] = {
        "need_deep": False,
        "missing": [],
        "why": "",
        "confidence": 0.0,
        "deep_plan": [],
        "parse_status": "none",
    }
    if not text:
        return signal, text

    raw_lines = str(text).splitlines()
    first_line = raw_lines[0].strip() if raw_lines else ""

    if first_line.startswith("{") and first_line.endswith("}"):
        try:
            obj = json.loads(first_line)
            if isinstance(obj, dict) and ("need_deep" in obj):
                signal["need_deep"] = bool(obj.get("need_deep"))
                missing = obj.get("missing")
                if isinstance(missing, list):
                    signal["missing"] = [str(x)[:200] for x in missing if str(x).strip()][:10]
                signal["why"] = str(obj.get("why") or "")[:300]
                try:
                    signal["confidence"] = float(obj.get("confidence") or 0.0)
                except Exception:
                    signal["confidence"] = 0.0
                deep_plan = obj.get("deep_plan")
                if isinstance(deep_plan, list):
                    signal["deep_plan"] = [str(x)[:200] for x in deep_plan if str(x).strip()][:10]
                signal["parse_status"] = "json"
                cleaned = "\n".join(raw_lines[1:]).lstrip("\n")
                return signal, cleaned
        except Exception:
            pass

    if "__ROUTE_DEEP__" in str(text):
        signal["need_deep"] = True
        signal["parse_status"] = "token"
        return signal, text

    return signal, text


def _wp6_detect_topic_change(intent_key: str, state: Dict[str, Any]) -> Tuple[bool, str]:
    return False, "disabled"


def _wp6_deep_cooldown_allowed(state: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        last_ts = float((state or {}).get("wp6_last_deep_at") or 0.0)
        if not last_ts:
            return True, "cooldown_pass"
        age = time.time() - last_ts
        if age >= float(WP6_DEEP_COOLDOWN_SECONDS):
            return True, "cooldown_pass"
        return False, "cooldown_active"
    except Exception:
        return True, "cooldown_error"


def _wp6_extract_semantic_ids_from_index(index_jsonl_text: str, max_ids: int) -> list[str]:
    """
    Extract recent interaction ids from the semantic index.

    Important: older index.jsonl may contain many near-duplicate entries (same summary/tags).
    To avoid re-reading almost the same blobs (esp. for DEEP candidate_sources), we keep only one id per
    dedup group where possible.
    """

    if max_ids <= 0:
        return []

    # Parse most-recent-first.
    raw_items: list[dict] = []
    for line in (index_jsonl_text or "").splitlines()[::-1]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if isinstance(obj, dict):
            raw_items.append(obj)
        if len(raw_items) >= max_ids * 6:
            break

    def _ts_key(x: dict) -> float:
        ts = str((x or {}).get("timestamp_utc") or "").strip()
        if not ts:
            return 0.0
        try:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.datetime.fromisoformat(ts).timestamp()
        except Exception:
            return 0.0

    # Prefer the newest entry per dedup_key (if present); otherwise fall back to interaction_id.
    by_key: dict[str, tuple[float, str]] = {}
    for obj in raw_items:
        iid = str(obj.get("interaction_id") or "").strip()
        if not iid:
            continue
        key = str(obj.get("dedup_key") or iid).strip()
        ts = _ts_key(obj)
        prev = by_key.get(key)
        if not prev or ts >= prev[0]:
            by_key[key] = (ts, iid)

    # Return newest-first, unique.
    unique = sorted(by_key.values(), key=lambda t: t[0], reverse=True)
    out: list[str] = []
    for _, iid in unique:
        if iid not in out:
            out.append(iid)
        if len(out) >= max_ids:
            break
    return out


def _wp6_core_candidate_sources_tm_lo_ps(user_id: str) -> Tuple[list[dict], Dict[str, Any]]:
    """
    Provide short snippets for core PA files so Context Builder (no tools) can answer
    TM/LO/PS-related questions without needing additional reads.
    """

    meta: Dict[str, Any] = {"core_snippets_count": 0, "core_snippets_bytes": 0, "core_files": []}
    core_files = ["TM.json", "LO.json", "PS.json"]

    try:
        raw_str, _ = execute_tool_call(
            "read_many_blobs",
            {
                "files": core_files,
                "tail_lines": 80,
                "tail_bytes": 16384,
                "max_bytes_per_file": 12000,
                "parse_json": False,
                "max_files": len(core_files),
            },
            user_id,
        )
        payload = json.loads(raw_str) if isinstance(raw_str, str) else {}
    except Exception:
        payload = {}

    out: list[dict] = []
    if isinstance(payload, dict) and payload.get("status") == "success":
        for it in (payload.get("items") or []):
            if not isinstance(it, dict):
                continue
            path = str(it.get("path") or it.get("name") or "").strip()
            data = it.get("data")
            if not path or not isinstance(data, str):
                continue
            snippet = data.strip()
            if not snippet:
                continue
            out.append({"path": path, "excerpt_or_snippet": snippet[:4000]})
            meta["core_snippets_count"] += 1
            meta["core_snippets_bytes"] += int(it.get("bytes") or 0)
            meta["core_files"].append(path)

    return out, meta


def _wp6_sum_candidates(fast_meta: Dict[str, Any], core_meta: Dict[str, Any]) -> Tuple[int, int]:
    selected = int((fast_meta or {}).get("selected_sources_count") or 0)
    candidates = int((fast_meta or {}).get("semantic_candidates_count") or 0)
    core = int((core_meta or {}).get("core_snippets_count") or 0)
    return selected, candidates, core


def _wp6_can_run_deep(fast_meta: Dict[str, Any], core_meta: Dict[str, Any], handles_state: Dict[str, Any]) -> Tuple[bool, str]:
    selected, candidates, core = _wp6_sum_candidates(fast_meta, core_meta)
    if selected >= 3 or candidates >= 6 or core >= 3:
        allowed, reason = _wp6_deep_cooldown_allowed(handles_state)
        if allowed:
            return True, "inputs_ok"
        return False, reason
    return False, "insufficient_inputs"


def _wp6_fast_context_from_wp7_semantic(user_id: str, max_sources: int, max_chars: int) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "semantic_candidates_count": 0,
        "selected_sources_count": 0,
        "raw_bytes_read": 0,
        "candidate_sources": [],
        "selected_source_ids": [],
        "max_sources_requested": int(max_sources or 0),
        "max_chars_requested": int(max_chars or 0),
    }

    # Tail the semantic index
    idx_str, _ = execute_tool_call(
        "read_many_blobs",
        {
            "files": ["interactions/semantic/index.jsonl"],
            "tail_lines": 200,
            "tail_bytes": 65536,
            "max_bytes_per_file": 48000,
            "parse_json": False,
            "max_files": 1,
        },
        user_id,
    )
    try:
        idx_payload = json.loads(idx_str) if isinstance(idx_str, str) else {}
    except Exception:
        idx_payload = {}

    index_text = ""
    if isinstance(idx_payload, dict) and idx_payload.get("status") == "success":
        items = idx_payload.get("items") or []
        if isinstance(items, list) and items and isinstance(items[0], dict):
            index_text = str(items[0].get("data") or "")
            meta["raw_bytes_read"] += int(items[0].get("bytes") or 0)

    interaction_ids = _wp6_extract_semantic_ids_from_index(index_text, max(1, max_sources) * 2)
    meta["semantic_candidates_count"] = len(interaction_ids)
    if not interaction_ids:
        return "", meta

    semantic_files = [f"interactions/semantic/{iid}.json" for iid in interaction_ids[: max(1, max_sources) * 2]]
    sem_str, _ = execute_tool_call(
        "read_many_blobs",
        {
            "files": semantic_files,
            "max_bytes_per_file": max(2048, max_chars),
            "parse_json": True,
            "max_files": max(1, max_sources) * 2,
        },
        user_id,
    )
    try:
        sem_payload = json.loads(sem_str) if isinstance(sem_str, str) else {}
    except Exception:
        sem_payload = {}

    items_data: list[dict] = []
    if isinstance(sem_payload, dict) and sem_payload.get("status") == "success":
        for it in (sem_payload.get("items") or []):
            if not isinstance(it, dict):
                continue
            meta["raw_bytes_read"] += int(it.get("bytes") or 0)
            data = it.get("data")
            if isinstance(data, dict):
                items_data.append(data)

    def _sig_rank(x: dict) -> int:
        sl = str((x or {}).get("signal_level") or "").lower()
        return 3 if sl == "high" else (2 if sl == "medium" else 1)

    def _ts_rank(x: dict) -> float:
        ts = str((x or {}).get("timestamp_utc") or "").strip()
        if not ts:
            return 0.0
        try:
            if ts.endswith("Z"):
                ts = ts[:-1] + "+00:00"
            return datetime.datetime.fromisoformat(ts).timestamp()
        except Exception:
            return 0.0

    # Prefer higher signal; within that, prefer most recent.
    items_data.sort(key=lambda x: (_sig_rank(x), _ts_rank(x)), reverse=True)
    out_lines: list[str] = []
    used = 0
    for it in items_data:
        if used >= max_sources:
            break
        iid = str(it.get("interaction_id") or "").strip()
        cat = str(it.get("category") or "").strip()
        summ = str(it.get("summary") or "").strip()
        tags = it.get("tags") if isinstance(it.get("tags"), list) else []
        tags_s = ",".join([str(t) for t in tags[:6] if str(t).strip()])
        if not iid or not summ:
            continue
        line = f"- [{cat}] {summ} (id={iid}{';tags='+tags_s if tags_s else ''})"
        if (sum(len(x) + 1 for x in out_lines) + len(line)) > max_chars:
            break
        out_lines.append(line)
        try:
            meta["candidate_sources"].append(
                {
                    "path": f"interactions/semantic/{iid}.json",
                    "excerpt_or_snippet": summ[:400],
                }
            )
            meta["selected_source_ids"].append(f"interactions/semantic/{iid}.json")
        except Exception:
            pass
        used += 1

    meta["selected_sources_count"] = used
    if not out_lines:
        return "", meta

    ctx = "WP7 semantic context (recent, prioritized):\n" + "\n".join(out_lines)
    return ctx, meta


def _wp6_format_recent_turns(turns: list[str]) -> str:
    safe = [str(t or "").strip() for t in (turns or []) if str(t or "").strip()]
    if not safe or int(WP6_RECENT_TURNS_MAX or 0) <= 0:
        return ""
    # Most recent first for routing clarity.
    safe = safe[::-1]
    lines = [f"- {t}" for t in safe[: max(1, int(WP6_RECENT_TURNS_MAX or 0))]]
    return "[RECENT_USER_TURNS]\n" + "\n".join(lines)


def _wp6_update_recent_user_turns(user_id: str, thread_id: str, user_message: str) -> list[str]:
    """
    Maintain a bounded ring buffer of recent raw user turns in handles.json.

    Stored under: handles[thread_id]["wp6_recent_user_turns"] = [{"ts_utc": "...", "text": "..."}, ...]
    """
    if int(WP6_RECENT_TURNS_MAX or 0) <= 0:
        return []
    if not thread_id:
        return []
    try:
        msg = str(user_message or "").strip()
        if not msg:
            return []
        if int(WP6_RECENT_TURNS_MAX_CHARS or 0) > 0:
            msg = msg[: int(WP6_RECENT_TURNS_MAX_CHARS)]

        handles = _load_handles(user_id)
        if not isinstance(handles, dict):
            return []
        state = handles.get(thread_id, {}) if isinstance(handles.get(thread_id), dict) else {}
        turns_raw = state.get("wp6_recent_user_turns")
        turns: list[dict] = []
        if isinstance(turns_raw, list):
            for t in turns_raw:
                if isinstance(t, dict) and t.get("text"):
                    turns.append({"ts_utc": str(t.get("ts_utc") or ""), "text": str(t.get("text") or "")})

        turns.append({"ts_utc": datetime.datetime.utcnow().isoformat() + "Z", "text": msg})
        turns = turns[-max(1, int(WP6_RECENT_TURNS_MAX)) :]

        handles[thread_id] = {
            **state,
            "wp6_recent_user_turns": turns,
            "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        _save_handles(user_id, handles, async_save=True)
        return [str(t.get("text") or "") for t in turns if str(t.get("text") or "").strip()]
    except Exception as exc:
        _best_effort_debug("wp6_recent_turns_update_failed", user_id=str(user_id), thread_id=str(thread_id), error=exc)
        return []


def _wp6_write_fast_audit(
    user_id: str,
    thread_id: str,
    *,
    audit_id: str,
    kind: str,
    payload: Dict[str, Any],
) -> str:
    if not WP6_FAST_AUDIT_ENABLED:
        return ""
    try:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = uuid.uuid4().hex[:8]
        path = f"semantics/wp6_fast_audit/{str(thread_id)}/{ts}_{audit_id}_{kind}_{suffix}.json"
        execute_tool_call("upload_data_or_file", {"target_blob_name": path, "file_content": payload}, user_id)
        return path
    except Exception as exc:
        _best_effort_debug(
            "wp6_fast_audit_write_failed",
            user_id=str(user_id),
            thread_id=str(thread_id),
            error=exc,
            kind=kind,
        )
        return ""


def _wp7_prepare_audit_input(
    user_id: str,
    *,
    count: int = 50,
    max_scan: int = 500,
    skip_already_audited: bool = True,
) -> Dict[str, Any]:
    """
    Prepare WP7 audit evidence bundle: >=50 index entries + >=50 corresponding artifacts.

    Sources:
    - WP7 index JSONL: interactions/semantic/index.jsonl
    - WP7 artifacts: interactions/semantic/<interaction_id>.json (resolved via semantic_blob_path if present)
    """
    from backend.shared.azure_client import AzureBlobClient

    count = max(1, int(count or 50))
    index_blob = "interactions/semantic/index.jsonl"
    bc = AzureBlobClient.get_blob_client(index_blob, user_id=user_id)
    text = bc.download_blob().content_as_text(encoding="utf-8")

    entries: List[Dict[str, Any]] = []
    for ln in (text or "").splitlines():
        ln = (ln or "").strip()
        if not ln:
            continue
        try:
            entries.append(json.loads(ln))
        except Exception:
            continue

    if max_scan > 0 and len(entries) > max_scan:
        entries = entries[-max_scan:]

    audited_ids: List[str] = []
    if skip_already_audited:
        handles = _load_handles(user_id)
        audited_ids = _wp_audit_state(handles, "wp7").get("audited_ids", []) if isinstance(handles, dict) else []
        audited_ids = [str(x) for x in audited_ids if str(x)]

    # Select most recent unique interaction_ids.
    seen: set[str] = set()
    selected: List[Dict[str, Any]] = []
    for e in reversed(entries):
        iid = str((e or {}).get("interaction_id") or "").strip()
        if not iid or iid in seen:
            continue
        if skip_already_audited and iid in audited_ids:
            continue
        seen.add(iid)
        selected.append(e)
        if len(selected) >= count * 2:
            break
    selected = list(reversed(selected))

    kept_entries: List[Dict[str, Any]] = []
    artifacts: List[Dict[str, Any]] = []
    for e in selected:
        iid = str((e or {}).get("interaction_id") or "").strip()
        if not iid:
            continue

        p = str((e or {}).get("semantic_blob_path") or "").strip()
        rel = ""
        if p.startswith("users/"):
            parts = p.split("/", 2)
            if len(parts) >= 3:
                rel = parts[2]
        if not rel:
            rel = f"interactions/semantic/{iid}.json"

        try:
            bc2 = AzureBlobClient.get_blob_client(rel, user_id=user_id)
            atext = bc2.download_blob().content_as_text(encoding="utf-8")
            art = json.loads(atext)
        except Exception:
            continue

        kept_entries.append(e)
        artifacts.append(art)
        if len(kept_entries) >= count:
            break

    out = {
        "run_id": f"wp7_audit_input::{user_id}::{len(kept_entries)}_{len(artifacts)}",
        "index_entries": kept_entries,
        "artifacts": artifacts,
    }
    return out


def _wp_audit_state(handles: Dict[str, Any], audit_type: str) -> Dict[str, Any]:
    state = handles.get("_audit_state", {}) if isinstance(handles, dict) else {}
    return state.get(audit_type, {}) if isinstance(state, dict) else {}


def _wp_audit_update_state(
    user_id: str,
    *,
    audit_type: str,
    audited_ids: List[str],
) -> None:
    if not audited_ids:
        return
    try:
        handles = _load_handles(user_id)
        if not isinstance(handles, dict):
            return
        state = handles.get("_audit_state", {}) if isinstance(handles.get("_audit_state"), dict) else {}
        type_state = state.get(audit_type, {}) if isinstance(state.get(audit_type), dict) else {}
        existing = type_state.get("audited_ids")
        ids = []
        if isinstance(existing, list):
            ids = [str(x) for x in existing if str(x)]
        for i in audited_ids:
            if i not in ids:
                ids.append(i)
        # Keep bounded history
        max_keep = 2000
        if len(ids) > max_keep:
            ids = ids[-max_keep:]
        type_state["audited_ids"] = ids
        type_state["updated_at"] = datetime.datetime.utcnow().isoformat() + "Z"
        handles["_audit_state"] = {**state, audit_type: type_state}
        _save_handles(user_id, handles, async_save=True)
    except Exception as exc:
        _best_effort_debug("audit_state_update_failed", user_id=str(user_id), audit_type=audit_type, error=exc)


def _wp_audit_write_log(user_id: str, *, audit_type: str, payload: Dict[str, Any]) -> str:
    try:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        suffix = uuid.uuid4().hex[:8]
        run_id = str(payload.get("run_id") or "run")
        path = f"semantics/audits/{audit_type}/{ts}_{run_id}_{suffix}.json"
        execute_tool_call("upload_data_or_file", {"target_blob_name": path, "file_content": payload}, user_id)
        return path
    except Exception as exc:
        _best_effort_debug("audit_log_write_failed", user_id=str(user_id), audit_type=audit_type, error=exc)
        return ""


def _wp7_audit_json_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "run_id": {"type": "string"},
            "gate": {"type": "string", "enum": ["OK", "X"]},
            "integrity_metrics": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index_entries_total": {"type": "integer", "minimum": 0},
                    "artifacts_total": {"type": "integer", "minimum": 0},
                    "mapped_pairs_total": {"type": "integer", "minimum": 0},
                    "missing_artifacts_percent": {"type": "number", "minimum": 0},
                    "orphan_artifacts_percent": {"type": "number", "minimum": 0},
                    "duplicates_percent": {"type": "number", "minimum": 0},
                    "invalid_schema_percent": {"type": "number", "minimum": 0},
                },
                "required": [
                    "index_entries_total",
                    "artifacts_total",
                    "mapped_pairs_total",
                    "missing_artifacts_percent",
                    "orphan_artifacts_percent",
                    "duplicates_percent",
                    "invalid_schema_percent",
                ],
            },
            "quality_summary": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "overall_assessment": {"type": "string"},
                    "top_strengths": {"type": "array", "items": {"type": "string"}},
                    "top_weaknesses": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["overall_assessment", "top_strengths", "top_weaknesses"],
            },
            "issue_classes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string"},
                        "severity": {"type": "string", "enum": ["P0", "P1", "P2"]},
                        "description": {"type": "string"},
                        "evidence_examples": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["code", "severity", "description", "evidence_examples"],
                },
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
                        "area": {"type": "string", "enum": ["indexing", "artifact_schema", "dedup", "ranking", "logging", "validation"]},
                        "recommendation": {"type": "string"},
                        "expected_impact": {"type": "string"},
                        "verification": {"type": "string"},
                    },
                    "required": ["priority", "area", "recommendation", "expected_impact", "verification"],
                },
            },
            "wp6_impact": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "expected_change_in_top_sources_quality": {"type": "string"},
                    "expected_change_in_coverage": {"type": "string"},
                    "risks_if_unchanged": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["expected_change_in_top_sources_quality", "expected_change_in_coverage", "risks_if_unchanged"],
            },
        },
        "required": ["run_id", "gate", "integrity_metrics", "quality_summary", "issue_classes", "recommendations", "wp6_impact"],
    }


def _wp7_run_audit(
    openai_client: OpenAI,
    *,
    user_id: str,
    audit_input: Dict[str, Any],
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
) -> Dict[str, Any]:
    system_prompt = (
        "You are an auditor agent for OmniFlow WP7 (Semantic Indexer) quality.\n\n"
        "Context (backend-aware):\n"
        "- WP7 produces a semantic index JSONL at `interactions/semantic/index.jsonl` and semantic artifacts at `interactions/semantic/<interaction_id>.json`.\n"
        "- WP6 FAST later reads candidates from the WP7 index, fetches artifacts, and selects top sources. If WP7 is noisy, duplicated, inconsistent, or poorly grounded, WP6 FAST loses coverage/top_sources quality.\n\n"
        "Task:\n"
        "Given JSON with: run_id, index_entries (>=50), artifacts (>=50), audit WP7 for integrity, schema consistency, duplication/noise, signal validity, and WP6 usability.\n\n"
        "Rules:\n"
        "- Output JSON only.\n"
        "- If evidence is insufficient, gate='X' and explain in issue_classes + recommendations.\n"
        "- Be technical and evidence-based; do not invent missing fields.\n"
    )

    reasoning_effort = str(reasoning_effort or "").strip().lower()
    if reasoning_effort not in ("low", "medium", "high"):
        reasoning_effort = "medium"

    schema = _wp7_audit_json_schema()
    resp = _openai_call(
        openai_client.responses.create,
        model=str(model or WP7_AUDIT_DEFAULT_MODEL),
        reasoning={"effort": reasoning_effort},
        max_output_tokens=int(max_output_tokens or 8000),
        text={"format": {"type": "json_schema", "name": "wp7_semantic_index_audit", "strict": True, "schema": schema}},
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(audit_input, ensure_ascii=False)}]},
        ],
        metadata={"runtime": "wp7_audit", "user_id": str(user_id)},
    )

    out_text = ""
    try:
        # Similar extraction to other call sites: concatenate output_text parts.
        chunks: List[str] = []
        for item in (getattr(resp, "output", None) or []):
            if isinstance(item, dict) and item.get("type") == "message":
                for c in item.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "output_text" and c.get("text"):
                        chunks.append(str(c.get("text")))
        out_text = "".join(chunks).strip()
    except Exception:
        out_text = ""
    if not out_text:
        try:
            out_text = str(getattr(resp, "output_text", "") or "").strip()
        except Exception:
            out_text = ""

    if not out_text:
        return {"run_id": str(audit_input.get("run_id") or ""), "gate": "X", "integrity_metrics": {"index_entries_total": 0, "artifacts_total": 0, "mapped_pairs_total": 0, "missing_artifacts_percent": 100, "orphan_artifacts_percent": 100, "duplicates_percent": 0, "invalid_schema_percent": 100}, "quality_summary": {"overall_assessment": "No output_text from model", "top_strengths": [], "top_weaknesses": ["No output_text from model"]}, "issue_classes": [{"code": "no_output_text", "severity": "P0", "description": "Responses API returned no output_text.", "evidence_examples": []}], "recommendations": [{"priority": "P0", "area": "validation", "recommendation": "Inspect raw Responses output and retry.", "expected_impact": "Restores audit availability.", "verification": "Confirm model returns json_schema output_text."}], "wp6_impact": {"expected_change_in_top_sources_quality": "unknown", "expected_change_in_coverage": "unknown", "risks_if_unchanged": ["audit cannot be performed"]}}

    return json.loads(out_text)


def _wp6_prepare_audit_samples(
    user_id: str,
    *,
    count: int = 10,
    max_sources: int = 8,
    max_chars: int = 12000,
    recent_turns: int = 5,
    recent_interactions: int = 200,
    skip_already_audited: bool = True,
) -> Dict[str, Any]:
    """
    Prepare WP6 audit samples (fast_in/fast_out pairs) from `interaction_logs.json`
    and a freshly built FAST pack snapshot (from WP7 semantic artifacts).
    """
    from backend.shared.azure_client import AzureBlobClient

    count = max(1, int(count or 10))
    max_sources = max(1, int(max_sources or 8))
    max_chars = max(1, int(max_chars or 12000))
    recent_turns = max(0, int(recent_turns or 0))

    fast_ctx, fast_meta = _wp6_fast_context_from_wp7_semantic(user_id, max_sources=max_sources, max_chars=max_chars)
    selected_source_ids: List[str] = []
    for src in (fast_meta.get("candidate_sources") or []):
        if isinstance(src, dict) and src.get("path"):
            selected_source_ids.append(str(src.get("path")))

    bc = AzureBlobClient.get_blob_client("interaction_logs.json", user_id=user_id)
    raw_text = bc.download_blob().content_as_text(encoding="utf-8")
    try:
        history = json.loads(raw_text)
    except Exception:
        history = []

    interactions: List[Dict[str, Any]] = [x for x in (history or []) if isinstance(x, dict)]
    interactions.sort(key=lambda x: str(x.get("timestamp") or ""))
    if recent_interactions > 0 and len(interactions) > recent_interactions:
        interactions = interactions[-recent_interactions:]

    audited_ids: List[str] = []
    if skip_already_audited:
        handles = _load_handles(user_id)
        audited_ids = _wp_audit_state(handles, "wp6").get("audited_ids", []) if isinstance(handles, dict) else []
        audited_ids = [str(x) for x in audited_ids if str(x)]

    samples: List[Dict[str, Any]] = []
    for it in reversed(interactions):
        if len(samples) >= count:
            break
        user_message = str(it.get("user_message") or "").strip()
        assistant_text = str(it.get("assistant_response") or "").strip()
        if not user_message or not assistant_text:
            continue
        audit_id = str(it.get("interaction_id") or "").strip()
        if skip_already_audited and audit_id and audit_id in audited_ids:
            continue
        thread_id = str(it.get("thread_id") or "unknown_thread")

        routing_mode, route_reason, route_meta = _wp6_route_context_mode({}, user_message)

        turns: List[Dict[str, str]] = []
        if recent_turns > 0:
            for prev in interactions:
                if prev is it:
                    break
                if str(prev.get("thread_id") or "") != thread_id:
                    continue
                um = str(prev.get("user_message") or "").strip()
                if not um:
                    continue
                turns.append({"ts_utc": str(prev.get("timestamp") or ""), "text": um[: int(WP6_RECENT_TURNS_MAX_CHARS or 320)]})
            turns = turns[-recent_turns:]

        samples.append(
            {
                "audit_id": audit_id or uuid.uuid4().hex[:12],
                "user_id": str(user_id),
                "thread_id": thread_id,
                "created_utc": str(it.get("timestamp") or ""),
                "fast_in": {
                    "user_message": user_message,
                    "routing_mode": routing_mode,
                    "route_reason": route_reason,
                    "route_meta": route_meta,
                    "recent_user_turns": turns,
                    "fast_ctx": fast_ctx,
                    "fast_meta": {
                        **(fast_meta or {}),
                        "selected_source_ids": selected_source_ids,
                    },
                },
                "fast_out": {"assistant_text": assistant_text},
            }
        )

    samples = list(reversed(samples))
    return {
        "run_id": f"wp6_auditor_samples::{user_id}::{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
        "samples": samples,
    }


def _wp6_audit_json_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "run_id": {"type": "string"},
            "gate": {"type": "string", "enum": ["OK", "X"]},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "audit_id": {"type": "string"},
                        "gate": {"type": "string", "enum": ["OK", "X"]},
                        "reasoning_steps": {"type": "array", "items": {"type": "string"}},
                        "scores": {
                            "anyOf": [
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "relevance": {"type": "integer", "minimum": 0, "maximum": 10},
                                        "coverage": {"type": "integer", "minimum": 0, "maximum": 10},
                                        "traceability": {"type": "integer", "minimum": 0, "maximum": 10},
                                        "redundancy_inverse": {"type": "integer", "minimum": 0, "maximum": 10},
                                        "freshness": {"type": "integer", "minimum": 0, "maximum": 10},
                                        "coherence": {"type": "integer", "minimum": 0, "maximum": 10},
                                        "routing_sanity": {"type": "integer", "minimum": 0, "maximum": 10},
                                    },
                                    "required": [
                                        "relevance",
                                        "coverage",
                                        "traceability",
                                        "redundancy_inverse",
                                        "freshness",
                                        "coherence",
                                        "routing_sanity",
                                    ],
                                },
                            ]
                        },
                        "risks": {
                            "anyOf": [
                                {"type": "null"},
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "hallucination_risk": {"type": "integer", "minimum": 0, "maximum": 10},
                                        "wrong_topic_risk": {"type": "integer", "minimum": 0, "maximum": 10},
                                    },
                                    "required": ["hallucination_risk", "wrong_topic_risk"],
                                },
                            ]
                        },
                        "key_findings": {"type": "array", "items": {"type": "string"}},
                        "actionables": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
                                    "area": {"type": "string", "enum": ["pack", "ranking", "dedup", "routing", "logging"]},
                                    "recommendation": {"type": "string"},
                                    "expected_impact": {"type": "string"},
                                },
                                "required": ["priority", "area", "recommendation", "expected_impact"],
                            },
                        },
                        "traceability_map": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "claim": {"type": "string"},
                                    "support": {"type": "string", "enum": ["supported", "partially_supported", "unsupported"]},
                                    "supporting_source_ids": {"type": "array", "items": {"type": "string"}},
                                },
                                "required": ["claim", "support", "supporting_source_ids"],
                            },
                        },
                    },
                    "required": [
                        "audit_id",
                        "gate",
                        "scores",
                        "risks",
                        "key_findings",
                        "actionables",
                        "traceability_map",
                        "reasoning_steps",
                    ],
                },
            },
            "global_summary": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "samples_total": {"type": "integer", "minimum": 0},
                    "samples_ok": {"type": "integer", "minimum": 0},
                    "samples_x": {"type": "integer", "minimum": 0},
                    "top_issue_patterns": {"type": "array", "items": {"type": "string"}},
                    "top_quick_wins": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["samples_total", "samples_ok", "samples_x", "top_issue_patterns", "top_quick_wins"],
            },
        },
        "required": ["run_id", "gate", "results", "global_summary"],
    }


def _wp6_run_audit(
    openai_client: OpenAI,
    *,
    user_id: str,
    audit_samples: Dict[str, Any],
    model: str,
    reasoning_effort: str,
    max_output_tokens: int,
) -> Dict[str, Any]:
    reasoning_effort = str(reasoning_effort or "").strip().lower()
    if reasoning_effort not in ("low", "medium", "high"):
        reasoning_effort = "medium"

    system_prompt = (
        "Evaluate the quality, coverage, and answer grounding of WP6 FAST context packs using backend FAST audit artifact pairs (fast_in, fast_out). "
        "For each sample, score core quality metrics, assess risk, check field/format validity, and produce JSON-only output.\n\n"
        "Hard requirements:\n"
        "- Output strictly valid JSON.\n"
        "- reasoning_steps must be a string array (no multiline strings).\n"
        "- Keep concise: reasoning_steps<=3, key_findings<=3, actionables<=3, traceability_map<=5.\n"
    )

    schema = _wp6_audit_json_schema()
    resp = _openai_call(
        openai_client.responses.create,
        model=str(model or WP6_AUDIT_DEFAULT_MODEL),
        reasoning={"effort": reasoning_effort},
        max_output_tokens=int(max_output_tokens or 8000),
        text={"format": {"type": "json_schema", "name": "wp6_fast_pack_audit", "strict": True, "schema": schema}},
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(audit_samples, ensure_ascii=False)}]},
        ],
        metadata={"runtime": "wp6_audit", "user_id": str(user_id)},
    )

    out_text = ""
    try:
        chunks: List[str] = []
        for item in (getattr(resp, "output", None) or []):
            if isinstance(item, dict) and item.get("type") == "message":
                for c in item.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "output_text" and c.get("text"):
                        chunks.append(str(c.get("text")))
        out_text = "".join(chunks).strip()
    except Exception:
        out_text = ""
    if not out_text:
        try:
            out_text = str(getattr(resp, "output_text", "") or "").strip()
        except Exception:
            out_text = ""
    if not out_text:
        return {
            "run_id": str(audit_samples.get("run_id") or ""),
            "gate": "X",
            "results": [],
            "global_summary": {
                "samples_total": int(len((audit_samples.get("samples") or []) if isinstance(audit_samples, dict) else [])),
                "samples_ok": 0,
                "samples_x": 0,
                "top_issue_patterns": ["no_output_text_from_model"],
                "top_quick_wins": ["retry_with_higher_max_output_tokens"],
            },
        }
    return json.loads(out_text)

def _wp6_route_context_mode(body: Dict[str, Any], user_message: str) -> Tuple[str, str, Dict[str, Any]]:
    requested_raw = str(body.get("context_mode") or body.get("context") or "").strip().upper()
    requested = requested_raw or WP6_DEFAULT_CONTEXT_MODE
    if requested not in ("AUTO", "FAST", "DEEP"):
        requested = "AUTO"

    est_prompt_tokens = _wp6_est_tokens_from_text(user_message or "")
    meta = {
        "context_mode_requested": requested,
        "context_mode_source": ("request" if requested_raw else "env_default"),
        "prompt_chars": len(user_message or ""),
        "prompt_tokens_est": est_prompt_tokens,
    }

    if requested == "DEEP":
        return "DEEP", "explicit", meta
    if requested == "FAST":
        return "FAST", "explicit", meta

    # AUTO is always FAST (for now).
    return "FAST", "auto_fast", meta


def _wp6_load_cached_pack_from_handles(state: Dict[str, Any], intent_key: str) -> Tuple[str, bool]:
    try:
        pack = (state or {}).get("context_pack")
        if not isinstance(pack, dict):
            return "", False
        if str(pack.get("intent_key") or "") != str(intent_key):
            return "", False
        created_ts = float(pack.get("created_ts") or 0.0)
        if not created_ts or (time.time() - created_ts) > WP6_CONTEXT_PACK_TTL_SECONDS:
            return "", False
        pack_path = str(pack.get("path") or "").strip()
        return pack_path, bool(pack_path)
    except Exception as exc:
        _best_effort_debug("context_pack_cache_read_failed", error=exc, intent_key=intent_key)
        return "", False


def _wp6_save_pack_to_blob(user_id: str, pack: Dict[str, Any]) -> str:
    pack_id = f"pack_{uuid.uuid4().hex[:12]}"
    path = f"semantics/context_packs/{pack_id}.json"
    execute_tool_call("upload_data_or_file", {"target_blob_name": path, "file_content": pack}, user_id)
    return path


def _wp6_build_or_reuse_context_pack(
    openai_client: OpenAI,
    user_id: str,
    thread_id: str,
    user_message: str,
    state: Dict[str, Any],
    fast_ctx: str,
    intent_key: str,
    candidate_sources: list[dict] | None = None,
    max_candidates: int | None = None,
) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {"intent_key": intent_key, "pack_reused": False, "pack_path": "", "pack_tokens_est": 0}

    pack_path_cached, ok = _wp6_load_cached_pack_from_handles(state, intent_key)
    if ok:
        try:
            pack_str, _ = execute_tool_call("read_blob_file", {"file_name": pack_path_cached}, user_id)
            pack_payload = json.loads(pack_str) if isinstance(pack_str, str) else {}
            if isinstance(pack_payload, dict) and pack_payload.get("status") == "success":
                pack = pack_payload.get("data")
                if isinstance(pack, dict):
                    ok_pack, reason = _wp6_validate_context_pack(pack)
                    if ok_pack:
                        meta["pack_reused"] = True
                        meta["pack_path"] = pack_path_cached
                        meta["pack_tokens_est"] = int(pack.get("pack_tokens_est") or 0)
                        return json.dumps(pack, ensure_ascii=False), meta
                    meta["pack_cache_invalid"] = reason
        except Exception as exc:
            _best_effort_debug(
                "context_pack_cache_fetch_failed",
                user_id=str(user_id),
                thread_id=str(thread_id),
                error=exc,
                pack_path=pack_path_cached,
            )

    if not OPENAI_CONTEXT_BUILDER_PROMPT_ID:
        meta["error"] = "OPENAI_CONTEXT_BUILDER_PROMPT_ID not set"
        return "", meta

    # Contract: {request, candidate_sources[], constraints}
    cand = list(candidate_sources or [])
    if not cand:
        cand = [{"path": "interactions/semantic/index.jsonl", "excerpt_or_snippet": str(fast_ctx or "")[:1200]}]

    cb_input = {
        "request": {"user_prompt": str(user_message or "")},
        "candidate_sources": cand[: max(1, int(max_candidates or WP6_DEEP_MAX_CANDIDATE_SOURCES))],
        "constraints": {"max_pack_tokens": WP6_DEEP_MAX_PACK_TOKENS, "max_bullets": 6, "max_top_sources": 5},
    }

    ok_in, reason = _wp6_validate_context_builder_input(cb_input)
    if not ok_in:
        meta["error"] = "invalid_context_builder_input_schema"
        meta["validation_error"] = reason
        return "", meta

    cb_kwargs: Dict[str, Any] = {
        "prompt": {"id": OPENAI_CONTEXT_BUILDER_PROMPT_ID},
        # Responses API requires `input` to be a string or array of input items; provide JSON as a string.
        "input": json.dumps(cb_input, ensure_ascii=False),
        "max_output_tokens": min(WP6_DEEP_MAX_PACK_TOKENS, 8192),
        "metadata": {"user_id": str(user_id), "thread_id": str(thread_id), "runtime": "context_builder"},
    }
    cb_resp = _openai_call(openai_client.responses.create, **cb_kwargs)
    cb_text = getattr(cb_resp, "output_text", None) or ""
    try:
        pack = json.loads(cb_text) if cb_text else {}
    except Exception as exc:
        _best_effort_debug("context_pack_json_parse_failed", user_id=str(user_id), thread_id=str(thread_id), error=exc)
        pack = {}
    ok_pack, reason = _wp6_validate_context_pack(pack)
    if not ok_pack:
        meta["error"] = "invalid_context_pack_output_schema"
        meta["validation_error"] = reason
        return "", meta

    try:
        pack_path = _wp6_save_pack_to_blob(user_id, pack)
        meta["pack_path"] = pack_path
        meta["pack_tokens_est"] = int(pack.get("pack_tokens_est") or 0)
        try:
            handles = _load_handles(user_id)
            if isinstance(handles, dict):
                thread_state = handles.get(thread_id, {}) if isinstance(handles.get(thread_id), dict) else {}
                handles[thread_id] = {
                    **thread_state,
                    "context_pack": {"path": pack_path, "intent_key": intent_key, "created_ts": time.time()},
                    "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
                }
                _save_handles(user_id, handles, async_save=True)
        except Exception as exc:
            _best_effort_debug(
                "context_pack_handle_update_failed",
                user_id=str(user_id),
                thread_id=str(thread_id),
                error=exc,
                pack_path=pack_path,
            )
    except Exception as exc:
        _best_effort_debug(
            "context_pack_persist_failed",
            user_id=str(user_id),
            thread_id=str(thread_id),
            error=exc,
            intent_key=intent_key,
        )

    return json.dumps(pack, ensure_ascii=False), meta

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
            # Preserve user-relative paths (e.g. "interactions/semantic/index.jsonl").
            # If the assistant passes "users/<id>/<path>", normalize to "<path>".
            parts = [p for p in str(file_name).strip().split("/") if p]
            if len(parts) >= 3 and parts[0].lower() == "users":
                file_name = "/".join(parts[2:])
            else:
                file_name = "/".join(parts)
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
                    try:
                        # azure.functions provides HttpRequestHeaders (Mapping-like), not a dict
                        v = hdrs.get(hk) if hasattr(hdrs, "get") else None
                        if v:
                            return str(v), "header"
                    except Exception:
                        pass
                # Fallback: iterate keys for case-insensitive match if possible
                try:
                    for k, v in (hdrs.items() if hasattr(hdrs, "items") else []):
                        if k and str(k).lower() == "x-user-id" and v:
                            return str(v), "header"
                except Exception:
                    pass
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
        with CACHE_LOCK:
            cached = _handles_cache.get(str(user_id))
        if cached:
            age = time.time() - cached.get("ts", 0)
            if age <= HANDLES_CACHE_TTL_SECONDS:
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.debug(f"[DEBUG] handles cache hit user_id={user_id} age_s={age:.2f}")
                return cached.get("data", {}) or {}
            if DEBUG_TOOL_CALL_HANDLER:
                logging.debug(f"[DEBUG] handles cache expired user_id={user_id} age_s={age:.2f}")
        elif DEBUG_TOOL_CALL_HANDLER:
            logging.debug(f"[DEBUG] handles cache miss user_id={user_id}")
    elif DEBUG_TOOL_CALL_HANDLER:
        logging.debug("[DEBUG] handles cache disabled (TTL=0)")
    try:
        result_str, _info = execute_tool_call("read_blob_file", {"file_name": "handles.json"}, user_id)
        payload = json.loads(result_str) if isinstance(result_str, str) else {}
        if isinstance(payload, dict) and payload.get("status") == "success":
            data = payload.get("data")
            if isinstance(data, dict):
                if HANDLES_CACHE_TTL_SECONDS > 0:
                    with CACHE_LOCK:
                        _handles_cache[str(user_id)] = {"data": data, "ts": time.time()}
                    if DEBUG_TOOL_CALL_HANDLER:
                        logging.debug(f"[DEBUG] handles cache set user_id={user_id} entries={len(data)}")
                return data
            if isinstance(data, str):
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict):
                        if HANDLES_CACHE_TTL_SECONDS > 0:
                            with CACHE_LOCK:
                                _handles_cache[str(user_id)] = {"data": parsed, "ts": time.time()}
                            if DEBUG_TOOL_CALL_HANDLER:
                                logging.debug(f"[DEBUG] handles cache set user_id={user_id} entries={len(parsed)}")
                        return parsed
                except Exception as exc:
                    _best_effort_debug("handles_json_parse_failed", user_id=str(user_id), error=exc)
                    return {}
        if isinstance(payload, dict) and payload.get("error"):
            error_text = str(payload.get("error") or "")
            if "not found" in error_text.lower() or "blobnotfound" in error_text.lower():
                if DEBUG_TOOL_CALL_HANDLER:
                    logging.debug(f"[DEBUG] handles.json missing; initializing user_id={user_id}")
                _save_handles(user_id, {}, async_save=True)
        return {}
    except Exception as exc:
        _best_effort_debug("handles_load_failed", user_id=str(user_id), error=exc)
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
                with CACHE_LOCK:
                    _handles_cache[str(user_id)] = {"data": handles or {}, "ts": time.time()}
            if DEBUG_TOOL_CALL_HANDLER:
                logging.debug(f"[DEBUG] handles async save done user_id={user_id}")
        except Exception as exc:
            if DEBUG_TOOL_CALL_HANDLER:
                logging.debug(f"[DEBUG] handles async save failed user_id={user_id} error={exc}")

    if async_save:
        if DEBUG_TOOL_CALL_HANDLER:
            logging.debug(f"[DEBUG] handles async save queued user_id={user_id}")
        threading.Thread(target=_do_save, daemon=True).start()
        return

    try:
        _do_save()
    except Exception:
        pass


RUN_PROGRESS_MAX_EVENTS = int(os.environ.get("RUN_PROGRESS_MAX_EVENTS", "25") or 25)
RUN_PROGRESS_MIN_WRITE_INTERVAL_S = float(os.environ.get("RUN_PROGRESS_MIN_WRITE_INTERVAL_S", "0.35") or 0.35)
_RUN_PROGRESS_LOCK = threading.Lock()
_run_progress_last_write_s: Dict[str, float] = {}


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _get_run_progress(handles: Dict[str, Any], thread_id: str) -> Dict[str, Any] | None:
    if not (isinstance(handles, dict) and thread_id):
        return None
    state = handles.get(thread_id)
    if not isinstance(state, dict):
        return None
    rp = state.get("run_progress")
    return rp if isinstance(rp, dict) else None


def _update_run_progress_in_handles(
    *,
    handles: Dict[str, Any],
    user_id: str,
    thread_id: str,
    run_id: str,
    trace_id: str,
    status: str,
    stage: str,
    message: str,
    tool_name: str = "",
) -> Dict[str, Any] | None:
    """
    Store a minimal "quasi streaming" milestone state in `handles.json` under:
      handles[thread_id]["run_progress"].
    """
    if not (isinstance(handles, dict) and thread_id):
        return None
    thread_state = handles.get(thread_id, {}) if isinstance(handles.get(thread_id), dict) else {}
    prev = thread_state.get("run_progress") if isinstance(thread_state.get("run_progress"), dict) else {}
    prev_events = prev.get("events") if isinstance(prev.get("events"), list) else []

    try:
        seq = int(prev.get("seq") or 0) + 1
    except Exception:
        seq = 1

    ts_utc = _utc_now_iso()
    event = {
        "seq": seq,
        "ts_utc": ts_utc,
        "status": str(status or ""),
        "stage": str(stage or ""),
        "message": str(message or ""),
        **({"tool": str(tool_name)} if tool_name else {}),
    }
    events = [e for e in prev_events if isinstance(e, dict)]
    events.append(event)
    if RUN_PROGRESS_MAX_EVENTS > 0 and len(events) > RUN_PROGRESS_MAX_EVENTS:
        events = events[-RUN_PROGRESS_MAX_EVENTS:]

    rp = {
        "schema_version": "omniflow.run_progress.v1",
        "user_id": str(user_id or ""),
        "thread_id": str(thread_id or ""),
        "run_id": str(run_id or ""),
        "trace_id": str(trace_id or ""),
        "status": str(status or ""),
        "stage": str(stage or ""),
        "message": str(message or ""),
        "seq": seq,
        "ts_utc": ts_utc,
        "events": events,
    }

    handles[thread_id] = {
        **thread_state,
        "run_progress": rp,
        "updated_at": ts_utc,
    }
    return rp


def _emit_run_progress(
    *,
    user_id: str,
    thread_id: str,
    run_id: str,
    trace_id: str = "",
    status: str,
    stage: str,
    message: str,
    tool_name: str = "",
    async_save: bool = True,
    handles: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """Best-effort progress emitter; never raises."""
    uid = str(user_id or "").strip()
    tid = str(thread_id or "").strip()
    if not (uid and tid):
        return None

    now_s = time.time()
    key = f"{uid}:{tid}"
    try:
        with _RUN_PROGRESS_LOCK:
            last = float(_run_progress_last_write_s.get(key) or 0.0)
            if (now_s - last) < RUN_PROGRESS_MIN_WRITE_INTERVAL_S:
                return None
            _run_progress_last_write_s[key] = now_s
    except Exception:
        pass

    try:
        local_handles = handles if isinstance(handles, dict) else _load_handles(uid)
        rp = _update_run_progress_in_handles(
            handles=local_handles,
            user_id=uid,
            thread_id=tid,
            run_id=str(run_id or ""),
            trace_id=str(trace_id or ""),
            status=status,
            stage=stage,
            message=message,
            tool_name=tool_name,
        )
        if isinstance(local_handles, dict):
            _save_handles(uid, local_handles, async_save=async_save)
        return rp
    except Exception as exc:
        _best_effort_debug(
            "emit_run_progress_failed",
            user_id=uid,
            thread_id=tid,
            error=exc,
            stage=stage,
        )
        return None


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


def _persist_responses_state(user_id: str, thread_id: str, conversation_id: str, response_id: str) -> None:
    """Persist Responses continuation pointers (best-effort)."""
    if WP6_RESPONSES_STATELESS:
        return
    try:
        handles = _load_handles(user_id)
        if not isinstance(handles, dict) or not thread_id:
            return
        prev = handles.get(thread_id, {}) if isinstance(handles.get(thread_id), dict) else {}
        handles[thread_id] = {
            **prev,
            "responses_conversation_id": str(conversation_id or ""),
            "responses_last_response_id": str(response_id or ""),
            "active_runtime": "responses",
            "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
        }
        _save_handles(user_id, handles, async_save=True)
    except Exception:
        return

def _wp6_recent_turns_metadata(turns: list[str]) -> str:
    safe = [str(t or "").strip() for t in turns if str(t or "").strip()]
    if not safe:
        return ""
    if int(WP6_RECENT_TURNS_MAX or 0) > 0:
        safe = safe[-int(WP6_RECENT_TURNS_MAX) :]
    joined = "\n".join(safe)
    if len(joined) <= 512:
        return joined
    ellipsis = "…\n…\n"
    allowed = 512 - len(ellipsis)
    if allowed <= 0:
        return joined[:512]
    half = allowed // 2
    prefix = joined[:half].rstrip()
    suffix = joined[-(allowed - half) :].lstrip()
    return f"{prefix}{ellipsis}{suffix}"


def run_responses(
    openai_client: OpenAI,
    user_id: str,
    user_message: str,
    thread_id: str,
    *,
    persist_handles: bool = True,
    recent_turns: list[str] | None = None,
    run_id: str = "",
    trace_id: str = "",
    stage: str = "",
    phase: str = "",
    intent_router: Dict[str, Any] | None = None,
) -> Tuple[str, list, Dict[str, Any], str]:
    """Responses API deterministic tool loop using a Prompt ID (dual-runtime mode)."""
    if not thread_id:
        thread_id = f"handle_{uuid.uuid4().hex[:12]}"

    handles = _load_handles(user_id)
    state = handles.get(thread_id, {}) if isinstance(handles, dict) else {}

    conversation_id = ""
    previous_response_id = ""
    if not WP6_RESPONSES_STATELESS:
        conversation_id = _coerce_conversation_id(state.get("responses_conversation_id"))
        previous_response_id = str(state.get("responses_last_response_id") or "").strip()

    all_tool_calls = []
    current_input: Any = user_message or ""
    retried_without_previous = False
    responses_max_output_tokens = int(os.environ.get("RESPONSES_MAX_OUTPUT_TOKENS", "4096") or 4096)
    retried_with_smaller_output = False
    retried_after_tpm_reset = False
    recent_turns_buffer: list[str] = list(recent_turns or [])

    for iteration in range(25):
        prompt_payload: Dict[str, Any] = {"id": OPENAI_PROMPT_ID}
        if stage or phase:
            prompt_payload["variables"] = {"stage": stage, "phase": phase}
        create_kwargs: Dict[str, Any] = {
            "prompt": prompt_payload,
            "input": current_input,
            "tool_choice": "auto",
            "parallel_tool_calls": False,
            # Important: without an explicit cap, the Prompt/model defaults may request very large output budgets,
            # which can blow TPM limits even for tiny user prompts (because conversation history is server-side).
            "max_output_tokens": responses_max_output_tokens,
            "metadata": {
                "user_id": str(user_id),
                "thread_id": str(thread_id),
                "runtime": "responses",
                **({"stage": stage, "phase": phase} if (stage or phase) else {}),
                **(
                    {"recent_user_turns": _wp6_recent_turns_metadata(recent_turns_buffer)}
                    if recent_turns_buffer
                    else {}
                ),
            },
            }
        registered_call_ids = [call.get("call_id") for call in all_tool_calls if isinstance(call, dict)]
        logging.debug(
            "responses.prepare user_id=%s thread_id=%s iteration=%s tool_calls_registered=%s tool_calls_kw=%s recent_turns=%s input_type=%s",
            user_id,
            thread_id,
            iteration,
            registered_call_ids,
            create_kwargs.get("tool_calls"),
            len(recent_turns_buffer),
            type(create_kwargs.get("input")).__name__,
        )
        if (not WP6_RESPONSES_STATELESS) and conversation_id:
            create_kwargs["conversation"] = conversation_id
        # Even in stateless mode, continue the tool loop within this single request.
        # Otherwise, `function_call_output` items cannot be matched to a pending tool call.
        if previous_response_id and iteration > 0:
            create_kwargs["previous_response_id"] = previous_response_id

        try:
            response = _openai_call(openai_client.responses.create, **create_kwargs)
        except Exception as exc:
            msg = str(exc)
            # If the request exceeds TPM due to a large server-side conversation context + large output budget,
            # retry once with a much smaller max_output_tokens.
            if (
                (not retried_with_smaller_output)
                and responses_max_output_tokens > 1024
                and ("Request too large" in msg or "tokens per min" in msg or "TPM" in msg)
            ):
                retried_with_smaller_output = True
                old = responses_max_output_tokens
                responses_max_output_tokens = 1024
                logging.warning(
                    "Responses request hit TPM size limit; retrying with smaller max_output_tokens "
                    f"user_id={user_id} thread_id={thread_id} old={old} new={responses_max_output_tokens}"
                )
                continue

            # If shrinking output isn't enough, the server-side conversation history itself can exceed TPM.
            # Self-heal by resetting persisted continuation pointers for this thread, then retry once.
            if (
                (not retried_after_tpm_reset)
                and ("Request too large" in msg or "tokens per min" in msg or "TPM" in msg)
                and (previous_response_id or conversation_id)
                and isinstance(current_input, (str, bytes))
            ):
                retried_after_tpm_reset = True
                logging.warning(
                    "Responses request hit TPM size limit; resetting conversation continuation (previous_response_id + conversation) "
                    f"user_id={user_id} thread_id={thread_id}"
                )
                previous_response_id = ""
                conversation_id = ""
                # Persist cleared continuation so subsequent calls don't keep failing.
                try:
                    if isinstance(handles, dict):
                        handles[thread_id] = {
                            **(state if isinstance(state, dict) else {}),
                            "responses_conversation_id": "",
                            "responses_last_response_id": "",
                            "active_runtime": "responses",
                            "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
                        }
                        _save_handles(user_id, handles, async_save=True)
                except Exception:
                    pass
                continue
            # If the last persisted `previous_response_id` points to a response that had pending tool calls
            # (e.g., crash before tool outputs were submitted), OpenAI rejects new input with:
            # "No tool output found for function call call_...". We can safely self-heal by retrying once
            # without previous_response_id (conversation id may still be kept).
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
                if not WP6_RESPONSES_STATELESS:
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
        logging.debug(
            "responses iteration function_calls user_id=%s thread_id=%s iteration=%s calls=%s",
            user_id,
            thread_id,
            iteration,
            [{"name": call.get("name"), "call_id": call.get("call_id")} for call in function_calls],
        )
        if not function_calls:
            final_text = getattr(response, "output_text", None) or ""
            if not final_text:
                final_text = "No response from assistant."
            meta = {
                "responses_conversation_id": conversation_id,
                "responses_last_response_id": previous_response_id,
                "stage": stage,
                "phase": phase,
            }
            if intent_router:
                meta["intent_router"] = intent_router
            # Persist only after reaching a "final" response to avoid saving a response id with pending tool calls.
            try:
                if (not WP6_RESPONSES_STATELESS) and persist_handles and isinstance(handles, dict):
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
            _emit_run_progress(
                user_id=user_id,
                thread_id=thread_id,
                run_id=str(run_id or ""),
                trace_id=str(trace_id or ""),
                status="in_progress",
                stage="calling_tools",
                message=f"Calling tool: {name}",
                tool_name=str(name or ""),
                async_save=True,
                handles=handles if isinstance(handles, dict) else None,
            )
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
            resp = requests_post(
                create_url,
                json=payload,
                headers=headers,
                timeout=15,
                user_id=str(user_id),
                thread_id="",
                code="openai_rest_create_thread",
            )
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
                        logging.debug(f"[DEBUG] REST POST {msg_url} headers={_redact_sensitive(dict(headers))} payload={_redact_sensitive(payload)}")
                    resp_msg = requests_post(
                        msg_url,
                        json=payload,
                        headers=headers,
                        timeout=10,
                        user_id="",
                        thread_id=str(thread_id),
                        code="openai_rest_post_message",
                    )
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
            logging.debug(f"[DEBUG] Direct call {action} URL={url} params={_redact_sensitive(dict(params))} headers={_redact_sensitive(dict(headers))}")
        if action == "get_interaction_history":
            resp = requests_get(
                url,
                params=params,
                headers=headers,
                timeout=45,
                user_id=str(user_id_local),
                thread_id=str(thread_id or ""),
                code="direct_action_get_history",
            )
        else:
            resp = requests_post(
                url,
                json=params,
                headers=headers,
                timeout=45,
                user_id=str(user_id_local),
                thread_id=str(thread_id or ""),
                code="direct_action_post",
            )
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
            logging.debug(f"[DEBUG] Direct response status={resp.status_code} body={_redact_sensitive(snippet if isinstance(snippet, dict) else {'raw': snippet})}")
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
            resp = requests_post(
                runs_url,
                json=payload,
                headers=headers,
                timeout=15,
                user_id=str(user_id),
                thread_id=str(thread_id),
                code="openai_rest_create_run",
            )
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
        save_interaction_log_inprocess(
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
    dispatch_args = params_with_user
    logging.debug(f"Dispatching tool={tool_name} with params={dispatch_args}")

    # WP6.M1 preferences enforcement (best-effort).
    # Goal: reduce costly/history reads and prevent agent "browsing" beyond allowlisted files.
    try:
        # Prevent recursion while loading preferences.
        if not getattr(_prefs_loading, "active", False):
            prefs = _load_preferences(user_id)
            allowed, reason = _wp6_allowed_to_read(tool_name, normalized_args, prefs)
            if not allowed:
                duration_ms = (time.time() - start_time) * 1000
                info = {
                    "tool_name": tool_name,
                    "arguments": dispatch_args,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error": reason,
                    "code": "preferences_blocked",
                }
                return json.dumps({"error": reason, "code": "preferences_blocked"}), info
    except Exception as exc:
        _best_effort_debug("preferences_enforcement_failed", user_id=str(user_id), error=exc, tool_name=tool_name)

    # Phase 2: Try registry-driven dispatch first (if available)
    if REGISTRY_DISPATCH_AVAILABLE:
        try:
            context = {"trace_id": f"tool-{tool_name}-{user_id[:8]}"}
            result = registry_dispatch(
                tool_name=tool_name,
                params=normalized_args,
                user_id=user_id,
                context=context
            )
            duration_ms = (time.time() - start_time) * 1000
            
            # Handle registry dispatch response
            if result.get("status") == "error":
                # Error from registry dispatch
                info = {
                    "tool_name": tool_name,
                    "arguments": dispatch_args,
                    "status": "failed",
                    "duration_ms": duration_ms,
                    "error": result.get("error", "Unknown error"),
                    "code": result.get("code", "INTERNAL_ERROR"),
                }
                return json.dumps(result), info
            else:
                # Success from registry dispatch
                info = {
                    "tool_name": tool_name,
                    "arguments": dispatch_args,
                    "result": result.get("result", result),
                    "status": "success",
                    "duration_ms": duration_ms
                }
                logging.info(f"Tool {tool_name} OK via registry dispatch in {duration_ms:.1f}ms")
                # Return the result payload (unwrap if needed)
                return json.dumps(result.get("result", result)), info
        except Exception as e:
            logging.warning(f"Registry dispatch failed for {tool_name}: {e}. Falling back to legacy dispatch.")
    
    # Fallback: Try legacy in-process dispatch
    try:
        from tools import dispatch_tool
        inprocess_args = dict(dispatch_args or {})
        inprocess_args.pop("user_id", None)
        result = dispatch_tool(tool_name, inprocess_args, user_id)
        duration_ms = (time.time() - start_time) * 1000
        info = {"tool_name": tool_name, "arguments": dispatch_args, "result": result, "status": "success", "duration_ms": duration_ms}
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

        # Prefer catalog-driven allowlists when available (keeps tool routing
        # aligned with AGENT_FUNCTIONS_CATALOG.json).
        try:
            from shared.agent_functions_catalog import allowed_fields_for_tool

            manifest_fields = [
                field
                for field in allowed_fields_for_tool(tool_name)
                if field and field != "user_id"
            ]
            if manifest_fields:
                DATA_EXTRACTION_REQUIRED[tool_name] = manifest_fields
        except Exception as exc:
            _best_effort_debug(
                "agent_functions_catalog_load_failed",
                user_id=str(user_id),
                error=exc,
                tool_name=tool_name,
            )

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

        dispatch_args = filtered_args if "filtered_args" in locals() else params_with_user
        logging.debug(f"Dispatching tool={tool_name} with params={dispatch_args}")
    dispatch_args = filtered_args if "filtered_args" in locals() else params_with_user
    headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
    if PROXY_FUNCTION_KEY:
        headers["x-functions-key"] = PROXY_FUNCTION_KEY

    # Hard validation for manage_files to avoid bad requests
    if tool_name == "manage_files":
        op = dispatch_args.get("operation")
        src = dispatch_args.get("source_name")
        tgt = dispatch_args.get("target_name")
        if op is None:
            err = "manage_files requires 'operation' (rename/delete)"
            info = {"tool_name": tool_name, "arguments": dispatch_args, "error": err, "status": "failed", "duration_ms": 0}
            return json.dumps({"error": err}), info
        if op not in ["rename", "delete"]:
            err = f"manage_files operation '{op}' is not supported. Use list_blobs for listing."
            info = {"tool_name": tool_name, "arguments": dispatch_args, "error": err, "status": "failed", "duration_ms": 0}
            return json.dumps({"error": err}), info
        if not src:
            err = "manage_files requires 'source_name'"
            info = {"tool_name": tool_name, "arguments": dispatch_args, "error": err, "status": "failed", "duration_ms": 0}
            return json.dumps({"error": err}), info
        if op == "rename" and not tgt:
            err = "manage_files rename requires 'target_name'"
            info = {"tool_name": tool_name, "arguments": dispatch_args, "error": err, "status": "failed", "duration_ms": 0}
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
                logging.debug(f"[DEBUG] GET {func_url} params={_redact_sensitive(dict(dispatch_args))} headers={_redact_sensitive(dict(headers))}")
            try:
                resp = requests_get(
                    func_url,
                    params=dispatch_args,
                    headers=headers,
                    timeout=45,
                    user_id=str(user_id),
                    thread_id="",
                    code="execute_tool_call_get_history",
                )
                resp.raise_for_status()
                try:
                    result = resp.json()
                except ValueError:
                    result = {"raw_response": resp.text}
            except requests.RequestException as e:
                duration_ms = (time.time() - start_time) * 1000
                logging.warning(f"GET {func_url} failed: {e}")
                info = {"tool_name": tool_name, "arguments": dispatch_args, "error": str(e), "status": "failed", "duration_ms": duration_ms}
                return json.dumps({"error": str(e)}), info
        else:
            if not PROXY_URL:
                err = "AZURE_PROXY_URL not configured"
                duration_ms = (time.time() - start_time) * 1000
                info = {"tool_name": tool_name, "arguments": dispatch_args, "error": err, "status": "failed", "duration_ms": duration_ms}
                logging.error(err)
                return json.dumps({"error": err}), info
            # When dispatching via proxy, prefer the filtered argument set constructed
            # above to avoid leaking assistant-supplied or extraneous fields.
            payload = {"action": tool_name, "params": dispatch_args}
            if DEBUG_TOOL_CALL_HANDLER:
                logging.debug(f"[DEBUG] POST {PROXY_URL} json={_redact_sensitive(payload)} headers={_redact_sensitive(dict(headers))}")
            try:
                resp = requests_post(
                    PROXY_URL,
                    json=payload,
                    headers=headers,
                    timeout=45,
                    user_id=str(user_id),
                    thread_id="",
                    code="execute_tool_call_proxy_post",
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                duration_ms = (time.time() - start_time) * 1000
                logging.warning(f"POST to proxy failed: {e}")
                info = {"tool_name": tool_name, "arguments": dispatch_args, "error": str(e), "status": "failed", "duration_ms": duration_ms}
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
            logging.debug(f"[DEBUG] Response status={getattr(resp, 'status_code', 'n/a')} body={_redact_sensitive(body_snippet if isinstance(body_snippet, dict) else {'raw': body_snippet})}")
        duration_ms = (time.time() - start_time) * 1000
        info = {"tool_name": tool_name, "arguments": dispatch_args, "result": result, "status": "success", "duration_ms": duration_ms}
        logging.info(f"Tool {tool_name} OK via proxy_router in {duration_ms:.1f}ms")
        return json.dumps(result), info
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        if DEBUG_TOOL_CALL_HANDLER:
            logging.exception(f"Tool {tool_name} failed in {duration_ms:.1f}ms: {e}")
        else:
            logging.error(f"Tool {tool_name} failed in {duration_ms:.1f}ms: {e}")
        info = {"tool_name": tool_name, "arguments": dispatch_args, "error": str(e), "status": "failed", "duration_ms": duration_ms}
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
                    logging.debug(f"[DEBUG] save_interaction in-process done body={body_text[:500]}")
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
                    logging.warning(f"save_interaction in-process failed: {inproc_exc}; falling back to HTTP")

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
                r = requests_post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=(1, 10),
                    user_id=str(user_id),
                    thread_id=str(thread_id or ""),
                    code="save_interaction_fire_and_forget",
                )
                if DEBUG_TOOL_CALL_HANDLER:
                    try:
                        snippet = (r.text or "")[:500]
                    except Exception:
                        snippet = "<unreadable>"
                    logging.debug(f"[DEBUG] save_interaction http status={getattr(r,'status_code','n/a')} body={snippet}")
            except Exception as post_exc:
                logging.warning(f"save_interaction_log failed: {post_exc}")

        threading.Thread(target=_fire_and_forget, daemon=True).start()
    except Exception as e:
        logging.warning(f"save_interaction_log failed: {e}")


def save_interaction_log_inprocess(
    user_id: str,
    user_message: str,
    assistant_response: str,
    thread_id: str,
    tool_calls_info: list,
):
    if not ENABLE_SAVE_INTERACTION:
        return

    def _fire_and_forget():
        try:
            from save_interaction.service import save_interaction_entry

            result = save_interaction_entry(
                user_id=str(user_id),
                user_message=str(user_message or ""),
                assistant_response=str(assistant_response or ""),
                thread_id=str(thread_id or "") if thread_id is not None else None,
                tool_calls=tool_calls_info or [],
                metadata={"assistant_id": ASSISTANT_ID, "source": "tool_call_handler"},
            )
            if DEBUG_TOOL_CALL_HANDLER:
                logging.debug(f"[DEBUG] save_interaction in-process result={_redact_sensitive(result)}")
        except Exception as exc:
            logging.warning(f"save_interaction_log failed (in-process): {exc}")

    threading.Thread(target=_fire_and_forget, daemon=True).start()


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
        trace_id = str(body.get("trace_id") or "").strip()

        # Direct actions bypass agent/tool loop
        if action in ["save_interaction", "get_interaction_history"]:
            resp_direct = handle_direct_actions(req, body, action, user_id)
            if resp_direct is not None:
                return resp_direct

        if action == "get_run_progress":
            if not user_id:
                return _make_response({"error": "user_id is required", "action": action}, status_code=400)
            if not thread_id:
                return _make_response({"error": "thread_id is required", "action": action}, status_code=400)
            handles = _load_handles(str(user_id))
            rp = _get_run_progress(handles if isinstance(handles, dict) else {}, str(thread_id))
            return _make_response(
                {
                    "status": "success",
                    "action": action,
                    "user_id": str(user_id),
                    "thread_id": str(thread_id),
                    "has_progress": bool(isinstance(rp, dict) and rp),
                    "run_progress": rp or {},
                },
                status_code=200,
            )

        if action in ["wp7_prepare_audit", "wp7_run_audit"]:
            if not user_id:
                return _make_response({"error": "user_id is required"}, status_code=400)
            # WP7 audit does not require AZURE_PROXY_URL; it reads blobs via connection string and calls OpenAI directly.
            if not OPENAI_API_KEY:
                return _make_response({"error": "Missing env vars: OPENAI_API_KEY", "status": "not_configured"}, status_code=503)
            params = body.get("params", {}) or {}
            try:
                if action == "wp7_prepare_audit":
                    count = int(params.get("count", 50) or 50)
                    max_scan = int(params.get("max_scan", 500) or 500)
                    skip_already = bool(params.get("skip_already_audited", True))
                    audit_input = _wp7_prepare_audit_input(
                        str(user_id),
                        count=count,
                        max_scan=max_scan,
                        skip_already_audited=skip_already,
                    )
                    return _make_response({"status": "success", "result": audit_input}, status_code=200)

                # wp7_run_audit
                model = str(params.get("model") or WP7_AUDIT_DEFAULT_MODEL).strip()
                reasoning_effort = str(params.get("reasoning_effort") or WP7_AUDIT_DEFAULT_REASONING_EFFORT).strip().lower()
                max_output_tokens = int(params.get("max_output_tokens", 8000) or 8000)
                audit_input = params.get("audit_input")
                if not isinstance(audit_input, dict):
                    # Convenience: if not provided, prepare now (default 50).
                    audit_input = _wp7_prepare_audit_input(str(user_id), count=50)
                openai_client = OpenAI(api_key=OPENAI_API_KEY)
                result = _wp7_run_audit(
                    openai_client,
                    user_id=str(user_id),
                    audit_input=audit_input,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    max_output_tokens=max_output_tokens,
                )
                # Persist audited IDs + log run
                audited_ids = []
                try:
                    audited_ids = [
                        str(x.get("interaction_id"))
                        for x in (audit_input.get("index_entries") or [])
                        if isinstance(x, dict) and x.get("interaction_id")
                    ]
                except Exception:
                    audited_ids = []
                _wp_audit_update_state(str(user_id), audit_type="wp7", audited_ids=audited_ids)
                _wp_audit_write_log(
                    str(user_id),
                    audit_type="wp7",
                    payload={
                        "run_id": str(audit_input.get("run_id") or ""),
                        "user_id": str(user_id),
                        "audit_type": "wp7",
                        "model": model,
                        "reasoning_effort": reasoning_effort,
                        "max_output_tokens": max_output_tokens,
                        "selected_interaction_ids": audited_ids,
                        "result_summary": {
                            "gate": result.get("gate"),
                            "integrity_metrics": result.get("integrity_metrics"),
                        },
                        "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
                    },
                )
                return _make_response({"status": "success", "result": result}, status_code=200)
            except Exception as exc:
                _best_effort_debug("wp7_audit_action_failed", user_id=str(user_id), thread_id=str(thread_id or ""), error=exc, action=action)
                return _make_response({"status": "error", "error": str(exc), "action": action}, status_code=500)

        if action in ["wp6_prepare_audit", "wp6_run_audit"]:
            if not user_id:
                return _make_response({"error": "user_id is required"}, status_code=400)
            # WP6 audit does not require AZURE_PROXY_URL; it reads blobs via connection string and calls OpenAI directly.
            if not OPENAI_API_KEY:
                return _make_response({"error": "Missing env vars: OPENAI_API_KEY", "status": "not_configured"}, status_code=503)
            params = body.get("params", {}) or {}
            try:
                if action == "wp6_prepare_audit":
                    audit_samples = _wp6_prepare_audit_samples(
                        str(user_id),
                        count=int(params.get("count", 10) or 10),
                        max_sources=int(params.get("max_sources", 8) or 8),
                        max_chars=int(params.get("max_chars", 12000) or 12000),
                        recent_turns=int(params.get("recent_turns", 5) or 5),
                        recent_interactions=int(params.get("recent_interactions", 200) or 200),
                        skip_already_audited=bool(params.get("skip_already_audited", True)),
                    )
                    return _make_response({"status": "success", "result": audit_samples}, status_code=200)

                model = str(params.get("model") or WP6_AUDIT_DEFAULT_MODEL).strip()
                reasoning_effort = str(params.get("reasoning_effort") or WP6_AUDIT_DEFAULT_REASONING_EFFORT).strip().lower()
                max_output_tokens = int(params.get("max_output_tokens", 8000) or 8000)
                audit_samples = params.get("audit_samples")
                if not isinstance(audit_samples, dict):
                    audit_samples = _wp6_prepare_audit_samples(str(user_id), count=10, max_sources=8, max_chars=12000, recent_turns=5)
                openai_client = OpenAI(api_key=OPENAI_API_KEY)
                result = _wp6_run_audit(
                    openai_client,
                    user_id=str(user_id),
                    audit_samples=audit_samples,
                    model=model,
                    reasoning_effort=reasoning_effort,
                    max_output_tokens=max_output_tokens,
                )
                audited_ids = []
                try:
                    audited_ids = [
                        str(x.get("audit_id"))
                        for x in (audit_samples.get("samples") or [])
                        if isinstance(x, dict) and x.get("audit_id")
                    ]
                except Exception:
                    audited_ids = []
                _wp_audit_update_state(str(user_id), audit_type="wp6", audited_ids=audited_ids)
                _wp_audit_write_log(
                    str(user_id),
                    audit_type="wp6",
                    payload={
                        "run_id": str(audit_samples.get("run_id") or ""),
                        "user_id": str(user_id),
                        "audit_type": "wp6",
                        "model": model,
                        "reasoning_effort": reasoning_effort,
                        "max_output_tokens": max_output_tokens,
                        "selected_audit_ids": audited_ids,
                        "result_summary": {
                            "gate": result.get("gate"),
                            "global_summary": result.get("global_summary"),
                        },
                        "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
                    },
                )
                return _make_response({"status": "success", "result": result}, status_code=200)
            except Exception as exc:
                _best_effort_debug("wp6_audit_action_failed", user_id=str(user_id), thread_id=str(thread_id or ""), error=exc, action=action)
                return _make_response({"status": "error", "error": str(exc), "action": action}, status_code=500)

        if OMNIFLOW_MOCK_AGENT:
            forced_user_id = mock_user_id()
            mock_thread_id = str(thread_id or "mock_thread")
            body_mock = build_mock_agent_response(
                agent="wp6",
                user_id=str(forced_user_id),
                thread_id=mock_thread_id,
                user_message=str(user_message or ""),
                marker=mock_marker("wp6"),
            )
            return _make_response(body_mock, status_code=200)

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
                wp6_meta: Dict[str, Any] = {}
                if not thread_id:
                    thread_id = f"handle_{uuid.uuid4().hex[:12]}"
                run_id = uuid.uuid4().hex[:12]
                _emit_run_progress(
                    user_id=str(user_id),
                    thread_id=str(thread_id),
                    run_id=run_id,
                    trace_id=trace_id,
                    status="in_progress",
                    stage="grasping_context",
                    message="Starting: building context",
                    async_save=True,
                )

                recent_turns = _wp6_update_recent_user_turns(user_id, str(thread_id), user_message)
                recent_block = _wp6_format_recent_turns(recent_turns)
                wp6_meta["recent_user_turns_count"] = int(len(recent_turns or []))
                wp6_meta["recent_user_turns_chars"] = int(sum(len(str(t or "")) for t in (recent_turns or [])))

                requested_stage = str(body.get("stage") or "").strip().upper()
                requested_phase = str(body.get("phase") or "").strip().upper()
                intent_router = None
                if not requested_stage or not requested_phase:
                    intent_router = _pa_intent_router(user_message)
                    if not requested_stage:
                        requested_stage = str(intent_router.get("recommended_stage") or "").strip().upper()
                    if not requested_phase:
                        requested_phase = str(intent_router.get("recommended_phase") or "").strip().upper()
                if not requested_stage:
                    requested_stage = "DECISION_SUPPORT"
                if not requested_phase:
                    requested_phase = "DISCOVERY"
                wp6_meta["pa_stage"] = requested_stage
                wp6_meta["pa_phase"] = requested_phase
                if intent_router:
                    wp6_meta["pa_intent_router"] = intent_router
                logging.info(
                    "PA routing stage=%s phase=%s need_clarification=%s",
                    requested_stage,
                    requested_phase,
                    bool(intent_router and intent_router.get("need_clarification")),
                )

                audit_id = uuid.uuid4().hex[:12] if WP6_FAST_AUDIT_ENABLED else ""
                audit_in_path = ""
                audit_out_path = ""

                routed_mode, route_reason, route_meta = _wp6_route_context_mode(body, user_message)

                # Build bounded FAST semantic context (used also as an input for DEEP builder).
                fast_ctx, fast_meta = _wp6_fast_context_from_wp7_semantic(
                    user_id=user_id,
                    max_sources=min(WP6_FAST_MAX_SOURCES, 10),
                    max_chars=min(WP6_FAST_MAX_RAW_BYTES, WP6_FAST_MAX_INPUT_TOKENS * 4),
                )
                wp6_meta = {**route_meta, **fast_meta}
                try:
                    wp6_meta["recent_user_turns_count"] = int(len(recent_turns or []))
                    wp6_meta["recent_user_turns_chars"] = int(sum(len(str(t or "")) for t in (recent_turns or [])))
                except Exception:
                    pass

                handles_for_thread = _load_handles(user_id)
                state_for_thread = (
                    handles_for_thread.get(thread_id, {}) if (thread_id and isinstance(handles_for_thread, dict)) else {}
                )
                intent_key = _wp6_norm_intent_key(user_message)
                wp6_meta["intent_key"] = intent_key

                # Minimum input evidence for DEEP builder (Context Builder has no tools).
                core_sources, core_meta = _wp6_core_candidate_sources_tm_lo_ps(user_id)
                wp6_meta["core_snippets_count"] = int((core_meta or {}).get("core_snippets_count") or 0)
                wp6_meta["core_snippets_bytes"] = int((core_meta or {}).get("core_snippets_bytes") or 0)

                semantic_selected = int((fast_meta or {}).get("selected_sources_count") or 0)
                semantic_candidates = int((fast_meta or {}).get("semantic_candidates_count") or 0)
                deep_allowed_inputs = (
                    semantic_selected >= int(WP6_DEEP_MIN_SEMANTIC_SELECTED)
                    or semantic_candidates >= int(WP6_DEEP_MIN_SEMANTIC_CANDIDATES)
                    or int(wp6_meta.get("core_snippets_count") or 0) >= 3
                )
                wp6_meta["deep_allowed_inputs"] = bool(deep_allowed_inputs)
                wp6_meta["deep_allowed_inputs_semantic_selected"] = semantic_selected
                wp6_meta["deep_allowed_inputs_semantic_candidates"] = semantic_candidates

                # Cooldown is applied only for AUTO-mode escalations to avoid repeated costly DEEP runs.
                cooldown_ok, cooldown_reason = _wp6_deep_cooldown_allowed(state_for_thread if isinstance(state_for_thread, dict) else {})
                wp6_meta["deep_cooldown_ok"] = bool(cooldown_ok)
                wp6_meta["deep_cooldown_reason"] = cooldown_reason

                requested_mode = str(route_meta.get("context_mode_requested") or "AUTO").upper()
                auto_mode = requested_mode == "AUTO"
                deep_allowed = bool(deep_allowed_inputs) and (bool(cooldown_ok) if auto_mode else True)
                wp6_meta["deep_allowed"] = bool(deep_allowed)

                # FAST input (evidence-lite) is always built; used both for FAST run and as seed for DEEP builder.
                fast_input_message = user_message
                if fast_ctx:
                    fast_input_message = f"[FAST_CONTEXT]\n{fast_ctx}\n\n[USER_MESSAGE]\n{user_message}"
                if recent_block:
                    fast_input_message = f"{recent_block}\n\n{fast_input_message}"

                # Routing: AUTO defaults to FAST; DEEP can be entered:
                # - deterministically (e.g., FAST context empty) before first call, or
                # - agent-driven after FAST via need_deep/__ROUTE_DEEP__ signal.
                mode_initial = "FAST"
                reason_initial = route_reason
                if requested_mode == "DEEP":
                    mode_initial = "DEEP"
                    reason_initial = "explicit"
                elif requested_mode == "FAST":
                    mode_initial = "FAST"
                    reason_initial = "explicit"
                else:
                    if deep_allowed and not str(fast_ctx or "").strip():
                        mode_initial = "DEEP"
                        reason_initial = "fast_context_empty"
                    else:
                        mode_initial = "FAST"
                        reason_initial = "auto_fast"

                wp6_meta["routing"] = {
                    "mode_requested": requested_mode,
                    "mode_initial": mode_initial,
                    "reason_initial": reason_initial,
                    "deep_allowed": bool(deep_allowed),
                }

                if audit_id:
                    try:
                        fast_ctx_trunc = str(fast_ctx or "")
                        if int(WP6_FAST_AUDIT_MAX_CHARS or 0) > 0:
                            fast_ctx_trunc = fast_ctx_trunc[: int(WP6_FAST_AUDIT_MAX_CHARS)]
                        fast_limits = {
                            "max_sources_requested": int((fast_meta or {}).get("max_sources_requested") or 0),
                            "max_chars_requested": int((fast_meta or {}).get("max_chars_requested") or 0),
                            "fast_max_input_tokens": int(WP6_FAST_MAX_INPUT_TOKENS or 0),
                            "fast_max_raw_bytes": int(WP6_FAST_MAX_RAW_BYTES or 0),
                        }
                        fast_selected_ids = list((fast_meta or {}).get("selected_source_ids") or [])
                        payload_in = {
                            "schema_version": "omniflow.wp6.fast_audit.v1",
                            "kind": "fast_in",
                            "audit_id": audit_id,
                            "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
                            "user_id": str(user_id),
                            "thread_id": str(thread_id),
                            "stateless": bool(WP6_RESPONSES_STATELESS),
                            "intent_key": str(intent_key),
                            "routing": dict(wp6_meta.get("routing") or {}),
                            "recent_user_turns": list(recent_turns or []),
                            "fast_ctx": fast_ctx_trunc,
                            "limits": fast_limits,
                            "fast_meta": {
                                "semantic_candidates_count": int((fast_meta or {}).get("semantic_candidates_count") or 0),
                                "selected_sources_count": int((fast_meta or {}).get("selected_sources_count") or 0),
                                "raw_bytes_read": int((fast_meta or {}).get("raw_bytes_read") or 0),
                                "candidate_sources": list((fast_meta or {}).get("candidate_sources") or []),
                                "selected_source_ids": fast_selected_ids,
                            },
                        }
                        audit_in_path = _wp6_write_fast_audit(
                            user_id,
                            str(thread_id),
                            audit_id=audit_id,
                            kind="fast_in",
                            payload=payload_in,
                        )
                    except Exception as exc:
                        _best_effort_debug("wp6_fast_audit_in_failed", user_id=str(user_id), thread_id=str(thread_id), error=exc)

                # For AUTO we delay persisting response continuation until we know if we escalate to DEEP.
                persist_in_run = not auto_mode
                escalations_used = 0

                mode_used = mode_initial
                mode_reason = reason_initial

                # Helper: build Context Builder pack input and return model input message (or "" on failure).
                def _build_deep_input_message() -> Tuple[str, Dict[str, Any]]:
                    # Merge core snippets (TM/LO/PS) with semantic sources; keep order and dedupe by path.
                    merged_sources: list[dict] = []
                    seen_paths: set[str] = set()
                    for src in (core_sources or []) + list((fast_meta or {}).get("candidate_sources") or []):
                        if not isinstance(src, dict):
                            continue
                        pth = str(src.get("path") or "").strip()
                        if not pth or pth in seen_paths:
                            continue
                        merged_sources.append(src)
                        seen_paths.add(pth)

                    max_candidates_eff = WP6_DEEP_MAX_CANDIDATE_SOURCES + (
                        2 if int(wp6_meta.get("core_snippets_count") or 0) >= 3 else 0
                    )
                    wp6_meta["deep_max_candidates_eff"] = int(max_candidates_eff)
                    wp6_meta["deep_candidate_sources_count"] = int(len(merged_sources))

                    pack_text, pack_meta = _wp6_build_or_reuse_context_pack(
                        openai_client=openai_client,
                        user_id=user_id,
                        thread_id=str(thread_id or ""),
                        user_message=user_message,
                        state=state_for_thread if isinstance(state_for_thread, dict) else {},
                        fast_ctx=fast_ctx,
                        intent_key=intent_key,
                        candidate_sources=merged_sources,
                        max_candidates=max_candidates_eff,
                    )
                    return (f"[CONTEXT_PACK_JSON]\n{pack_text}\n\n[USER_MESSAGE]\n{user_message}" if pack_text else ""), pack_meta

                # Run phase 1 (FAST by default, or DEEP deterministically).
                model_input_message = fast_input_message
                if mode_initial == "DEEP":
                    if deep_allowed_inputs:
                        deep_input_message, pack_meta = _build_deep_input_message()
                        wp6_meta.update(pack_meta)
                        if deep_input_message:
                            model_input_message = deep_input_message
                            mode_used = "DEEP"
                            mode_reason = reason_initial
                        else:
                            mode_used = "FAST"
                            mode_reason = f"deep_fallback:{pack_meta.get('error') or 'no_pack'}"
                            model_input_message = fast_input_message
                    else:
                        mode_used = "FAST"
                        mode_reason = "deep_skipped_insufficient_inputs"
                        model_input_message = fast_input_message

                _emit_run_progress(
                    user_id=str(user_id),
                    thread_id=str(thread_id),
                    run_id=run_id,
                    trace_id=trace_id,
                    status="in_progress",
                    stage=("looking_more_data" if mode_initial == "DEEP" else "grasping_context"),
                    message=("Routing to DEEP" if mode_initial == "DEEP" else "Routing to FAST"),
                    async_save=True,
                )
                assistant_response, all_tool_calls, responses_meta, thread_id = run_responses(
                    openai_client=openai_client,
                    user_id=user_id,
                    user_message=model_input_message,
                    thread_id=thread_id,
                    persist_handles=persist_in_run,
                    recent_turns=recent_turns,
                    run_id=run_id,
                    trace_id=trace_id,
                    stage=requested_stage,
                    phase=requested_phase,
                    intent_router=intent_router,
                )

                # Phase 2 (AUTO only): parse FAST response signal and optionally escalate to DEEP once.
                if auto_mode and mode_used == "FAST":
                    signal, cleaned = _wp6_parse_need_deep_signal(assistant_response or "")
                    wp6_meta["need_deep_signal"] = signal
                    assistant_response = cleaned

                    if bool(signal.get("need_deep")):
                        wp6_meta["routing"]["need_deep_from_model"] = True
                        wp6_meta["routing"]["parse_status"] = str(signal.get("parse_status") or "none")
                        wp6_meta["routing"]["escalations_used"] = escalations_used

                        if deep_allowed and escalations_used == 0:
                            escalations_used = 1
                            deep_input_message, pack_meta = _build_deep_input_message()
                            wp6_meta.update(pack_meta)
                            if deep_input_message:
                                _emit_run_progress(
                                    user_id=str(user_id),
                                    thread_id=str(thread_id),
                                    run_id=run_id,
                                    trace_id=trace_id,
                                    status="in_progress",
                                    stage="looking_more_data",
                                    message="Escalating: building DEEP context",
                                    async_save=True,
                                )
                                mode_used = "DEEP"
                                mode_reason = "agent_need_deep"
                                wp6_meta["routing"]["escalated"] = True
                                wp6_meta["routing"]["escalations_used"] = escalations_used
                                deep_resp, deep_calls, deep_meta, thread_id = run_responses(
                                    openai_client=openai_client,
                                    user_id=user_id,
                                    user_message=deep_input_message,
                                    thread_id=thread_id,
                                    persist_handles=persist_in_run,
                                    recent_turns=recent_turns,
                                    run_id=run_id,
                                    trace_id=trace_id,
                                    stage=requested_stage,
                                    phase=requested_phase,
                                    intent_router=intent_router,
                                )
                                deep_signal, deep_cleaned = _wp6_parse_need_deep_signal(deep_resp or "")
                                wp6_meta["need_deep_signal_deep"] = deep_signal
                                assistant_response = deep_cleaned
                                all_tool_calls = list(all_tool_calls or []) + list(deep_calls or [])
                                responses_meta = deep_meta
                            else:
                                wp6_meta["routing"]["escalated"] = False
                                wp6_meta["routing"]["escalation_block_reason"] = "no_context_pack"
                        else:
                            wp6_meta["routing"]["escalated"] = False
                            wp6_meta["routing"]["escalation_block_reason"] = (
                                "deep_disallowed" if not deep_allowed else "already_escalated"
                            )
                            missing = signal.get("missing") or []
                            why = str(signal.get("why") or "").strip()
                            if missing or why:
                                note = "DEEP blocked"
                                if why:
                                    note += f": {why}"
                                if missing:
                                    note += f" (missing: {', '.join([str(x) for x in missing][:5])})"
                                assistant_response = (assistant_response or "").rstrip() + "\n\n" + note
                    else:
                        wp6_meta["routing"]["need_deep_from_model"] = False
                        wp6_meta["routing"]["parse_status"] = str(signal.get("parse_status") or "none")
                        wp6_meta["routing"]["escalated"] = False

                try:
                    if isinstance(wp6_meta.get("routing"), dict):
                        wp6_meta["routing"]["mode_used"] = mode_used
                        wp6_meta["routing"]["reason_used"] = mode_reason
                        wp6_meta["routing"]["escalations_used"] = int(escalations_used or 0)
                except Exception:
                    pass

                # Persist continuation pointers for AUTO after deciding whether we escalated.
                if auto_mode and isinstance(responses_meta, dict):
                    _persist_responses_state(
                        user_id=user_id,
                        thread_id=str(thread_id or ""),
                        conversation_id=str(responses_meta.get("responses_conversation_id") or ""),
                        response_id=str(responses_meta.get("responses_last_response_id") or ""),
                    )

                # Persist last intent for deterministic topic-change routing (best-effort).
                try:
                    if isinstance(handles_for_thread, dict) and thread_id:
                        thread_state = handles_for_thread.get(thread_id, {}) if isinstance(handles_for_thread.get(thread_id), dict) else {}
                        handles_for_thread[thread_id] = {
                            **thread_state,
                            "wp6_last_intent_key": intent_key,
                            "wp6_last_intent_ts": time.time(),
                            "wp6_last_deep_at": (time.time() if mode_used == "DEEP" else float(thread_state.get("wp6_last_deep_at") or 0.0)),
                            "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
                        }
                        _save_handles(user_id, handles_for_thread, async_save=True)
                except Exception:
                    pass

                wp6_meta["context_mode_used"] = mode_used
                wp6_meta["context_mode_reason"] = mode_reason
                wp6_meta["fast_ctx_tokens_est"] = _wp6_est_tokens_from_text(fast_ctx or "")
                wp6_meta["fast_ctx_chars"] = len(fast_ctx or "")

                logging.info(
                    "WP6 route user_id=%s mode=%s reason=%s prompt_tokens_est=%s selected_sources=%s raw_bytes=%s",
                    user_id,
                    mode_used,
                    mode_reason,
                    wp6_meta.get("prompt_tokens_est"),
                    wp6_meta.get("selected_sources_count"),
                    wp6_meta.get("raw_bytes_read"),
                )
            except RuntimeError as rexc:
                return _make_response({"error": str(rexc), "runtime": "responses"}, status_code=500)
            except Exception as exc:
                logging.exception(f"Failed during responses loop: {exc}")
                return _make_response({"error": "Internal server error", "details": str(exc), "runtime": "responses"}, status_code=500)

            total_ms = (time.time() - request_start) * 1000
            if audit_id:
                try:
                    resp_snip = str(assistant_response or "")
                    resp_len = len(resp_snip)
                    resp_snip = resp_snip[:2000]
                    payload_out = {
                        "schema_version": "omniflow.wp6.fast_audit.v1",
                        "kind": "fast_out",
                        "audit_id": audit_id,
                        "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
                        "user_id": str(user_id),
                        "thread_id": str(thread_id),
                        "stateless": bool(WP6_RESPONSES_STATELESS),
                        "audit_in_path": str(audit_in_path or ""),
                        "assistant_response_len": int(resp_len),
                        "assistant_response_snip": resp_snip,
                        "wp6": wp6_meta,
                    }
                    audit_out_path = _wp6_write_fast_audit(
                        user_id,
                        str(thread_id),
                        audit_id=audit_id,
                        kind="fast_out",
                        payload=payload_out,
                    )
                    if isinstance(responses_meta, dict):
                        responses_meta["wp6_fast_audit_in_path"] = str(audit_in_path or "")
                        responses_meta["wp6_fast_audit_out_path"] = str(audit_out_path or "")
                except Exception as exc:
                    _best_effort_debug("wp6_fast_audit_out_failed", user_id=str(user_id), thread_id=str(thread_id), error=exc)
            try:
                if isinstance(responses_meta, dict):
                    responses_meta["wp6"] = wp6_meta
            except Exception:
                pass
            _emit_run_progress(
                user_id=str(user_id),
                thread_id=str(thread_id),
                run_id=run_id,
                trace_id=trace_id,
                status="completed",
                stage="done",
                message="Done",
                async_save=False,
            )
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
                    logging.debug(f"[DEBUG] Calling restore_session {restore_url} user_id={user_id}")
                try:
                    r = requests_post(
                        restore_url,
                        json={"user_id": user_id, "thread_id": thread_id},
                        headers=headers,
                        timeout=30,
                        user_id=str(user_id),
                        thread_id=str(thread_id),
                        code="restore_session_post",
                    )
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
