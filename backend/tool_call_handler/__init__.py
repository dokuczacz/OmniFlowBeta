import datetime
import json
import logging
import os
import sys
import time
import re
import hashlib
from typing import Dict, Any, Tuple, List, Optional
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

try:
    from shared.session_manifest import build_session_event, append_session_event
    from shared.session_domain_classifier import classify_capability as _classify_cap
    SESSION_MANIFEST_AVAILABLE = True
except Exception:  # pragma: no cover
    SESSION_MANIFEST_AVAILABLE = False

# Phase 2: Import registry-driven dispatch pipeline
try:
    from tool_call_handler.dispatch import dispatch_tool_call as registry_dispatch
    REGISTRY_DISPATCH_AVAILABLE = True
except ImportError:
    REGISTRY_DISPATCH_AVAILABLE = False

try:
    from prompt_registry import compose_prompt_for_pa
except Exception:
    compose_prompt_for_pa = None

# Config
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ASSISTANT_ID = os.environ.get("OPENAI_ASSISTANT_ID", "")
OPENAI_PROMPT_ID = os.environ.get("OPENAI_PROMPT_ID", "")
LLM_RUNTIME_DEFAULT = os.environ.get("LLM_RUNTIME", "responses")
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
# Backend-owned tools: default ON so the system never depends on dashboard-configured tools.
# Set RESPONSES_INCLUDE_TOOLS=0 to disable (debug only).
RESPONSES_INCLUDE_TOOLS = os.environ.get("RESPONSES_INCLUDE_TOOLS", "1").lower() in ("1", "true", "yes")
RESPONSES_PARALLEL_TOOL_CALLS = os.environ.get("RESPONSES_PARALLEL_TOOL_CALLS", "1").lower() in ("1", "true", "yes")
RESPONSES_PROMPT_VARIABLES_ENABLED = os.environ.get("RESPONSES_PROMPT_VARIABLES_ENABLED", "0").lower() in ("1", "true", "yes")
RESPONSES_INSTRUCTIONS = str(os.environ.get("RESPONSES_INSTRUCTIONS", "") or "").strip()
if not RESPONSES_INSTRUCTIONS:
    # Default "tool discipline" so the agent cannot silently hallucinate state changes.
    # Keep this short; the backend owns tool allowlists/validation anyway.
    RESPONSES_INSTRUCTIONS = (
        "You are OmniFlow PA. Use tools for any claim about user data.\n"
        "- If asked about tasks, read/update TM.json via tools. Do not claim writes without a write tool call.\n"
        "- If asked about Gmail, use mail.search for query-based filtering and gmail_recent_metadata for lightweight recent metadata; do not ask for 50 if user requested 20.\n"
        "- For calendar.events.create/update, send start and end as nested objects with dateTime and timeZone.\n"
        "- For calendar.events.list, prefer include_all_calendars=true when the user asks for their calendar broadly, and use calendar_ids to narrow to specific calendars.\n"
        "- For gmail_action gmail_send, always provide JSON with payload.to, payload.subject, payload.body.\n"
        "- For gmail_action gmail_get/gmail_trash/gmail_delete, always provide payload.message_id.\n"
        "- If a Gmail tool returns NOT_AUTHORIZED, instruct user to Connect.\n"
        "- If asked to summarize blob contents, call list_blobs (and read_blob_file only if needed).\n"
        "If tools are unavailable or a tool errors, say so and stop."
    )
OPENAI_MAX_REQUESTS = int(os.environ.get("OPENAI_MAX_REQUESTS", "0") or 0)
# PA init gate: do not auto-create starter pack on request; require explicit confirmation via action.
PA_REQUIRE_INIT = str(os.environ.get("PA_REQUIRE_INIT", "1") or "").strip().lower() in ("1", "true", "yes", "y", "on")

# Optional intention step (separate model call) for ML artifacts / traceability.
PA_INTENTION_ENABLED = str(os.environ.get("PA_INTENTION_ENABLED", "1") or "").strip().lower() in ("1", "true", "yes", "y", "on")
PA_INTENTION_MODEL = str(os.environ.get("PA_INTENTION_MODEL", "gpt-5-nano") or "gpt-5-nano").strip()
PA_INTENTION_REASONING_EFFORT = str(os.environ.get("PA_INTENTION_REASONING_EFFORT", "low") or "low").strip().lower()
PA_INTENTION_MAX_OUTPUT_TOKENS = int(os.environ.get("PA_INTENTION_MAX_OUTPUT_TOKENS", "1200") or 1200)
# Allow a local-only debug endpoint to call PA intention directly (for batch eval).
PA_INTENTION_DEBUG_ENDPOINT = str(os.environ.get("PA_INTENTION_DEBUG_ENDPOINT", "") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
    "on",
)
# Per-run artifact (debug observability): default ON for dev/local runs, opt-out via env.
PA_RUN_ARTIFACT_ENABLED = str(os.environ.get("PA_RUN_ARTIFACT_ENABLED", "1") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
    "on",
)
PA_RUN_ARTIFACT_DEV_ONLY = str(os.environ.get("PA_RUN_ARTIFACT_DEV_ONLY", "1") or "").strip().lower() in (
    "1",
    "true",
    "yes",
    "y",
    "on",
)
PA_RUN_ARTIFACT_MAX_USER_MESSAGE_CHARS = int(
    os.environ.get("PA_RUN_ARTIFACT_MAX_USER_MESSAGE_CHARS", "2000") or 2000
)
PA_RUN_ARTIFACT_MAX_ASSISTANT_CHARS = int(
    os.environ.get("PA_RUN_ARTIFACT_MAX_ASSISTANT_CHARS", "4000") or 4000
)

PA_INTENTION_SCHEMA_V3: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "primary": {
            "type": "object",
            "properties": {
                "pa_id": {"type": "string", "maxLength": 16},
                "intent": {"type": "string", "maxLength": 64},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
                "is_selected": {"type": "boolean"},
            },
            "required": ["pa_id", "intent", "score", "is_selected"],
            "additionalProperties": False,
        },
        "alternatives": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "pa_id": {"type": "string", "maxLength": 16},
                    "intent": {"type": "string", "maxLength": 64},
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                    "is_selected": {"type": "boolean"},
                },
                "required": ["pa_id", "intent", "score", "is_selected"],
                "additionalProperties": False,
            },
        },
        "slots": {
            "type": "object",
            "properties": {
                "count": {"type": ["integer", "null"], "minimum": 1, "maximum": 50},
                "task_index": {"type": ["integer", "null"], "minimum": 1},
                "email_ref": {"type": ["string", "null"], "maxLength": 64},
                "query": {"type": ["string", "null"], "maxLength": 256},
            },
            "required": ["count", "task_index", "email_ref", "query"],
            "additionalProperties": False,
        },
        "signals": {
            "type": "object",
            "properties": {
                "is_gmail": {"type": "boolean"},
                "is_tm": {"type": "boolean"},
                "has_write_intent": {"type": "boolean"},
            },
            "required": ["is_gmail", "is_tm", "has_write_intent"],
            "additionalProperties": False,
        },
    },
    "required": ["primary", "alternatives", "slots", "signals"],
    "additionalProperties": False,
}

PA_FUNCTION_NAMES: Dict[str, str] = {
    "PA-01": "Task Management (TM)",
    "PA-02": "Daily Planning (LO)",
    "PA-03": "Priority Reasoning",
    "PA-04": "Goal Alignment (PS)",
    "PA-05": "Progress Review",
    "PA-06": "Knowledge Recall",
    "PA-07": "Note & Idea Handling (GEN)",
    "PA-08": "Artifact Analysis",
    "PA-09": "Context Integration",
    "PA-10": "Decision Reflection",
    "PA-11": "Summary & Reporting",
    "PA-12": "Function Proposal",
    "PA-13": "Mail Management",
    "PA-14": "Mail Analysis & Triage",
    "PA-15": "Mail-to-Action Mapping",
}

PA_FUNCTION_DEFAULT_ARTIFACTS: Dict[str, List[str]] = {
    "PA-01": ["TM.json"],
    "PA-02": ["LO.json"],
    "PA-03": ["TM.json", "PS.json", "LO.json"],
    "PA-04": ["PS.json", "TM.json"],
    "PA-05": ["SYS.json", "TM.json", "LO.json"],
    "PA-06": ["GEN.json", "TM.json", "PS.json"],
    "PA-07": ["GEN.json"],
    "PA-08": [],
    "PA-09": ["TM.json", "PS.json", "LO.json", "GEN.json", "MAIL.json"],
    "PA-10": ["SYS.json", "TM.json", "MAIL.json"],
    "PA-11": ["SYS.json", "TM.json", "MAIL.json"],
    "PA-12": ["TM.json", "PS.json", "LO.json", "GEN.json", "MAIL.json"],
    "PA-13": ["MAIL.json"],
    "PA-14": ["MAIL.json"],
    "PA-15": ["MAIL.json", "TM.json", "PS.json"],
}

PA_INTENT_FUNCTION_CATALOG: List[Dict[str, Any]] = [
    {"pa_id": "PA-01", "name": "Task Management", "intents": ["check_tasks", "add_task", "mark_done", "show_delayed", "update_task", "delete_task"]},
    {"pa_id": "PA-14", "name": "Mail Analysis & Triage", "intents": ["check_gmail", "summarize_inbox", "answer_latest_email", "send_email", "trash_email", "delete_email"]},
    {"pa_id": "PA-13", "name": "Mail Management", "intents": ["list_mailboxes", "show_labels"]},
    {"pa_id": "PA-15", "name": "Mail-to-Action Mapping", "intents": ["mail_to_tasks"]},
    {"pa_id": "PA-02", "name": "Daily Planning", "intents": ["build_day_plan"]},
    {"pa_id": "PA-03", "name": "Priority Reasoning", "intents": ["rank_priorities"]},
    {"pa_id": "PA-04", "name": "Goal Alignment", "intents": ["map_tasks_to_goals"]},
    {"pa_id": "PA-05", "name": "Progress Review", "intents": ["review_progress"]},
    {"pa_id": "PA-06", "name": "Knowledge Recall", "intents": ["recall_knowledge"]},
    {"pa_id": "PA-07", "name": "Note & Idea Handling", "intents": ["create_note", "update_note", "search_notes"]},
    {"pa_id": "PA-08", "name": "Artifact Analysis", "intents": ["analyze_artifact"]},
    {"pa_id": "PA-09", "name": "Context Integration", "intents": ["merge_context"]},
    {"pa_id": "PA-10", "name": "Decision Reflection", "intents": ["reflect_decision"]},
    {"pa_id": "PA-11", "name": "Summary & Reporting", "intents": ["generate_summary"]},
    {"pa_id": "PA-12", "name": "Function Proposal", "intents": ["propose_next_steps"]},
]

PA_INTENT_TO_PA_ID: Dict[str, str] = {}
for _entry in PA_INTENT_FUNCTION_CATALOG:
    _entry_pa = str(_entry.get("pa_id") or "").strip()
    for _intent in list(_entry.get("intents") or []):
        _key = str(_intent or "").strip().lower()
        if _key and _key not in PA_INTENT_TO_PA_ID:
            PA_INTENT_TO_PA_ID[_key] = _entry_pa

PA_TM_INTENT_TO_OPERATION: Dict[str, str] = {
    "check_tasks": "list",
    "show_delayed": "list",
    "add_task": "add",
    "mark_done": "complete",
    "update_task": "update",
    "delete_task": "delete",
}

PA_GMAIL_INTENT_TO_OPERATION: Dict[str, str] = {
    "check_gmail": "unknown",
    "summarize_inbox": "summarize",
    "answer_latest_email": "send",
    "send_email": "send",
    "trash_email": "trash",
    "delete_email": "delete",
}


def _pa_extract_first_int_in_range(text: str, low: int = 1, high: int = 50) -> int | None:
    msg = str(text or "")
    m = re.search(r"\b(\d{1,3})\b", msg)
    if not m:
        return None
    try:
        value = int(m.group(1))
    except Exception:
        return None
    if value < int(low) or value > int(high):
        return None
    return value


def _pa_extract_email_count(text: str, default_value: int = 20) -> int:
    msg = str(text or "").lower()
    candidates = [
        r"(?:dokladnie|exactly)?\s*(\d{1,2})\s*(?:ostatnich|najnowszych)\s*(?:mail|wiadom|email)",
        r"(?:mail|wiadom|email)\s*(?:.*?)(\d{1,2})\s*(?:ostatnich|najnowszych)",
        r"\b(\d{1,2})\b",
    ]
    for pat in candidates:
        m = re.search(pat, msg)
        if not m:
            continue
        try:
            value = int(m.group(1))
        except Exception:
            continue
        if 1 <= value <= 50:
            return value
    return int(default_value)


