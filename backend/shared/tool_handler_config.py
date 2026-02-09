import os
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ToolHandlerConfig:
    """Typed configuration for shared tool handler behavior."""

    wp7_audit_default_model: str
    wp7_audit_default_reasoning_effort: str
    debug_tool_call_handler: bool
    omniflow_debug: bool
    omniflow_mock_agent: bool
    enable_save_interaction: bool
    handles_cache_ttl_seconds: int
    preferences_cache_ttl_seconds: int
    openai_max_requests: int
    openai_indexer_prompt_id: str
    openai_indexer_model: str

    wp6_default_context_mode: str
    wp6_responses_stateless: bool
    wp6_recent_turns_max: int
    wp6_recent_turns_max_chars: int
    wp6_fast_audit_enabled: bool
    wp6_fast_audit_max_chars: int
    wp6_audit_default_model: str
    wp6_audit_default_reasoning_effort: str
    wp6_fast_max_input_tokens: int
    wp6_fast_max_sources: int
    wp6_fast_max_raw_bytes: int
    wp6_deep_max_pack_tokens: int
    wp6_deep_max_candidate_sources: int
    wp6_deep_min_semantic_selected: int
    wp6_deep_min_semantic_candidates: int
    wp6_context_pack_ttl_seconds: int
    wp6_deep_cooldown_seconds: int
    wp6_preferences_auto_create: bool

    wp7_batch_size_multiplier: int
    wp7_target_batch_tokens: int
    wp7_hard_min_batch_tokens: int
    wp7_max_wait_seconds: int
    wp7_max_items_per_run: int
    wp7_max_output_tokens_per_item: int
    wp7_log_verbose: bool
    wp7_indexer_input_compact: bool
    wp7_indexer_mode: str
    wp7_allowed_categories: tuple[str, ...]
    wp7_uncategorized_confidence_lt: float
    wp7_semantic_dedup_enabled: bool
    wp7_semantic_dedup_window_seconds: int
    wp7_semantic_dedup_tail_bytes: int
    wp7_semantic_dedup_max_lines: int
    wp7_semantic_dedup_max_matches: int
    wp7_max_user_chars: int
    wp7_max_assistant_chars: int
    wp7_enabled: bool
    wp7_indexer_user_ids: str


def _env_str(name: str, default: str) -> str:
    return str(os.environ.get(name, default) or default).strip()


def _env_str_lower(name: str, default: str) -> str:
    return _env_str(name, default).lower()


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _env_choice(names: Iterable[str], default: str) -> str:
    for name in names:
        val = os.environ.get(name)
        if val:
            return str(val).strip()
    return default


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _env_csv(name: str, default: str) -> tuple[str, ...]:
    raw = os.environ.get(name, default)
    if not raw:
        return tuple()
    return tuple(
        part.strip()
        for part in str(raw).split(",")
        if part and part.strip()
    )


