"""
Tests for tool_registry module (WU3 - Registry Functions).

Tests canonical_tool_name(), apply_param_aliases(), validate_tool_params(),
and other registry helper functions.
"""
import pytest

from shared.error_codes import ToolError
from shared.tool_registry import (
    canonical_tool_name,
    apply_param_aliases,
    validate_tool_params,
    get_allowed_fields,
    filter_allowed_fields,
    normalize_tool_and_params,
    get_param_spec
)


class TestCanonicalToolName:
    """Test canonical_tool_name function."""
    
    def test_canonical_name_returned_as_is(self):
        """Test that canonical names are returned unchanged."""
        assert canonical_tool_name("read_blob_file") == "read_blob_file"
        assert canonical_tool_name("list_blobs") == "list_blobs"
        assert canonical_tool_name("get_current_time") == "get_current_time"
        
    def test_empty_string_returns_empty(self):
        """Test that empty string returns empty string."""
        assert canonical_tool_name("") == ""
        
    def test_whitespace_is_stripped(self):
        """Test that whitespace is stripped."""
        assert canonical_tool_name("  read_blob_file  ") == "read_blob_file"
        assert canonical_tool_name("\tlist_blobs\n") == "list_blobs"
        
    def test_case_is_normalized(self):
        """Test that case is normalized to lowercase."""
        assert canonical_tool_name("READ_BLOB_FILE") == "read_blob_file"
        assert canonical_tool_name("List_Blobs") == "list_blobs"
        
    def test_unknown_tool_returns_normalized(self):
        """Test that unknown tools return normalized form."""
        result = canonical_tool_name("unknown_tool")
        assert result == "unknown_tool"
        
    def test_all_registry_tools_are_canonical(self):
        """Test that all tools in registry are already canonical."""
        from shared.tool_specs import get_tool_names
        
        for tool in get_tool_names():
            assert canonical_tool_name(tool) == tool


class TestApplyParamAliases:
    """Test apply_param_aliases function."""
    
    def test_no_aliases_returns_params_unchanged(self):
        """Test that tools without aliases return params unchanged."""
        params = {"limit": 10}
        result = apply_param_aliases("get_current_time", params)
        
        assert result == params
        
    def test_alias_is_converted_to_canonical(self):
        """Test that aliases are converted to canonical names."""
        params = {"target_blob_name": "test.json"}
        result = apply_param_aliases("read_blob_file", params)
        
        assert result == {"file_name": "test.json"}
        assert "target_blob_name" not in result
        
    def test_multiple_aliases_converted(self):
        """Test that multiple aliases are converted."""
        params = {
            "find_key": "status",
            "find_value": "active",
            "target_blob_name": "data.json"
        }
        result = apply_param_aliases("get_filtered_data", params)
        
        assert result["filter_key"] == "status"
        assert result["filter_value"] == "active"
        assert result["target_blob_name"] == "data.json"
        
    def test_canonical_params_unchanged(self):
        """Test that canonical params are not affected."""
        params = {"file_name": "test.json"}
        result = apply_param_aliases("read_blob_file", params)
        
        assert result == {"file_name": "test.json"}
        
    def test_keep_legacy_preserves_both(self):
        """Test that keep_legacy=True preserves legacy params."""
        params = {"target_blob_name": "test.json"}
        result = apply_param_aliases("read_blob_file", params, keep_legacy=True)
        
        assert result["file_name"] == "test.json"
        assert result["target_blob_name"] == "test.json"
        
    def test_canonical_takes_precedence_over_alias(self):
        """Test that if both canonical and alias exist, canonical is used."""
        params = {"file_name": "canonical.json", "target_blob_name": "alias.json"}
        result = apply_param_aliases("read_blob_file", params)
        
        # Canonical should be preserved, alias removed
        assert result["file_name"] == "canonical.json"
        assert "target_blob_name" not in result
        
    def test_none_params_returns_empty_dict(self):
        """Test that None params returns empty dict."""
        result = apply_param_aliases("read_blob_file", None)
        
        assert result == {}
        
    def test_empty_params_returns_empty_dict(self):
        """Test that empty params returns empty dict."""
        result = apply_param_aliases("read_blob_file", {})
        
        assert result == {}
        
    def test_unknown_tool_returns_params_unchanged(self):
        """Test that unknown tools return params unchanged."""
        params = {"key": "value"}
        result = apply_param_aliases("unknown_tool", params)
        
        assert result == params