def _pa_extract_task_index(text: str) -> int | None:
    msg = str(text or "").lower()
    patterns = [
        r"(?:zadanie|task)\s*(?:nr|numer)?\s*(\d+)",
        r"\b(?:nr|numer)\s*(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, msg)
        if not m:
            continue
        try:
            value = int(m.group(1))
        except Exception:
            continue
        if value >= 1:
            return value
    return None


def _pa_detect_tm_operation(text: str, current: str) -> str:
    msg = str(text or "").lower()
    op = str(current or "").strip().lower()
    if any(k in msg for k in ("usun", "skasuj", "delete", "remove")):
        return "delete"
    if any(k in msg for k in ("oznacz", "wykonane", "zrobione", "complete", "done")):
        return "complete"
    if any(k in msg for k in ("dodaj", "utworz", "dopisz", "add", "create")):
        return "add"
    if any(k in msg for k in ("zaktualizuj", "zmien", "edytuj", "update", "edit")):
        return "update"
    if any(k in msg for k in ("jakie", "lista", "poka", "co mam", "tasks", "zadania", "list")):
        return "list"
    if op in ("list", "add", "update", "complete", "delete"):
        return op
    return "unknown"


def _pa_detect_gmail_operation(text: str, current: str) -> str:
    msg = str(text or "").lower()
    op = str(current or "").strip().lower()
    if any(k in msg for k in ("permanent", "na stale", "hard delete", "usun na stale")):
        return "delete"
    if any(k in msg for k in ("odpisz", "reply", "wyslij", "send")):
        return "send"
    if any(k in msg for k in ("usun", "skasuj", "trash", "delete")):
        return "trash"
    if any(k in msg for k in ("podsum", "streszcz", "skategoryzuj", "categor", "summar")):
        return "summarize"
    if any(k in msg for k in ("wypisz", "lista", "list", "nadawca", "temat")):
        return "list"
    if op in ("list", "get", "summarize", "send", "trash", "delete"):
        return op
    return "summarize"


def _pa_backend_normalize_intention_payload(
    *,
    intent_payload: Dict[str, Any] | None,
    user_message: str,
    single_step_focus: bool,
) -> Dict[str, Any]:
    payload = dict(intent_payload or {}) if isinstance(intent_payload, dict) else {}
    msg = str(user_message or "")
    msg_l = msg.lower()

    def _opt_str(value: Any, max_len: int) -> str | None:
        if value is None:
            return None
        txt = str(value).strip()
        if not txt:
            return None
        if txt.lower() in ("null", "none", "na", "n/a", "undefined"):
            return None
        return txt[: int(max_len)]

    is_mail = any(k in msg_l for k in ("gmail", "mail", "maile", "wiadom", "inbox", "skrzynk", "odpisz", "reply", "wyslij", "send"))
    is_task = any(
        k in msg_l
        for k in ("task", "tasks", "zadanie", "zadania", "todo", "to-do", "do zrobienia", "co mam jeszcze")
    )

    primary = payload.get("primary") if isinstance(payload.get("primary"), dict) else {}
    alternatives_raw = payload.get("alternatives") if isinstance(payload.get("alternatives"), list) else []
    # Backward compatibility for previous nano schema.
    if not alternatives_raw and isinstance(payload.get("secondary"), list):
        alternatives_raw = payload.get("secondary")
    slots_raw = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    signals_raw = payload.get("signals") if isinstance(payload.get("signals"), dict) else {}

    primary_pa_id = str(primary.get("pa_id") or "").strip()
    primary_intent = str(primary.get("intent") or "").strip().lower()
    pa_id_from_intent = PA_INTENT_TO_PA_ID.get(primary_intent, "")

    pa_id = str(payload.get("pa_function_id") or "").strip() or primary_pa_id or pa_id_from_intent
    if single_step_focus:
        if is_mail and not is_task:
            pa_id = "PA-14"
        elif is_task and not is_mail:
            pa_id = "PA-01"
    if pa_id not in PA_FUNCTION_NAMES:
        pa_id = "PA-14" if is_mail else ("PA-01" if is_task else "PA-11")

    raw_candidates = payload.get("candidate_pa_function_ids")
    candidates: List[str] = []
    if isinstance(raw_candidates, list):
        for item in raw_candidates:
            sid = str(item or "").strip()
            if sid in PA_FUNCTION_NAMES and sid not in candidates:
                candidates.append(sid)
            if len(candidates) >= 5:
                break
    if isinstance(alternatives_raw, list):
        for item in alternatives_raw:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("pa_id") or "").strip()
            if not sid:
                sid = PA_INTENT_TO_PA_ID.get(str(item.get("intent") or "").strip().lower(), "")
            if sid in PA_FUNCTION_NAMES and sid not in candidates:
                candidates.append(sid)
            if len(candidates) >= 5:
                break
    if pa_id not in candidates:
        candidates.insert(0, pa_id)
    candidates = candidates[:5]

    signal_is_gmail = bool(signals_raw.get("is_gmail")) if isinstance(signals_raw, dict) else False
    signal_is_tm = bool(signals_raw.get("is_tm")) if isinstance(signals_raw, dict) else False
    if signal_is_gmail and not signal_is_tm and pa_id not in ("PA-13", "PA-14", "PA-15"):
        pa_id = "PA-14"
    if signal_is_tm and not signal_is_gmail and pa_id != "PA-01":
        pa_id = "PA-01"

    requires_internet = bool(payload.get("requires_internet"))
    # TM/Gmail never require web search by default.
    if pa_id in ("PA-01", "PA-14"):
        requires_internet = False

    no_confirm_hint = ("nie pytaj o dodatkowe potwierdzenia" in msg_l) or ("bez potwierdzen" in msg_l)

    tm_raw = payload.get("tm") if isinstance(payload.get("tm"), dict) else {}
    tm_fields_raw = tm_raw.get("fields") if isinstance(tm_raw.get("fields"), dict) else {}
    gmail_raw = payload.get("gmail") if isinstance(payload.get("gmail"), dict) else {}

    tm_op_from_intent = PA_TM_INTENT_TO_OPERATION.get(primary_intent, "unknown")
    tm_op = tm_op_from_intent if tm_op_from_intent != "unknown" else _pa_detect_tm_operation(msg, str(tm_raw.get("operation") or "unknown"))
    tm_index = tm_raw.get("task_index_1based")
    if tm_index is None and slots_raw.get("task_index") is not None:
        tm_index = slots_raw.get("task_index")
    if tm_index is None:
        tm_index = _pa_extract_task_index(msg)
    try:
        tm_index = int(tm_index) if tm_index is not None else None
    except Exception:
        tm_index = None
    if isinstance(tm_index, int) and tm_index < 1:
        tm_index = None

    tm_title = tm_raw.get("task_title")
    if tm_title is not None:
        tm_title = str(tm_title).strip() or None

    gmail_op_from_intent = PA_GMAIL_INTENT_TO_OPERATION.get(primary_intent, "unknown")
    gmail_op = gmail_op_from_intent if gmail_op_from_intent != "unknown" else _pa_detect_gmail_operation(msg, str(gmail_raw.get("operation") or "unknown"))
    gmail_label = str(gmail_raw.get("label") or "INBOX").strip() or "INBOX"
    gmail_query = str(gmail_raw.get("query") or slots_raw.get("query") or "").strip() or None
    gmail_max_results: int | None = None
    if gmail_op in ("list", "summarize"):
        raw_count = gmail_raw.get("max_results")
        if raw_count is None:
            raw_count = slots_raw.get("count")
        try:
            gmail_max_results = int(raw_count) if raw_count is not None else _pa_extract_email_count(msg, 20)
        except Exception:
            gmail_max_results = _pa_extract_email_count(msg, 20)
        gmail_max_results = max(1, min(50, int(gmail_max_results)))

    required_tools: List[str] = []
    prefetch_plan: List[Dict[str, Any]] = []
    target_artifacts = list(PA_FUNCTION_DEFAULT_ARTIFACTS.get(pa_id, []))
    write_will = False
    write_consent = False
    requires_user_confirmation = False
    confirmation_question = None

    if pa_id == "PA-01":
        required_tools = ["read_blob_file"]
        prefetch_plan = [
            {
                "tool_name": "read_blob_file",
                "args": {
                    "file_name": "TM.json",
                    "prefix": None,
                    "include_meta": False,
                    "max_results": None,
                    "label": None,
                    "query": None,
                },
            }
        ]
        write_will = tm_op in ("add", "update", "complete", "delete")
        write_consent = tm_op == "delete"
        requires_user_confirmation = bool(write_consent and (not no_confirm_hint))
        if requires_user_confirmation:
            idx_txt = f" nr {tm_index}" if isinstance(tm_index, int) else ""
            confirmation_question = f"Czy na pewno usunac zadanie{idx_txt}?"
    elif pa_id == "PA-14":
        if gmail_op in ("list", "summarize"):
            required_tools = ["gmail_recent_metadata"]
            prefetch_plan = [
                {
                    "tool_name": "gmail_recent_metadata",
                    "args": {
                        "file_name": None,
                        "prefix": None,
                        "include_meta": None,
                        "max_results": int(gmail_max_results or 20),
                        "label": gmail_label,
                        "query": gmail_query,
                    },
                }
            ]
        else:
            required_tools = ["gmail_action"]
            ordinal_ref = re.search(r"\b\d+\)", msg_l) is not None
            email_ref = str(slots_raw.get("email_ref") or "").strip().lower()
            if gmail_op == "send" and (ordinal_ref or email_ref in ("latest", "last", "newest", "ostatni", "najnowszy")):
                prefetch_plan = [
                    {
                        "tool_name": "gmail_recent_metadata",
                        "args": {
                            "file_name": None,
                            "prefix": None,
                            "include_meta": None,
                            "max_results": _pa_extract_email_count(msg, 20),
                            "label": gmail_label,
                            "query": gmail_query,
                        },
                    }
                ]
        # Send/trash/delete are side effects, require explicit confirm unless user explicitly disabled confirm.
        requires_user_confirmation = bool(gmail_op in ("send", "trash", "delete") and (not no_confirm_hint))
        if requires_user_confirmation:
            confirmation_question = "Czy na pewno wykonac operacje Gmail (send/trash/delete)?"
    elif pa_id == "PA-13":
        required_tools = ["gmail_recent_metadata"]
        prefetch_plan = [
            {
                "tool_name": "gmail_recent_metadata",
                "args": {
                    "file_name": None,
                    "prefix": None,
                    "include_meta": None,
                    "max_results": int(gmail_max_results or 20),
                    "label": gmail_label,
                    "query": gmail_query,
                },
            }
        ]
    elif pa_id == "PA-15":
        required_tools = ["gmail_recent_metadata", "read_blob_file"]
        prefetch_plan = [
            {
                "tool_name": "gmail_recent_metadata",
                "args": {
                    "file_name": None,
                    "prefix": None,
                    "include_meta": None,
                    "max_results": int(gmail_max_results or 20),
                    "label": gmail_label,
                    "query": gmail_query,
                },
            }
        ]
        for file_name in ("TM.json", "PS.json"):
            prefetch_plan.append(
                {
                    "tool_name": "read_blob_file",
                    "args": {
                        "file_name": file_name,
                        "prefix": None,
                        "include_meta": False,
                        "max_results": None,
                        "label": None,
                        "query": None,
                    },
                }
            )
    else:
        if target_artifacts:
            required_tools = ["read_blob_file"]
            for file_name in list(target_artifacts)[:3]:
                prefetch_plan.append(
                    {
                        "tool_name": "read_blob_file",
                        "args": {
                            "file_name": file_name,
                            "prefix": None,
                            "include_meta": False,
                            "max_results": None,
                            "label": None,
                            "query": None,
                        },
                    }
                )
        else:
            required_tools = ["list_blobs"]
            prefetch_plan = [
                {
                    "tool_name": "list_blobs",
                    "args": {
                        "prefix": "users",
                        "max_results": 20,
                    },
                }
            ]

    confidence = payload.get("confidence")
    if confidence is None and isinstance(primary, dict):
        confidence = primary.get("score")
    if confidence is None and isinstance(primary, dict):
        confidence = primary.get("confidence")
    try:
        confidence_f = float(confidence)
    except Exception:
        confidence_f = 0.6
    confidence_f = max(0.0, min(1.0, confidence_f))

    normalized: Dict[str, Any] = {
        "schema_version": "omniflow.pa.intention.v3",
        "pa_function_id": pa_id,
        "candidate_pa_function_ids": candidates,
        "pa_function_name": PA_FUNCTION_NAMES.get(pa_id, "Unknown"),
        "intent_summary": str(payload.get("intent_summary") or primary_intent or "")[:200],
        "language": str(payload.get("language") or "pl")[:8] or "pl",
        "requires_internet": bool(requires_internet),
        "requires_user_confirmation": bool(requires_user_confirmation),
        "confirmation_question": confirmation_question,
        "target_artifacts": target_artifacts,
        "required_tools": required_tools,
        "prefetch_plan": prefetch_plan,
        "write_intent": {
            "will_write": bool(write_will),
            "consent_required": bool(write_consent),
            "target_files": list(target_artifacts if write_will else []),
        },
        "tm": {
            "operation": tm_op if pa_id == "PA-01" else "unknown",
            "task_index_1based": tm_index if pa_id == "PA-01" else None,
            "task_title": tm_title if pa_id == "PA-01" else None,
            "fields": {
                "status": _opt_str(tm_fields_raw.get("status"), 32),
                "due_date_iso": _opt_str(tm_fields_raw.get("due_date_iso"), 32),
                "priority": _opt_str(tm_fields_raw.get("priority"), 32),
                "notes": _opt_str(tm_fields_raw.get("notes"), 240),
            },
        },
        "gmail": {
            "operation": gmail_op if pa_id == "PA-14" else "unknown",
            "max_results": gmail_max_results if pa_id == "PA-14" and gmail_op in ("list", "summarize") else None,
            "label": gmail_label if pa_id == "PA-14" else None,
            "query": gmail_query if pa_id == "PA-14" else None,
        },
        "confidence": confidence_f,
    }
    summary_txt = str(normalized.get("intent_summary") or "").strip()
    blocked_markers = (
        "cannot access",
        "without tool access",
        "tools are available",
        "tools unavailable",
        "cannot do",
        "not available",
        "nie moge",
        "brak dostepu",
        "brak narzedzi",
    )
    if (not summary_txt) or any(m in summary_txt.lower() for m in blocked_markers):
        if pa_id == "PA-14":
            op = str(((normalized.get("gmail") or {}).get("operation")) or "unknown")
            if op in ("list", "summarize"):
                summary_txt = "Route to PA-14: analyze recent inbox messages."
            elif op in ("send", "trash"):
                summary_txt = "Route to PA-14: execute Gmail side-effect flow."
            else:
                summary_txt = "Route to PA-14: Gmail intent detected."
        elif pa_id == "PA-01":
            op = str(((normalized.get("tm") or {}).get("operation")) or "unknown")
            summary_txt = f"Route to PA-01: task operation={op}."
        else:
            summary_txt = f"Route to {pa_id} based on user request."
    normalized["intent_summary"] = summary_txt[:200]
    return normalized


def _pa_runtime_tools_include_from_intent(intent_payload: Dict[str, Any] | None) -> List[str] | None:
    if not isinstance(intent_payload, dict):
        return None
    pa_id = str(intent_payload.get("pa_function_id") or "").strip()
    if pa_id == "PA-13":
        return ["get_current_time", "gmail_recent_metadata", "gmail_action"]
    if pa_id == "PA-14":
        return ["get_current_time", "gmail_recent_metadata", "gmail_action"]
    if pa_id == "PA-15":
        return [
            "get_current_time",
            "gmail_recent_metadata",
            "gmail_action",
            "read_blob_file",
            "add_new_data",
            "update_data_entry",
            "upload_data_or_file",
        ]
    if pa_id == "PA-01":
        return [
            "get_current_time",
            "read_blob_file",
            "get_filtered_data",
            "add_new_data",
            "update_data_entry",
            "remove_data_entry",
            "upload_data_or_file",
        ]
    if pa_id == "PA-07":
        return [
            "get_current_time",
            "read_blob_file",
            "add_new_data",
            "update_data_entry",
            "remove_data_entry",
            "upload_data_or_file",
        ]
    if pa_id == "PA-08":
        return ["get_current_time", "list_blobs", "read_blob_file"]
    if pa_id in ("PA-02", "PA-03", "PA-04", "PA-05", "PA-06", "PA-09", "PA-10", "PA-11", "PA-12"):
        return ["get_current_time", "read_blob_file"]
    return None


def _pa_intention_text_json_schema_format() -> Dict[str, Any]:
    return {
        "format": {
            "type": "json_schema",
            "name": "pa_intention_min_v2",
            "strict": True,
            "schema": PA_INTENTION_SCHEMA_V3,
        }
    }

# Optional built-in web search tool (OpenAI hosted tool). If enabled, it is added to the Responses tools list.
PA_WEB_SEARCH_ENABLED = str(os.environ.get("PA_WEB_SEARCH_ENABLED", "1") or "").strip().lower() in ("1", "true", "yes", "y", "on")
PA_WEB_SEARCH_CONTEXT_SIZE = str(os.environ.get("PA_WEB_SEARCH_CONTEXT_SIZE", "low") or "low").strip().lower()
PA_WEB_SEARCH_ALLOWED_DOMAINS = str(os.environ.get("PA_WEB_SEARCH_ALLOWED_DOMAINS", "") or "").strip()
# WP6 routing: when UI does not send `context_mode`, fall back to this default.
# Values: AUTO | FAST | DEEP
WP6_DEFAULT_CONTEXT_MODE = (os.environ.get("WP6_DEFAULT_CONTEXT_MODE", "AUTO") or "AUTO").strip().upper()
WP6_TOPIC_CHANGE_ENABLED = False
WP6_TOPIC_CHANGE_WINDOW_SECONDS = 0
WP6_RESPONSES_STATELESS = os.environ.get("WP6_RESPONSES_STATELESS", "1").lower() in ("1", "true", "yes")
WP6_RECENT_TURNS_MAX = int(os.environ.get("WP6_RECENT_TURNS_MAX", "8") or 8)
WP6_RECENT_TURNS_MAX_CHARS = int(os.environ.get("WP6_RECENT_TURNS_MAX_CHARS", "320") or 320)
WP6_CAPSULE_RECENT_TURNS = int(os.environ.get("WP6_CAPSULE_RECENT_TURNS", "4") or 4)
WP6_CAPSULE_LAST_QUESTIONS = int(os.environ.get("WP6_CAPSULE_LAST_QUESTIONS", "3") or 3)
WP6_CAPSULE_MAX_CHARS = int(os.environ.get("WP6_CAPSULE_MAX_CHARS", "9000") or 9000)
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