def build_tool_handler_config() -> ToolHandlerConfig:
    """Build a config snapshot from the current environment."""
    omniflow_debug = _env_bool("OMNIFLOW_DEBUG", False)
    return ToolHandlerConfig(
        wp7_audit_default_model=_env_str("WP7_AUDIT_DEFAULT_MODEL", "gpt-5-mini"),
        wp7_audit_default_reasoning_effort=_env_str_lower(
            "WP7_AUDIT_DEFAULT_REASONING_EFFORT", "medium"
        ),
        debug_tool_call_handler=_env_bool("DEBUG_TOOL_CALL_HANDLER", False)
        or omniflow_debug,
        omniflow_debug=omniflow_debug,
        omniflow_mock_agent=_env_bool("OMNIFLOW_MOCK_AGENT", False),
        enable_save_interaction=_env_bool("ENABLE_SAVE_INTERACTION", True),
        handles_cache_ttl_seconds=_env_int("HANDLES_CACHE_TTL_SECONDS", 600),   
        preferences_cache_ttl_seconds=_env_int("PREFERENCES_CACHE_TTL_SECONDS", 600),
        openai_max_requests=_env_int("OPENAI_MAX_REQUESTS", 0),
        openai_indexer_prompt_id=_env_str("OPENAI_INDEXER_PROMPT_ID", ""),
        openai_indexer_model=_env_str("OPENAI_INDEXER_MODEL", "gpt-5-mini"),
        wp6_default_context_mode=_env_str("WP6_DEFAULT_CONTEXT_MODE", "AUTO").upper(),
        wp6_responses_stateless=_env_bool("WP6_RESPONSES_STATELESS", True),
        wp6_recent_turns_max=_env_int("WP6_RECENT_TURNS_MAX", 8),
        wp6_recent_turns_max_chars=_env_int("WP6_RECENT_TURNS_MAX_CHARS", 320),
        wp6_fast_audit_enabled=_env_bool("WP6_FAST_AUDIT_ENABLED", False),
        wp6_fast_audit_max_chars=_env_int("WP6_FAST_AUDIT_MAX_CHARS", 160000),
        wp6_audit_default_model=_env_choice(
            ["WP6_AUDIT_DEFAULT_MODEL", "OPENAI_WP6_AUDIT_MODEL"], "gpt-5-mini"
        ),
        wp6_audit_default_reasoning_effort=_env_choice(
            ["WP6_AUDIT_DEFAULT_REASONING_EFFORT", "OPENAI_WP6_AUDIT_REASONING_EFFORT"],
            "medium",
        ).lower(),
        wp6_fast_max_input_tokens=_env_int("WP6_FAST_MAX_INPUT_TOKENS", 2000),
        wp6_fast_max_sources=_env_int("WP6_FAST_MAX_SOURCES", 4),
        wp6_fast_max_raw_bytes=_env_int("WP6_FAST_MAX_RAW_BYTES", 64000),
        wp6_deep_max_pack_tokens=_env_int("WP6_DEEP_MAX_PACK_TOKENS", 16000),
        wp6_deep_max_candidate_sources=_env_int("WP6_DEEP_MAX_CANDIDATE_SOURCES", 12),
        wp6_deep_min_semantic_selected=_env_int("WP6_DEEP_MIN_SEMANTIC_SELECTED", 3),
        wp6_deep_min_semantic_candidates=_env_int("WP6_DEEP_MIN_SEMANTIC_CANDIDATES", 6),
        wp6_context_pack_ttl_seconds=_env_int("WP6_CONTEXT_PACK_TTL_SECONDS", 300),
        wp6_deep_cooldown_seconds=_env_int("WP6_DEEP_COOLDOWN_SECONDS", 600),
        wp6_preferences_auto_create=_env_bool("WP6_PREFERENCES_AUTO_CREATE", True),
        wp7_batch_size_multiplier=_env_int("WP7_BATCH_SIZE_MULTIPLIER", 9),
        wp7_target_batch_tokens=_env_int("WP7_TARGET_BATCH_TOKENS", 1000),
        wp7_hard_min_batch_tokens=_env_int("WP7_HARD_MIN_BATCH_TOKENS", 600),
        wp7_max_wait_seconds=_env_int("WP7_MAX_WAIT_SECONDS", 300),
        wp7_max_items_per_run=_env_int("WP7_MAX_ITEMS_PER_RUN", 25),
        wp7_max_output_tokens_per_item=_env_int("WP7_MAX_OUTPUT_TOKENS_PER_ITEM", 180),
        wp7_log_verbose=_env_bool("WP7_LOG_VERBOSE", False) or omniflow_debug,
        wp7_indexer_input_compact=_env_bool("WP7_INDEXER_INPUT_COMPACT", False),
        wp7_indexer_mode=_env_str_lower("WP7_INDEXER_MODE", "batch"),
        wp7_allowed_categories=_env_csv(
            "WP7_ALLOWED_CATEGORIES", "PE,UI,ML,LO,PS,TM,SYS,GEN,ID"
        ),
        wp7_uncategorized_confidence_lt=_env_float(
            "WP7_UNCATEGORIZED_CONFIDENCE_LT", 0.6
        ),
        wp7_indexer_user_ids=_env_str("WP7_INDEXER_USER_IDS", "auto"),
        wp7_semantic_dedup_enabled=_env_bool("WP7_SEMANTIC_DEDUP_ENABLED", True),
        wp7_semantic_dedup_window_seconds=_env_int(
            "WP7_SEMANTIC_DEDUP_WINDOW_SECONDS", 300
        ),
        wp7_semantic_dedup_tail_bytes=_env_int(
            "WP7_SEMANTIC_DEDUP_TAIL_BYTES", 65536
        ),
        wp7_semantic_dedup_max_lines=_env_int(
            "WP7_SEMANTIC_DEDUP_MAX_LINES", 200
        ),
        wp7_semantic_dedup_max_matches=_env_int(
            "WP7_SEMANTIC_DEDUP_MAX_MATCHES", 50
        ),
        wp7_max_user_chars=_env_int("WP7_MAX_USER_CHARS", 2000),
        wp7_max_assistant_chars=_env_int("WP7_MAX_ASSISTANT_CHARS", 4000),      
        wp7_enabled=_env_bool("WP7_ENABLED", True),
    )


DEFAULT_TOOL_HANDLER_CONFIG = build_tool_handler_config()
