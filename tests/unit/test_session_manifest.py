"""Unit tests for session domain classifier and session manifest (event model, writer, summary)."""
import os
import sys
import json
import uuid
from unittest.mock import MagicMock, patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared.session_domain_classifier import classify_capability, domains_for_capabilities


# ---------------------------------------------------------------------------
# Domain classifier tests
# ---------------------------------------------------------------------------

class TestClassifyCapability:
    def test_system_now_is_ops(self):
        domain, mutating = classify_capability("system.now")
        assert domain == "OPS"
        assert mutating is False

    def test_mail_send_is_com_and_mutating(self):
        domain, mutating = classify_capability("mail.send")
        assert domain == "COM"
        assert mutating is True

    def test_mail_inbox_list_is_know(self):
        domain, mutating = classify_capability("mail.inbox.list")
        assert domain == "KNOW"
        assert mutating is False

    def test_task_create_is_act_and_mutating(self):
        domain, mutating = classify_capability("task.create")
        assert domain == "ACT"
        assert mutating is True

    def test_task_list_is_plan(self):
        domain, mutating = classify_capability("task.list")
        assert domain == "PLAN"
        assert mutating is False

    def test_planning_build_day_plan_is_plan_and_mutating(self):
        domain, mutating = classify_capability("planning.build_day_plan")
        assert domain == "PLAN"
        assert mutating is True

    def test_memory_preferences_get_is_pref(self):
        domain, mutating = classify_capability("memory.preferences.get")
        assert domain == "PREF"
        assert mutating is False

    def test_memory_preferences_update_is_pref_and_mutating(self):
        domain, mutating = classify_capability("memory.preferences.update")
        assert domain == "PREF"
        assert mutating is True

    def test_memory_interaction_save_is_know_and_mutating(self):
        domain, mutating = classify_capability("memory.interaction.save")
        assert domain == "KNOW"
        assert mutating is True

    def test_memory_interaction_list_is_know(self):
        domain, mutating = classify_capability("memory.interaction.list")
        assert domain == "KNOW"
        assert mutating is False

    def test_mail_status_is_ops(self):
        domain, mutating = classify_capability("mail.status")
        assert domain == "OPS"
        assert mutating is False

    def test_mail_trash_is_act_and_mutating(self):
        domain, mutating = classify_capability("mail.trash")
        assert domain == "ACT"
        assert mutating is True

    def test_unknown_capability_defaults_to_ops(self):
        domain, mutating = classify_capability("some.unknown.capability")
        assert domain == "OPS"
        assert mutating is False

    def test_empty_string_defaults_to_ops(self):
        domain, mutating = classify_capability("")
        assert domain == "OPS"
        assert mutating is False

    def test_memory_session_summary_get_is_ops(self):
        domain, mutating = classify_capability("memory.session.summary.get")
        assert domain == "OPS"
        assert mutating is False


class TestDomainsForCapabilities:
    def test_deduplicates_domains(self):
        caps = ["mail.inbox.list", "mail.read", "task.list"]
        domains = domains_for_capabilities(caps)
        # mail is KNOW, task.list is PLAN → 2 unique domains
        assert "KNOW" in domains
        assert "PLAN" in domains
        assert len(domains) == 2

    def test_empty_list(self):
        assert domains_for_capabilities([]) == []


# ---------------------------------------------------------------------------
# Session event model tests
# ---------------------------------------------------------------------------

from shared.session_manifest import (
    build_session_event,
    SCHEMA_VERSION,
    MAX_GPT_NOTE_LEN,
)


class TestBuildSessionEvent:
    def _base_event(self, **kwargs):
        return build_session_event(
            user_id="user123",
            capability="task.create",
            **kwargs,
        )

    def test_required_fields_present(self):
        ev = self._base_event()
        for field in ("schema_version", "event_id", "session_id", "user_id", "timestamp_utc",
                      "capability", "domains_touched", "state_changed"):
            assert field in ev, f"Missing field: {field}"

    def test_schema_version_correct(self):
        ev = self._base_event()
        assert ev["schema_version"] == SCHEMA_VERSION

    def test_domain_is_act_for_task_create(self):
        ev = self._base_event()
        assert "ACT" in ev["domains_touched"]

    def test_gpt_note_stripped_when_not_state_changed(self):
        ev = self._base_event(state_changed=False, gpt_note="Some note")
        assert "gpt_note" not in ev

    def test_gpt_note_present_when_state_changed(self):
        ev = self._base_event(state_changed=True, gpt_note="Task created!")
        assert ev.get("gpt_note") == "Task created!"

    def test_gpt_note_truncated_to_max_len(self):
        long_note = "x" * (MAX_GPT_NOTE_LEN + 100)
        ev = self._base_event(state_changed=True, gpt_note=long_note)
        assert len(ev.get("gpt_note", "")) <= MAX_GPT_NOTE_LEN

    def test_event_id_is_uuid(self):
        ev = self._base_event()
        # Should not raise
        uuid.UUID(ev["event_id"])

    def test_session_id_contains_user_id(self):
        ev = self._base_event()
        assert "user123" in ev["session_id"]

    def test_artifacts_updated_defaults_empty(self):
        ev = self._base_event()
        assert ev["artifacts_updated"] == []

    def test_open_loops_defaults_empty(self):
        ev = self._base_event()
        assert ev["open_loops"] == []


# ---------------------------------------------------------------------------
# Session writer tests (mocked blob)
# ---------------------------------------------------------------------------

from shared.session_manifest import append_session_event, build_session_summary, list_session_events