class TestValidateToolParams:
    """Test validate_tool_params function."""
    
    def test_valid_params_no_error(self):
        """Test that valid params don't raise error."""
        # Should not raise
        validate_tool_params("read_blob_file", {"file_name": "test.json"})
        validate_tool_params("list_blobs", {"prefix": "data/"})
        validate_tool_params("get_current_time", {})
        
    def test_missing_required_param_raises_error(self):
        """Test that missing required param raises ToolError."""
        with pytest.raises(ToolError) as exc_info:
            validate_tool_params("read_blob_file", {})
        
        assert exc_info.value.code == "MISSING_PARAM"
        assert "file_name" in exc_info.value.message
        
    def test_invalid_tool_raises_error(self):
        """Test that invalid tool raises ToolError."""
        with pytest.raises(ToolError) as exc_info:
            validate_tool_params("unknown_tool", {})
        
        assert exc_info.value.code == "INVALID_TOOL"
        
    def test_empty_tool_name_raises_error(self):
        """Test that empty tool name raises ToolError."""
        with pytest.raises(ToolError) as exc_info:
            validate_tool_params("", {})
        
        assert exc_info.value.code == "INVALID_TOOL_NAME"
        
    def test_optional_params_not_required(self):
        """Test that optional params don't cause errors."""
        # list_blobs has optional params
        validate_tool_params("list_blobs", {})
        
    def test_error_includes_tool_and_param_info(self):
        """Test that error includes helpful context."""
        with pytest.raises(ToolError) as exc_info:
            validate_tool_params("read_blob_file", {"wrong_param": "value"})
        
        error = exc_info.value
        assert error.details["tool"] == "read_blob_file"
        assert error.details["param"] == "file_name"
        assert "params_provided" in error.details


class TestGetAllowedFields:
    """Test get_allowed_fields function."""
    
    def test_returns_set_for_valid_tool(self):
        """Test that valid tool returns set of fields."""
        fields = get_allowed_fields("read_blob_file")
        
        assert isinstance(fields, set)
        assert len(fields) > 0
        
    def test_includes_canonical_params(self):
        """Test that canonical params are included."""
        fields = get_allowed_fields("read_blob_file")
        
        assert "file_name" in fields
        
    def test_includes_aliases(self):
        """Test that aliases are included."""
        fields = get_allowed_fields("read_blob_file")
        
        assert "target_blob_name" in fields
        assert "blob_name" in fields
        assert "name" in fields
        
    def test_includes_system_fields(self):
        """Test that system fields are always included."""
        fields = get_allowed_fields("read_blob_file")
        
        assert "user_id" in fields
        assert "trace_id" in fields
        assert "metadata" in fields
        
    def test_returns_none_for_unknown_tool(self):
        """Test that unknown tool returns None."""
        fields = get_allowed_fields("unknown_tool")
        
        assert fields is None
        
    def test_different_tools_have_different_fields(self):
        """Test that different tools have different allowed fields."""
        fields1 = get_allowed_fields("read_blob_file")
        fields2 = get_allowed_fields("list_blobs")
        
        # Both should have system fields
        assert "user_id" in fields1
        assert "user_id" in fields2
        
        # But different specific fields
        assert "file_name" in fields1
        assert "file_name" not in fields2
        assert "prefix" in fields2
        assert "prefix" not in fields1


class TestFilterAllowedFields:
    """Test filter_allowed_fields function."""
    
    def test_allowed_fields_pass_through(self):
        """Test that allowed fields pass through."""
        params = {"file_name": "test.json", "user_id": "user123"}
        result = filter_allowed_fields("read_blob_file", params)
        
        assert result == params
        
    def test_disallowed_fields_removed(self):
        """Test that disallowed fields are removed."""
        params = {
            "file_name": "test.json",
            "malicious_field": "bad_value",
            "another_bad": "value"
        }
        result = filter_allowed_fields("read_blob_file", params)
        
        assert result["file_name"] == "test.json"
        assert "malicious_field" not in result
        assert "another_bad" not in result
        
    def test_aliases_allowed(self):
        """Test that alias fields are allowed."""
        params = {"target_blob_name": "test.json"}
        result = filter_allowed_fields("read_blob_file", params)
        
        assert result["target_blob_name"] == "test.json"
        
    def test_system_fields_allowed(self):
        """Test that system fields are always allowed."""
        params = {
            "file_name": "test.json",
            "user_id": "user123",
            "trace_id": "trace-abc",
            "metadata": {"key": "value"}
        }
        result = filter_allowed_fields("read_blob_file", params)
        
        assert len(result) == 4
        assert all(k in result for k in params.keys())
        
    def test_unknown_tool_returns_params_unchanged(self):
        """Test that unknown tool returns params unchanged."""
        params = {"any_field": "value"}
        result = filter_allowed_fields("unknown_tool", params)
        
        assert result == params


