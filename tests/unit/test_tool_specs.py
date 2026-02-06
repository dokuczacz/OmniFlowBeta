"""
Tests for tool_specs module (WU2 - Tool Specifications Registry).

Tests TOOL_SPECS registry, helper functions, and specification integrity.
"""
import pytest

from shared.tool_specs import (
    TOOL_SPECS,
    get_tool_names,
    get_tool_spec,
    tool_exists
)


class TestToolSpecs:
    """Test TOOL_SPECS registry."""
    
    def test_tool_specs_exists(self):
        """Test that TOOL_SPECS dict exists."""
        assert TOOL_SPECS is not None
        assert isinstance(TOOL_SPECS, dict)
        
    def test_tool_specs_has_expected_tools(self):
        """Test that all expected tools are in registry."""
        expected_tools = [
            "get_current_time",
            "list_blobs",
            "read_blob_file",
            "read_many_blobs",
            "get_filtered_data",
            "add_new_data",
            "update_data_entry",
            "remove_data_entry",
            "upload_data_or_file",
            "manage_files",
            "save_interaction",
            "get_interaction_history",
            "custom_gpt_tools"
        ]
        
        for tool in expected_tools:
            assert tool in TOOL_SPECS, f"Tool {tool} should be in TOOL_SPECS"
            
    def test_tool_specs_count(self):
        """Test that we have the expected number of tools."""
        assert len(TOOL_SPECS) == 13, "Should have 13 tools in registry"
        
    def test_all_tools_have_required_fields(self):
        """Test that all tools have required fields."""
        required_fields = ["description", "method", "params", "aliases", "examples"]
        
        for tool_name, spec in TOOL_SPECS.items():
            for field in required_fields:
                assert field in spec, f"{tool_name} missing required field: {field}"
                
    def test_all_tools_have_non_empty_description(self):
        """Test that all tools have non-empty descriptions."""
        for tool_name, spec in TOOL_SPECS.items():
            assert spec["description"], f"{tool_name} should have non-empty description"
            assert isinstance(spec["description"], str)
            
    def test_all_tools_have_valid_method(self):
        """Test that all tools have valid HTTP method."""
        valid_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        
        for tool_name, spec in TOOL_SPECS.items():
            assert spec["method"] in valid_methods, f"{tool_name} has invalid method: {spec['method']}"
            
    def test_all_tools_have_params_dict(self):
        """Test that all tools have params dict (even if empty)."""
        for tool_name, spec in TOOL_SPECS.items():
            assert isinstance(spec["params"], dict), f"{tool_name} params should be dict"
            
    def test_all_tools_have_aliases_dict(self):
        """Test that all tools have aliases dict (even if empty)."""
        for tool_name, spec in TOOL_SPECS.items():
            assert isinstance(spec["aliases"], dict), f"{tool_name} aliases should be dict"
            
    def test_all_tools_have_examples_list(self):
        """Test that all tools have examples list."""
        for tool_name, spec in TOOL_SPECS.items():
            assert isinstance(spec["examples"], list), f"{tool_name} examples should be list"
            assert len(spec["examples"]) > 0, f"{tool_name} should have at least one example"


class TestParamSpecs:
    """Test parameter specifications within tools."""
    
    def test_required_params_have_required_field(self):
        """Test that params with required=True are properly defined."""
        tools_with_required = ["read_blob_file", "read_many_blobs", "get_filtered_data"]
        
        for tool_name in tools_with_required:
            spec = TOOL_SPECS[tool_name]
            for param_name, param_spec in spec["params"].items():
                if param_spec.get("required"):
                    assert "type" in param_spec
                    assert "description" in param_spec
                    
    def test_optional_params_have_defaults(self):
        """Test that optional params have default values."""
        spec = TOOL_SPECS["read_many_blobs"]
        
        # These should have defaults
        assert spec["params"]["tail_lines"]["default"] == 0
        assert spec["params"]["tail_bytes"]["default"] == 65536
        assert spec["params"]["max_bytes_per_file"]["default"] == 262144
        assert spec["params"]["parse_json"]["default"] is True
        
    def test_param_types_are_valid(self):
        """Test that param types are standard types."""
        valid_types = ["str", "int", "bool", "list", "dict", "any"]
        
        for tool_name, spec in TOOL_SPECS.items():
            for param_name, param_spec in spec["params"].items():
                if "type" in param_spec:
                    assert param_spec["type"] in valid_types, \
                        f"{tool_name}.{param_name} has invalid type: {param_spec['type']}"
                        
    def test_all_params_have_description(self):
        """Test that all params have descriptions."""
        for tool_name, spec in TOOL_SPECS.items():
            for param_name, param_spec in spec["params"].items():
                assert "description" in param_spec, \
                    f"{tool_name}.{param_name} missing description"
                assert param_spec["description"], \
                    f"{tool_name}.{param_name} description should not be empty"


