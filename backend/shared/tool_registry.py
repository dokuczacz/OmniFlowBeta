"""
Tool registry functions for OmniFlowBeta - Canonical names, aliases, validation.

This module provides functions for working with the TOOL_SPECS registry:
- canonical_tool_name(): Convert any tool name to canonical form
- apply_param_aliases(): Apply parameter aliases for backward compatibility
- validate_tool_params(): Validate that required params are present
- get_allowed_fields(): Get list of allowed parameter fields for a tool

Based on patterns from OmniFlowCentral.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from .error_codes import ToolError
from .tool_specs import TOOL_SPECS, get_tool_spec, tool_exists


def canonical_tool_name(raw_name: str) -> str:
    """
    Convert any tool name to canonical form.
    
    Handles:
    - Direct canonical names (returns as-is)
    - Legacy names via reverse alias lookup
    - Case normalization
    
    Args:
        raw_name: Tool name (canonical or alias)
        
    Returns:
        Canonical tool name, or original if not found
        
    Examples:
        >>> canonical_tool_name("read_blob_file")
        'read_blob_file'
        >>> canonical_tool_name("")
        ''
    """
    if not raw_name:
        return ""
    
    # Normalize: strip whitespace, lowercase
    normalized = str(raw_name).strip().lower()
    
    # Already canonical?
    if tool_exists(normalized):
        return normalized
    
    # Check if it's an alias in any tool's alias map
    for tool_name, spec in TOOL_SPECS.items():
        # Check if raw_name is a tool alias (reverse lookup)
        # Tool aliases map old tool names to canonical names
        # We're not using those yet, but keeping for future
        pass
    
    # Return normalized even if unknown (caller will validate)
    return normalized


def apply_param_aliases(
    tool: str,
    params: Optional[Dict[str, Any]],
    keep_legacy: bool = False
) -> Dict[str, Any]:
    """
    Apply parameter aliases for a tool.
    
    Converts legacy parameter names to canonical names based on the tool's
    alias map. This ensures backward compatibility with old parameter names.
    
    Args:
        tool: Canonical tool name
        params: Parameters dict (may contain aliases)
        keep_legacy: If True, keep both legacy and canonical params
                    If False, remove legacy params after mapping
        
    Returns:
        Dict with canonical parameter names
        
    Examples:
        >>> params = {"target_blob_name": "file.json"}
        >>> apply_param_aliases("read_blob_file", params)
        {'file_name': 'file.json'}
        
        >>> params = {"target_blob_name": "file.json"}
        >>> apply_param_aliases("read_blob_file", params, keep_legacy=True)
        {'target_blob_name': 'file.json', 'file_name': 'file.json'}
    """
    if not params:
        return {}
    
    # Get canonical tool name
    canonical_tool = canonical_tool_name(tool)
    
    # Get tool spec
    spec = get_tool_spec(canonical_tool)
    if not spec:
        return dict(params)  # Return as-is if tool not found
    
    # Get alias mapping for this tool
    aliases = spec.get("aliases", {})
    if not aliases:
        return dict(params)  # No aliases, return as-is
    
    # Apply aliases
    normalized = dict(params)
    
    for legacy_name, canonical_name in aliases.items():
        if legacy_name in normalized:
            if canonical_name not in normalized:
                # Map legacy to canonical
                normalized[canonical_name] = normalized[legacy_name]
            
            # Always remove legacy if not keeping (even if canonical exists)
            if not keep_legacy:
                normalized.pop(legacy_name, None)
    
    return normalized


def validate_tool_params(tool: str, params: Dict[str, Any]) -> None:
    """
    Validate that required parameters are present for a tool.
    
    Raises ToolError if:
    - Tool not found in registry
    - Required parameters are missing
    
    Args:
        tool: Canonical tool name
        params: Parameters dict (should have canonical names)
        
    Raises:
        ToolError: If validation fails
        
    Examples:
        >>> validate_tool_params("read_blob_file", {"file_name": "test.json"})
        # No error
        
        >>> validate_tool_params("read_blob_file", {})
        # Raises ToolError("MISSING_PARAM", ...)
    """
    # Check if tool exists
    if not tool:
        raise ToolError("INVALID_TOOL_NAME", "Tool name cannot be empty")
    
    canonical_tool = canonical_tool_name(tool)
    
    if not tool_exists(canonical_tool):
        raise ToolError(
            "INVALID_TOOL",
            f"Unknown tool: {tool}",
            {"tool": tool}
        )
    
    # Get tool spec
    spec = get_tool_spec(canonical_tool)
    if not spec:
        # Should not happen if tool_exists returned True
        raise ToolError("INVALID_TOOL", f"Tool spec not found: {canonical_tool}")
    
    # Get param specs
    param_specs = spec.get("params", {})
    
    # Check required params
    for param_name, param_spec in param_specs.items():
        if param_spec.get("required", False):
            if param_name not in params:
                raise ToolError(
                    "MISSING_PARAM",
                    f"Missing required parameter: {param_name}",
                    {
                        "tool": canonical_tool,
                        "param": param_name,
                        "params_provided": list(params.keys())
                    }
                )


def get_allowed_fields(tool: str) -> Optional[Set[str]]:
    """
    Get set of allowed parameter fields for a tool.
    
    Includes:
    - All parameters defined in the tool spec
    - All parameter aliases
    - Common system fields (user_id, trace_id, etc.)
    
    Args:
        tool: Canonical tool name
        
    Returns:
        Set of allowed field names, or None if tool not found
        
    Examples:
        >>> fields = get_allowed_fields("read_blob_file")
        >>> "file_name" in fields
        True
        >>> "target_blob_name" in fields  # alias
        True
    """
    canonical_tool = canonical_tool_name(tool)
    
    spec = get_tool_spec(canonical_tool)
    if not spec:
        return None
    
    # Start with canonical param names
    allowed = set(spec.get("params", {}).keys())
    
    # Add all aliases
    allowed.update(spec.get("aliases", {}).keys())
    
    # Add common system fields (always allowed)
    system_fields = {
        "user_id",
        "trace_id",
        "metadata",
        "timeout",
        "code"  # Azure Functions function key
    }
    allowed.update(system_fields)
    
    return allowed


def filter_allowed_fields(
    tool: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Filter parameters to only allowed fields for a tool.
    
    This prevents injection of extraneous fields and provides
    security by ensuring only expected parameters reach handlers.
    
    Args:
        tool: Canonical tool name
        params: Parameters dict (may contain extra fields)
        
    Returns:
        Dict with only allowed fields
        
    Examples:
        >>> params = {"file_name": "test.json", "malicious_field": "value"}
        >>> filtered = filter_allowed_fields("read_blob_file", params)
        >>> "file_name" in filtered
        True
        >>> "malicious_field" in filtered
        False
    """
    allowed = get_allowed_fields(tool)
    
    if allowed is None:
        # Tool not found - return as-is (let validation handle it)
        return dict(params)
    
    # Filter to allowed fields only
    return {
        key: value
        for key, value in params.items()
        if key in allowed
    }