class TestNormalizeToolAndParams:
    """Test normalize_tool_and_params function."""
    
    def test_full_normalization_pipeline(self):
        """Test that full pipeline works correctly."""
        tool, params = normalize_tool_and_params(
            "read_blob_file",
            {"target_blob_name": "test.json", "extra_field": "value"}
        )
        
        assert tool == "read_blob_file"
        assert params == {"file_name": "test.json"}
        
    def test_canonical_tool_name_returned(self):
        """Test that canonical tool name is returned."""
        tool, _ = normalize_tool_and_params("READ_BLOB_FILE", {"file_name": "test.json"})
        
        assert tool == "read_blob_file"
        
    def test_aliases_applied(self):
        """Test that aliases are applied."""
        _, params = normalize_tool_and_params(
            "get_filtered_data",
            {"find_key": "status", "target_blob_name": "data.json"}
        )
        
        assert params["filter_key"] == "status"
        assert params["target_blob_name"] == "data.json"
        
    def test_validation_raises_on_missing_param(self):
        """Test that validation raises error for missing param."""
        with pytest.raises(ToolError) as exc_info:
            normalize_tool_and_params("read_blob_file", {})
        
        assert exc_info.value.code == "MISSING_PARAM"
        
    def test_skip_validation_allows_missing_params(self):
        """Test that validate=False skips validation."""
        # Should not raise
        tool, params = normalize_tool_and_params(
            "read_blob_file",
            {},
            validate=False
        )
        
        assert tool == "read_blob_file"
        assert params == {}
        
    def test_none_params_handled(self):
        """Test that None params are handled."""
        tool, params = normalize_tool_and_params(
            "get_current_time",
            None,
            validate=False
        )
        
        assert tool == "get_current_time"
        assert params == {}
        
    def test_complex_example(self):
        """Test complex normalization with multiple features."""
        tool, params = normalize_tool_and_params(
            "get_filtered_data",
            {
                "blob_name": "data.json",  # alias
                "find_key": "status",      # alias
                "find_value": "active",    # alias
                "extra": "removed",        # should be filtered
                "user_id": "user123"       # system field, kept
            }
        )
        
        assert tool == "get_filtered_data"
        assert params["target_blob_name"] == "data.json"
        assert params["filter_key"] == "status"
        assert params["filter_value"] == "active"
        assert params["user_id"] == "user123"
        assert "extra" not in params


class TestGetParamSpec:
    """Test get_param_spec function."""
    
    def test_returns_spec_for_valid_param(self):
        """Test that valid param returns spec."""
        spec = get_param_spec("read_blob_file", "file_name")
        
        assert spec is not None
        assert isinstance(spec, dict)
        assert spec["required"] is True
        
    def test_returns_none_for_invalid_param(self):
        """Test that invalid param returns None."""
        spec = get_param_spec("read_blob_file", "nonexistent_param")
        
        assert spec is None
        
    def test_returns_none_for_invalid_tool(self):
        """Test that invalid tool returns None."""
        spec = get_param_spec("unknown_tool", "param")
        
        assert spec is None
        
    def test_spec_has_expected_fields(self):
        """Test that spec has expected fields."""
        spec = get_param_spec("list_blobs", "prefix")
        
        assert "type" in spec
        assert "required" in spec
        assert "default" in spec
        assert "description" in spec


class TestRegistryIntegration:
    """Test integration between registry functions."""
    
    def test_canonical_and_validate_work_together(self):
        """Test that canonical_tool_name and validate work together."""
        tool = canonical_tool_name("READ_BLOB_FILE")
        
        # Should validate successfully
        validate_tool_params(tool, {"file_name": "test.json"})
        
    def test_apply_aliases_and_validate_work_together(self):
        """Test that apply_param_aliases and validate work together."""
        params = {"target_blob_name": "test.json"}
        normalized = apply_param_aliases("read_blob_file", params)
        
        # Should validate successfully after aliasing
        validate_tool_params("read_blob_file", normalized)
        
    def test_full_pipeline_with_normalize(self):
        """Test full pipeline with normalize_tool_and_params."""
        # Start with messy input
        tool, params = normalize_tool_and_params(
            "  READ_BLOB_FILE  ",
            {"target_blob_name": "test.json", "bad_field": "value"}
        )
        
        # Should get clean output
        assert tool == "read_blob_file"
        assert params == {"file_name": "test.json"}
