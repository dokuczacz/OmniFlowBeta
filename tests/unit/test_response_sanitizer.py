import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


import tool_call_handler as handler  # noqa: E402


def test_looks_like_internal_contract_payload_detects_manifest_shape():
    text = (
        '{"name":"OmniFlow_PA","version":"1.0","type":"runtime+tests",'
        '"runtime":{"workflow":{}}, "tests":{"suite":"x"}}'
    )
    assert handler._looks_like_internal_contract_payload(text) is True


def test_looks_like_internal_contract_payload_ignores_normal_reply():
    text = "1. Reasoning: everything is ready. 2. Summary: done."
    assert handler._looks_like_internal_contract_payload(text) is False


def test_sanitize_responses_final_text_blocks_internal_payload():
    text = (
        '{"runtime":{"execution_policy":{}},'
        '"format_rules":{"output_order":["reasoning","summary"]},'
        '"tests":{"framework":"harness"}}'
    )
    out = handler._sanitize_responses_final_text(text)
    assert "blocked" in out.lower()
    assert "internal configuration content" in out


def test_sanitize_responses_final_text_keeps_user_text():
    text = "Reasoning: checked tasks. Summary: you have 3 tasks today."
    assert handler._sanitize_responses_final_text(text) == text
