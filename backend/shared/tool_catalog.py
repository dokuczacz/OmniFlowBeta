"""
Minimal tool catalog for Beta dispatcher.

Used to keep canonical names and parameter alias mappings aligned with Central.
"""
from __future__ import annotations

from typing import Dict


# Canonical tool list.
CANONICAL_TOOLS = [
    "read_blob",
    "list_blobs",
]


# Tool name aliases.
TOOL_ALIASES: Dict[str, str] = {
    "read_blob_file": "read_blob",
}


# Parameter aliases per canonical tool.
PARAM_ALIASES: Dict[str, Dict[str, str]] = {
    "read_blob": {
        "file_name": "name",
    },
}


def canonical_tool_name(name: str) -> str:
    if not name:
        return ""
    normalized = str(name).strip()
    return TOOL_ALIASES.get(normalized, normalized)


def apply_param_aliases(tool: str, params: Dict[str, object] | None, keep_legacy: bool = False) -> Dict[str, object]:
    resolved_tool = canonical_tool_name(tool)
    mapping = PARAM_ALIASES.get(resolved_tool, {})
    if not params:
        return {}
    normalized = dict(params)
    for legacy, canonical in mapping.items():
        if legacy in normalized and canonical not in normalized:
            normalized[canonical] = normalized[legacy]
            if not keep_legacy:
                normalized.pop(legacy, None)
    return normalized
