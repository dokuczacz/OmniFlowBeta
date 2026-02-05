"""
Tests for error_codes module (WU1 - Error Handling).

Tests ToolError exception class, ERROR_CODES taxonomy, and helper functions.
"""
import pytest
from datetime import datetime, timezone

from shared.error_codes import (
    ToolError,
    ERROR_CODES,
    build_error_payload,
    get_status_code
)


class TestToolError:
    """Test ToolError exception class."""
    
    def test_tool_error_basic(self):
        """Test basic ToolError creation."""
        error = ToolError("MISSING_PARAM", "Parameter 'name' is required")
        
        assert error.code == "MISSING_PARAM"
        assert error.message == "Parameter 'name' is required"
        assert error.details == {}
        assert error.status == 400  # From ERROR_CODES
        
    def test_tool_error_with_details(self):
        """Test ToolError with details dict."""
        details = {"param": "name", "tool": "read_blob"}
        error = ToolError("MISSING_PARAM", "Missing param", details)
        
        assert error.details == details
        assert error.details["param"] == "name"
        assert error.details["tool"] == "read_blob"
        
    def test_tool_error_with_custom_status(self):
        """Test ToolError with custom status code."""
        error = ToolError("CUSTOM_ERROR", "Custom error", status=418)
        
        assert error.status == 418
        
    def test_tool_error_unknown_code_defaults_to_500(self):
        """Test that unknown error codes default to status 500."""
        error = ToolError("UNKNOWN_CODE", "Unknown error")
        
        assert error.status == 500
        
    def test_tool_error_string_representation(self):
        """Test ToolError string representation."""
        error = ToolError("VALIDATION_FAILED", "Bad format")
        
        assert str(error) == "VALIDATION_FAILED: Bad format"
        
    def test_tool_error_is_exception(self):
        """Test that ToolError is an Exception."""
        error = ToolError("MISSING_PARAM", "Test")
        
        assert isinstance(error, Exception)
        
    def test_tool_error_can_be_raised(self):
        """Test that ToolError can be raised and caught."""
        with pytest.raises(ToolError) as exc_info:
            raise ToolError("INVALID_TOOL", "Tool not found")
        
        assert exc_info.value.code == "INVALID_TOOL"
        assert exc_info.value.message == "Tool not found"


class TestErrorCodes:
    """Test ERROR_CODES taxonomy."""
    
    def test_error_codes_exists(self):
        """Test that ERROR_CODES dict exists."""
        assert ERROR_CODES is not None
        assert isinstance(ERROR_CODES, dict)
        
    def test_all_client_errors_have_4xx_status(self):
        """Test that client errors have 4xx status codes."""
        client_errors = ["MISSING_PARAM", "VALIDATION_FAILED", "INVALID_TOOL", 
                        "INVALID_TOOL_NAME", "AUTHORIZATION_FAILED", 
                        "PREFERENCES_BLOCKED", "RATE_LIMITED"]
        
        for code in client_errors:
            assert code in ERROR_CODES
            status = ERROR_CODES[code]["status"]
            assert 400 <= status < 500, f"{code} should have 4xx status, got {status}"
            
    def test_all_server_errors_have_5xx_status(self):
        """Test that server errors have 5xx status codes."""
        server_errors = ["UPSTREAM_ERROR", "TIMEOUT", "SCHEMA_VIOLATION", "INTERNAL_ERROR"]
        
        for code in server_errors:
            assert code in ERROR_CODES
            status = ERROR_CODES[code]["status"]
            assert 500 <= status < 600, f"{code} should have 5xx status, got {status}"
            
    def test_all_error_codes_have_required_fields(self):
        """Test that all error codes have required fields."""
        required_fields = ["status", "description"]
        
        for code, info in ERROR_CODES.items():
            for field in required_fields:
                assert field in info, f"{code} missing required field: {field}"
                assert info[field], f"{code}.{field} should not be empty"
                
    def test_error_codes_have_user_action(self):
        """Test that error codes have user_action guidance."""
        for code, info in ERROR_CODES.items():
            assert "user_action" in info, f"{code} should have user_action"
            assert info["user_action"], f"{code}.user_action should not be empty"
            
    def test_missing_param_error_code(self):
        """Test MISSING_PARAM error code details."""
        assert ERROR_CODES["MISSING_PARAM"]["status"] == 400
        assert "parameter" in ERROR_CODES["MISSING_PARAM"]["description"].lower()
        
    def test_validation_failed_error_code(self):
        """Test VALIDATION_FAILED error code details."""
        assert ERROR_CODES["VALIDATION_FAILED"]["status"] == 400
        assert "validation" in ERROR_CODES["VALIDATION_FAILED"]["description"].lower()
        
    def test_invalid_tool_error_code(self):
        """Test INVALID_TOOL error code details."""
        assert ERROR_CODES["INVALID_TOOL"]["status"] == 404
        assert "tool" in ERROR_CODES["INVALID_TOOL"]["description"].lower()