# Best-effort manifest updater: tool_call_handler can mutate blobs via tools like
# `upload_data_or_file`, but those code paths do not automatically update
# `manifests/{user_id}/manifest.json` (unlike add_new_data/update_data_entry endpoints).
def _best_effort_update_manifest_after_tool_call(
    *,
    user_id: str,
    tool_name: str,
    tool_args: Dict[str, Any] | None,
    result_str: str,
) -> None:
    try:
        from shared.azure_client import AzureBlobClient
        from shared.manifest_helper import (
            build_manifest_entry,
            upsert_manifest_entry,
            remove_manifest_entry,
            rename_manifest_entry,
        )
    except Exception:
        return

    uid = str(user_id or "").strip()
    if not uid:
        return

    name = str(tool_name or "").strip()
    args = tool_args if isinstance(tool_args, dict) else {}

    if name not in ("upload_data_or_file", "manage_files", "add_new_data", "update_data_entry", "remove_data_entry"):
        return

    # Don't update manifest on failures.
    try:
        parsed = json.loads(result_str) if isinstance(result_str, str) else {}
    except Exception:
        parsed = {}
    if isinstance(parsed, dict):
        status = str(parsed.get("status") or "").lower()
        if status and status not in ("success", "ok"):
            return
        if parsed.get("error"):
            return

    try:
        container = AzureBlobClient.get_container_client()
    except Exception:
        return

    if name == "manage_files":
        op = str(args.get("operation") or "").strip().lower()
        src = str(args.get("source_name") or "").lstrip("/")
        tgt = str(args.get("target_name") or "").lstrip("/")
        if not src:
            return
        old_namespaced = f"users/{uid}/{src}"
        if op == "delete":
            try:
                remove_manifest_entry(container, uid, old_namespaced)
            except Exception:
                pass
            return
        if op == "rename" and tgt:
            new_namespaced = f"users/{uid}/{tgt}"
            try:
                rename_manifest_entry(container, uid, old_namespaced, new_namespaced, display_name=tgt)
            except Exception:
                pass
            return
        return

    # For blob writes, upsert a lightweight entry.
    target = str(args.get("target_blob_name") or "").lstrip("/")
    if not target:
        return

    namespaced = f"users/{uid}/{target}"

    # Conservative size estimate without embedding contents.
    payload_bytes = b""
    content_type = "application/octet-stream"
    try:
        if name == "upload_data_or_file":
            fc = args.get("file_content")
            if isinstance(fc, (dict, list)):
                payload_bytes = json.dumps(fc, ensure_ascii=False, indent=2).encode("utf-8")
                content_type = "application/json"
            elif isinstance(fc, (bytes, bytearray)):
                payload_bytes = bytes(fc)
            else:
                payload_bytes = str(fc or "").encode("utf-8")
                if target.lower().endswith(".json"):
                    content_type = "application/json"
        else:
            payload_bytes = (result_str or "").encode("utf-8")
            if target.lower().endswith(".json"):
                content_type = "application/json"
    except Exception:
        payload_bytes = (result_str or "").encode("utf-8")

    try:
        entry = build_manifest_entry(
            namespaced=namespaced,
            target_blob_name=target,
            payload={
                "target_blob_name": target,
                "category": "artifact",
                "source": "tool_call_handler",
                "metadata": {"tool_name": name},
            },
            content_type=content_type,
            size=len(payload_bytes or b""),
        )
        upsert_manifest_entry(container, uid, entry)
    except Exception:
        return

# PA starter pack: explicit init only (no silent auto-create).
def _pa_has_starter_pack(user_id: str) -> bool:
    try:
        from shared.azure_client import AzureBlobClient

        return bool(AzureBlobClient.blob_exists("SYS.json", user_id=str(user_id)))
    except Exception:
        return False


def _pa_init_starter_pack(user_id: str) -> Dict[str, Any]:
    from shared.starter_pack import ensure_starter_pack

    return ensure_starter_pack(str(user_id))


def _pa_detect_correction_signal(user_message: str) -> bool:
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    markers = (
        "nie,",
        "nie ",
        "zle",
        "źle",
        "wrong",
        "not this",
        "i meant",
        "chodzilo o",
        "chodziło o",
        "popraw",
    )
    return any(marker in text for marker in markers)


