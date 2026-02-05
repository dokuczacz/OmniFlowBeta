import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


import tool_call_handler as handler  # noqa: E402


def test_wp6_default_preferences_is_schema_valid():
    prefs = handler._wp6_default_preferences()
    ok, reason = handler._wp6_validate_preferences(prefs)
    assert ok, reason


def test_wp6_validate_preferences_rejects_missing_required_keys():
    ok, reason = handler._wp6_validate_preferences({})
    assert not ok
    assert reason


def test_wp6_context_builder_input_validation():
    cb_input = {
        "request": {"user_prompt": "hello"},
        "candidate_sources": [{"path": "interactions/semantic/index.jsonl", "excerpt_or_snippet": "x"}],
        "constraints": {"max_pack_tokens": 16000, "max_bullets": 6, "max_top_sources": 5},
    }
    ok, reason = handler._wp6_validate_context_builder_input(cb_input)
    assert ok, reason


def test_wp6_context_pack_validation():
    pack = {
        "mode": "DEEP",
        "summary": "short summary",
        "bullets": ["a", "b"],
        "top_sources": [{"path": "interactions/semantic/INT_1.json"}],
        "pack_tokens_est": 123,
        "coverage": "partial",
        "need_more_sources": False,
        "created_utc": "2026-01-01T00:00:00Z",
    }
    ok, reason = handler._wp6_validate_context_pack(pack)
    assert ok, reason


def test_load_preferences_autocreates_on_invalid_schema(monkeypatch):
    monkeypatch.setattr(handler, "PREFERENCES_CACHE_TTL_SECONDS", 0)
    monkeypatch.setattr(handler, "WP6_PREFERENCES_AUTO_CREATE", True)
    handler._prefs_cache.clear()

    def fake_read(_user_id, _file_name):
        return {"status": "success", "data": {}}

    uploaded = {}

    def fake_upload(_user_id, target_blob_name, file_content):
        uploaded["target_blob_name"] = target_blob_name
        uploaded["file_content"] = file_content
        return {"status": "success"}

    monkeypatch.setattr(handler, "_inprocess_read_blob_file", fake_read)
    monkeypatch.setattr(handler, "_inprocess_upload_data_or_file", fake_upload)

    prefs = handler._load_preferences("alice")
    assert prefs.get("schema_version") == "omniflow.wp6.preferences.v1"
    assert uploaded.get("target_blob_name") == "semantics/preferences.json"