class TestAppendSessionEvent:
    def _make_blob_client(self, existing_content=""):
        mock_blob = MagicMock()
        if existing_content:
            mock_blob.download_blob.return_value.readall.return_value = existing_content.encode("utf-8")
        else:
            from azure.core.exceptions import ResourceNotFoundError
            mock_blob.download_blob.side_effect = ResourceNotFoundError("not found")
        return mock_blob

    def test_appends_new_line_to_empty_blob(self):
        mock_blob = self._make_blob_client()
        with patch("shared.session_manifest.AzureBlobClient.get_blob_client", return_value=mock_blob):
            ev = build_session_event(user_id="u1", capability="task.create")
            result = append_session_event("u1", ev)
        assert result is True
        upload_call = mock_blob.upload_blob.call_args
        uploaded = upload_call[0][0].decode("utf-8")
        parsed = json.loads(uploaded.strip())
        assert parsed["capability"] == "task.create"
        assert parsed["user_id"] == "u1"

    def test_appends_to_existing_content(self):
        existing_ev = {"capability": "system.now", "event_id": "old"}
        existing_line = json.dumps(existing_ev) + "\n"
        mock_blob = self._make_blob_client(existing_content=existing_line)
        with patch("shared.session_manifest.AzureBlobClient.get_blob_client", return_value=mock_blob):
            ev = build_session_event(user_id="u1", capability="task.create")
            result = append_session_event("u1", ev)
        assert result is True
        uploaded = mock_blob.upload_blob.call_args[0][0].decode("utf-8")
        lines = [l for l in uploaded.splitlines() if l.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["capability"] == "system.now"
        assert json.loads(lines[1])["capability"] == "task.create"

    def test_returns_false_on_storage_error(self):
        mock_blob = MagicMock()
        mock_blob.download_blob.side_effect = Exception("Storage error")
        with patch("shared.session_manifest.AzureBlobClient.get_blob_client", return_value=mock_blob):
            ev = build_session_event(user_id="u1", capability="task.create")
            result = append_session_event("u1", ev)
        assert result is False


# ---------------------------------------------------------------------------
# Session summary + events list tests
# ---------------------------------------------------------------------------

class TestBuildSessionSummary:
    def _mock_events(self, events):
        raw = "\n".join(json.dumps(e) for e in events) + "\n"
        mock_blob = MagicMock()
        mock_blob.download_blob.return_value.readall.return_value = raw.encode("utf-8")
        return mock_blob

    def test_summary_aggregates_domains(self):
        events = [
            build_session_event(user_id="u1", capability="task.create", state_changed=True),
            build_session_event(user_id="u1", capability="mail.inbox.list"),
        ]
        mock_blob = self._mock_events(events)
        with patch("shared.session_manifest.AzureBlobClient.get_blob_client", return_value=mock_blob):
            summary = build_session_summary("u1")
        assert "ACT" in summary["domains_touched"]
        assert "KNOW" in summary["domains_touched"]
        assert summary["state_changed_count"] == 1
        assert summary["event_count"] == 2

    def test_summary_empty_when_no_blob(self):
        from azure.core.exceptions import ResourceNotFoundError
        mock_blob = MagicMock()
        mock_blob.download_blob.side_effect = ResourceNotFoundError("not found")
        with patch("shared.session_manifest.AzureBlobClient.get_blob_client", return_value=mock_blob):
            summary = build_session_summary("u1")
        assert summary["event_count"] == 0
        assert summary["domains_touched"] == []


class TestListSessionEvents:
    def test_returns_newest_first(self):
        ev1 = build_session_event(user_id="u1", capability="system.now")
        ev2 = build_session_event(user_id="u1", capability="task.create")
        raw = "\n".join([json.dumps(ev1), json.dumps(ev2)]) + "\n"
        mock_blob = MagicMock()
        mock_blob.download_blob.return_value.readall.return_value = raw.encode("utf-8")
        with patch("shared.session_manifest.AzureBlobClient.get_blob_client", return_value=mock_blob):
            events = list_session_events("u1", limit=10)
        # newest first: task.create should be first
        assert events[0]["capability"] == "task.create"
        assert events[1]["capability"] == "system.now"

    def test_limit_respected(self):
        evs = [build_session_event(user_id="u1", capability="system.now") for _ in range(5)]
        raw = "\n".join(json.dumps(e) for e in evs) + "\n"
        mock_blob = MagicMock()
        mock_blob.download_blob.return_value.readall.return_value = raw.encode("utf-8")
        with patch("shared.session_manifest.AzureBlobClient.get_blob_client", return_value=mock_blob):
            events = list_session_events("u1", limit=2)
        assert len(events) == 2


# ---------------------------------------------------------------------------
# gpt_note policy regression test
# ---------------------------------------------------------------------------

class TestGptNotePolicy:
    """gpt_note must NOT appear when state_changed=False."""

    def test_no_gpt_note_on_readonly_capability(self):
        ev = build_session_event(
            user_id="u1",
            capability="memory.interaction.list",
            state_changed=False,
            gpt_note="Should be stripped",
        )
        assert "gpt_note" not in ev

    def test_gpt_note_absent_when_none_even_with_state_changed(self):
        ev = build_session_event(
            user_id="u1",
            capability="task.create",
            state_changed=True,
            gpt_note=None,
        )
        assert "gpt_note" not in ev

    def test_gpt_note_empty_string_not_stored(self):
        ev = build_session_event(
            user_id="u1",
            capability="task.create",
            state_changed=True,
            gpt_note="   ",
        )
        assert "gpt_note" not in ev