class TestSpecificTools:
    """Test specific tool configurations."""
    
    def test_read_blob_file_has_aliases(self):
        """Test that read_blob_file has expected aliases."""
        spec = TOOL_SPECS["read_blob_file"]
        aliases = spec["aliases"]
        
        assert "target_blob_name" in aliases
        assert aliases["target_blob_name"] == "file_name"
        assert "blob_name" in aliases
        assert aliases["blob_name"] == "file_name"
        assert "name" in aliases
        assert aliases["name"] == "file_name"
        
    def test_read_blob_file_required_param(self):
        """Test that read_blob_file requires file_name."""
        spec = TOOL_SPECS["read_blob_file"]
        
        assert "file_name" in spec["params"]
        assert spec["params"]["file_name"]["required"] is True
        
    def test_get_filtered_data_has_aliases(self):
        """Test that get_filtered_data has expected aliases."""
        spec = TOOL_SPECS["get_filtered_data"]
        aliases = spec["aliases"]
        
        assert "find_key" in aliases
        assert aliases["find_key"] == "filter_key"
        assert "find_value" in aliases
        assert aliases["find_value"] == "filter_value"
        
    def test_manage_files_has_allowed_values(self):
        """Test that manage_files operation has allowed values."""
        spec = TOOL_SPECS["manage_files"]
        operation_param = spec["params"]["operation"]
        
        assert "allowed_values" in operation_param
        assert "rename" in operation_param["allowed_values"]
        assert "delete" in operation_param["allowed_values"]
        
    def test_list_blobs_has_optional_params(self):
        """Test that list_blobs has optional params with defaults."""
        spec = TOOL_SPECS["list_blobs"]
        
        assert spec["params"]["prefix"]["required"] is False
        assert spec["params"]["prefix"]["default"] == ""
        assert spec["params"]["include_meta"]["required"] is False
        assert spec["params"]["include_meta"]["default"] is False
        
    def test_read_many_blobs_has_required_files(self):
        """Test that read_many_blobs requires files param."""
        spec = TOOL_SPECS["read_many_blobs"]
        
        assert "files" in spec["params"]
        assert spec["params"]["files"]["required"] is True
        assert spec["params"]["files"]["type"] == "list"
        
    def test_get_current_time_has_no_params(self):
        """Test that get_current_time has no params."""
        spec = TOOL_SPECS["get_current_time"]
        
        assert spec["params"] == {}
        assert spec["method"] == "GET"


class TestExamples:
    """Test tool examples."""
    
    def test_all_examples_have_input_and_output(self):
        """Test that all examples have input and output."""
        for tool_name, spec in TOOL_SPECS.items():
            for i, example in enumerate(spec["examples"]):
                assert "input" in example, f"{tool_name} example {i} missing input"
                assert "output" in example, f"{tool_name} example {i} missing output"
                
    def test_examples_match_param_specs(self):
        """Test that example inputs match param specs."""
        # Test a few key tools
        spec = TOOL_SPECS["read_blob_file"]
        example = spec["examples"][0]
        
        # Example should have required param
        assert "file_name" in example["input"]
        
    def test_examples_have_valid_structure(self):
        """Test that examples have valid structure."""
        for tool_name, spec in TOOL_SPECS.items():
            for example in spec["examples"]:
                assert isinstance(example["input"], dict)
                assert isinstance(example["output"], dict)


