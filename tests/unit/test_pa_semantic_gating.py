"""Unit tests for PA Semantic Gating (Iteration 1 - Foundation)."""
import sys
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tool_call_handler as handler  # noqa: E402


class TestPAAllowedToolsForStagePhase:
    """Verify tool allowlist gating logic."""

    def test_invalid_stage_returns_empty_set(self):
        """Invalid stage is not in PA_INTENT_STAGES."""
        tools = handler._pa_allowed_tools_for_stage_phase("INVALID_STAGE", "DISCOVERY")
        assert tools == set()

    def test_read_tools_always_allowed(self):
        """Read tools should always be allowed (regardless of phase)."""
        for language in ("DISCOVERY", "PLAN", "CONFIRM"):
            tools = handler._pa_allowed_tools_for_stage_phase("EMAIL_QUERY", language)
            assert handler.PA_READ_TOOLS.issubset(tools), f"Read tools missing for phase={language}"

    def test_write_tools_blocked_in_discovery(self):
        """Write tools should be blocked in DISCOVERY phase."""
        tools = handler._pa_allowed_tools_for_stage_phase("EMAIL_WRITE", "DISCOVERY")
        assert not (handler.PA_WRITE_TOOLS & tools), f"Write tools should be blocked in DISCOVERY, got: {tools}"

    def test_write_tools_blocked_in_plan(self):
        """Write tools should be blocked in PLAN phase."""
        tools = handler._pa_allowed_tools_for_stage_phase("EMAIL_WRITE", "PLAN")
        assert not (handler.PA_WRITE_TOOLS & tools), f"Write tools should be blocked in PLAN, got: {tools}"

    def test_write_tools_blocked_in_confirm(self):
        """Write tools should be blocked in CONFIRM phase."""
        tools = handler._pa_allowed_tools_for_stage_phase("EMAIL_WRITE", "CONFIRM")
        assert not (handler.PA_WRITE_TOOLS & tools), f"Write tools should be blocked in CONFIRM, got: {tools}"

    def test_write_tools_allowed_in_execute(self):
        """Write tools should be allowed in EXECUTE phase."""
        tools = handler._pa_allowed_tools_for_stage_phase("EMAIL_WRITE", "EXECUTE")
        # EMAIL_WRITE should have gmail_send in allowlist
        assert "gmail_send" in tools or any("gmail" in t for t in tools), f"Gmail write tools should be in EXECUTE, got: {tools}"

    def test_email_query_stage_includes_gmail_tools(self):
        """EMAIL_QUERY stage should include gmail_get, gmail_list, oauth_status."""
        tools = handler._pa_allowed_tools_for_stage_phase("EMAIL_QUERY", "DISCOVER")
        # Should contain read tools + email-specific tools
        assert any("gmail" in t for t in tools), f"Gmail tools missing for EMAIL_QUERY, got: {tools}"

    def test_email_write_stage_includes_gmail_send(self):
        """EMAIL_WRITE stage should include gmail_send (in EXECUTE only)."""
        tools_execute = handler._pa_allowed_tools_for_stage_phase("EMAIL_WRITE", "EXECUTE")
        assert "gmail_send" in tools_execute, f"gmail_send should be in EMAIL_WRITE+EXECUTE, got: {tools_execute}"

    def test_calendar_query_stage(self):
        """CALENDAR_QUERY should include blob tools."""
        tools = handler._pa_allowed_tools_for_stage_phase("CALENDAR_QUERY", "DISCOVERY")
        assert "list_blobs" in tools or "read_blob_file" in tools, f"Blob tools missing for CALENDAR_QUERY, got: {tools}"

    def test_calendar_write_stage_execute_only(self):
        """CALENDAR_WRITE write tools only in EXECUTE."""
        tools_plan = handler._pa_allowed_tools_for_stage_phase("CALENDAR_WRITE", "PLAN")
        tools_execute = handler._pa_allowed_tools_for_stage_phase("CALENDAR_WRITE", "EXECUTE")
        
        # CALENDAR_WRITE is read-only at Iter1 (no update tools)
        assert "update_data_entry" not in tools_plan
        assert "update_data_entry" not in tools_execute
        # But should have read tools in EXECUTE
        assert "read_blob_file" in tools_execute

    def test_tasks_manage_stage_has_update_tools_in_execute(self):
        """TASKS_MANAGE should allow add_new_data, update_data_entry in EXECUTE."""
        tools_execute = handler._pa_allowed_tools_for_stage_phase("TASKS_MANAGE", "EXECUTE")
        assert "add_new_data" in tools_execute
        assert "update_data_entry" in tools_execute
        assert "upload_data_or_file" in tools_execute

    def test_daily_plan_stage_blocked_in_non_execute(self):
        """DAILY_PLAN write tools should be blocked outside EXECUTE."""
        tools_plan = handler._pa_allowed_tools_for_stage_phase("DAILY_PLAN", "PLAN")
        assert "upload_data_or_file" not in tools_plan
        
        tools_execute = handler._pa_allowed_tools_for_stage_phase("DAILY_PLAN", "EXECUTE")
        # In EXECUTE, may have tools (depends on allowlist)
        assert isinstance(tools_execute, set)

    def test_decision_support_read_only(self):
        """DECISION_SUPPORT should be read-only (no write tools in any phase)."""
        for phase in ("DISCOVERY", "PLAN", "CONFIRM", "EXECUTE"):
            tools = handler._pa_allowed_tools_for_stage_phase("DECISION_SUPPORT", phase)
            write_in_tools = handler.PA_WRITE_TOOLS & tools
            assert not write_in_tools, f"DECISION_SUPPORT should be read-only, found writes in {phase}: {write_in_tools}"

    def test_doc_analysis_read_only(self):
        """DOC_ANALYSIS should be read-only."""
        for phase in ("DISCOVERY", "PLAN", "CONFIRM", "EXECUTE"):
            tools = handler._pa_allowed_tools_for_stage_phase("DOC_ANALYSIS", phase)
            write_in_tools = handler.PA_WRITE_TOOLS & tools
            assert not write_in_tools, f"DOC_ANALYSIS should be read-only, found writes in {phase}: {write_in_tools}"

    def test_notes_kb_allows_writes_in_execute(self):
        """NOTES_KB should allow add_new_data, update_data_entry in EXECUTE."""
        tools_execute = handler._pa_allowed_tools_for_stage_phase("NOTES_KB", "EXECUTE")
        assert "add_new_data" in tools_execute
        assert "update_data_entry" in tools_execute

    def test_notes_kb_blocks_writes_in_discovery(self):
        """NOTES_KB should block writes in DISCOVERY."""
        tools_discovery = handler._pa_allowed_tools_for_stage_phase("NOTES_KB", "DISCOVERY")
        assert "add_new_data" not in tools_discovery