def _pa_extract_resolved_slots(intent_payload: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(intent_payload or {}) if isinstance(intent_payload, dict) else {}
    tm = payload.get("tm") if isinstance(payload.get("tm"), dict) else {}
    gmail = payload.get("gmail") if isinstance(payload.get("gmail"), dict) else {}
    return {
        "count": gmail.get("max_results"),
        "task_index": tm.get("task_index_1based"),
        "email_ref": None,
        "query": gmail.get("query"),
    }


def _pa_build_ml_labels(
    *,
    user_message: str,
    intent_payload: Dict[str, Any] | None,
    execution_outcome: str,
    source: str = "real",
) -> Dict[str, Any]:
    payload = dict(intent_payload or {}) if isinstance(intent_payload, dict) else {}
    tm = payload.get("tm") if isinstance(payload.get("tm"), dict) else {}
    gmail = payload.get("gmail") if isinstance(payload.get("gmail"), dict) else {}
    final_resolved_intent = {
        "pa_function_id": str(payload.get("pa_function_id") or ""),
        "tm_operation": str(tm.get("operation") or "unknown"),
        "gmail_operation": str(gmail.get("operation") or "unknown"),
    }
    correction = _pa_detect_correction_signal(str(user_message or ""))
    return {
        "dataset_schema": "omniflow.pa.ml_dataset_row.v1",
        "input_text": str(user_message or "")[:4000],
        "nano_output_raw": payload,
        "final_resolved_intent": final_resolved_intent,
        "resolved_slots": _pa_extract_resolved_slots(payload),
        "execution_outcome": str(execution_outcome or "pending"),
        "source": str(source or "real"),
        "correction_signal": bool(correction),
        "corrected_intent": None,
    }


def _pa_compute_execution_outcome(all_tool_calls: list) -> str:
    calls = list(all_tool_calls or [])
    if not calls:
        return "success"
    for item in calls:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").lower() != "error":
            continue
        err = str(item.get("error") or "").lower()
        if "valueerror" in err or "required" in err or "invalid" in err:
            return "validation_error"
        return "tool_error"
    return "success"


def _pa_write_intention_artifact(
    *,
    user_id: str,
    thread_id: str,
    run_id: str,
    phase: str,
    stage: str,
    model: str,
    intent_response_id: str,
    request_message: str,
    intent_payload: Dict[str, Any],
) -> str:
    """
    Persist intention artifact as JSON for ML.
    Best-effort: never raises.
    """
    try:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_tid = str(thread_id or "").strip() or "no_thread"
        safe_rid = str(run_id or "").strip() or uuid.uuid4().hex[:12]
        path = f"semantics/intents/INTENT_{ts}_{safe_tid}_{safe_rid}.json"
        payload = {
            "schema_version": "omniflow.pa.intention.v3",
            "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
            "user_id": str(user_id),
            "thread_id": str(thread_id),
            "run_id": str(run_id),
            "phase": str(phase or ""),
            "stage": str(stage or ""),
            "model": str(model or ""),
            "intent_response_id": str(intent_response_id or ""),
            "request_message": str(request_message or "")[:4000],
            "intention": intent_payload,
            "ml_labels": _pa_build_ml_labels(
                user_message=str(request_message or ""),
                intent_payload=intent_payload if isinstance(intent_payload, dict) else {},
                execution_outcome="pending",
                source="real",
            ),
        }
        execute_tool_call("upload_data_or_file", {"target_blob_name": path, "file_content": payload}, user_id)
        _best_effort_update_manifest_after_tool_call(
            user_id=str(user_id),
            tool_name="upload_data_or_file",
            tool_args={"target_blob_name": path, "file_content": {"schema_version": payload.get("schema_version")}},
            result_str=json.dumps({"status": "success"}),
        )
        return path
    except Exception:
        return ""


def _pa_run_intention_step(
    *,
    openai_client: OpenAI,
    user_id: str,
    thread_id: str,
    run_id: str,
    phase: str,
    stage: str,
    user_message: str,
    single_step_focus: bool = False,
    raise_on_error: bool = False,
) -> Tuple[Dict[str, Any], str]:
    """
    Separate "intention" call (no tools) to produce an ML-ready artifact.
    Returns (intent_payload, artifact_path).
    """
    if not PA_INTENTION_ENABLED:
        return {}, ""
    try:
        _emit_run_progress(
            user_id=str(user_id),
            thread_id=str(thread_id),
            run_id=str(run_id or ""),
            trace_id="",
            status="in_progress",
            stage="intention",
            message=f"Intention: calling model {PA_INTENTION_MODEL}",
            async_save=True,
        )
    except Exception:
        pass
    try:
        # Keep a stable prompt prefix to maximize prompt-caching hits.
        # Do not embed phase/stage/user ids in the prompt text; send those as metadata.
        single_step_constraints = (
            "Single-step focus hint:\n"
            "- Prefer PA-01 (Task Management) or PA-14 (Mail Analysis & Triage) when clear.\n"
        ) if single_step_focus else ""

        catalog_json = json.dumps(PA_INTENT_FUNCTION_CATALOG, ensure_ascii=False)
        input_contract = json.dumps(
            {
                "user_message": str(user_message or "")[:2000],
                "candidate_functions": PA_INTENT_FUNCTION_CATALOG,
            },
            ensure_ascii=False,
        )
        prompt = (
            "You are a semantic intention classifier for OmniFlow Personal Assistance (PA).\n"
            "Return STRICT JSON only. No markdown. No prose.\n"
            "Do not select tools. Do not propose phase/stage. Do not add schema_version.\n"
            "\n"
            "Allowed candidate functions and intents:\n"
            + catalog_json
            + "\n\n"
            "Output contract:\n"
            "{\n"
            '  "primary": {"pa_id":"PA-xx","intent":"intent_name","score":0.0-1.0,"is_selected":true},\n'
            '  "alternatives": [{"pa_id":"PA-xx","intent":"intent_name","score":0.0-1.0,"is_selected":false}],\n'
            '  "slots": {"count":int|null,"task_index":int|null,"email_ref":string|null,"query":string|null},\n'
            '  "signals": {"is_gmail":bool,"is_tm":bool,"has_write_intent":bool}\n'
            "}\n"
            "\n"
            "Rules:\n"
            "- Use only intents from candidate_functions.\n"
            "- Keep count exact when user requests N emails.\n"
            "- Keep output compact and deterministic.\n"
            "- primary.is_selected must be true.\n"
            "- alternatives entries must use is_selected=false.\n"
            + single_step_constraints
            + "\n"
            "Input contract JSON:\n"
            + input_contract
        )
        call_kwargs = {
            "model": PA_INTENTION_MODEL,
            "input": prompt,
            "tool_choice": "none",
            "parallel_tool_calls": bool(RESPONSES_PARALLEL_TOOL_CALLS),
            "text": _pa_intention_text_json_schema_format(),
            "max_output_tokens": int(PA_INTENTION_MAX_OUTPUT_TOKENS),
            "store": True,
            "metadata": {
                "purpose": "pa_intention",
                "user_id": str(user_id),
                "thread_id": str(thread_id),
                "run_id": str(run_id or ""),
                "phase": str(phase or ""),
                "stage": str(stage or ""),
            },
        }
        if PA_INTENTION_REASONING_EFFORT in ("low", "medium", "high"):
            call_kwargs["reasoning"] = {"effort": PA_INTENTION_REASONING_EFFORT}
        resp = _openai_call(openai_client.responses.create, **call_kwargs)
        resp_id = str(getattr(resp, "id", None) or "").strip()
        out_text = str(getattr(resp, "output_text", None) or "").strip()
        if not out_text:
            body: Any = None
            try:
                body = resp.model_dump()  # type: ignore[attr-defined]
            except Exception:
                try:
                    body = resp.to_dict()  # type: ignore[attr-defined]
                except Exception:
                    body = None
            out_text = _output_text_from_response_body(body)
        try:
            payload = json.loads(out_text) if out_text else {}
        except Exception:
            # Best-effort recovery: some models may wrap JSON with prose/code fences despite instructions.
            # Try to extract a JSON object substring before giving up.
            recovered = None
            try:
                txt = str(out_text or "")
                txt = txt.replace("```json", "```").strip()
                if "```" in txt:
                    # take first fenced block content if present
                    parts = txt.split("```")
                    if len(parts) >= 3:
                        txt = parts[1].strip()
                i1 = txt.find("{")
                i2 = txt.rfind("}")
                if i1 != -1 and i2 != -1 and i2 > i1:
                    recovered = json.loads(txt[i1 : i2 + 1])
            except Exception:
                recovered = None
            if isinstance(recovered, dict):
                payload = recovered
            else:
                payload = {"schema_version": "omniflow.pa.intention.v3", "parse_error": True, "raw": out_text[:4000]}
        if not isinstance(payload, dict):
            payload = {"schema_version": "omniflow.pa.intention.v3", "parse_error": True, "raw": out_text[:4000]}

        payload = _pa_backend_normalize_intention_payload(
            intent_payload=payload,
            user_message=str(user_message or ""),
            single_step_focus=bool(single_step_focus),
        )

        path = _pa_write_intention_artifact(
            user_id=str(user_id),
            thread_id=str(thread_id),
            run_id=str(run_id or ""),
            phase=str(phase or ""),
            stage=str(stage or ""),
            model=str(PA_INTENTION_MODEL),
            intent_response_id=resp_id,
            request_message=str(user_message or ""),
            intent_payload=payload,
        )
        return payload, path
    except Exception as exc:
        _best_effort_debug("pa_intention_failed", user_id=str(user_id), thread_id=str(thread_id), error=exc)
        if raise_on_error:
            raise
        return {}, ""


def _pa_execute_prefetch_plan(
    *,
    user_id: str,
    thread_id: str,
    run_id: str,
    intent_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Execute a bounded, backend-validated prefetch plan produced by PA intention.
    Deterministic orchestration only: allowlist + strict limits + small artifacts.
    """

    def _tm_count(value: Any) -> int:
        if isinstance(value, dict):
            if isinstance(value.get("items"), list):
                return len(value["items"])
            if isinstance(value.get("tasks"), list):
                return len(value["tasks"])
            return 0
        if isinstance(value, list):
            extra = 0
            for el in value:
                if isinstance(el, dict) and isinstance(el.get("tasks"), list):
                    extra += len(el["tasks"])
            return len(value) + extra
        return 0

    plan = intent_payload.get("prefetch_plan") if isinstance(intent_payload, dict) else None
    if not isinstance(plan, list) or not plan:
        return {"executed": [], "skipped": [], "errors": [], "artifact_path": ""}

    allow = {"read_blob_file", "list_blobs", "gmail_recent_metadata"}
    executed: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    tm_task_count: int | None = None
    tm_sha256: str | None = None

    def _write_mail_snapshot_from_recent(result_payload: Dict[str, Any]) -> None:
        if not isinstance(result_payload, dict):
            return
        payload = dict(result_payload)
        # Accept both direct tool payload and wrapped dispatch envelope.
        if str(payload.get("status") or "").lower() == "success" and isinstance(payload.get("result"), dict):
            payload = dict(payload.get("result") or {})
        if str(payload.get("status") or "").lower() != "ok":
            return
        rows = payload.get("messages")
        if not isinstance(rows, list):
            rows = []
        normalized: List[Dict[str, Any]] = []
        for row in rows[:50]:
            if not isinstance(row, dict):
                continue
            headers = row.get("headers") if isinstance(row.get("headers"), dict) else {}
            normalized.append(
                {
                    "id": str(row.get("id") or "")[:120],
                    "threadId": str(row.get("threadId") or "")[:120],
                    "from": str(headers.get("From") or "")[:300],
                    "to": str(headers.get("To") or "")[:300],
                    "subject": str(headers.get("Subject") or "")[:500],
                    "date": str(headers.get("Date") or row.get("internalDate") or "")[:120],
                    "snippet": str(row.get("snippet") or "")[:2000],
                    "labels": list(row.get("labelIds") or [])[:20] if isinstance(row.get("labelIds"), list) else [],
                }
            )
        snapshot_payload = {
            "schema_version": "omniflow.pa.mail_snapshot.v1",
            "updated_utc": datetime.datetime.utcnow().isoformat() + "Z",
            "source": "gmail_recent_metadata",
            "result_count": int(len(normalized)),
            "messages": normalized,
        }
        execute_tool_call(
            "upload_data_or_file",
            {"target_blob_name": "MAIL.json", "file_content": snapshot_payload},
            user_id,
        )

    for step in plan[:10]:
        if not isinstance(step, dict):
            continue
        tool_name = str(step.get("tool_name") or "").strip()
        args = step.get("args") if isinstance(step.get("args"), dict) else {}
        if tool_name not in allow:
            skipped.append({"tool_name": tool_name, "reason": "not_allowlisted"})
            continue

        # Clamp and validate args deterministically.
        if tool_name == "read_blob_file":
            file_name = str(args.get("file_name") or "").strip()
            if not file_name:
                skipped.append({"tool_name": tool_name, "reason": "missing_file_name"})
                continue
            args = {"file_name": file_name}
        elif tool_name == "list_blobs":
            prefix = str(args.get("prefix") or "").strip()
            include_meta = bool(args.get("include_meta") if args.get("include_meta") is not None else True)
            args = {"prefix": prefix, "include_meta": include_meta}
        elif tool_name == "gmail_recent_metadata":
            try:
                max_results = int(args.get("max_results") or 20)
            except Exception:
                max_results = 20
            if max_results < 1:
                max_results = 1
            if max_results > 50:
                max_results = 50
            label = str(args.get("label") or "INBOX").strip() or "INBOX"
            query = str(args.get("query") or "").strip()
            args = {"max_results": max_results, "label": label, "query": query}

        try:
            result_str, info = execute_tool_call(tool_name, args, user_id)
            executed.append(
                {
                    "tool_name": tool_name,
                    "status": str((info or {}).get("status") or "unknown"),
                    "duration_ms": float((info or {}).get("duration_ms") or 0),
                }
            )
            if tool_name == "gmail_recent_metadata":
                try:
                    parsed_recent = json.loads(result_str) if isinstance(result_str, str) else {}
                except Exception:
                    parsed_recent = {}
                try:
                    _write_mail_snapshot_from_recent(parsed_recent if isinstance(parsed_recent, dict) else {})
                except Exception:
                    pass
            if tool_name == "read_blob_file" and str(args.get("file_name") or "").upper() == "TM.JSON":
                # Best-effort: compute a stable digest and task count without storing task contents.
                try:
                    parsed = json.loads(result_str) if isinstance(result_str, str) else {}
                except Exception:
                    parsed = {}
                if isinstance(parsed, dict) and parsed.get("status") == "success":
                    data = parsed.get("data")
                    try:
                        raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8", "ignore")
                        import hashlib

                        tm_sha256 = hashlib.sha256(raw).hexdigest()
                    except Exception:
                        tm_sha256 = None
                    try:
                        tm_task_count = int(_tm_count(data))
                    except Exception:
                        tm_task_count = None
        except Exception as exc:
            errors.append({"tool_name": tool_name, "error": f"{type(exc).__name__}: {exc}"})

    artifact_path = ""
    try:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_tid = str(thread_id or "").strip() or "no_thread"
        safe_rid = str(run_id or "").strip() or uuid.uuid4().hex[:12]
        artifact_path = f"semantics/prefetch/PREFETCH_{ts}_{safe_tid}_{safe_rid}.json"
        payload = {
            "schema_version": "omniflow.pa.prefetch.v1",
            "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
            "user_id": str(user_id),
            "thread_id": str(thread_id),
            "run_id": str(run_id),
            "pa_function_id": str(intent_payload.get("pa_function_id") or ""),
            "executed": executed,
            "skipped": skipped,
            "errors": errors,
            "tm_digest": {"sha256": tm_sha256, "task_count": tm_task_count},
        }
        execute_tool_call("upload_data_or_file", {"target_blob_name": artifact_path, "file_content": payload}, user_id)
    except Exception:
        artifact_path = ""

    return {"executed": executed, "skipped": skipped, "errors": errors, "artifact_path": artifact_path}

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


def _inprocess_save_interaction(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from save_interaction import main as save_interaction_main

    resp = _inprocess_call_function_main(
        save_interaction_main,
        user_id,
        body={**dict(payload or {}), "user_id": user_id},
    )
    try:
        body_text = resp.get_body().decode("utf-8") if hasattr(resp, "get_body") else str(resp)
        return json.loads(body_text) if body_text else {}
    except Exception as exc:
        _best_effort_debug("inprocess_save_interaction_parse_failed", user_id=str(user_id), error=exc)
        return {}


def _inprocess_get_interaction_history(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from get_interaction_history import main as get_interaction_history_main

    resp = _inprocess_call_function_main(
        get_interaction_history_main,
        user_id,
        params={**dict(params or {}), "user_id": user_id},
    )
    try:
        body_text = resp.get_body().decode("utf-8") if hasattr(resp, "get_body") else str(resp)
        return json.loads(body_text) if body_text else {}
    except Exception as exc:
        _best_effort_debug("inprocess_get_interactions_parse_failed", user_id=str(user_id), error=exc)
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


def _wp6_load_user_profile_snapshot(user_id: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    try:
        raw, _ = execute_tool_call(
            "read_blob_file",
            {"file_name": "semantics/preferences.json", "parse_json": True, "max_bytes": 10000},
            user_id,
        )
        payload = json.loads(raw) if isinstance(raw, str) else {}
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            return {}
        for key in list(data.keys())[:20]:
            k = str(key or "").strip()
            if not k:
                continue
            val = data.get(key)
            if isinstance(val, (str, int, float, bool)) or val is None:
                out[k] = val
                continue
            if isinstance(val, list):
                slim = []
                for item in val[:8]:
                    if isinstance(item, (str, int, float, bool)) or item is None:
                        slim.append(item)
                if slim:
                    out[k] = slim
                continue
            if isinstance(val, dict):
                nested = {}
                for nk in list(val.keys())[:8]:
                    nv = val.get(nk)
                    if isinstance(nv, (str, int, float, bool)) or nv is None:
                        nested[str(nk)] = nv
                if nested:
                    out[k] = nested
        return out
    except Exception:
        return {}


def _wp6_load_mail_snapshot_snippet(user_id: str, max_items: int = 8) -> Dict[str, Any]:
    try:
        raw, _ = execute_tool_call(
            "read_blob_file",
            {"file_name": "MAIL.json", "parse_json": True, "max_bytes": 80000},
            user_id,
        )
        payload = json.loads(raw) if isinstance(raw, str) else {}
        data = payload.get("data") if isinstance(payload, dict) else None
        items: List[Dict[str, Any]] = []
        candidate_lists: List[Any] = []
        if isinstance(data, list):
            candidate_lists.append(data)
        elif isinstance(data, dict):
            for key in ("messages", "items", "inbox", "emails", "mail"):
                if isinstance(data.get(key), list):
                    candidate_lists.append(data.get(key))
            if not candidate_lists:
                for value in data.values():
                    if isinstance(value, list):
                        candidate_lists.append(value)
                        break
        for lst in candidate_lists:
            for row in list(lst or []):
                if not isinstance(row, dict):
                    continue
                one = {
                    "id": str(row.get("id") or row.get("message_id") or "")[:120],
                    "from": str(row.get("from") or row.get("sender") or "")[:200],
                    "subject": str(row.get("subject") or "")[:220],
                    "date": str(row.get("date") or row.get("internal_date") or "")[:80],
                }
                labels = row.get("labels")
                if isinstance(labels, list):
                    one["labels"] = [str(x)[:32] for x in labels[:6]]
                elif labels is not None:
                    one["labels"] = [str(labels)[:32]]
                items.append(one)
                if len(items) >= max(1, int(max_items)):
                    break
            if len(items) >= max(1, int(max_items)):
                break
        if not items:
            return {}
        return {"source": "MAIL.json", "items": items}
    except Exception:
        return {}


def _wp6_build_context_capsule(
    *,
    user_id: str,
    user_message: str,
    recent_turns: list[str],
    core_sources: list[dict],
    fast_ctx: str,
    intent_payload: Dict[str, Any] | None = None,
) -> Tuple[str, Dict[str, Any]]:
    meta: Dict[str, Any] = {
        "capsule_enabled": True,
        "capsule_chars": 0,
        "capsule_recent_turns_count": 0,
        "capsule_last_questions_count": 0,
        "capsule_semantic_lines_count": 0,
        "capsule_has_tm_snippet": False,
        "capsule_has_user_profile": False,
    }
    try:
        payload = dict(intent_payload or {}) if isinstance(intent_payload, dict) else {}
        pa_function_id = str(payload.get("pa_function_id") or "").strip()
        tm_meta = payload.get("tm") if isinstance(payload.get("tm"), dict) else {}
        gmail_meta = payload.get("gmail") if isinstance(payload.get("gmail"), dict) else {}
        intent_view = {
            "primary": {
                "pa_id": pa_function_id,
                "summary": str(payload.get("intent_summary") or "")[:120],
                "confidence": payload.get("confidence"),
            },
            "tm": {"operation": str(tm_meta.get("operation") or "unknown")},
            "gmail": {
                "operation": str(gmail_meta.get("operation") or "unknown"),
                "max_results": gmail_meta.get("max_results"),
                "label": gmail_meta.get("label"),
                "query": gmail_meta.get("query"),
            },
        }
        profile = _wp6_load_user_profile_snapshot(user_id)
        forbidden_profile_keys = {
            "user_id",
            "session_id",
            "run_id",
            "ts_utc",
            "phase",
            "stage",
            "response_id",
            "prompt_id",
            "requires_confirmation",
            "write_intent",
            "tool_budget",
        }
        if isinstance(profile, dict):
            profile = {k: v for k, v in profile.items() if str(k or "") not in forbidden_profile_keys}
        tm_snippet = {}
        if pa_function_id == "PA-01":
            for src in (core_sources or []):
                if not isinstance(src, dict):
                    continue
                if str(src.get("path") or "").strip() != "TM.json":
                    continue
                snippet = str(src.get("excerpt_or_snippet") or "").strip()[:2200]
                if snippet:
                    tm_snippet = {"source": "TM.json", "snippet": snippet}
                    break

        mail_snippet = {}
        if pa_function_id == "PA-14":
            mail_snippet = _wp6_load_mail_snapshot_snippet(user_id=user_id, max_items=8)

        recent = [str(t or "").strip() for t in (recent_turns or []) if str(t or "").strip()]
        if int(WP6_CAPSULE_RECENT_TURNS or 0) > 0:
            recent = recent[-int(WP6_CAPSULE_RECENT_TURNS) :]
        last_q = recent[-max(1, int(WP6_CAPSULE_LAST_QUESTIONS or 0)) :] if recent else []

        semantic_lines: list[str] = []
        for line in str(fast_ctx or "").splitlines():
            s = str(line or "").strip()
            if not s or not s.startswith("- "):
                continue
            semantic_lines.append(s[:260])
            if len(semantic_lines) >= 4:
                break

        artifact_snippets: Dict[str, Any] = {}
        if pa_function_id == "PA-01" and tm_snippet:
            artifact_snippets["tm"] = tm_snippet
        if pa_function_id == "PA-14" and mail_snippet:
            artifact_snippets["mail"] = mail_snippet

        capsule = {
            "intent": intent_view,
            "user_profile": profile,
            "recent_user_turns": recent,
            "last_user_questions": last_q,
            "artifact_snippets": artifact_snippets,
            "semantic_signals": semantic_lines,
        }
        packed = json.dumps(capsule, ensure_ascii=False)
        meta["capsule_chars"] = int(len(packed))
        meta["capsule_recent_turns_count"] = int(len(recent))
        meta["capsule_last_questions_count"] = int(len(last_q))
        meta["capsule_semantic_lines_count"] = int(len(semantic_lines))
        meta["capsule_has_tm_snippet"] = bool(artifact_snippets.get("tm"))
        meta["capsule_has_mail_snippet"] = bool(artifact_snippets.get("mail"))
        meta["capsule_has_user_profile"] = bool(profile)
        return packed, meta
    except Exception as exc:
        meta["capsule_enabled"] = False
        meta["capsule_error"] = str(type(exc).__name__)
        return "", meta


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


def _pa_compact_tool_calls_for_run_artifact(tool_calls: list, *, max_items: int = 50) -> List[Dict[str, Any]]:
    compact: List[Dict[str, Any]] = []
    if not isinstance(tool_calls, list):
        return compact
    for item in tool_calls[: max(1, int(max_items or 50))]:
        if not isinstance(item, dict):
            continue
        row: Dict[str, Any] = {
            "tool_name": str(item.get("tool_name") or ""),
            "status": str(item.get("status") or ""),
            "duration_ms": item.get("duration_ms"),
            "call_id": str(item.get("call_id") or ""),
            "runtime": str(item.get("runtime") or ""),
        }
        err = item.get("error")
        if err:
            row["error"] = str(err)[:400]
        compact.append(row)
    return compact


def _pa_write_run_artifact(
    *,
    user_id: str,
    thread_id: str,
    run_id: str,
    trace_id: str,
    runtime_used: str,
    phase: str,
    stage: str,
    user_message: str,
    assistant_response: str,
    all_tool_calls: list,
    responses_meta: Dict[str, Any] | None,
    total_ms: float,
) -> str:
    try:
        ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        rid = str(run_id or "").strip() or uuid.uuid4().hex[:12]
        safe_thread = re.sub(r"[^A-Za-z0-9_.-]", "_", str(thread_id or "thread"))
        suffix = uuid.uuid4().hex[:8]
        path = f"semantics/runs/{safe_thread}/RUN_{ts}_{rid}_{suffix}.json"
        payload: Dict[str, Any] = {
            "schema_version": "omniflow.pa.run.v1",
            "created_utc": datetime.datetime.utcnow().isoformat() + "Z",
            "user_id": str(user_id or ""),
            "thread_id": str(thread_id or ""),
            "session_id": str(thread_id or ""),
            "run_id": rid,
            "trace_id": str(trace_id or ""),
            "runtime_used": str(runtime_used or ""),
            "phase": str(phase or ""),
            "stage": str(stage or ""),
            "timings": {"total_ms": float(total_ms or 0)},
            "user_message": str(user_message or "")[: max(1, int(PA_RUN_ARTIFACT_MAX_USER_MESSAGE_CHARS or 2000))],
            "assistant_response": str(assistant_response or "")[
                : max(1, int(PA_RUN_ARTIFACT_MAX_ASSISTANT_CHARS or 4000))
            ],
            "tool_calls_count": int(len(all_tool_calls or [])),
            "tool_calls": _pa_compact_tool_calls_for_run_artifact(all_tool_calls, max_items=50),
        }
        intent_payload_for_ml: Dict[str, Any] = {}
        if isinstance(responses_meta, dict):
            payload["responses"] = {
                "responses_conversation_id": str(responses_meta.get("responses_conversation_id") or ""),
                "responses_last_response_id": str(responses_meta.get("responses_last_response_id") or ""),
                "prompt_id": str(responses_meta.get("prompt_id") or ""),
                "prompt_vars_enabled": bool(responses_meta.get("prompt_vars_enabled")),
                "tools_included": list(responses_meta.get("tools_included") or []),
                "include_web_search": bool(responses_meta.get("include_web_search")),
                "web_search_enabled": bool(responses_meta.get("web_search_enabled")),
                "composer_matrix_id": str(responses_meta.get("composer_matrix_id") or ""),
                "composer_block_ids": list(responses_meta.get("composer_block_ids") or []),
                "composer_schema_id": str(responses_meta.get("composer_schema_id") or ""),
                "composer_tools_id": str(responses_meta.get("composer_tools_id") or ""),
            }
            intent_payload_for_ml = (
                responses_meta.get("pa_intention_payload")
                if isinstance(responses_meta.get("pa_intention_payload"), dict)
                else {}
            )
        payload["ml_labels"] = _pa_build_ml_labels(
            user_message=str(user_message or ""),
            intent_payload=intent_payload_for_ml,
            execution_outcome=_pa_compute_execution_outcome(list(all_tool_calls or [])),
            source="real",
        )
        execute_tool_call("upload_data_or_file", {"target_blob_name": path, "file_content": payload}, str(user_id or ""))
        return path
    except Exception as exc:
        _best_effort_debug(
            "pa_run_artifact_write_failed",
            user_id=str(user_id or ""),
            thread_id=str(thread_id or ""),
            error=exc,
            run_id=str(run_id or ""),
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
    runtime = (body or {}).get("runtime") or LLM_RUNTIME_DEFAULT or "responses"
    runtime = str(runtime).strip().lower()
    if runtime in ("assistants", "assistant"):
        # Backward-compatible env/request handling after assistants runtime removal.
        runtime = "responses"
    if runtime not in ("responses", "auto"):
        raise ValueError("Invalid runtime. Allowed: responses|auto (assistants runtime removed)")
    return runtime


def _missing_env_vars_for_runtime(runtime: str) -> list:
    runtime = (runtime or "").strip().lower()
    missing = []
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not PROXY_URL:
        missing.append("AZURE_PROXY_URL")
    if runtime == "responses":
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
    intent_router: Dict[str, Any] | None = None,
    phase: str = "",
    stage: str = "",
    include_web_search: bool = False,
    tool_include_names: List[str] | None = None,
    composer_meta: Dict[str, Any] | None = None,
) -> Tuple[str, list, Dict[str, Any], str]:
    """Responses API deterministic tool loop using a Prompt ID."""
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
    tools_included_names: List[str] = []
    prompt_vars_forced = False

    for iteration in range(25):
        create_kwargs: Dict[str, Any] = {
            "prompt": {"id": OPENAI_PROMPT_ID},
            "input": current_input,
            "tool_choice": "auto",
            "parallel_tool_calls": bool(RESPONSES_PARALLEL_TOOL_CALLS),
            # Important: without an explicit cap, the Prompt/model defaults may request very large output budgets,
            # which can blow TPM limits even for tiny user prompts (because conversation history is server-side).
            "max_output_tokens": responses_max_output_tokens,
            "metadata": {
                "user_id": str(user_id),
                "thread_id": str(thread_id),
                "runtime": "responses",
                **({"phase": str(phase or "")} if (phase or "") else {}),
                **({"stage": str(stage or "")} if (stage or "") else {}),
                **(
                    {"recent_user_turns": _wp6_recent_turns_metadata(recent_turns_buffer)}
                    if recent_turns_buffer
                    else {}
                ),
            },
        }
        if isinstance(composer_meta, dict) and composer_meta:
            for key in ("composer_matrix_id", "composer_schema_id", "composer_tools_id"):
                value = str(composer_meta.get(key) or "").strip()
                if value:
                    create_kwargs["metadata"][key] = value
        if intent_router:
            try:
                # OpenAI metadata values must be scalar-ish; store a short JSON string for traceability.
                create_kwargs["metadata"]["intent_router"] = json.dumps(intent_router, ensure_ascii=False)[:768]
            except Exception:
                pass
        if RESPONSES_PROMPT_VARIABLES_ENABLED or prompt_vars_forced:
            create_kwargs["prompt"] = {
                "id": OPENAI_PROMPT_ID,
                "variables": {
                    "phase": str(phase or ""),
                    "stage": str(stage or ""),
                    "user_id": str(user_id or ""),
                    "thread_id": str(thread_id or ""),
                    "run_id": str(run_id or ""),
                },
            }
        if RESPONSES_INSTRUCTIONS:
            create_kwargs["instructions"] = RESPONSES_INSTRUCTIONS
        if RESPONSES_INCLUDE_TOOLS:
            # Allow tool calling even if the dashboard Prompt ID is instruction-only.
            from shared.openai_tools import build_responses_tools

            allowed_domains = []
            if PA_WEB_SEARCH_ALLOWED_DOMAINS:
                allowed_domains = [d.strip() for d in PA_WEB_SEARCH_ALLOWED_DOMAINS.split(",") if d.strip()]
            tools_payload = build_responses_tools(
                include=list(tool_include_names or []),
                include_web_search=bool(PA_WEB_SEARCH_ENABLED) and bool(include_web_search),
                web_search_context_size=str(PA_WEB_SEARCH_CONTEXT_SIZE or "low"),
                web_search_allowed_domains=allowed_domains,
            )
            create_kwargs["tools"] = tools_payload
            # Compact provenance: record tool names included in this call.
            try:
                tools_included_names = []
                for t in tools_payload:
                    if not isinstance(t, dict):
                        continue
                    if t.get("type") == "web_search":
                        tools_included_names.append("web_search")
                    elif t.get("type") == "function":
                        tools_included_names.append(str(t.get("name") or ""))
                tools_included_names = [x for x in tools_included_names if x]
            except Exception:
                tools_included_names = []
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
            if (
                (not prompt_vars_forced)
                and ("Missing prompt variables" in msg or "prompt_variable_missing" in msg)
            ):
                prompt_vars_forced = True
                logging.warning(
                    "Responses prompt requires variables; retrying with prompt.variables "
                    f"user_id={user_id} thread_id={thread_id}"
                )
                continue
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
                "prompt_id": str(OPENAI_PROMPT_ID or ""),
                "prompt_vars_enabled": bool(RESPONSES_PROMPT_VARIABLES_ENABLED or prompt_vars_forced),
                "stage": str(stage or ""),
                "phase": str(phase or ""),
                "tools_included": tools_included_names,
                "include_web_search": bool(include_web_search),
                "web_search_enabled": bool(PA_WEB_SEARCH_ENABLED),
            }
            try:
                meta["web_search_allowed_domains"] = allowed_domains if isinstance(allowed_domains, list) else []
            except Exception:
                pass
            if intent_router:
                meta["intent_router"] = intent_router
            if isinstance(composer_meta, dict) and composer_meta:
                meta["composer_matrix_id"] = str(composer_meta.get("composer_matrix_id") or "")
                meta["composer_block_ids"] = list(composer_meta.get("composer_block_ids") or [])
                meta["composer_schema_id"] = str(composer_meta.get("composer_schema_id") or "")
                meta["composer_tools_id"] = str(composer_meta.get("composer_tools_id") or "")
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
            _best_effort_update_manifest_after_tool_call(
                user_id=str(user_id),
                tool_name=str(name or ""),
                tool_args=args if isinstance(args, dict) else {},
                result_str=str(result_str or ""),
            )
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
    thread_id = body.get("thread_id") or body.get("session_id")
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
                    _best_effort_update_manifest_after_tool_call(
                        user_id=str(user_id),
                        tool_name=str(name or ""),
                        tool_args=args if isinstance(args, dict) else {},
                        result_str=str(result_str or ""),
                    )
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
    runtime_used: str = "responses",
    responses_meta: Dict[str, Any] = None,
    run_id: str = "",
    trace_id: str = "",
    phase: str = "",
    stage: str = "",
    persist_run_artifact: bool = False,
):
    """Collect response metadata, save interaction, and return final HttpResponse."""
    assistant_response = str(assistant_response_override or "").strip()
    if not assistant_response:
        assistant_response = "No response from model."

    try:
        user_snip = (user_message or "")[:120]
        assistant_snip = (assistant_response or "")[:120]
        logging.info("--- interaction summary ---\n" + f"user_id={user_id} thread_id={thread_id}\n" + f"user_message={user_snip}\n" + f"assistant_message={assistant_snip}\n" + "--- end summary ---")
    except Exception:
        logging.debug("Failed to emit concise interaction summary")

    if log_interaction:
        # Persist provenance so we can later audit prompt/phase/stage and tool availability.
        interaction_metadata: Dict[str, Any] = {
            "runtime_used": str(runtime_used or ""),
        }
        if isinstance(responses_meta, dict):
            # Keep it compact; interaction_logs.json is user data.
            try:
                for k in (
                    "prompt_id",
                    "prompt_vars_enabled",
                    "phase",
                    "stage",
                    "tools_included",
                    "include_web_search",
                    "web_search_enabled",
                    "web_search_allowed_domains",
                    "intent_artifact_path",
                    "pa_intention",
                    "pa_intent_router",
                    "composer_matrix_id",
                    "composer_block_ids",
                    "composer_schema_id",
                    "composer_tools_id",
                ):
                    if k in responses_meta:
                        interaction_metadata[k] = responses_meta.get(k)
            except Exception:
                pass
        save_interaction_log_inprocess(
            user_id=user_id,
            user_message=user_message,
            assistant_response=assistant_response,
            thread_id=thread_id,
            tool_calls_info=all_tool_calls,
            interaction_metadata=interaction_metadata,
        )

    # `total_ms` can be supplied by caller; default to 0 if not provided.
    tools_ms = sum(call.get("duration_ms", 0) for call in all_tool_calls)
    run_artifact_path = ""
    if persist_run_artifact:
        run_artifact_path = _pa_write_run_artifact(
            user_id=str(user_id or ""),
            thread_id=str(thread_id or ""),
            run_id=str(run_id or ""),
            trace_id=str(trace_id or ""),
            runtime_used=str(runtime_used or ""),
            phase=str(phase or ""),
            stage=str(stage or ""),
            user_message=str(user_message or ""),
            assistant_response=str(assistant_response or ""),
            all_tool_calls=list(all_tool_calls or []),
            responses_meta=responses_meta if isinstance(responses_meta, dict) else {},
            total_ms=float(total_ms or 0),
        )
        if run_artifact_path and isinstance(responses_meta, dict):
            responses_meta["run_artifact_path"] = str(run_artifact_path)

    body = {
        "status": "success",
        "response": assistant_response,
        "thread_id": thread_id,
        "session_id": thread_id,
        "user_id": user_id,
        "runtime_used": runtime_used,
        "vector_store_attached": vector_store_attached,
        "tool_calls_count": len(all_tool_calls),
        "timings": {
            "total_ms": total_ms,
            "tools_ms": tools_ms,
        },
    }
    if run_artifact_path:
        body["run_artifact_path"] = str(run_artifact_path)
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


def _capability_response(status: str, capability: str, *, result: Dict[str, Any] | None = None, error: Dict[str, Any] | None = None, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    now_epoch = int(time.time())
    now_utc = datetime.datetime.utcfromtimestamp(now_epoch).replace(microsecond=0).isoformat() + "Z"
    merged_meta = dict(meta) if isinstance(meta, dict) else {}
    merged_meta.setdefault("now_utc", now_utc)
    merged_meta.setdefault("now_epoch", now_epoch)
    merged_meta.setdefault("request_id", str(uuid.uuid4()))
    merged_meta.setdefault("run_id", f"cap_{now_epoch}_{uuid.uuid4().hex[:8]}")
    merged_meta.setdefault("duration_ms", 0)

    payload: Dict[str, Any] = {
        "schema_version": "omniflow.capability_exec.v1",
        "status": status,
        "action": "capability_exec",
        "capability": str(capability or ""),
        "result": result if isinstance(result, dict) else None,
        "error": error if isinstance(error, dict) else None,
        "meta": merged_meta,
    }
    return payload


def _tm_flatten_with_refs(tm_data: Any) -> Tuple[list[dict], list[dict]]:
    rows: list[dict] = []
    refs: list[dict] = []
    if not isinstance(tm_data, list):
        return rows, refs
    idx = 1
    for top_i, item in enumerate(tm_data):
        if isinstance(item, dict) and isinstance(item.get("tasks"), list):
            nested = item.get("tasks") or []
            for nested_i, task in enumerate(nested):
                if not isinstance(task, dict):
                    continue
                title = str(task.get("title") or task.get("content") or f"Task {idx}")
                row = {
                    "task_index": idx,
                    "id": task.get("id"),
                    "title": title,
                    "status": str(task.get("status") or "unknown"),
                    "due_date": task.get("due_date"),
                    "priority": task.get("priority"),
                    "tags": task.get("tags"),
                    "estimated_time": task.get("estimated_time"),
                    "energy": task.get("energy"),
                    "created_at": task.get("created_at"),
                    "updated_at": task.get("updated_at"),
                    "source": "nested",
                }
                rows.append(row)
                refs.append({"kind": "nested", "top_index": top_i, "nested_index": nested_i})
                idx += 1
            continue
        if isinstance(item, dict):
            title = str(item.get("title") or item.get("content") or item.get("task") or f"Task {idx}")
            row = {
                "task_index": idx,
                "id": item.get("id"),
                "title": title,
                "status": str(item.get("status") or "unknown"),
                "due_date": item.get("due_date"),
                "priority": item.get("priority"),
                "tags": item.get("tags"),
                "estimated_time": item.get("estimated_time"),
                "energy": item.get("energy"),
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "source": "top",
            }
            rows.append(row)
            refs.append({"kind": "top", "top_index": top_i})
            idx += 1
    return rows, refs


def _next_task_id(rows: list[dict]) -> str:
    seq = 1
    for row in rows:
        raw_id = str(row.get("id") or "")
        match = re.match(r"^TM\.(\d+)\.", raw_id)
        if not match:
            continue
        try:
            seq = max(seq, int(match.group(1)) + 1)
        except Exception:
            continue
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M")
    return f"TM.{seq:03d}.{ts}"


def _mail_extract_header(message_obj: Dict[str, Any], header_name: str) -> str:
    payload = message_obj.get("payload") if isinstance(message_obj, dict) else None
    headers = payload.get("headers") if isinstance(payload, dict) else None
    if not isinstance(headers, list):
        return ""
    target = str(header_name or "").strip().lower()
    for item in headers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if name == target:
            return str(item.get("value") or "").strip()
    return ""


def _mail_enriched_row(raw_item: Dict[str, Any], message_obj: Dict[str, Any]) -> Dict[str, Any]:
    internal_date = str(message_obj.get("internalDate") or "").strip() if isinstance(message_obj, dict) else ""
    date_value = _mail_extract_header(message_obj, "Date") or internal_date
    label_ids = list(raw_item.get("labelIds") or []) if isinstance(raw_item.get("labelIds"), list) else []
    return {
        "id": str(raw_item.get("id") or "").strip(),
        "threadId": str(raw_item.get("threadId") or "").strip(),
        "from": _mail_extract_header(message_obj, "From"),
        "subject": _mail_extract_header(message_obj, "Subject"),
        "snippet": str(message_obj.get("snippet") or "").strip() if isinstance(message_obj, dict) else "",
        "date": date_value,
        "labelIds": label_ids[:50],
    }


def _mail_normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    elif isinstance(value, tuple):
        items = list(value)
    elif isinstance(value, str):
        items = value.split(",")
    else:
        items = [value]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _bridge_action(action: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    # Keep Gmail behavior aligned with custom_bridge implementation.
    from custom_bridge.__init__ import ACTION_HANDLERS as BRIDGE_HANDLERS

    handler = BRIDGE_HANDLERS.get(str(action or "").strip())
    if not callable(handler):
        raise ValueError(f"Unsupported bridge action: {action}")
    return handler(str(user_id), dict(payload or {}), None)


def _try_record_session_event(
    user_id: str,
    params: Dict[str, Any],
    resp_body: Dict[str, Any],
    resp_status: int,
    *,
    thread_id: Optional[str] = None,
    interaction_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """Fire-and-forget session event append. Never raises."""
    if not SESSION_MANIFEST_AVAILABLE:
        return
    try:
        cap = str((params or {}).get("capability") or "").strip()
        if not cap:
            return
        _, is_mutating = _classify_cap(cap)
        # state_changed: mutating capability + success response
        state_changed = is_mutating and (resp_status == 200)
        result = (resp_body or {}).get("result") or {}
        artifacts_updated: List[str] = []
        if isinstance(result, dict) and result.get("blob_name"):
            artifacts_updated = [str(result["blob_name"])]
        gpt_note: Optional[str] = None
        if state_changed:
            # Build a minimal note from result keys for GPT context
            note_parts = []
            if isinstance(result, dict):
                for k in ("interaction_id", "updated_keys", "message_id", "task_id"):
                    v = result.get(k)
                    if v:
                        note_parts.append(f"{k}={v}")
            gpt_note = "; ".join(note_parts) if note_parts else None
        event = build_session_event(
            user_id=user_id,
            capability=cap,
            thread_id=thread_id,
            state_changed=state_changed,
            artifacts_updated=artifacts_updated,
            gpt_note=gpt_note,
            interaction_id=interaction_id,
            request_id=request_id,
        )
        append_session_event(user_id, event)
    except Exception as exc:  # pragma: no cover
        logging.warning("_try_record_session_event: %s", exc)


def _handle_capability_exec(user_id: str, params: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    capability = str((params or {}).get("capability") or "").strip()
    arguments = (params or {}).get("arguments") or {}
    if not isinstance(arguments, dict):
        body = _capability_response(
            "error",
            capability,
            error={"code": "INVALID_ARGUMENTS", "message": "params.arguments must be an object"},
        )
        return body, 400
    confirm = bool((params or {}).get("confirm", False))

    if not capability:
        body = _capability_response(
            "error",
            capability,
            error={"code": "INVALID_REQUEST", "message": "capability is required"},
        )
        return body, 400

    # Some clients pass user_id inside params.arguments; prefer it when present.
    effective_user_id = str(arguments.get("user_id") or user_id or "").strip() or "default"

    # Compatibility fallback for clients that send account_slot outside params.arguments.
    def _resolve_account_slot(default: str = "primary") -> str:
        return str(arguments.get("account_slot") or (params or {}).get("account_slot") or default).strip() or default

    try:
        if capability == "system.now":
            now_utc = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
            return _capability_response("success", capability, result={"current_time_utc": now_utc}), 200

        if capability == "mail.status":
            account_slot = _resolve_account_slot()
            result = _bridge_action("oauth_status", str(effective_user_id), {"account_slot": account_slot})
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.authorize":
            account_slot = _resolve_account_slot()
            result = _bridge_action("ensure_authorized", str(effective_user_id), {
                "login_hint": arguments.get("login_hint"),
                "account_slot": account_slot,
                "force": bool(arguments.get("force", False)),
            })
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.inbox.list":
            max_results = int(arguments.get("max_results", arguments.get("limit", 20)) or 20)
            account_slot = _resolve_account_slot()
            payload = {
                "max_results": max(1, min(50, max_results)),
                "q": arguments.get("q") or arguments.get("query"),
                "category": arguments.get("category"),
                "label_ids": _mail_normalize_list(arguments.get("label_ids") or arguments.get("labelIds") or arguments.get("label")),
                "exclude_label_ids": _mail_normalize_list(arguments.get("exclude_label_ids") or arguments.get("excludeLabelIds")),
                "include_spam_trash": bool(arguments.get("include_spam_trash", arguments.get("includeSpamTrash", False))),
                "page_token": arguments.get("page_token") or arguments.get("pageToken"),
                "account_slot": account_slot,
            }
            result = _bridge_action("gmail_list", str(effective_user_id), payload)
            messages = list(result.get("messages") or []) if isinstance(result, dict) else []
            metadata_limit = int(arguments.get("metadata_limit", 20) or 20)
            metadata_limit = max(1, min(20, metadata_limit))
            enriched: list[dict] = []
            for idx, raw_item in enumerate(messages):
                if not isinstance(raw_item, dict):
                    continue
                mid = str(raw_item.get("id") or "").strip()
                if not mid:
                    continue
                message_obj: Dict[str, Any] = {}
                if idx < metadata_limit:
                    try:
                        got = _bridge_action(
                            "gmail_get",
                            str(effective_user_id),
                            {"message_id": mid, "format": "metadata", "account_slot": account_slot},
                        )
                        message_obj = dict(got.get("message") or {}) if isinstance(got, dict) else {}
                    except Exception:
                        message_obj = {}
                enriched.append(_mail_enriched_row(raw_item, message_obj))
            result["messages"] = enriched
            result["enriched_count"] = len([m for m in enriched if (m.get("subject") or m.get("from") or m.get("snippet"))])
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.search":
            max_results = int(arguments.get("max_results", arguments.get("limit", 20)) or 20)
            account_slot = _resolve_account_slot()
            query = str(arguments.get("query") or arguments.get("q") or "").strip()
            if not query:
                return _capability_response("error", capability, error={"code": "INVALID_REQUEST", "message": "arguments.query is required"}), 400
            payload = {
                "max_results": max(1, min(50, max_results)),
                "q": query,
                "category": arguments.get("category"),
                "label_ids": _mail_normalize_list(arguments.get("label_ids") or arguments.get("labelIds")),
                "exclude_label_ids": _mail_normalize_list(arguments.get("exclude_label_ids") or arguments.get("excludeLabelIds")),
                "include_spam_trash": bool(arguments.get("include_spam_trash", arguments.get("includeSpamTrash", False))),
                "page_token": arguments.get("page_token") or arguments.get("pageToken"),
                "account_slot": account_slot,
            }
            result = _bridge_action("gmail_search", str(effective_user_id), payload)
            messages = list(result.get("messages") or []) if isinstance(result, dict) else []
            metadata_limit = int(arguments.get("metadata_limit", 20) or 20)
            metadata_limit = max(1, min(20, metadata_limit))
            enriched: list[dict] = []
            for idx, raw_item in enumerate(messages):
                if not isinstance(raw_item, dict):
                    continue
                mid = str(raw_item.get("id") or "").strip()
                if not mid:
                    continue
                message_obj: Dict[str, Any] = {}
                if idx < metadata_limit:
                    try:
                        got = _bridge_action(
                            "gmail_get",
                            str(effective_user_id),
                            {"message_id": mid, "format": "metadata", "account_slot": account_slot},
                        )
                        message_obj = dict(got.get("message") or {}) if isinstance(got, dict) else {}
                    except Exception:
                        message_obj = {}
                enriched.append(_mail_enriched_row(raw_item, message_obj))
            result["messages"] = enriched
            result["enriched_count"] = len([m for m in enriched if (m.get("subject") or m.get("from") or m.get("snippet"))])
            result["query"] = query
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.read":
            message_id = str(arguments.get("message_id") or "").strip()
            if not message_id:
                return _capability_response("error", capability, error={"code": "INVALID_REQUEST", "message": "arguments.message_id is required"}), 400
            account_slot = _resolve_account_slot()
            payload = {"message_id": message_id, "format": str(arguments.get("format") or "full"), "account_slot": account_slot}
            result = _bridge_action("gmail_get", str(effective_user_id), payload)
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.summarize":
            max_results = int(arguments.get("max_results", 10) or 10)
            account_slot = _resolve_account_slot()
            list_result = _bridge_action("gmail_list", str(effective_user_id), {"max_results": max(1, min(20, max_results)), "account_slot": account_slot})
            ids = [str(x.get("id")) for x in (list_result.get("messages") or []) if isinstance(x, dict) and x.get("id")]
            summary_items: list[dict] = []
            for mid in ids[:5]:
                try:
                    msg = _bridge_action("gmail_get", str(effective_user_id), {"message_id": mid, "format": "metadata", "account_slot": account_slot})
                    summary_items.append({"message_id": mid, "message": msg.get("message")})
                except Exception:
                    continue
            result = {
                "listed": int(len(ids)),
                "sampled": int(len(summary_items)),
                "items": summary_items,
            }
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.send":
            if not confirm:
                return _capability_response(
                    "error",
                    capability,
                    error={"code": "CONFIRMATION_REQUIRED", "message": "Set params.confirm=true to send email."},
                ), 409
            account_slot = _resolve_account_slot()
            to = arguments.get("to")
            if isinstance(to, str):
                to = [to]
            payload = {
                "to": list(to or []),
                "subject": str(arguments.get("subject") or ""),
                "body": str(arguments.get("body") or ""),
                "cc": list(arguments.get("cc") or []),
                "bcc": list(arguments.get("bcc") or []),
                "attachments": list(arguments.get("attachments") or []),
                "account_slot": account_slot,
            }
            if not payload["to"] or not payload["subject"] or not payload["body"]:
                return _capability_response(
                    "error",
                    capability,
                    error={"code": "INVALID_REQUEST", "message": "arguments.to, arguments.subject and arguments.body are required"},
                ), 400
            result = _bridge_action("gmail_send", str(effective_user_id), payload)
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.reply":
            if not confirm:
                return _capability_response(
                    "error",
                    capability,
                    error={"code": "CONFIRMATION_REQUIRED", "message": "Set params.confirm=true to send email."},
                ), 409
            account_slot = _resolve_account_slot()
            message_id = str(arguments.get("message_id") or "").strip()
            body = str(arguments.get("body") or "")
            if not message_id:
                return _capability_response(
                    "error",
                    capability,
                    error={"code": "INVALID_REQUEST", "message": "arguments.message_id is required"},
                ), 400
            if not body:
                return _capability_response(
                    "error",
                    capability,
                    error={"code": "INVALID_REQUEST", "message": "arguments.body is required"},
                ), 400
            to = arguments.get("to")
            if isinstance(to, str):
                to = [to]
            payload = {
                "message_id": message_id,
                "to": list(to or []),
                "subject": str(arguments.get("subject") or ""),
                "body": body,
                "cc": list(arguments.get("cc") or []),
                "bcc": list(arguments.get("bcc") or []),
                "attachments": list(arguments.get("attachments") or []),
                "account_slot": account_slot,
            }
            result = _bridge_action("gmail_reply", str(effective_user_id), payload)
            return _capability_response("success", capability, result=result), 200

        if capability in ("mail.trash", "mail.delete"):
            if not confirm:
                return _capability_response(
                    "error",
                    capability,
                    error={"code": "CONFIRMATION_REQUIRED", "message": "Set params.confirm=true for destructive mail action."},
                ), 409
            message_id = str(arguments.get("message_id") or "").strip()
            if not message_id:
                return _capability_response("error", capability, error={"code": "INVALID_REQUEST", "message": "arguments.message_id is required"}), 400
            account_slot = _resolve_account_slot()
            action = "gmail_trash" if capability == "mail.trash" else "gmail_delete"
            result = _bridge_action(action, str(effective_user_id), {"message_id": message_id, "account_slot": account_slot})
            return _capability_response("success", capability, result=result), 200

        if capability == "mail.accounts.list":
            result = _bridge_action("gmail_accounts_list", str(effective_user_id), {})
            return _capability_response("success", capability, result=result), 200

        if capability == "calendar.events.list":
            account_slot = _resolve_account_slot()
            def _to_rfc3339(val: Any) -> Any:
                """Normalise bare date YYYY-MM-DD → YYYY-MM-DDT00:00:00Z for Google Calendar."""
                if isinstance(val, str) and len(val) == 10 and val[4] == "-" and val[7] == "-":
                    return val + "T00:00:00Z"
                return val
            payload = {
                "account_slot": account_slot,
                "time_min": _to_rfc3339(arguments.get("time_min")),
                "time_max": _to_rfc3339(arguments.get("time_max")),
                "max_results": arguments.get("max_results"),
                "calendar_ids": arguments.get("calendar_ids") or arguments.get("calendarIds"),
                "include_all_calendars": bool(arguments.get("include_all_calendars", arguments.get("includeAllCalendars", True))),
            }
            result = _bridge_action("calendar_list_events", str(effective_user_id), payload)
            return _capability_response("success", capability, result=result), 200

        if capability == "calendar.events.get":
            event_id = str(arguments.get("event_id") or "").strip()
            if not event_id:
                return _capability_response("error", capability, error={"code": "INVALID_REQUEST", "message": "arguments.event_id is required"}), 400
            account_slot = _resolve_account_slot()
            result = _bridge_action("calendar_get_event", str(effective_user_id), {"event_id": event_id, "account_slot": account_slot})
            return _capability_response("success", capability, result=result), 200

        if capability == "calendar.events.create":
            if not confirm:
                return _capability_response("error", capability, error={"code": "CONFIRMATION_REQUIRED", "message": "Set params.confirm=true to create calendar event."}), 409
            account_slot = _resolve_account_slot()
            payload = {k: arguments[k] for k in ("summary", "description", "start", "end", "attendees", "location", "recurrence") if k in arguments}
            payload["account_slot"] = account_slot
            result = _bridge_action("calendar_create_event", str(effective_user_id), payload)
            return _capability_response("success", capability, result=result), 200

        if capability == "calendar.events.update":
            event_id = str(arguments.get("event_id") or "").strip()
            if not event_id:
                return _capability_response("error", capability, error={"code": "INVALID_REQUEST", "message": "arguments.event_id is required"}), 400
            account_slot = _resolve_account_slot()
            payload = {k: arguments[k] for k in ("summary", "description", "start", "end", "attendees", "location", "recurrence") if k in arguments}
            payload["event_id"] = event_id
            payload["account_slot"] = account_slot
            result = _bridge_action("calendar_update_event", str(effective_user_id), payload)
            return _capability_response("success", capability, result=result), 200

        if capability == "calendar.events.delete":
            if not confirm:
                return _capability_response("error", capability, error={"code": "CONFIRMATION_REQUIRED", "message": "Set params.confirm=true to delete calendar event."}), 409
            event_id = str(arguments.get("event_id") or "").strip()
            if not event_id:
                return _capability_response("error", capability, error={"code": "INVALID_REQUEST", "message": "arguments.event_id is required"}), 400
            account_slot = _resolve_account_slot()
            result = _bridge_action("calendar_delete_event", str(effective_user_id), {"event_id": event_id, "account_slot": account_slot})
            return _capability_response("success", capability, result=result), 200

        if capability.startswith("task."):
            raw = _inprocess_read_blob_file(str(effective_user_id), "TM.json")
            tm_data = raw.get("data") if isinstance(raw, dict) else None
            if not isinstance(tm_data, list):
                tm_data = []
            rows, refs = _tm_flatten_with_refs(tm_data)
            id_to_index = {
                str(row.get("id")): int(row.get("task_index"))
                for row in rows
                if str(row.get("id") or "").strip()
            }

            if capability == "task.list":
                return _capability_response("success", capability, result={"tasks": rows, "count": len(rows)}), 200

            if capability == "task.delayed":
                today = datetime.datetime.utcnow().date().isoformat()
                delayed = [
                    r for r in rows
                    if str(r.get("due_date") or "").strip()
                    and str(r.get("due_date")) < today
                    and str(r.get("status") or "").lower() not in ("done", "completed")
                ]
                return _capability_response("success", capability, result={"tasks": delayed, "count": len(delayed)}), 200

            if capability == "task.create":
                title = str(arguments.get("title") or arguments.get("content") or "").strip()
                if not title:
                    return _capability_response("error", capability, error={"code": "INVALID_REQUEST", "message": "arguments.title is required"}), 400
                now_utc = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
                entry = {
                    "id": _next_task_id(rows),
                    "timestamp": now_utc,
                    "created_at": now_utc,
                    "updated_at": now_utc,
                    "title": title,
                    "status": str(arguments.get("status") or "open"),
                }
                if arguments.get("due_date"):
                    entry["due_date"] = arguments.get("due_date")
                if arguments.get("priority"):
                    entry["priority"] = arguments.get("priority")
                if arguments.get("tags") is not None:
                    entry["tags"] = list(arguments.get("tags") or [])
                if arguments.get("estimated_time") is not None:
                    entry["estimated_time"] = arguments.get("estimated_time")
                if arguments.get("energy") is not None:
                    entry["energy"] = arguments.get("energy")
                tm_data.append(entry)
                _inprocess_upload_data_or_file(str(effective_user_id), "TM.json", tm_data)
                # Compute index from flattened refs after persist so returned task_index
                # matches the same index space used by task.update/task.complete/task.delete.
                rows_after, _ = _tm_flatten_with_refs(tm_data)
                created_id = str(entry.get("id") or "").strip()
                created_index = None
                if created_id:
                    for row in rows_after:
                        if str(row.get("id") or "").strip() == created_id:
                            try:
                                created_index = int(row.get("task_index"))
                            except (TypeError, ValueError):
                                created_index = None
                            break
                if not created_index:
                    # Fallback to last flattened row if id lookup fails unexpectedly.
                    created_index = len(rows_after)
                return _capability_response("success", capability, result={"created": entry, "task_index": created_index}), 200

            task_id = str(arguments.get("id") or "").strip()
            task_index = int(arguments.get("task_index") or 0)
            if task_id and task_id in id_to_index:
                task_index = id_to_index[task_id]
            if task_index < 1 or task_index > len(refs):
                return _capability_response("error", capability, error={"code": "NOT_FOUND", "message": "Task not found. Provide arguments.id or valid arguments.task_index."}), 404
            ref = refs[task_index - 1]
            if str(ref.get("kind")) == "nested":
                target = tm_data[ref["top_index"]]["tasks"][ref["nested_index"]]
            else:
                target = tm_data[ref["top_index"]]

            if capability == "task.update":
                for field in ("title", "content", "status", "due_date", "priority", "tags", "estimated_time", "energy"):
                    if field in arguments and arguments.get(field) is not None:
                        target[field] = arguments.get(field)
                target["updated_at"] = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
                _inprocess_upload_data_or_file(str(effective_user_id), "TM.json", tm_data)
                return _capability_response("success", capability, result={"updated": target, "task_index": task_index}), 200

            if capability == "task.complete":
                target["status"] = "done"
                target["updated_at"] = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
                _inprocess_upload_data_or_file(str(effective_user_id), "TM.json", tm_data)
                return _capability_response("success", capability, result={"completed": True, "task_index": task_index}), 200

            if capability == "task.delete":
                if not confirm:
                    return _capability_response(
                        "error",
                        capability,
                        error={"code": "CONFIRMATION_REQUIRED", "message": "Set params.confirm=true for task.delete."},
                    ), 409
                if str(ref.get("kind")) == "nested":
                    deleted = tm_data[ref["top_index"]]["tasks"].pop(ref["nested_index"])
                else:
                    deleted = tm_data.pop(ref["top_index"])
                _inprocess_upload_data_or_file(str(effective_user_id), "TM.json", tm_data)
                return _capability_response("success", capability, result={"deleted": deleted, "task_index": task_index, "id": deleted.get("id")}), 200

        if capability == "planning.build_day_plan":
            raw = _inprocess_read_blob_file(str(effective_user_id), "TM.json")
            tm_data = raw.get("data") if isinstance(raw, dict) else None
            if not isinstance(tm_data, list):
                tm_data = []
            rows, _ = _tm_flatten_with_refs(tm_data)

            today = datetime.datetime.utcnow().date().isoformat()
            overdue = [
                r for r in rows
                if str(r.get("due_date") or "").strip()
                and str(r.get("due_date")) < today
                and str(r.get("status") or "").lower() not in ("done", "completed")
            ]
            due_today = [
                r for r in rows
                if str(r.get("due_date") or "").strip() == today
                and str(r.get("status") or "").lower() not in ("done", "completed")
            ]
            in_progress = [
                r for r in rows
                if str(r.get("status") or "").lower() in ("in_progress", "in-progress", "doing", "started")
            ]

            morning = [f"Review delayed task: {r.get('title')}" for r in overdue[:5]]
            midday = [f"Execute today task: {r.get('title')}" for r in due_today[:5]]
            afternoon = [f"Continue in-progress task: {r.get('title')}" for r in in_progress[:5]]

            if not morning and overdue:
                morning = ["Review delayed tasks"]
            if not midday and due_today:
                midday = ["Execute planned tasks for today"]
            if not afternoon and in_progress:
                afternoon = ["Continue in-progress tasks"]

            result = {
                "summary": {
                    "tasks_total": len(rows),
                    "overdue_count": len(overdue),
                    "today_count": len(due_today),
                    "in_progress_count": len(in_progress),
                },
                "sections": {
                    "Morning": morning,
                    "Midday": midday,
                    "Afternoon": afternoon,
                },
                "source": {
                    "now": "system.now (in-process)",
                    "tasks": "task.list (TM.json)",
                    "delayed": "task.delayed (derived)",
                },
            }
            return _capability_response("success", capability, result=result), 200

        if capability == "memory.interaction.save":
            user_message = str(arguments.get("user_message") or "").strip()
            assistant_response = str(arguments.get("assistant_response") or "").strip()
            role = str(arguments.get("role") or "").strip().lower()
            content = str(arguments.get("content") or "").strip()

            normalized_from_role_content = False
            if content and role in ("user", "assistant") and (not user_message or not assistant_response):
                normalized_from_role_content = True
                if role == "user":
                    user_message = user_message or content
                    assistant_response = assistant_response or "[pending_assistant_response]"
                else:
                    user_message = user_message or "[pending_user_message]"
                    assistant_response = assistant_response or content

            if not user_message or not assistant_response:
                return _capability_response(
                    "error",
                    capability,
                    error={
                        "code": "INVALID_REQUEST",
                        "message": "Provide arguments.user_message and arguments.assistant_response, or arguments.role + arguments.content.",
                    },
                ), 400

            save_payload = {
                "user_message": user_message,
                "assistant_response": assistant_response,
                "thread_id": str(arguments.get("thread_id") or "capability-thread"),
                "tool_calls": list(arguments.get("tool_calls") or []),
                "metadata": dict(arguments.get("metadata") or {}),
            }
            parsed = _inprocess_save_interaction(str(effective_user_id), save_payload)
            if isinstance(parsed, dict) and parsed.get("status") == "error":
                return _capability_response(
                    "error",
                    capability,
                    error={
                        "code": "SAVE_INTERACTION_FAILED",
                        "message": str(parsed.get("error") or parsed.get("details") or "Unknown save_interaction error"),
                    },
                    result={"raw": parsed},
                ), 400

            result_payload = parsed if isinstance(parsed, dict) else {"raw": parsed}
            if normalized_from_role_content:
                result_payload = {**dict(result_payload or {}), "normalized_from_role_content": True}
            return _capability_response("success", capability, result=result_payload), 200

        if capability == "memory.preferences.get":
            prefs = _load_preferences(str(effective_user_id))
            if not isinstance(prefs, dict) or not prefs:
                prefs = _wp6_default_preferences()
            return _capability_response("success", capability, result={"preferences": prefs}), 200

        if capability == "memory.preferences.update":
            base = _load_preferences(str(effective_user_id))
            if not isinstance(base, dict) or not base:
                base = _wp6_default_preferences()

            if isinstance(arguments.get("preferences"), dict):
                updates_raw = dict(arguments.get("preferences") or {})
            else:
                updates_raw = dict(arguments or {})

            allowed_keys = {"brevity", "fast_mode", "allowed_reads", "disable_history_reads"}
            updates: Dict[str, Any] = {}
            for key in allowed_keys:
                if key in updates_raw:
                    updates[key] = updates_raw.get(key)

            if "allowed_reads" in updates:
                updates["allowed_reads"] = [str(x) for x in list(updates.get("allowed_reads") or [])]

            merged = {
                **dict(base or {}),
                **updates,
                "schema_version": "omniflow.wp6.preferences.v1",
                "updated_utc": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            }
            ok, reason = _wp6_validate_preferences(merged)
            if not ok:
                return _capability_response(
                    "error",
                    capability,
                    error={
                        "code": "INVALID_PREFERENCES",
                        "message": f"Invalid preferences payload: {reason}",
                    },
                ), 400

            save_result = _inprocess_upload_data_or_file(str(effective_user_id), "semantics/preferences.json", merged)
            if isinstance(save_result, dict) and save_result.get("status") == "error":
                return _capability_response(
                    "error",
                    capability,
                    error={"code": "STORAGE_ERROR", "message": str(save_result.get("error") or "Failed to save preferences")},
                ), 500

            if PREFERENCES_CACHE_TTL_SECONDS > 0:
                with CACHE_LOCK:
                    _prefs_cache[str(effective_user_id)] = {"data": merged, "ts": time.time()}

            provided_keys = set(updates_raw.keys()) - {"schema_version", "updated_utc"}
            unknown_keys = sorted(provided_keys - allowed_keys)
            result_payload: Dict[str, Any] = {"preferences": merged, "updated_keys": sorted(list(updates.keys()))}
            if unknown_keys:
                result_payload["unknown_keys"] = unknown_keys
            return _capability_response(
                "success",
                capability,
                result=result_payload,
            ), 200

        if capability == "memory.interaction.list":
            history_params = {
                "limit": int(arguments.get("limit", 20) or 20),
                "offset": int(arguments.get("offset", 0) or 0),
            }
            thread_id_arg = str(arguments.get("thread_id") or "").strip()
            if thread_id_arg:
                history_params["thread_id"] = thread_id_arg
            parsed = _inprocess_get_interaction_history(str(effective_user_id), history_params)
            if isinstance(parsed, dict):
                result = {
                    "interactions": list(parsed.get("interactions") or []),
                    "total_count": int(parsed.get("total_count") or 0),
                    "returned_count": int(parsed.get("returned_count") or 0),
                    "offset": int(parsed.get("offset") or 0),
                    "limit": int(parsed.get("limit") or history_params.get("limit") or 20),
                }
            else:
                result = {"interactions": [], "total_count": 0, "returned_count": 0, "offset": 0, "limit": int(history_params.get("limit") or 20), "raw": parsed}
            return _capability_response("success", capability, result=result), 200

        if capability == "memory.session.summary.get":
            if not SESSION_MANIFEST_AVAILABLE:
                return _capability_response("error", capability, error={"code": "UNSUPPORTED_CAPABILITY", "message": "Session manifest not available"}), 400
            from shared.session_manifest import build_session_summary
            summary = build_session_summary(str(effective_user_id))
            return _capability_response("success", capability, result=summary), 200

        if capability == "memory.session.events.list":
            if not SESSION_MANIFEST_AVAILABLE:
                return _capability_response("error", capability, error={"code": "UNSUPPORTED_CAPABILITY", "message": "Session manifest not available"}), 400
            from shared.session_manifest import list_session_events
            limit = int(arguments.get("limit", 20) or 20)
            offset = int(arguments.get("offset", 0) or 0)
            events = list_session_events(str(effective_user_id), limit=max(1, min(100, limit)), offset=max(0, offset))
            return _capability_response("success", capability, result={"events": events, "returned_count": len(events), "limit": limit, "offset": offset}), 200

        return _capability_response(
            "error",
            capability,
            error={"code": "UNSUPPORTED_CAPABILITY", "message": f"Capability not supported: {capability}"},
        ), 400
    except Exception as exc:
        logging.error("capability_exec failed for %s: %s", capability, exc, exc_info=True)
        msg = str(exc or "")
        if capability.startswith(("mail.", "calendar.")) and (
            "oauth2.googleapis.com/token" in msg
            or "Token exchange failed" in msg
            or "NOT_AUTHORIZED" in msg
            or "Gmail tokens not found" in msg
            or "Refresh token missing" in msg
        ):
            err = _capability_response(
                "error",
                capability,
                error={
                    "code": "MAIL_AUTH_REQUIRED",
                    "message": "Email access is not authorized. Gmail authorization is required before mailbox operations can be performed.",
                },
            )
            return err, 409
        err = _capability_response(
            "error",
            capability,
            error={"code": "INTERNAL_ERROR", "message": msg},
        )
        return err, 500


def _openai_rest_headers() -> Dict[str, str]:
    """Build standard headers for OpenAI REST requests."""
    return {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}


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
                    "error": result.get("error") or result.get("message") or "Unknown error",
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
    interaction_metadata: Dict[str, Any] | None = None,
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
                metadata={
                    "assistant_id": ASSISTANT_ID,
                    "source": "tool_call_handler",
                    **(interaction_metadata or {}),
                },
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
        thread_id = body.get("thread_id") or body.get("session_id")
        time_only = bool(body.get("time_only", False))
        action = body.get("action")
        params = body.get("params", {})
        log_interaction = bool(body.get("log_interaction", True))
        trace_id = str(body.get("trace_id") or "").strip()
        # UI may send phase/stage, but backend owns these semantics.
        # Keep UI values only for debug (do not trust them for orchestration).
        phase_ui = str(body.get("phase") or "").strip()
        stage_ui = str(body.get("stage") or "").strip()

        def _mentions_gmail(msg: str) -> bool:
            m = str(msg or "").lower()
            return any(k in m for k in ("gmail", "mail", "maile", "wiadom", "inbox", "skrzynk"))

        def _mentions_mail_flow(msg: str) -> bool:
            m = str(msg or "").lower()
            return any(
                k in m
                for k in ("gmail", "mail", "maile", "wiadom", "inbox", "skrzynk", "odpisz", "reply", "wyslij", "send")
            )

        def _mentions_tasks(msg: str) -> bool:
            m = str(msg or "").lower()
            return any(
                k in m
                for k in ("task", "tasks", "zadanie", "zadania", "todo", "to-do", "do zrobienia", "co mam jeszcze")
            )

        def _is_custom_gpt_request() -> bool:
            try:
                hdrs = {str(k).lower(): str(v).lower() for k, v in dict(req.headers or {}).items()}
            except Exception:
                hdrs = {}
            ua = str(hdrs.get("user-agent") or "")
            if any(k.startswith("x-openai-") for k in hdrs.keys()):
                return True
            if any(tok in ua for tok in ("chatgpt", "gpt-actions", "openai")):
                return True
            hints = " ".join(
                [
                    str(body.get("client") or ""),
                    str(body.get("channel") or ""),
                    str(body.get("source") or ""),
                    str(body.get("origin") or ""),
                    str(body.get("caller") or ""),
                ]
            ).lower()
            return any(
                x in hints
                for x in ("custom_gpt", "custom-gpt", "gpt_action", "gpt-action", "chatgpt", "openai_actions")
            )

        if action == "chat" and _is_custom_gpt_request():
            return _make_response(
                {
                    "status": "error",
                    "action": "chat",
                    "error": {
                        "code": "UNSUPPORTED_FOR_CUSTOM_GPT",
                        "message": "Custom GPT requests must use action=capability_exec.",
                    },
                },
                status_code=403,
            )

        if not action and isinstance(user_message, str) and user_message.strip():
            # Deterministic OAuth gate: if Gmail is not connected, do not involve the LLM.
            # This prevents "oauth_status loops" and makes the failure mode explicit and testable.
            if _mentions_gmail(user_message):
                try:
                    from shared.gmail_oauth import GmailTokenStore

                    tokens = GmailTokenStore.load_tokens(str(user_id))
                except Exception as exc:
                    return _make_response(
                        {
                            "status": "error",
                            "code": "GMAIL_OAUTH_NOT_CONFIGURED",
                            "error": f"Gmail OAuth token store unavailable: {type(exc).__name__}: {exc}",
                            "required_action": "configure_gmail_oauth",
                            "authorized": False,
                            "user_id": str(user_id),
                        },
                        status_code=503,
                    )
                if not tokens:
                    return _make_response(
                        {
                            "status": "error",
                            "code": "NOT_AUTHORIZED",
                            "error": "Gmail not connected for this user. Use UI Gmail OAuth Connect, then retry.",
                            "required_action": "gmail_oauth_connect",
                            "authorized": False,
                            "user_id": str(user_id),
                        },
                        status_code=409,
                    )

        # Direct actions bypass agent/tool loop
        if action in ["save_interaction", "get_interaction_history"]:
            resp_direct = handle_direct_actions(req, body, action, user_id)
            if resp_direct is not None:
                return resp_direct

        # Deterministic capability layer for Custom GPT schema-first integration.
        # This path intentionally avoids legacy context builder/composer reads.
        if action == "capability_exec":
            capability_params = params if isinstance(params, dict) else {}
            resp_body, resp_status = _handle_capability_exec(str(user_id), capability_params)
            _try_record_session_event(
                str(user_id),
                capability_params,
                resp_body,
                int(resp_status),
                thread_id=str(body.get("thread_id") or "").strip() or None,
                request_id=str(body.get("request_id") or "").strip() or None,
            )
            return _make_response(resp_body, status_code=int(resp_status))

        def _is_local_request() -> bool:
            try:
                host = str(req.headers.get("host") or req.headers.get("Host") or "")
            except Exception:
                host = ""
            host = host.lower().strip()
            return host.startswith("localhost") or host.startswith("127.0.0.1")

        request_env = str(body.get("environment") or body.get("env") or "").strip().lower()
        runtime_env = str(
            os.environ.get("OMNIFLOW_ENV")
            or os.environ.get("ENVIRONMENT")
            or os.environ.get("APP_ENV")
            or ""
        ).strip().lower()
        is_dev_context = bool(_is_local_request() or request_env in ("dev", "local") or runtime_env in ("dev", "local"))
        persist_run_artifact = bool(PA_RUN_ARTIFACT_ENABLED and (is_dev_context or (not PA_RUN_ARTIFACT_DEV_ONLY)))

        if action == "pa_intention":
            # Local-only debug endpoint for batch evaluation of the intention prompt.
            if not (PA_INTENTION_DEBUG_ENDPOINT or OMNIFLOW_DEBUG or _is_local_request()):
                return _make_response({"error": "pa_intention is disabled"}, status_code=403)
            if not str(user_message or "").strip():
                return _make_response({"error": "Missing message"}, status_code=400)
            if not thread_id:
                thread_id = f"handle_{uuid.uuid4().hex[:12]}"
            run_id = uuid.uuid4().hex[:12]
            if not OPENAI_API_KEY:
                return _make_response({"error": "Missing env vars: OPENAI_API_KEY", "status": "not_configured"}, status_code=503)
            openai_client = OpenAI(api_key=OPENAI_API_KEY)
            try:
                intent_payload, intent_artifact_path = _pa_run_intention_step(
                    openai_client=openai_client,
                    user_id=str(user_id),
                    thread_id=str(thread_id),
                    run_id=str(run_id or ""),
                    phase="P4",
                    stage="S6",
                    user_message=str(user_message or ""),
                    single_step_focus=bool(_mentions_mail_flow(user_message) or _mentions_tasks(user_message)),
                    raise_on_error=True,
                )
            except Exception as exc:
                return _make_response(
                    {"error": f"pa_intention_failed: {type(exc).__name__}: {exc}"},
                    status_code=500,
                )
            return _make_response(
                {
                    "status": "ok",
                    "action": "pa_intention",
                    "user_id": str(user_id),
                    "thread_id": str(thread_id),
                    "session_id": str(thread_id),
                    "run_id": str(run_id),
                    "intent": intent_payload,
                    "artifact_path": str(intent_artifact_path or ""),
                },
                status_code=200,
            )

        # Deterministic maintenance: rebuild interactions index after merges/imports.
        if action == "pa_rebuild_interactions_index":
            if not user_id:
                return _make_response({"status": "error", "error": "user_id is required", "action": action}, status_code=400)
            params = body.get("params", {}) or {}
            confirm = bool(params.get("confirm", False))
            if not confirm:
                return _make_response(
                    {
                        "status": "error",
                        "action": action,
                        "error": "Confirmation required. Set params.confirm=true to rebuild interactions/index.jsonl.",
                        "required_confirmation": True,
                    },
                    status_code=409,
                )
            try:
                from save_interaction.service import rebuild_interactions_index

                max_scan = int(params.get("max_scan", 5000) or 5000)
                result = rebuild_interactions_index(str(user_id), max_scan=max_scan)
                return _make_response({"status": "success", "action": action, "result": result}, status_code=200)
            except Exception as exc:
                return _make_response({"status": "error", "action": action, "error": str(exc)}, status_code=500)

        # Explicit PA initialization (starter pack) requires confirmation.
        if action == "pa_init":
            if not user_id:
                return _make_response({"status": "error", "error": "user_id is required", "action": action}, status_code=400)
            params = body.get("params", {}) or {}
            confirm = bool(params.get("confirm_create", False))
            if not confirm:
                return _make_response(
                    {
                        "status": "error",
                        "action": action,
                        "error": "PA not initialized. Set params.confirm_create=true to create starter files.",
                        "required_confirmation": True,
                        "will_create": ["TM.json", "PS.json", "LO.json", "GEN.json", "SYS.json", "semantics/preferences.json"],
                        "phase_ui": phase_ui,
                        "stage_ui": stage_ui,
                    },
                    status_code=409,
                )
            result = _pa_init_starter_pack(str(user_id))
            return _make_response({"status": "success", "action": action, "result": result}, status_code=200)

        # Gate: do not auto-create PA core files during normal runs.
        if PA_REQUIRE_INIT and user_id and action not in ("get_run_progress", "wp6_prepare_audit", "wp6_run_audit", "wp7_prepare_audit", "wp7_run_audit"):
            if not _pa_has_starter_pack(str(user_id)):
                return _make_response(
                    {
                        "status": "error",
                        "error": "PA starter pack missing. Initialize user first (explicit confirmation required).",
                        "action_required": "pa_init",
                        "action_params": {"confirm_create": True},
                        "phase_ui": phase_ui,
                        "stage_ui": stage_ui,
                    },
                    status_code=409,
                )

        if action == "get_run_progress":
            if not user_id:
                return _make_response({"error": "user_id is required", "action": action}, status_code=400)
            if not thread_id:
                return _make_response({"error": "session_id (thread_id) is required", "action": action}, status_code=400)
            handles = _load_handles(str(user_id))
            rp = _get_run_progress(handles if isinstance(handles, dict) else {}, str(thread_id))
            return _make_response(
                {
                    "status": "success",
                    "action": action,
                    "user_id": str(user_id),
                    "thread_id": str(thread_id),
                    "session_id": str(thread_id),
                    "has_progress": bool(isinstance(rp, dict) and rp),
                    "run_progress": rp or {},
                },
                status_code=200,
            )

        # Deterministic tool execution (read-only allowlist) for E2E verification.
        # This avoids requiring local Azure connection strings to validate persisted artifacts in prod.
        if action == "tool_exec":
            if not user_id:
                return _make_response({"status": "error", "error": "user_id is required", "action": action}, status_code=400)
            params = body.get("params", {}) or {}
            confirm = bool(params.get("confirm", False))
            if not confirm:
                return _make_response(
                    {
                        "status": "error",
                        "action": action,
                        "error": "Confirmation required. Set params.confirm=true to execute a tool.",
                        "required_confirmation": True,
                    },
                    status_code=409,
                )
            tool_name = str(params.get("tool_name") or "").strip()
            tool_arguments = params.get("tool_arguments") or {}
            if not isinstance(tool_arguments, dict):
                return _make_response(
                    {"status": "error", "action": action, "error": "params.tool_arguments must be an object"},
                    status_code=400,
                )
            # Read-only allowlist.
            allowed = {"read_blob_file", "list_blobs"}
            if tool_name not in allowed:
                return _make_response(
                    {"status": "error", "action": action, "error": f"tool not allowed: {tool_name}", "allowed_tools": sorted(allowed)},
                    status_code=403,
                )
            try:
                result_str, info = execute_tool_call(tool_name, tool_arguments, str(user_id))
                # Best-effort parse; keep response compact.
                parsed = None
                try:
                    parsed = json.loads(result_str) if isinstance(result_str, str) else None
                except Exception:
                    parsed = None
                resp = {
                    "status": "success",
                    "action": action,
                    "tool_name": tool_name,
                    "tool_arguments": tool_arguments,
                    "result": parsed if parsed is not None else None,
                    "result_excerpt": (result_str[:4000] if isinstance(result_str, str) else str(result_str)[:4000]),
                    "tool_call": info or {},
                }
                return _make_response(resp, status_code=200)
            except Exception as exc:
                return _make_response({"status": "error", "action": action, "error": str(exc)}, status_code=500)

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

        # Runtime selection (responses-only; assistants removed)
        try:
            runtime_requested = resolve_runtime(body)
        except ValueError as vex:
            return _make_response({"error": str(vex)}, status_code=400)

        if runtime_requested == "auto":
            runtime_used = "responses"
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

                # Optional separate "intention" model call (for ML artifacts and explicit traceability).
                # This does NOT execute tools. It produces a JSON artifact under `semantics/intents/`.
                phase_intent = "P4"
                stage_intent = "S6"
                phase_response = "P7"
                stage_response = "S8"
                requires_internet = False
                response_tool_include: List[str] | None = None
                intent_payload: Dict[str, Any] = {}
                intent_artifact_path = ""
                single_step_focus = bool(_mentions_mail_flow(user_message) or _mentions_tasks(user_message))
                try:
                    intent_payload, intent_artifact_path = _pa_run_intention_step(
                        openai_client=openai_client,
                        user_id=str(user_id),
                        thread_id=str(thread_id),
                        run_id=str(run_id or ""),
                        phase=phase_intent,
                        stage=stage_intent,
                        user_message=str(user_message or ""),
                        single_step_focus=single_step_focus,
                    )
                    if isinstance(intent_payload, dict) and intent_payload:
                        requires_internet = bool(intent_payload.get("requires_internet"))
                        response_tool_include = _pa_runtime_tools_include_from_intent(intent_payload)
                        # Optional deterministic prefetch after intention. Backend-owned orchestration only.
                        try:
                            prefetch_meta = _pa_execute_prefetch_plan(
                                user_id=str(user_id),
                                thread_id=str(thread_id),
                                run_id=str(run_id or ""),
                                intent_payload=intent_payload,
                            )
                            if isinstance(prefetch_meta, dict) and prefetch_meta:
                                wp6_meta["pa_prefetch"] = prefetch_meta
                        except Exception:
                            pass
                        wp6_meta["pa_intention"] = {
                            "model": PA_INTENTION_MODEL,
                            "reasoning_effort": PA_INTENTION_REASONING_EFFORT,
                            "artifact_path": str(intent_artifact_path or ""),
                            "requires_internet": bool(requires_internet),
                            "intent": str(intent_payload.get("intent") or "") if isinstance(intent_payload, dict) else "",
                            "runtime_tool_include": list(response_tool_include or []),
                        }
                except Exception:
                    pass

                recent_turns = _wp6_update_recent_user_turns(user_id, str(thread_id), user_message)
                wp6_meta["recent_user_turns_count"] = int(len(recent_turns or []))
                wp6_meta["recent_user_turns_chars"] = int(sum(len(str(t or "")) for t in (recent_turns or [])))

                requested_stage = str(body.get("stage") or "").strip().upper()
                requested_phase = str(body.get("phase") or "").strip().upper()
                # PA intention is the single source-of-truth for PA routing/policies.
                # UI-provided phase/stage are treated as debug-only; we do not call legacy intent_router for PA flows.
                intent_router = None
                try:
                    if isinstance(intent_payload, dict) and intent_payload:
                        wp6_meta["pa_function_id"] = str(intent_payload.get("pa_function_id") or "").strip()
                        wp6_meta["pa_function_name"] = str(intent_payload.get("pa_function_name") or "").strip()
                        wp6_meta["pa_intention_schema_version"] = str(intent_payload.get("schema_version") or "").strip()
                except Exception:
                    pass
                wp6_meta["pa_phase"] = str(phase_response or "")
                wp6_meta["pa_stage"] = str(stage_response or "")
                if phase_ui or stage_ui:
                    wp6_meta["pa_phase_ui"] = phase_ui
                    wp6_meta["pa_stage_ui"] = stage_ui
                logging.info(
                    "PA routing intention_sot phase=%s stage=%s pa_function_id=%s",
                    str(phase_response or ""),
                    str(stage_response or ""),
                    str(wp6_meta.get("pa_function_id") or ""),
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

                requested_mode_raw = str(route_meta.get("context_mode_requested") or "AUTO").upper()
                if single_step_focus:
                    wp6_meta["single_step_mode"] = True
                # WU-11: fast/deep no longer controls routing. Keep only as quality hint for observability.
                requested_mode = "FAST"
                auto_mode = False
                deep_allowed = False
                wp6_meta["deep_allowed"] = False
                wp6_meta["quality_hint"] = requested_mode_raw if requested_mode_raw in ("FAST", "DEEP", "AUTO") else "AUTO"
                route_reason = "deprecated_fast_deep_control_flag"

                # FAST input (single-step): semantic-only context capsule.
                fast_input_message = user_message
                capsule_json, capsule_meta = _wp6_build_context_capsule(
                    user_id=str(user_id),
                    user_message=str(user_message or ""),
                    recent_turns=list(recent_turns or []),
                    core_sources=list(core_sources or []),
                    fast_ctx=str(fast_ctx or ""),
                    intent_payload=intent_payload if isinstance(intent_payload, dict) else {},
                )
                composer_info: Dict[str, Any] = {}
                if capsule_json:
                    composer_used = False
                    pa_id_for_composer = (
                        str((intent_payload or {}).get("pa_function_id") or "")
                        if isinstance(intent_payload, dict)
                        else ""
                    )
                    try:
                        composed = compose_prompt_for_pa(
                            intent_payload=intent_payload if isinstance(intent_payload, dict) else {},
                            user_message=str(user_message or ""),
                            capsule_json=str(capsule_json or ""),
                        ) if callable(compose_prompt_for_pa) else {}
                        if isinstance(composed, dict) and bool(composed.get("enabled")):
                            fast_input_message = str(composed.get("input_message") or "")
                            composer_info = {
                                "composer_matrix_id": str(composed.get("matrix_id") or ""),
                                "composer_block_ids": list(composed.get("block_ids") or []),
                                "composer_schema_id": str(composed.get("schema_id") or ""),
                                "composer_tools_id": str(composed.get("tools_id") or ""),
                            }
                            wp6_meta["prompt_composer"] = dict(composer_info)
                            composer_tools = list(composed.get("tool_include_names") or [])
                            if composer_tools:
                                response_tool_include = composer_tools
                            composer_used = True
                    except Exception:
                        composer_used = False
                    if not composer_used and pa_id_for_composer in ("PA-01", "PA-14"):
                        raise RuntimeError("prompt_composer_required_for_tm_gmail")
                    if not composer_used:
                        fast_input_message = f"[CONTEXT_CAPSULE]\n{capsule_json}\n\n[USER_MESSAGE]\n{user_message}"
                wp6_meta.update(capsule_meta)

                # Routing: AUTO defaults to FAST; DEEP can be entered:
                # - deterministically (e.g., FAST context empty) before first call, or
                # - agent-driven after FAST via need_deep/__ROUTE_DEEP__ signal.
                mode_initial = "FAST"
                reason_initial = route_reason
                mode_initial = "FAST"
                reason_initial = route_reason

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
                    # Compatibility guard: mode_initial is forced to FAST in WU-11.
                    model_input_message = fast_input_message

                _emit_run_progress(
                    user_id=str(user_id),
                    thread_id=str(thread_id),
                    run_id=run_id,
                    trace_id=trace_id,
                    status="in_progress",
                    stage="grasping_context",
                    message="Routing to FAST",
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
                    phase=phase_response,
                    stage=stage_response,
                    intent_router=intent_router,
                    include_web_search=bool(requires_internet),
                    tool_include_names=response_tool_include,
                    composer_meta=composer_info,
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
                                    phase=phase_response,
                                    stage=stage_response,
                                    intent_router=intent_router,
                                    include_web_search=bool(requires_internet),
                                    tool_include_names=response_tool_include,
                                    composer_meta=composer_info,
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
                    if isinstance(intent_payload, dict) and intent_payload:
                        responses_meta["pa_intention_payload"] = intent_payload
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
                run_id=str(run_id or ""),
                trace_id=str(trace_id or ""),
                phase=str(phase_response or ""),
                stage=str(stage_response or ""),
                persist_run_artifact=bool(persist_run_artifact),
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
            run_id=str(getattr(run, "id", "") or ""),
            trace_id=str(trace_id or ""),
            phase="",
            stage="",
            persist_run_artifact=bool(persist_run_artifact),
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