class TestGetToolNames:
    """Test get_tool_names helper function."""
    
    def test_get_tool_names_returns_list(self):
        """Test that get_tool_names returns a list."""
        names = get_tool_names()
        assert isinstance(names, list)
        
    def test_get_tool_names_has_all_tools(self):
        """Test that get_tool_names returns all tools."""
        names = get_tool_names()
        assert len(names) == 13
        
    def test_get_tool_names_contains_known_tools(self):
        """Test that known tools are in the list."""
        names = get_tool_names()
        
        assert "read_blob_file" in names
        assert "list_blobs" in names
        assert "read_many_blobs" in names
        assert "get_current_time" in names
        
    def test_get_tool_names_returns_strings(self):
        """Test that all tool names are strings."""
        names = get_tool_names()
        for name in names:
            assert isinstance(name, str)


class TestGetToolSpec:
    """Test get_tool_spec helper function."""
    
    def test_get_tool_spec_returns_dict_for_valid_tool(self):
        """Test that get_tool_spec returns dict for valid tool."""
        spec = get_tool_spec("read_blob_file")
        
        assert spec is not None
        assert isinstance(spec, dict)
        
    def test_get_tool_spec_returns_none_for_invalid_tool(self):
        """Test that get_tool_spec returns None for invalid tool."""
        spec = get_tool_spec("nonexistent_tool")
        
        assert spec is None
        
    def test_get_tool_spec_has_expected_fields(self):
        """Test that returned spec has expected fields."""
        spec = get_tool_spec("list_blobs")
        
        assert "description" in spec
        assert "method" in spec
        assert "params" in spec
        assert "aliases" in spec
        assert "examples" in spec
        
    def test_get_tool_spec_for_all_tools(self):
        """Test that we can get spec for all tools."""
        for tool_name in get_tool_names():
            spec = get_tool_spec(tool_name)
            assert spec is not None


class TestToolExists:
    """Test tool_exists helper function."""
    
    def test_tool_exists_returns_true_for_valid_tool(self):
        """Test that tool_exists returns True for valid tools."""
        assert tool_exists("read_blob_file") is True
        assert tool_exists("list_blobs") is True
        assert tool_exists("get_current_time") is True
        
    def test_tool_exists_returns_false_for_invalid_tool(self):
        """Test that tool_exists returns False for invalid tools."""
        assert tool_exists("nonexistent_tool") is False
        assert tool_exists("") is False
        assert tool_exists("random_string") is False
        
    def test_tool_exists_for_all_registry_tools(self):
        """Test that tool_exists works for all tools in registry."""
        for tool_name in get_tool_names():
            assert tool_exists(tool_name) is True


class TestRegistryIntegrity:
    """Test overall registry integrity."""
    
    def test_no_duplicate_tool_names(self):
        """Test that there are no duplicate tool names."""
        tool_names = get_tool_names()
        assert len(tool_names) == len(set(tool_names)), "Duplicate tool names found"
        
    def test_aliases_point_to_valid_params(self):
        """Test that all aliases point to valid params in the spec."""
        for tool_name, spec in TOOL_SPECS.items():
            for alias, canonical in spec["aliases"].items():
                assert canonical in spec["params"], \
                    f"{tool_name}: alias {alias} points to non-existent param {canonical}"
                    
    def test_no_circular_aliases(self):
        """Test that there are no circular alias references."""
        for tool_name, spec in TOOL_SPECS.items():
            aliases = spec["aliases"]
            for alias, canonical in aliases.items():
                # Canonical should not itself be an alias
                assert canonical not in aliases, \
                    f"{tool_name}: circular alias {alias} -> {canonical}"
                    
    def test_all_required_params_documented(self):
        """Test that all required params are documented in examples."""
        for tool_name, spec in TOOL_SPECS.items():
            required_params = [
                param_name for param_name, param_spec in spec["params"].items()
                if param_spec.get("required", False)
            ]
            
            if required_params and spec["examples"]:
                # At least one example should show all required params
                example = spec["examples"][0]
                for param in required_params:
                    # Check if param or one of its aliases is in example
                    param_in_example = param in example["input"]
                    alias_in_example = any(
                        alias in example["input"]
                        for alias, canonical in spec["aliases"].items()
                        if canonical == param
                    )
                    assert param_in_example or alias_in_example, \
                        f"{tool_name}: required param {param} not in any example"
