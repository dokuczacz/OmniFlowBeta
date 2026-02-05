import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import shared.tool_handler_config as tool_handler_config


def test_tool_handler_config_defaults(monkeypatch):
    monkeypatch.delenv("WP7_AUDIT_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("WP7_AUDIT_DEFAULT_REASONING_EFFORT", raising=False)
    config = tool_handler_config.build_tool_handler_config()
    assert config.wp7_audit_default_model == "gpt-5-mini"
    assert config.wp7_audit_default_reasoning_effort == "medium"
    assert config.wp7_target_batch_tokens == 1000
    assert config.wp7_max_items_per_run == 25
    assert not config.wp7_log_verbose
    assert config.wp7_allowed_categories == ("PE", "UI", "ML", "LO", "PS", "TM", "SYS", "GEN", "ID")
    assert config.wp7_uncategorized_confidence_lt == 0.6
    assert config.wp7_semantic_dedup_enabled
    assert config.wp7_semantic_dedup_window_seconds == 300
    assert config.wp7_semantic_dedup_tail_bytes == 65536
    assert config.wp7_semantic_dedup_max_lines == 200
    assert config.wp7_semantic_dedup_max_matches == 50
    assert config.wp7_max_user_chars == 2000
    assert config.wp7_max_assistant_chars == 4000
    assert config.wp7_enabled
    assert config.openai_indexer_model == "gpt-5-mini"
    assert config.openai_indexer_prompt_id == ""
    assert config.wp7_indexer_mode == "batch"
    assert config.wp7_indexer_user_ids == "auto"


def test_tool_handler_config_overrides(monkeypatch):
    monkeypatch.setenv("WP7_AUDIT_DEFAULT_MODEL", " custom-model ")
    monkeypatch.setenv("WP7_AUDIT_DEFAULT_REASONING_EFFORT", "HIGH")
    config = tool_handler_config.build_tool_handler_config()
    assert config.wp7_audit_default_model == "custom-model"
    assert config.wp7_audit_default_reasoning_effort == "high"


def test_tool_handler_config_toggles_and_ints(monkeypatch):
    monkeypatch.setenv("DEBUG_TOOL_CALL_HANDLER", "0")
    monkeypatch.setenv("OMNIFLOW_DEBUG", "true")
    monkeypatch.setenv("OMNIFLOW_MOCK_AGENT", "yes")
    monkeypatch.setenv("ENABLE_SAVE_INTERACTION", "0")
    monkeypatch.setenv("HANDLES_CACHE_TTL_SECONDS", "900")
    monkeypatch.setenv("PREFERENCES_CACHE_TTL_SECONDS", "1200")
    monkeypatch.setenv("OPENAI_MAX_REQUESTS", "42")
    config = tool_handler_config.build_tool_handler_config()
    assert config.debug_tool_call_handler
    assert config.omniflow_debug
    assert config.omniflow_mock_agent
    assert not config.enable_save_interaction
    assert config.handles_cache_ttl_seconds == 900
    assert config.preferences_cache_ttl_seconds == 1200
    assert config.openai_max_requests == 42


def test_tool_handler_config_wp6_overrides(monkeypatch):
    monkeypatch.setenv("WP6_DEFAULT_CONTEXT_MODE", "deep")
    monkeypatch.setenv("WP6_FAST_AUDIT_MAX_CHARS", "1234")
    monkeypatch.setenv("WP6_AUDIT_DEFAULT_MODEL", "owned-model")
    monkeypatch.setenv("WP6_AUDIT_DEFAULT_REASONING_EFFORT", "HIGH")
    monkeypatch.setenv("WP6_FAST_MAX_INPUT_TOKENS", "2500")
    monkeypatch.setenv("WP6_FAST_MAX_SOURCES", "10")
    monkeypatch.setenv("WP6_DEEP_MIN_SEMANTIC_SELECTED", "5")
    monkeypatch.setenv("WP6_PREFERENCES_AUTO_CREATE", "0")
    config = tool_handler_config.build_tool_handler_config()
    assert config.wp6_default_context_mode == "DEEP"
    assert config.wp6_fast_audit_max_chars == 1234
    assert config.wp6_audit_default_model == "owned-model"
    assert config.wp6_audit_default_reasoning_effort == "high"
    assert config.wp6_fast_max_input_tokens == 2500
    assert config.wp6_fast_max_sources == 10
    assert config.wp6_deep_min_semantic_selected == 5
    assert not config.wp6_preferences_auto_create


def test_tool_handler_config_wp7_overrides(monkeypatch):
    monkeypatch.setenv("WP7_BATCH_SIZE_MULTIPLIER", "5")
    monkeypatch.setenv("WP7_TARGET_BATCH_TOKENS", "1500")
    monkeypatch.setenv("WP7_HARD_MIN_BATCH_TOKENS", "800")
    monkeypatch.setenv("WP7_MAX_WAIT_SECONDS", "600")
    monkeypatch.setenv("WP7_MAX_ITEMS_PER_RUN", "10")
    monkeypatch.setenv("WP7_MAX_OUTPUT_TOKENS_PER_ITEM", "520")
    monkeypatch.setenv("WP7_LOG_VERBOSE", "1")
    monkeypatch.setenv("WP7_INDEXER_INPUT_COMPACT", "true")
    monkeypatch.setenv("WP7_ALLOWED_CATEGORIES", "AAA,BBB")
    monkeypatch.setenv("WP7_UNCATEGORIZED_CONFIDENCE_LT", "0.42")
    monkeypatch.setenv("WP7_SEMANTIC_DEDUP_ENABLED", "0")
    monkeypatch.setenv("WP7_SEMANTIC_DEDUP_WINDOW_SECONDS", "120")
    monkeypatch.setenv("WP7_SEMANTIC_DEDUP_TAIL_BYTES", "512")
    monkeypatch.setenv("WP7_SEMANTIC_DEDUP_MAX_LINES", "50")
    monkeypatch.setenv("WP7_SEMANTIC_DEDUP_MAX_MATCHES", "12")
    monkeypatch.setenv("WP7_MAX_USER_CHARS", "900")
    monkeypatch.setenv("WP7_MAX_ASSISTANT_CHARS", "1100")
    config = tool_handler_config.build_tool_handler_config()
    assert config.wp7_batch_size_multiplier == 5
    assert config.wp7_target_batch_tokens == 1500
    assert config.wp7_hard_min_batch_tokens == 800
    assert config.wp7_max_wait_seconds == 600
    assert config.wp7_max_items_per_run == 10
    assert config.wp7_max_output_tokens_per_item == 520
    assert config.wp7_log_verbose
    assert config.wp7_indexer_input_compact
    assert config.wp7_allowed_categories == ("AAA", "BBB")
    assert config.wp7_uncategorized_confidence_lt == 0.42
    assert not config.wp7_semantic_dedup_enabled
    assert config.wp7_semantic_dedup_window_seconds == 120
    assert config.wp7_semantic_dedup_tail_bytes == 512
    assert config.wp7_semantic_dedup_max_lines == 50
    assert config.wp7_semantic_dedup_max_matches == 12
    assert config.wp7_max_user_chars == 900
    assert config.wp7_max_assistant_chars == 1100
    monkeypatch.setenv("WP7_ENABLED", "0")
    disabled_config = tool_handler_config.build_tool_handler_config()
    assert not disabled_config.wp7_enabled
    monkeypatch.setenv("WP7_INDEXER_MODE", "ASYNC")
    monkeypatch.setenv("WP7_INDEXER_USER_IDS", "alpha,beta")
    monkeypatch.setenv("OPENAI_INDEXER_MODEL", "gpt-5-custom")
    monkeypatch.setenv("OPENAI_INDEXER_PROMPT_ID", "pmpt_custom")
    override_config = tool_handler_config.build_tool_handler_config()
    assert override_config.wp7_indexer_mode == "async"
    assert override_config.wp7_indexer_user_ids == "alpha,beta"
    assert override_config.openai_indexer_model == "gpt-5-custom"
    assert override_config.openai_indexer_prompt_id == "pmpt_custom"