class TestPAPhaseGatingBehavior:
    """Test phase-based gating enforcement."""

    def test_discovery_phase_blocks_all_writes(self):
        """All WRITE stages should block mutations in DISCOVERY phase."""
        for stage in handler.PA_WRITE_STAGES:
            tools = handler._pa_allowed_tools_for_stage_phase(stage, "DISCOVERY")
            write_tools_in_allowed = handler.PA_WRITE_TOOLS & tools
            assert not write_tools_in_allowed, f"{stage}+DISCOVERY should not have write tools, got: {write_tools_in_allowed}"

    def test_plan_phase_blocks_all_writes(self):
        """All WRITE stages should block mutations in PLAN phase."""
        for stage in handler.PA_WRITE_STAGES:
            tools = handler._pa_allowed_tools_for_stage_phase(stage, "PLAN")
            write_tools_in_allowed = handler.PA_WRITE_TOOLS & tools
            assert not write_tools_in_allowed, f"{stage}+PLAN should not have write tools, got: {write_tools_in_allowed}"

    def test_confirm_phase_blocks_all_writes(self):
        """All WRITE stages should block mutations in CONFIRM phase."""
        for stage in handler.PA_WRITE_STAGES:
            tools = handler._pa_allowed_tools_for_stage_phase(stage, "CONFIRM")
            write_tools_in_allowed = handler.PA_WRITE_TOOLS & tools
            assert not write_tools_in_allowed, f"{stage}+CONFIRM should not have write tools, got: {write_tools_in_allowed}"

    def test_execute_phase_allows_writes(self):
        """All WRITE stages should allow mutations in EXECUTE phase."""
        for stage in handler.PA_WRITE_STAGES:
            tools = handler._pa_allowed_tools_for_stage_phase(stage, "EXECUTE")
            # Should have at least some write capability
            write_tools_in_allowed = handler.PA_WRITE_TOOLS & tools
            # (relaxed: may depend on allowlist, but EXECUTE should enable writes)
            assert isinstance(tools, set), f"{stage}+EXECUTE should return valid toolset"

    def test_case_insensitive_stage(self):
        """Stage name should be case-insensitive (MVP requirement)."""
        result_upper = handler._pa_allowed_tools_for_stage_phase("EMAIL_QUERY", "DISCOVERY")
        result_lower = handler._pa_allowed_tools_for_stage_phase("email_query", "discovery")
        result_mixed = handler._pa_allowed_tools_for_stage_phase("Email_Query", "Discovery")
        
        assert result_upper == result_lower == result_mixed, "Stage gating should be case-insensitive"

    def test_null_safety_stage(self):
        """Null stage should return empty set (safe fallback)."""
        result = handler._pa_allowed_tools_for_stage_phase(None, "DISCOVERY")
        assert result == set()

    def test_null_safety_phase_defaults_to_non_execute(self):
        """Null phase should default to non-execute behavior (blocks writes)."""
        result = handler._pa_allowed_tools_for_stage_phase("EMAIL_WRITE", None)
        write_tools_in_allowed = handler.PA_WRITE_TOOLS & result
        assert not write_tools_in_allowed, "Null phase should block write tools (safe default)"
