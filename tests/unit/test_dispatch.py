"""
Tests for dispatch module (Phase 2 - Dispatch Pipeline).

Tests dispatch_tool_call(), validate_and_normalize(), and integration
with Phase 1 registry.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

import sys
import os

# Add backend to path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Import dispatch module directly to avoid __init__.py dependencies
import importlib.util
spec = importlib.util.spec_from_file_location(
    "dispatch",
    os.path.join(backend_path, "tool_call_handler/dispatch.py")
)
dispatch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dispatch)

dispatch_tool_call = dispatch.dispatch_tool_call
validate_and_normalize = dispatch.validate_and_normalize
get_tool_info = dispatch.get_tool_info
_normalize_response = dispatch._normalize_response

from shared.error_codes import ToolError


class TestDispatchToolCall:
    """Test dispatch_tool_call function."""
    
    def test_successful_dispatch(self, monkeypatch):
        """Test successful tool dispatch."""
        mock_delegate = Mock(return_value={"data": "test_data"})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "read_blob_file",
            {"file_name": "test.json"},
            "user123"
        )
        
        assert result["status"] == "success"
        assert result["tool"] == "read_blob_file"
        assert result["user_id"] == "user123"
        assert "result" in result
        
    def test_dispatch_with_alias(self, monkeypatch):
        """Test dispatch with parameter alias."""
        mock_delegate = Mock(return_value={"data": "test"})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "read_blob_file",
            {"target_blob_name": "test.json"},  # alias
            "user123"
        )
        
        assert result["status"] == "success"
        # Verify alias was normalized
        mock_delegate.assert_called_once()
        call_args = mock_delegate.call_args
        assert call_args[0][1]["file_name"] == "test.json"
        
    def test_dispatch_with_trace_id(self, monkeypatch):
        """Test dispatch with trace_id in context."""
        mock_delegate = Mock(return_value={"data": "test"})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "read_blob_file",
            {"file_name": "test.json"},
            "user123",
            {"trace_id": "trace-abc"}
        )
        
        assert result["trace_id"] == "trace-abc"
        
    def test_dispatch_missing_required_param(self):
        """Test dispatch with missing required parameter."""
        result = dispatch_tool_call(
            "read_blob_file",
            {},  # missing file_name
            "user123"
        )
        
        assert result["status"] == "error"
        assert result["code"] == "MISSING_PARAM"
        assert "file_name" in result["message"]
        
    def test_dispatch_invalid_tool(self):
        """Test dispatch with invalid tool name."""
        result = dispatch_tool_call(
            "nonexistent_tool",
            {},
            "user123"
        )
        
        assert result["status"] == "error"
        assert result["code"] == "INVALID_TOOL"
        
    def test_dispatch_filters_bad_fields(self, monkeypatch):
        """Test that dispatch filters out malicious fields."""
        mock_delegate = Mock(return_value={"data": "test"})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "read_blob_file",
            {
                "file_name": "test.json",
                "malicious_field": "bad_value"
            },
            "user123"
        )
        
        # Should succeed with filtered params
        assert result["status"] == "success"
        
        # Verify malicious field was filtered
        call_args = mock_delegate.call_args
        params = call_args[0][1]
        assert "malicious_field" not in params
        assert "file_name" in params
        
    def test_dispatch_case_insensitive_tool_name(self, monkeypatch):
        """Test dispatch with case-insensitive tool name."""
        mock_delegate = Mock(return_value={"data": "test"})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "READ_BLOB_FILE",  # uppercase
            {"file_name": "test.json"},
            "user123"
        )
        
        assert result["status"] == "success"
        assert result["tool"] == "read_blob_file"  # canonicalized
        
    def test_dispatch_exception_handling(self, monkeypatch):
        """Test dispatch handles unexpected exceptions."""
        mock_delegate = Mock(side_effect=RuntimeError("Unexpected error"))
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "read_blob_file",
            {"file_name": "test.json"},
            "user123"
        )
        
        assert result["status"] == "error"
        assert result["code"] == "INTERNAL_ERROR"
        assert "error_type" in result["details"]


class TestValidateAndNormalize:
    """Test validate_and_normalize function."""
    
    def test_validate_success(self):
        """Test successful validation and normalization."""
        tool, params = validate_and_normalize(
            "read_blob_file",
            {"file_name": "test.json"}
        )
        
        assert tool == "read_blob_file"
        assert params["file_name"] == "test.json"
        
    def test_validate_with_alias(self):
        """Test validation with parameter alias."""
        tool, params = validate_and_normalize(
            "read_blob_file",
            {"target_blob_name": "test.json"}
        )
        
        assert tool == "read_blob_file"
        assert params["file_name"] == "test.json"
        assert "target_blob_name" not in params
        
    def test_validate_missing_param_raises(self):
        """Test that missing required param raises ToolError."""
        with pytest.raises(ToolError) as exc_info:
            validate_and_normalize("read_blob_file", {})
        
        assert exc_info.value.code == "MISSING_PARAM"
        
    def test_validate_invalid_tool_raises(self):
        """Test that invalid tool raises ToolError."""
        with pytest.raises(ToolError) as exc_info:
            validate_and_normalize("invalid_tool", {})
        
        assert exc_info.value.code == "INVALID_TOOL"
        
    def test_validate_normalizes_case(self):
        """Test that tool name case is normalized."""
        tool, params = validate_and_normalize(
            "LIST_BLOBS",
            {"prefix": "test/"}
        )
        
        assert tool == "list_blobs"


class TestGetToolInfo:
    """Test get_tool_info function."""
    
    def test_get_info_for_valid_tool(self):
        """Test getting info for valid tool."""
        info = get_tool_info("read_blob_file")
        
        assert info is not None
        assert "description" in info
        assert "params" in info
        assert "file_name" in info["params"]
        
    def test_get_info_for_invalid_tool(self):
        """Test getting info for invalid tool."""
        info = get_tool_info("nonexistent_tool")
        
        assert info is None
        
    def test_get_info_has_expected_fields(self):
        """Test that tool info has expected fields."""
        info = get_tool_info("list_blobs")
        
        assert "description" in info
        assert "method" in info
        assert "params" in info
        assert "aliases" in info
        assert "examples" in info
        
    def test_get_info_shows_required_params(self):
        """Test that required params are marked."""
        info = get_tool_info("read_blob_file")
        
        file_name_spec = info["params"]["file_name"]
        assert file_name_spec["required"] is True


class TestNormalizeResponse:
    """Test _normalize_response internal function."""
    
    def test_normalize_dict_with_status(self):
        """Test normalizing response that already has status."""
        result = {"status": "success", "data": "test"}
        
        normalized = _normalize_response("test_tool", "user123", result)
        
        assert normalized["status"] == "success"
        assert normalized["tool"] == "test_tool"
        assert normalized["user_id"] == "user123"
        
    def test_normalize_dict_with_error(self):
        """Test normalizing error response."""
        result = {"error": "Something failed", "code": "CUSTOM_ERROR"}
        
        normalized = _normalize_response("test_tool", "user123", result)
        
        assert normalized["status"] == "error"
        assert normalized["error"] == "Something failed"
        assert normalized["code"] == "CUSTOM_ERROR"
        
    def test_normalize_dict_without_status(self):
        """Test normalizing dict without status (assumes success)."""
        result = {"data": "test", "count": 1}
        
        normalized = _normalize_response("test_tool", "user123", result)
        
        assert normalized["status"] == "success"
        assert normalized["result"]["data"] == "test"
        
    def test_normalize_non_dict(self):
        """Test normalizing non-dict result."""
        result = "simple string result"
        
        normalized = _normalize_response("test_tool", "user123", result)
        
        assert normalized["status"] == "success"
        assert normalized["result"] == "simple string result"
        
    def test_normalize_adds_trace_id(self):
        """Test that trace_id is added when provided."""
        result = {"data": "test"}
        
        normalized = _normalize_response(
            "test_tool",
            "user123",
            result,
            trace_id="trace-abc"
        )
        
        assert normalized["trace_id"] == "trace-abc"
        
    def test_normalize_without_trace_id(self):
        """Test that trace_id is not added when not provided."""
        result = {"data": "test"}
        
        normalized = _normalize_response("test_tool", "user123", result)
        
        assert "trace_id" not in normalized


class TestDispatchIntegration:
    """Test dispatch integration with Phase 1 registry."""
    
    def test_full_pipeline(self, monkeypatch):
        """Test full dispatch pipeline."""
        mock_delegate = Mock(return_value={"count": 5, "items": []})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        # Use aliases, case-insensitive, extra fields
        result = dispatch_tool_call(
            "GET_FILTERED_DATA",  # uppercase
            {
                "find_key": "status",      # alias
                "find_value": "active",    # alias
                "blob_name": "data.json",  # alias
                "bad_field": "removed",    # should be filtered
                "user_id": "override"      # system field
            },
            "user123",
            {"trace_id": "trace-123"}
        )
        
        # Verify success
        assert result["status"] == "success"
        assert result["tool"] == "get_filtered_data"
        assert result["user_id"] == "user123"
        assert result["trace_id"] == "trace-123"
        
        # Verify normalization occurred
        call_args = mock_delegate.call_args
        params = call_args[0][1]
        assert "filter_key" in params  # alias applied
        assert "filter_value" in params  # alias applied
        assert "target_blob_name" in params  # alias applied
        assert "bad_field" not in params  # filtered out
        
    def test_dispatch_preserves_optional_params(self, monkeypatch):
        """Test that optional params are preserved."""
        mock_delegate = Mock(return_value={"blobs": []})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "list_blobs",
            {"prefix": "data/", "include_meta": True},
            "user123"
        )
        
        assert result["status"] == "success"
        
        call_args = mock_delegate.call_args
        params = call_args[0][1]
        assert params["prefix"] == "data/"
        assert params["include_meta"] is True


class TestDispatchContract:
    """Test that dispatch follows standard contracts."""
    
    def test_success_envelope_structure(self, monkeypatch):
        """Test that success envelope has required fields."""
        mock_delegate = Mock(return_value={"data": "test"})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "read_blob_file",
            {"file_name": "test.json"},
            "user123"
        )
        
        # Required fields
        assert "status" in result
        assert "tool" in result
        assert "user_id" in result
        assert result["status"] == "success"
        
    def test_error_envelope_structure(self):
        """Test that error envelope has required fields."""
        result = dispatch_tool_call(
            "read_blob_file",
            {},  # missing required param
            "user123"
        )
        
        # Required fields
        assert "status" in result
        assert "code" in result
        assert "message" in result
        assert result["status"] == "error"
        
    def test_response_is_json_serializable(self, monkeypatch):
        """Test that response can be JSON serialized."""
        import json
        
        mock_delegate = Mock(return_value={"data": "test", "count": 1})
        monkeypatch.setattr(dispatch, '_delegate_to_implementation', mock_delegate)
        
        result = dispatch_tool_call(
            "list_blobs",
            {},
            "user123",
            {"trace_id": "trace-abc"}
        )
        
        # Should not raise
        json_str = json.dumps(result)
        assert json_str
        
        # Should be deserializable
        parsed = json.loads(json_str)
        assert parsed["status"] == "success"
