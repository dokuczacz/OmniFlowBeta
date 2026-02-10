"""
OpenAI tool schema helpers.

This is intentionally small and deterministic: convert our internal TOOL_SPECS
registry into Responses API "tools" payloads.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from shared.tool_specs import TOOL_SPECS


def _json_schema_for_param(p: Dict[str, Any]) -> Dict[str, Any]:
    t = str((p or {}).get("type") or "any").strip().lower()
    desc = str((p or {}).get("description") or "").strip()

    if t in ("str", "string"):
        schema: Dict[str, Any] = {"type": "string"}
    elif t in ("int", "integer"):
        schema = {"type": "integer"}
    elif t in ("bool", "boolean"):
        schema = {"type": "boolean"}
    elif t in ("list", "array"):
        schema = {"type": "array", "items": {}}
    elif t in ("dict", "object"):
        schema = {"type": "object", "additionalProperties": True}
    else:
        # Best-effort: allow any JSON type.
        schema = {}

    if desc:
        schema["description"] = desc

    if "default" in (p or {}) and (p or {}).get("default") is not None:
        schema["default"] = (p or {}).get("default")

    return schema


def build_responses_tools(
    *,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    include_web_search: bool = False,
    web_search_context_size: str = "low",
    web_search_allowed_domains: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Build `tools=[{"type":"function","name":...,"description":...,"parameters":...,"strict":true}]`
    payload for the Responses API.

    Tool names and parameters come from `backend.shared.tool_specs.TOOL_SPECS`.
    """
    include_set = set(str(x) for x in (include or []) if str(x).strip())
    exclude_set = set(str(x) for x in (exclude or []) if str(x).strip())

    out: List[Dict[str, Any]] = []

    if include_web_search:
        tool: Dict[str, Any] = {"type": "web_search"}
        ctx = str(web_search_context_size or "").strip().lower()
        if ctx in ("low", "medium", "high"):
            tool["search_context_size"] = ctx
        allowed = [str(x).strip() for x in (web_search_allowed_domains or []) if str(x).strip()]
        if allowed:
            tool["allowed_domains"] = allowed
        out.append(tool)

    for name, spec in sorted((TOOL_SPECS or {}).items(), key=lambda kv: str(kv[0])):
        if include_set and name not in include_set:
            continue
        if name in exclude_set:
            continue
        params = spec.get("params") if isinstance(spec, dict) else {}
        if not isinstance(params, dict):
            params = {}

        required: List[str] = []
        props: Dict[str, Any] = {}
        for p_name, p_spec in params.items():
            if not p_name:
                continue
            props[str(p_name)] = _json_schema_for_param(p_spec if isinstance(p_spec, dict) else {})
            if isinstance(p_spec, dict) and bool(p_spec.get("required")):
                required.append(str(p_name))

        parameters_schema: Dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": props,
        }
        if required:
            parameters_schema["required"] = required

        out.append(
            {
                "type": "function",
                "name": str(name),
                "description": str((spec or {}).get("description") or ""),
                "parameters": parameters_schema,
                # `strict=true` requires the JSON Schema `required` list to include all properties
                # (no optional params), which doesn't match our tool registry. Keep it permissive.
                "strict": False,
            }
        )
    return out
