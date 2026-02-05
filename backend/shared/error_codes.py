"""
Structured error codes and handling for OmniFlowBeta.

This module provides a taxonomy of error codes and a ToolError exception class
for consistent error handling across the tool handler system.

Based on patterns from OmniFlowCentral.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class ToolError(Exception):
    """
    Structured tool error with code, message, and optional details.
    
    Usage:
        raise ToolError("MISSING_PARAM", "Parameter 'name' is required", {"param": "name"})
    """
    
    def __init__(
        self,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status: Optional[int] = None
    ):
        """
        Initialize a ToolError.
        
        Args:
            code: Error code from ERROR_CODES (e.g., "MISSING_PARAM")
            message: Human-readable error message
            details: Optional additional context (e.g., {"param": "name", "tool": "read_blob"})
            status: HTTP status code (if None, derived from ERROR_CODES)
        """
        self.code = code
        self.message = message
        self.details = details or {}
        self.status = status or ERROR_CODES.get(code, {}).get("status", 500)
        super().__init__(f"{code}: {message}")


# Error code taxonomy with descriptions and default HTTP status codes
ERROR_CODES: Dict[str, Dict[str, Any]] = {
    # Client errors (4xx)
    "MISSING_PARAM": {
        "status": 400,
        "description": "Required parameter not provided",
        "user_action": "Provide the required parameter"
    },
    "VALIDATION_FAILED": {
        "status": 400,
        "description": "Parameter validation failed",
        "user_action": "Check parameter format and try again"
    },
    "INVALID_TOOL": {
        "status": 404,
        "description": "Tool not found in registry",
        "user_action": "Use a valid tool name from capabilities"
    },
    "INVALID_TOOL_NAME": {
        "status": 400,
        "description": "Tool name is invalid or malformed",
        "user_action": "Provide a valid tool name"
    },
    "AUTHORIZATION_FAILED": {
        "status": 403,
        "description": "User not authorized for this operation",
        "user_action": "Check permissions and user_id"
    },
    "PREFERENCES_BLOCKED": {
        "status": 403,
        "description": "Operation blocked by user preferences",
        "user_action": "Modify preferences or request access"
    },
    "RATE_LIMITED": {
        "status": 429,
        "description": "Too many requests",
        "user_action": "Wait and retry"
    },
    
    # Server errors (5xx)
    "UPSTREAM_ERROR": {
        "status": 500,
        "description": "External service failure",
        "user_action": "Retry later or contact support"
    },
    "TIMEOUT": {
        "status": 504,
        "description": "Operation timed out",
        "user_action": "Retry with smaller request"
    },
    "SCHEMA_VIOLATION": {
        "status": 500,
        "description": "Output schema validation failed",
        "user_action": "Report to developers (internal error)"
    },
    "INTERNAL_ERROR": {
        "status": 500,
        "description": "Internal server error",
        "user_action": "Contact support if issue persists"
    }
}


def build_error_payload(
    code: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    trace_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Build a standardized error response payload.
    
    Args:
        code: Error code from ERROR_CODES
        message: Human-readable error message
        details: Optional additional context
        trace_id: Optional trace ID for request tracking
        
    Returns:
        Standardized error payload dict
        
    Example:
        >>> payload = build_error_payload("MISSING_PARAM", "Parameter 'name' required", {"param": "name"})
        >>> payload["status"]
        'error'
        >>> payload["code"]
        'MISSING_PARAM'
    """
    payload = {
        "status": "error",
        "code": code,
        "message": message,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Add user action if available
    error_info = ERROR_CODES.get(code, {})
    if "user_action" in error_info:
        payload["user_action"] = error_info["user_action"]
    
    # Add trace_id if provided
    if trace_id:
        payload["trace_id"] = trace_id
    
    return payload


def get_status_code(code: str, default: int = 500) -> int:
    """
    Get HTTP status code for an error code.
    
    Args:
        code: Error code from ERROR_CODES
        default: Default status code if code not found
        
    Returns:
        HTTP status code
        
    Example:
        >>> get_status_code("MISSING_PARAM")
        400
        >>> get_status_code("UNKNOWN_CODE", 500)
        500
    """
    return ERROR_CODES.get(code, {}).get("status", default)