def normalize_tool_and_params(
    tool_name: str,
    params: Optional[Dict[str, Any]],
    validate: bool = True
) -> tuple[str, Dict[str, Any]]:
    """
    Normalize tool name and parameters in one step.
    
    Pipeline:
    1. Canonicalize tool name
    2. Apply parameter aliases
    3. Filter to allowed fields
    4. Validate required parameters (if validate=True)
    
    Args:
        tool_name: Tool name (canonical or alias)
        params: Parameters dict (may contain aliases or extra fields)
        validate: Whether to validate required params
        
    Returns:
        Tuple of (canonical_tool_name, normalized_params)
        
    Raises:
        ToolError: If validation fails
        
    Examples:
        >>> tool, params = normalize_tool_and_params(
        ...     "read_blob_file",
        ...     {"target_blob_name": "test.json"}
        ... )
        >>> tool
        'read_blob_file'
        >>> params
        {'file_name': 'test.json'}
    """
    # 1. Canonicalize tool name
    canonical = canonical_tool_name(tool_name)
    
    # 2. Apply parameter aliases
    params = params or {}
    normalized_params = apply_param_aliases(canonical, params)
    
    # 3. Filter to allowed fields
    filtered_params = filter_allowed_fields(canonical, normalized_params)
    
    # 4. Validate if requested
    if validate:
        validate_tool_params(canonical, filtered_params)
    
    return canonical, filtered_params


def get_param_spec(tool: str, param_name: str) -> Optional[Dict[str, Any]]:
    """
    Get specification for a specific parameter.
    
    Args:
        tool: Canonical tool name
        param_name: Parameter name
        
    Returns:
        Parameter spec dict or None if not found
        
    Example:
        >>> spec = get_param_spec("read_blob_file", "file_name")
        >>> spec["required"]
        True
    """
    tool_spec = get_tool_spec(canonical_tool_name(tool))
    if not tool_spec:
        return None
    
    params = tool_spec.get("params", {})
    return params.get(param_name)
