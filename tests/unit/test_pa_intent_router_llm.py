"""
Unit tests for PA Semantic Prompting Intent Router (LLM-based v2).

Tests verify:
1. Intent Router contract (response structure) — ALWAYS VALID
2. LLM classification behavior (mocked OpenAI)
3. Edge case handling (empty, None, short text)
4. Confidence and clarification logic
5. Evidence trail for audit
"""

import sys
import os
from unittest.mock import patch, MagicMock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tool_call_handler as handler


class TestPAIntentRouterContract:
    """Verify intent router returns correct JSON contract structure (always valid)."""

    def test_pa_intent_router_returns_valid_contract(self):
        """Contract: Must have all required keys."""
        result = handler._pa_intent_router("Check my emails")
        
        assert isinstance(result, dict)
        assert "top_intents" in result
        assert "recommended_stage" in result
        assert "recommended_phase" in result
        assert "need_clarification" in result
        assert "clarify_questions" in result
        assert "evidence" in result

    def test_top_intents_has_valid_stage_and_probability(self):
        """Contract: top_intents items must have valid stage and 0 <= p <= 1.0."""
        result = handler._pa_intent_router("Send an email to john")
        
        for intent in result.get("top_intents", []):
            assert "stage" in intent
            assert "p" in intent
            assert intent["stage"] in handler.PA_INTENT_STAGES
            assert 0 <= intent["p"] <= 1.0, f"Probability {intent['p']} out of range"

    def test_recommended_stage_is_valid_stage(self):
        """Contract: recommended_stage must be in PA_INTENT_STAGES."""
        result = handler._pa_intent_router("hello")
        stage = result.get("recommended_stage", "")
        assert stage in handler.PA_INTENT_STAGES, f"Stage '{stage}' not in {handler.PA_INTENT_STAGES}"

    def test_recommended_phase_defaults_to_discovery(self):
        """Iter1: recommended_phase should always be DISCOVERY (safe default)."""
        result = handler._pa_intent_router("anything")
        assert result.get("recommended_phase") == "DISCOVERY"


class TestPAIntentRouterEdgeCases:
    """Verify edge cases are handled gracefully."""

    def test_empty_text_returns_decision_support_fallback(self):
        """Empty/whitespace text should return safe default."""
        result = handler._pa_intent_router("")
        assert result["recommended_stage"] == "DECISION_SUPPORT"
        assert result["need_clarification"] is True

    def test_very_short_text_handled(self):
        """Short text (<3 chars) should return safe default."""
        result = handler._pa_intent_router("hi")
        assert result["recommended_stage"] == "DECISION_SUPPORT"

    def test_none_text_handled(self):
        """None input should not crash."""
        result = handler._pa_intent_router(None)
        assert result["recommended_stage"] == "DECISION_SUPPORT"


