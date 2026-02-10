"""
Tool dispatch pipeline for OmniFlowBeta.

This module provides a clean dispatch interface that uses the Phase 1 registry
(tool_specs.py, tool_registry.py, error_codes.py) for normalization and validation,
then delegates to existing tool implementations.

Phase 2 of the Tool Handler refactor.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from shared.error_codes import ToolError, build_error_payload
from shared.tool_registry import normalize_tool_and_params
from shared.tool_specs import get_tool_spec


logger = logging.getLogger(__name__)


def dispatch_tool_call(
    tool_name: str,
    params: Optional[Dict[str, Any]],
    user_id: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Dispatch a tool call through the registry-driven pipeline.
    
    Pipeline:
    1. Normalize tool name and parameters (via registry)
    2. Validate required parameters
    3. Filter to allowed fields
    4. Delegate to tool implementation
    5. Normalize response envelope
    
    Args:
        tool_name: Tool name (canonical or alias)
        params: Tool parameters (may contain aliases)
        user_id: User ID for isolation
        context: Optional context (trace_id, metadata, etc.)
        
    Returns:
        Normalized response dict with status, result/error
        
    Raises:
        ToolError: If validation fails
        
    Example:
        >>> result = dispatch_tool_call(
        ...     "read_blob_file",
        ...     {"target_blob_name": "test.json"},
        ...     "user123"
        ... )
        >>> result["status"]
        'success'
    """
    context = context or {}
    trace_id = context.get("trace_id")
    
    try:
        # Phase 1: Normalize and validate using registry
        canonical_tool, normalized_params = normalize_tool_and_params(
            tool_name,
            params,
            validate=True
        )
        
        logger.info(
            f"Dispatching tool: {canonical_tool} (original: {tool_name}) for user: {user_id}",
            extra={"tool": canonical_tool, "user_id": user_id, "trace_id": trace_id}
        )
        
        # Phase 2: Delegate to implementation
        # For now, import the tools module and dispatch
        # In future phases, this will use TOOL_HANDLERS registry
        result = _delegate_to_implementation(
            canonical_tool,
            normalized_params,
            user_id,
            context
        )
        
        # Phase 3: Normalize response envelope
        return _normalize_response(canonical_tool, user_id, result, trace_id)
        
    except ToolError as e:
        # Structured error from validation
        logger.warning(
            f"Tool error in {tool_name}: {e.code} - {e.message}",
            extra={"tool": tool_name, "user_id": user_id, "trace_id": trace_id}
        )
        return build_error_payload(e.code, e.message, e.details, trace_id)
        
    except Exception as e:
        # Unexpected error
        logger.exception(
            f"Unexpected error dispatching {tool_name}",
            extra={"tool": tool_name, "user_id": user_id, "trace_id": trace_id}
        )
        return build_error_payload(
            "INTERNAL_ERROR",
            f"Internal error: {str(e)}",
            {"tool": tool_name, "error_type": type(e).__name__},
            trace_id
        )


def _delegate_to_implementation(
    tool: str,
    params: Dict[str, Any],
    user_id: str,
    context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Delegate to actual tool implementation.
    
    This is a bridge function that connects the registry-driven dispatch
    to existing tool implementations. In future phases, this will use
    a TOOL_HANDLERS registry pattern from OmniFlowCentral.
    
    Args:
        tool: Canonical tool name
        params: Normalized parameters
        user_id: User ID
        context: Request context
        
    Returns:
        Tool result dict
    """
    # Try to import and use the tools module (lazy import to avoid circular deps)
    try:
        # Lazy import to avoid pulling in heavy dependencies during module load
        import sys
        import os
        
        # Try to import tools dispatch.
        # Important: sys.path must include the *parent* directory that contains the `tools/` package.
        backend_root = os.path.dirname(os.path.dirname(__file__))
        if backend_root not in sys.path:
            sys.path.insert(0, backend_root)
        
        try:
            from tools import dispatch_tool
        except ImportError:
            # If tools module doesn't have dispatch_tool, raise error
            raise ToolError(
                "INTERNAL_ERROR",
                f"Tool dispatch not available: {tool}",
                {"tool": tool}
            )
        
        # Add user_id to params for tools that need it
        dispatch_params = dict(params)
        dispatch_params["user_id"] = user_id
        
        # Dispatch to existing implementation
        result = dispatch_tool(tool, dispatch_params, user_id)
        
        return result
        
    except ToolError:
        # Re-raise ToolError as-is
        raise
        
    except ImportError:
        # Fallback: tool implementation not found
        raise ToolError(
            "INTERNAL_ERROR",
            f"Tool implementation not found: {tool}",
            {"tool": tool}
        )


def _normalize_response(
    tool: str,
    user_id: str,
    result: Any,
    trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Normalize tool response to standard envelope.
    
    Standard envelope:
    {
        "status": "success" | "error",
        "tool": "canonical_tool_name",
        "user_id": "...",
        "result": {...} | "error": "...",
        "trace_id": "..." (optional)
    }
    
    Args:
        tool: Canonical tool name
        user_id: User ID
        result: Tool result (any format)
        trace_id: Optional trace ID
        
    Returns:
        Normalized response envelope
    """
    # If result is already a dict with status, use it
    if isinstance(result, dict):
        if "status" in result:
            # Already normalized
            response = dict(result)
        elif "error" in result:
            # Error format
            response = {
                "status": "error",
                "error": result.get("error"),
                "code": result.get("code", "UPSTREAM_ERROR"),
                "details": result.get("details", {})
            }
        else:
            # Success format
            response = {
                "status": "success",
                "result": result
            }
    else:
        # Wrap non-dict results
        response = {
            "status": "success",
            "result": result
        }
    
    # Add metadata
    response.setdefault("tool", tool)
    response.setdefault("user_id", user_id)
    
    if trace_id:
        response["trace_id"] = trace_id
    
    return response


def validate_and_normalize(
    tool_name: str,
    params: Optional[Dict[str, Any]]
) -> tuple[str, Dict[str, Any]]:
    """
    Convenience function for validation and normalization without dispatch.
    
    Useful for:
    - Pre-validation before async operations
    - Testing tool parameter handling
    - UI parameter validation
    
    Args:
        tool_name: Tool name (canonical or alias)
        params: Tool parameters (may contain aliases)
        
    Returns:
        Tuple of (canonical_tool_name, normalized_params)
        
    Raises:
        ToolError: If validation fails
        
    Example:
        >>> tool, params = validate_and_normalize(
        ...     "READ_BLOB_FILE",
        ...     {"target_blob_name": "test.json"}
        ... )
        >>> tool
        'read_blob_file'
        >>> params
        {'file_name': 'test.json'}
    """
    return normalize_tool_and_params(tool_name, params, validate=True)


def get_tool_info(tool_name: str) -> Optional[Dict[str, Any]]:
    """
    Get information about a tool from the registry.
    
    Useful for:
    - Tool discovery
    - Parameter documentation
    - UI generation
    
    Args:
        tool_name: Tool name (canonical or alias)
        
    Returns:
        Tool specification dict or None if not found
        
    Example:
        >>> info = get_tool_info("read_blob_file")
        >>> info["description"]
        'Read a single blob file by name...'
        >>> info["params"]["file_name"]["required"]
        True
    """
    from shared.tool_registry import canonical_tool_name
    canonical = canonical_tool_name(tool_name)
    return get_tool_spec(canonical)
