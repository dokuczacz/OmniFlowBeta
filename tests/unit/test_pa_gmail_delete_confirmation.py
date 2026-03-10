import sys
import types

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    sys.modules["openai"] = openai_stub

from tool_call_handler import _pa_backend_normalize_intention_payload, _pa_detect_gmail_operation


def _intent_payload(base_intent: str = "delete_email"):
    return {
        "primary": {"intent": base_intent, "pa_id": "PA-14", "score": 0.92},
        "signals": {"is_gmail": True, "is_tm": False, "has_write_intent": True},
        "gmail": {"operation": "unknown", "label": "INBOX"},
        "slots": {},
    }


def test_detect_gmail_delete_for_permanent_keywords():
    op = _pa_detect_gmail_operation("Usun na stale mail od szefa", "unknown")
    assert op == "delete"


def test_delete_operation_requires_confirmation_by_default():
    normalized = _pa_backend_normalize_intention_payload(
        intent_payload=_intent_payload(),
        user_message="Usun na stale wiadomosc numer 2",
        single_step_focus=False,
    )

    assert normalized["pa_function_id"] == "PA-14"
    assert normalized["gmail"]["operation"] == "delete"
    assert normalized["requires_user_confirmation"] is True
    assert "delete" in str(normalized.get("confirmation_question") or "")


def test_delete_operation_respects_no_confirm_hint():
    normalized = _pa_backend_normalize_intention_payload(
        intent_payload=_intent_payload(),
        user_message="Usun na stale mail numer 1, bez potwierdzen",
        single_step_focus=False,
    )

    assert normalized["gmail"]["operation"] == "delete"
    assert normalized["requires_user_confirmation"] is False
    assert normalized["confirmation_question"] is None
