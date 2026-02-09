import os
import sys
import json
from types import SimpleNamespace


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


import tool_call_handler as handler  # noqa: E402


class _FakeResponse:
    def __init__(self, *, output_text: str):
        self.id = "resp_test_1"
        self.conversation = None
        self.output = []
        self.output_text = output_text
        self.status = "completed"
        self.incomplete_details = None


def test_run_responses_includes_runtime_instructions(monkeypatch):
    captured = {}

    def fake_openai_call(_fn, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(output_text="Reasoning: ok. Summary: ok.")

    monkeypatch.setattr(handler, "_openai_call", fake_openai_call)
    monkeypatch.setattr(handler, "_load_handles", lambda _user_id: {})
    monkeypatch.setattr(handler, "_save_handles", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(handler, "WP6_RESPONSES_STATELESS", True)
    monkeypatch.setattr(handler, "OPENAI_RUNTIME_INSTRUCTIONS", "RUNTIME_GUARD")
    monkeypatch.setattr(handler, "OPENAI_PROMPT_ID", "pmpt_test")

    openai_client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_kwargs: None))
    final_text, _calls, _meta, _thread = handler.run_responses(
        openai_client=openai_client,
        user_id="u1",
        user_message="hello",
        thread_id="t1",
    )

    assert captured.get("instructions") == "RUNTIME_GUARD"
    assert final_text == "Reasoning: ok. Summary: ok."


def test_run_responses_blocks_internal_manifest_payload(monkeypatch):
    manifest_like = '{"name":"OmniFlow_PA","version":"1.0","type":"runtime+tests","runtime":{"workflow":{}},"tests":{"suite":"x"}}'

    def fake_openai_call(_fn, **_kwargs):
        return _FakeResponse(output_text=manifest_like)

    monkeypatch.setattr(handler, "_openai_call", fake_openai_call)
    monkeypatch.setattr(handler, "_load_handles", lambda _user_id: {})
    monkeypatch.setattr(handler, "_save_handles", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(handler, "WP6_RESPONSES_STATELESS", True)
    monkeypatch.setattr(handler, "OPENAI_PROMPT_ID", "pmpt_test")

    openai_client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_kwargs: None))
    final_text, _calls, _meta, _thread = handler.run_responses(
        openai_client=openai_client,
        user_id="u1",
        user_message="hello",
        thread_id="t1",
    )

    assert "internal configuration content" in final_text


def test_run_responses_includes_inline_tools_when_enabled(monkeypatch):
    captured = {}

    def fake_openai_call(_fn, **kwargs):
        captured.update(kwargs)
        return _FakeResponse(output_text="Reasoning: ok. Summary: ok.")

    monkeypatch.setattr(handler, "_openai_call", fake_openai_call)
    monkeypatch.setattr(handler, "_load_handles", lambda _user_id: {})
    monkeypatch.setattr(handler, "_save_handles", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(handler, "_responses_inline_tools", lambda: [{"type": "function", "name": "list_blobs", "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}, "strict": True}])
    monkeypatch.setattr(handler, "_responses_resolve_tool_source", lambda: "inline")
    monkeypatch.setattr(handler, "WP6_RESPONSES_STATELESS", True)
    monkeypatch.setattr(handler, "OPENAI_PROMPT_ID", "pmpt_test")

    openai_client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_kwargs: None))
    _final_text, _calls, meta, _thread = handler.run_responses(
        openai_client=openai_client,
        user_id="u1",
        user_message="hello",
        thread_id="t1",
    )

    assert isinstance(captured.get("tools"), list)
    assert captured["tools"][0]["name"] == "list_blobs"
    assert meta.get("tool_source") == "inline"
    assert meta.get("inline_tools_count") == 1


def test_normalize_inline_tool_parameters_strict_requires_all_properties():
    params = {
        "type": "object",
        "properties": {
            "timezone": {"type": "string"},
            "user_id": {"type": "string"},
        },
        "required": ["timezone"],
        "additionalProperties": False,
    }

    normalized = handler._normalize_inline_tool_parameters(params, strict=True)
    assert normalized["required"] == ["timezone", "user_id"]


def test_responses_inline_tools_normalizes_catalog_required_in_strict_mode(monkeypatch, tmp_path):
    catalog = {
        "openai_function_schemas": [
            {
                "name": "get_current_time",
                "description": "Return time",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string"},
                        "user_id": {"type": "string"},
                    },
                    "required": ["timezone"],
                    "additionalProperties": False,
                },
            }
        ]
    }
    catalog_path = tmp_path / "AGENT_FUNCTIONS_CATALOG.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    monkeypatch.setattr(handler, "_catalog_path", lambda: catalog_path)
    monkeypatch.setattr(handler, "_responses_inline_tools_cache", None)

    tools = handler._responses_inline_tools()
    assert isinstance(tools, list) and tools
    assert tools[0]["name"] == "get_current_time"
    assert tools[0]["parameters"]["required"] == ["timezone", "user_id"]


def test_normalize_inline_tool_parameters_sets_nested_additional_properties_false():
    params = {
        "type": "object",
        "properties": {
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "args": {"type": "object", "properties": {"k": {"type": "string"}}},
                    },
                    "required": ["name"],
                },
            }
        },
        "required": ["tool_calls"],
    }

    normalized = handler._normalize_inline_tool_parameters(params, strict=True)
    items = normalized["properties"]["tool_calls"]["items"]
    assert normalized["additionalProperties"] is False
    assert items["additionalProperties"] is False
    assert items["required"] == ["name", "args"]
    assert items["properties"]["args"]["additionalProperties"] is False
