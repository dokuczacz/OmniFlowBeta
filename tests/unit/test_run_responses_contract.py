import os
import sys
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