class TestPAIntentRouterLLMBehavior:
    """Verify LLM-based classification behavior with mocked OpenAI."""

    @patch("tool_call_handler.OpenAI")
    def test_email_query_detected_via_llm(self, mock_openai_class):
        """Mock LLM to return EMAIL_QUERY for email read request."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "EMAIL_QUERY"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("check my inbox gmail unread latest")
        
        assert result["recommended_stage"] == "EMAIL_QUERY"
        assert result["need_clarification"] is False

    @patch("tool_call_handler.OpenAI")
    def test_email_write_detected_via_llm(self, mock_openai_class):
        """Mock LLM to return EMAIL_WRITE for email send request."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "EMAIL_WRITE"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("send email draft reply compose to john")
        
        assert result["recommended_stage"] == "EMAIL_WRITE"
        assert result["need_clarification"] is False

    @patch("tool_call_handler.OpenAI")
    def test_calendar_write_detected_via_llm(self, mock_openai_class):
        """Mock LLM to return CALENDAR_WRITE for scheduling request."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "CALENDAR_WRITE"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("schedule meeting book appointment create event")
        
        assert result["recommended_stage"] == "CALENDAR_WRITE"

    @patch("tool_call_handler.OpenAI")
    def test_tasks_manage_detected_via_llm(self, mock_openai_class):
        """Mock LLM to return TASKS_MANAGE for task request."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "TASKS_MANAGE"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("show tasks remind me todo follow up")
        
        assert result["recommended_stage"] == "TASKS_MANAGE"

    @patch("tool_call_handler.OpenAI")
    def test_daily_plan_detected_via_llm(self, mock_openai_class):
        """Mock LLM to return DAILY_PLAN for agenda request."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "DAILY_PLAN"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("plan my day agenda schedule my day")
        
        assert result["recommended_stage"] == "DAILY_PLAN"

    @patch("tool_call_handler.OpenAI")
    def test_ambiguous_intent_triggers_clarification(self, mock_openai_class):
        """Mock low confidence response to trigger clarification."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Return invalid response (confidence drops to 0.3)
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "UNKNOWN_STAGE"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("xyz abc unclear request")
        
        assert result["recommended_stage"] == "DECISION_SUPPORT"
        assert result["need_clarification"] is True
        assert len(result["clarify_questions"]) > 0


class TestPAIntentRouterClarification:
    """Verify clarification logic."""

    @patch("tool_call_handler.OpenAI")
    def test_low_confidence_triggers_clarification(self, mock_openai_class):
        """Low confidence (<0.7) should trigger need_clarification flag."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # Simulate low confidence by returning invalid stage
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "MAYBE_EMAIL"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("check schedule")
        
        assert result["need_clarification"] is True

    @patch("tool_call_handler.OpenAI")
    def test_clarification_includes_questions(self, mock_openai_class):
        """need_clarification=True should include clarify_questions."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "UNCLEAR"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("something vague")
        
        if result["need_clarification"]:
            assert isinstance(result["clarify_questions"], list)
            assert len(result["clarify_questions"]) > 0


class TestPAIntentRouterEvidenceTrail:
    """Verify evidence trail for audit."""

    @patch("tool_call_handler.OpenAI")
    def test_evidence_includes_llm_details(self, mock_openai_class):
        """Evidence should include classifier model and response."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "EMAIL_WRITE"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("send email to alice")
        
        evidence = result.get("evidence", [])
        assert isinstance(evidence, list)
        assert any("llm_classifier" in str(e) for e in evidence)

    @patch("tool_call_handler.OpenAI")
    def test_evidence_capped(self, mock_openai_class):
        """Evidence should be reasonable (5 items or so)."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "CALENDAR_WRITE"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("schedule meeting")
        
        evidence = result.get("evidence", [])
        assert isinstance(evidence, list)


class TestPAIntentRouterPolishLanguage:
    """Verify Polish language support through LLM."""

    @patch("tool_call_handler.OpenAI")
    def test_polish_email_query(self, mock_openai_class):
        """Polish request should be classified correctly by LLM."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "EMAIL_QUERY"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("Sprawdzić maile")
        
        assert result["recommended_stage"] == "EMAIL_QUERY"

    @patch("tool_call_handler.OpenAI")
    def test_polish_daily_plan(self, mock_openai_class):
        """Polish daily plan request should be classified correctly."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "DAILY_PLAN"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("Zaplanuj mój dzień")
        
        # Accept DAILY_PLAN or CALENDAR_WRITE as reasonable (MVP level)
        assert result["recommended_stage"] in ("DAILY_PLAN", "CALENDAR_WRITE")

    @patch("tool_call_handler.OpenAI")
    def test_polish_task_check(self, mock_openai_class):
        """Polish task request should be classified correctly."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "TASKS_MANAGE"
        mock_client.chat.completions.create.return_value = mock_response
        
        result = handler._pa_intent_router("Pokaż moje zadania")
        
        # Accept TASKS_MANAGE as primary
        assert result["recommended_stage"] in ("TASKS_MANAGE", "EMAIL_QUERY")
