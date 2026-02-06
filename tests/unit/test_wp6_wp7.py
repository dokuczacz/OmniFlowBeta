import hashlib
import json
import os
import sys

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "backend")
)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tool_call_handler as handler  # noqa: E402
import shared.wp7_indexer as wp7_indexer  # noqa: E402
import wp7_indexer_timer as wp7_timer  # noqa: E402


def test_wp6_route_context_mode_variants():
    mode, source, meta = handler._wp6_route_context_mode({}, "hello world")
    assert mode == "FAST"
    assert source == "auto_fast"
    assert meta["context_mode_source"] == "env_default"
    assert meta["prompt_chars"] == len("hello world")

    mode, source, meta = handler._wp6_route_context_mode(
        {"context_mode": "deep"}, "foo"
    )
    assert mode == "DEEP"
    assert source == "explicit"
    assert meta["context_mode_requested"] == "DEEP"

    mode, source, meta = handler._wp6_route_context_mode(
        {"context_mode": "unknown"}, "bar"
    )
    assert mode == "FAST"
    assert source == "auto_fast"
    assert meta["context_mode_requested"] == "AUTO"


def test_wp6_norm_intent_key_stable_hash():
    base = "  Repeat   this   sentence "
    key1 = handler._wp6_norm_intent_key(base)
    key2 = handler._wp6_norm_intent_key("Repeat this sentence")
    assert isinstance(key1, str)
    assert len(key1) == 16
    assert key1 == key2
    assert key1 == hashlib.sha256(
        "repeat this sentence".encode("utf-8")
    ).hexdigest()[:16]


def test_wp6_parse_need_deep_signal_parses_json():
    payload = {
        "need_deep": True,
        "missing": ["foo", "bar"],
        "why": "context lacking",
        "confidence": 0.85,
        "deep_plan": ["step1"],
    }
    text = json.dumps(payload) + "\nrest of reply"
    signal, cleaned = handler._wp6_parse_need_deep_signal(text)
    assert signal["need_deep"] is True
    assert signal["missing"] == ["foo", "bar"]
    assert signal["confidence"] == 0.85
    assert signal["parse_status"] == "json"
    assert cleaned.startswith("rest of reply")


def test_wp6_parse_need_deep_signal_token_fallback():
    signal, cleaned = handler._wp6_parse_need_deep_signal(
        "some text __ROUTE_DEEP__ more"
    )
    assert signal["need_deep"] is True
    assert signal["parse_status"] == "token"
    assert cleaned == "some text __ROUTE_DEEP__ more"


def test_wp7_schema_format_enforces_items():
    schema_payload = wp7_indexer.wp7_text_json_schema_format()
    assert isinstance(schema_payload, dict)
    format_spec = schema_payload.get("format", {})
    schema = format_spec.get("schema", {})
    assert schema.get("required") == ["items"]
    assert "items" in schema.get("properties", {})


def test_wp7_compact_indexer_item_filters_tools():
    item = {
        "interaction_id": "INT_TEST",
        "user_message": "Hello",
        "assistant_response": "Ok",
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "thread_id": "thread-1",
        "tools_used": ["  tool-one  ", "", None, 123],
    }
    compacted = wp7_indexer.compact_indexer_item(item)
    assert compacted["interaction_id"] == "INT_TEST"
    assert compacted["timestamp_utc"] == "2026-01-01T00:00:00Z"
    assert compacted["thread_id"] == "thread-1"
    assert compacted["tools_used"] == ["tool-one", "123"]


def test_wp7_timer_call_indexer_model_uses_schema_and_fallback_output_text():
    artifacts_payload = {
        "items": [
            {
                "interaction_id": "INT_X",
                "category": "GEN",
                "summary": "Intent; Action(tool); Result (Scope).",
                "tags": ["one", "two", "three"],
                "confidence": 0.9,
                "signal_level": "high",
            }
        ]
    }

    class FakeResp:
        output_text = ""

        def model_dump(self):
            return {
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(artifacts_payload, ensure_ascii=False),
                            }
                        ]
                    }
                ]
            }

    seen = {}

    class FakeResponses:
        def create(self, **kwargs):
            seen.update(kwargs)
            return FakeResp()

    class FakeOpenAI:
        responses = FakeResponses()

    out = wp7_timer._call_indexer_model(
        FakeOpenAI(),
        "pmpt_test",
        [{"interaction_id": "INT_X", "user_message": "u", "assistant_response": "a"}],
    )
    assert isinstance(out, list)
    assert out and out[0]["interaction_id"] == "INT_X"
    assert seen.get("text", {}).get("format", {}).get("name") == "interaction_items"
    assert seen.get("reasoning", {}).get("effort") == "minimal"