class TestBuildErrorPayload:
    """Test build_error_payload function."""
    
    def test_build_error_payload_basic(self):
        """Test basic error payload building."""
        payload = build_error_payload("MISSING_PARAM", "Parameter 'name' is required")
        
        assert payload["status"] == "error"
        assert payload["code"] == "MISSING_PARAM"
        assert payload["message"] == "Parameter 'name' is required"
        assert "timestamp" in payload
        assert "user_action" in payload
        
    def test_build_error_payload_with_details(self):
        """Test error payload with details."""
        details = {"param": "name", "value": None}
        payload = build_error_payload("MISSING_PARAM", "Missing param", details)
        
        assert payload["details"] == details
        
    def test_build_error_payload_with_trace_id(self):
        """Test error payload with trace_id."""
        payload = build_error_payload("VALIDATION_FAILED", "Bad format", 
                                      trace_id="trace-123")
        
        assert payload["trace_id"] == "trace-123"
        
    def test_build_error_payload_without_trace_id(self):
        """Test error payload without trace_id doesn't include it."""
        payload = build_error_payload("MISSING_PARAM", "Test")
        
        assert "trace_id" not in payload
        
    def test_build_error_payload_includes_user_action(self):
        """Test that user_action is included from ERROR_CODES."""
        payload = build_error_payload("MISSING_PARAM", "Test")
        
        assert payload["user_action"] == ERROR_CODES["MISSING_PARAM"]["user_action"]
        
    def test_build_error_payload_timestamp_format(self):
        """Test that timestamp is in ISO format."""
        payload = build_error_payload("MISSING_PARAM", "Test")
        
        # Should be parseable as ISO datetime
        timestamp_str = payload["timestamp"]
        parsed = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        assert isinstance(parsed, datetime)
        
    def test_build_error_payload_unknown_code(self):
        """Test error payload with unknown error code."""
        payload = build_error_payload("UNKNOWN_CODE", "Unknown error")
        
        assert payload["code"] == "UNKNOWN_CODE"
        assert payload["status"] == "error"
        # user_action should not be present for unknown codes
        assert "user_action" not in payload or payload.get("user_action") is None


class TestGetStatusCode:
    """Test get_status_code helper function."""
    
    def test_get_status_code_known_code(self):
        """Test getting status code for known error code."""
        assert get_status_code("MISSING_PARAM") == 400
        assert get_status_code("VALIDATION_FAILED") == 400
        assert get_status_code("INVALID_TOOL") == 404
        assert get_status_code("UPSTREAM_ERROR") == 500
        assert get_status_code("TIMEOUT") == 504
        
    def test_get_status_code_unknown_code_uses_default(self):
        """Test that unknown code returns default status."""
        assert get_status_code("UNKNOWN_CODE") == 500
        assert get_status_code("UNKNOWN_CODE", 400) == 400
        assert get_status_code("UNKNOWN_CODE", 418) == 418
        
    def test_get_status_code_empty_string(self):
        """Test getting status code for empty string."""
        assert get_status_code("") == 500
        assert get_status_code("", 400) == 400


class TestErrorContract:
    """Test that errors follow standard contract."""
    
    def test_error_payload_has_required_fields(self):
        """Test that error payload has all required fields."""
        payload = build_error_payload("MISSING_PARAM", "Test message")
        
        required_fields = ["status", "code", "message", "details", "timestamp"]
        for field in required_fields:
            assert field in payload, f"Error payload missing required field: {field}"
            
    def test_error_payload_status_is_error(self):
        """Test that status field is always 'error'."""
        for code in ERROR_CODES.keys():
            payload = build_error_payload(code, "Test")
            assert payload["status"] == "error"
            
    def test_error_payload_serializable(self):
        """Test that error payload can be JSON serialized."""
        import json
        
        payload = build_error_payload("MISSING_PARAM", "Test", 
                                      {"key": "value"}, "trace-123")
        
        # Should not raise exception
        json_str = json.dumps(payload)
        assert json_str
        
        # Should be deserializable
        parsed = json.loads(json_str)
        assert parsed["code"] == "MISSING_PARAM"
