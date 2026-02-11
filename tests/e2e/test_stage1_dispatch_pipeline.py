"""
Stage 1 – Dispatch Pipeline E2E Tests

Tests the full dispatch pipeline for all 14 tools:
- Tool name normalization (canonical, case-insensitive)
- Parameter alias resolution
- Required parameter validation
- Field filtering (reject extraneous fields)
- Response envelope contract (status, tool, user_id)
- Trace ID propagation
"""
import json
import pytest
from unittest.mock import Mock

from .conftest import (
    dispatch_tool_call,
    validate_and_normalize,
    get_tool_info,
    dispatch_mod,
    TOOL_SPECS,
    get_tool_names,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

ALL_TOOLS = get_tool_names()

# Minimal valid params for each tool (satisfies required fields)
VALID_PARAMS = {
    "get_current_time": {},
    "list_blobs": {},
    "read_blob_file": {"file_name": "test.json"},
    "read_many_blobs": {"files": ["a.json", "b.json"]},
    "get_filtered_data": {"target_blob_name": "TM.json"},
    "add_new_data": {"target_blob_name": "tasks.json", "new_entry": {"task": "e2e"}},
    "update_data_entry": {
        "target_blob_name": "tasks.json",
        "find_key": "id",
        "find_value": "1",
        "update_key": "status",
        "update_value": "done",
    },
    "remove_data_entry": {
        "target_blob_name": "tasks.json",
        "remove_key": "id",
        "remove_value": "1",
    },
    "upload_data_or_file": {"target_blob_name": "out.txt", "file_content": "hello"},
    "manage_files": {"operation": "delete", "source_name": "temp.json"},
    "save_interaction": {
        "user_message": "hi",
        "assistant_response": "hello",
    },
    "get_interaction_history": {},
    "dataset_search": {},
    "custom_gpt_tools": {"action": "test_action"},
    "gmail_action": {"action": "gmail_profile", "payload": {}},
    "gmail_recent_metadata": {"max_results": 5, "label": "INBOX"},
}


# ── 1.1  Success path for every tool ────────────────────────────────────────

class TestDispatchSuccessAllTools:
    """Every canonical tool dispatches successfully with valid params."""

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_dispatch_success(self, tool_name, mock_delegate, test_user_id, trace_ctx):
        delegate = mock_delegate({"data": f"{tool_name}_result"})

        result = dispatch_tool_call(
            tool_name,
            VALID_PARAMS.get(tool_name, {}),
            test_user_id,
            trace_ctx,
        )

        assert result["status"] == "success", f"Tool {tool_name} failed: {result}"
        assert result["tool"] == tool_name
        assert result["user_id"] == test_user_id
        assert result["trace_id"] == trace_ctx["trace_id"]

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_response_is_json_serializable(self, tool_name, mock_delegate, test_user_id):
        mock_delegate({"ok": True})
        result = dispatch_tool_call(tool_name, VALID_PARAMS.get(tool_name, {}), test_user_id)
        serialized = json.dumps(result)
        assert json.loads(serialized)["status"] == "success"


# ── 1.2  Case-insensitive tool names ────────────────────────────────────────

class TestCaseInsensitiveToolNames:
    """Tool names should be accepted in any case."""

    @pytest.mark.parametrize(
        "raw_name, canonical",
        [
            ("READ_BLOB_FILE", "read_blob_file"),
            ("List_Blobs", "list_blobs"),
            ("GET_CURRENT_TIME", "get_current_time"),
            ("  add_new_data  ", "add_new_data"),
        ],
    )
    def test_case_normalization(self, raw_name, canonical, mock_delegate, test_user_id):
        mock_delegate({"ok": True})
        result = dispatch_tool_call(raw_name, VALID_PARAMS.get(canonical, {}), test_user_id)
        assert result["status"] == "success"
        assert result["tool"] == canonical


# ── 1.3  Parameter alias resolution ─────────────────────────────────────────

class TestParameterAliases:
    """Alias parameters are resolved to canonical names before dispatch."""

    ALIAS_CASES = [
        # (tool, alias_params, expected_canonical_key)
        ("read_blob_file", {"target_blob_name": "f.json"}, "file_name"),
        ("read_blob_file", {"blob_name": "f.json"}, "file_name"),
        ("read_blob_file", {"name": "f.json"}, "file_name"),
        ("get_filtered_data", {"find_key": "status", "find_value": "ok", "blob_name": "d.json"}, "filter_key"),
        ("add_new_data", {"blob_name": "t.json", "new_entry": {"a": 1}}, "target_blob_name"),
        ("upload_data_or_file", {"content": "hi", "file_name": "x.txt"}, "file_content"),
        ("remove_data_entry", {"find_key": "id", "find_value": "1", "blob_name": "t.json"}, "remove_key"),
    ]

    @pytest.mark.parametrize("tool,alias_params,expected_key", ALIAS_CASES)
    def test_alias_resolved(self, tool, alias_params, expected_key, mock_delegate, test_user_id):
        delegate = mock_delegate({"ok": True})
        result = dispatch_tool_call(tool, alias_params, test_user_id)

        assert result["status"] == "success", f"Dispatch failed: {result}"
        # Verify alias was resolved in the call to delegate
        call_params = delegate.call_args[0][1]
        assert expected_key in call_params


# ── 1.4  Field filtering ────────────────────────────────────────────────────

class TestFieldFiltering:
    """Extraneous fields must be stripped before reaching the handler."""

    @pytest.mark.parametrize("tool_name", ["read_blob_file", "list_blobs", "get_filtered_data"])
    def test_extra_fields_stripped(self, tool_name, mock_delegate, test_user_id):
        delegate = mock_delegate({"ok": True})
        params = {**VALID_PARAMS.get(tool_name, {}), "evil_key": "attack", "__proto__": "x"}
        result = dispatch_tool_call(tool_name, params, test_user_id)

        assert result["status"] == "success"
        call_params = delegate.call_args[0][1]
        assert "evil_key" not in call_params
        assert "__proto__" not in call_params


# ── 1.5  Response envelope contract ─────────────────────────────────────────

class TestResponseEnvelope:
    """Dispatch responses conform to the standard envelope."""

    def test_success_envelope_shape(self, mock_delegate, test_user_id):
        mock_delegate({"data": "test"})
        result = dispatch_tool_call("list_blobs", {}, test_user_id)

        required_keys = {"status", "tool", "user_id"}
        assert required_keys.issubset(result.keys())
        assert result["status"] == "success"

    def test_error_envelope_shape(self, test_user_id):
        result = dispatch_tool_call("read_blob_file", {}, test_user_id)

        required_keys = {"status", "code", "message"}
        assert required_keys.issubset(result.keys())
        assert result["status"] == "error"

    def test_trace_id_propagated(self, mock_delegate, test_user_id, trace_ctx):
        mock_delegate({"ok": True})
        result = dispatch_tool_call("get_current_time", {}, test_user_id, trace_ctx)
        assert result["trace_id"] == trace_ctx["trace_id"]

    def test_no_trace_when_not_provided(self, mock_delegate, test_user_id):
        mock_delegate({"ok": True})
        result = dispatch_tool_call("get_current_time", {}, test_user_id)
        assert "trace_id" not in result


# ── 1.6  Validate-and-normalize convenience ─────────────────────────────────

class TestValidateAndNormalize:
    """validate_and_normalize() returns canonical names and normalized params."""

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_roundtrip(self, tool_name):
        params = VALID_PARAMS.get(tool_name, {})
        canonical, normalized = validate_and_normalize(tool_name, params)
        assert canonical == tool_name
        # All originally-required keys should survive
        spec = TOOL_SPECS[tool_name]
        for pname, pspec in spec.get("params", {}).items():
            if pspec.get("required"):
                assert pname in normalized, f"Missing required param {pname} for {tool_name}"


# ── 1.7  Tool info / discovery ──────────────────────────────────────────────

class TestToolDiscovery:
    """get_tool_info returns complete specs for every tool."""

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_tool_info_complete(self, tool_name):
        info = get_tool_info(tool_name)
        assert info is not None
        for key in ("description", "method", "params", "aliases", "examples"):
            assert key in info, f"Missing key '{key}' in {tool_name} spec"

    @pytest.mark.parametrize("tool_name", ALL_TOOLS)
    def test_examples_are_valid(self, tool_name):
        info = get_tool_info(tool_name)
        for ex in info.get("examples", []):
            assert "input" in ex
            assert "output" in ex
