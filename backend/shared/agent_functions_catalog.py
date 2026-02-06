from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping


@dataclass(frozen=True)
class AgentToolSpec:
    """A minimal, local view of a tool entry from AGENT_FUNCTIONS_CATALOG.json."""

    name: str
    allowed_fields: tuple[str, ...]


def _unique_preserve_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return tuple(out)


def _repo_root() -> Path:
    # backend/shared/<this_file> -> backend -> repo root
    return Path(__file__).resolve().parents[2]


def _default_catalog_path() -> Path:
    return _repo_root() / "AGENT_FUNCTIONS_CATALOG.json"


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as exc:
        logging.warning("agent_functions_catalog: failed to read %s: %s", path, exc)
        return {}
    try:
        payload = json.loads(raw)
    except Exception as exc:
        logging.warning("agent_functions_catalog: failed to parse %s: %s", path, exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _tool_allowed_fields_from_tools_entry(entry: Mapping[str, Any]) -> tuple[str, ...]:
    inputs = entry.get("inputs") if isinstance(entry.get("inputs"), dict) else {}
    allowed: list[str] = []
    query = inputs.get("query") if isinstance(inputs.get("query"), list) else []
    for q in query:
        if isinstance(q, dict) and q.get("name"):
            allowed.append(str(q.get("name")))
    body = inputs.get("body")
    if isinstance(body, dict):
        required = body.get("required") if isinstance(body.get("required"), list) else []
        allowed.extend([str(x) for x in required if isinstance(x, (str, int, float))])
        props = body.get("properties") if isinstance(body.get("properties"), list) else []
        for prop in props:
            if isinstance(prop, dict) and prop.get("name"):
                allowed.append(str(prop.get("name")))
    return _unique_preserve_order(allowed)


def _tool_allowed_fields_from_openai_schema(entry: Mapping[str, Any]) -> tuple[str, ...]:
    parameters = entry.get("parameters") if isinstance(entry.get("parameters"), dict) else {}
    properties = parameters.get("properties") if isinstance(parameters.get("properties"), dict) else {}
    return _unique_preserve_order([str(k) for k in properties.keys()])


def load_agent_tool_specs(path: Path | None = None) -> Dict[str, AgentToolSpec]:
    catalog_path = path or _default_catalog_path()
    payload = _load_json(catalog_path)

    tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    openai_schemas = (
        payload.get("openai_function_schemas")
        if isinstance(payload.get("openai_function_schemas"), list)
        else []
    )

    allowed_by_name: dict[str, list[str]] = {}
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("operation_id") or "").strip()
        if not name:
            continue
        allowed_by_name.setdefault(name, []).extend(_tool_allowed_fields_from_tools_entry(tool))

    for schema in openai_schemas:
        if not isinstance(schema, dict):
            continue
        name = str(schema.get("name") or "").strip()
        if not name:
            continue
        allowed_by_name.setdefault(name, []).extend(_tool_allowed_fields_from_openai_schema(schema))

    return {
        name: AgentToolSpec(name=name, allowed_fields=_unique_preserve_order(fields))
        for name, fields in allowed_by_name.items()
        if name
    }


# Load once at import time (best-effort; code must work even if missing).
AGENT_TOOL_SPECS = load_agent_tool_specs()


def allowed_fields_for_tool(tool_name: str) -> tuple[str, ...]:
    spec = AGENT_TOOL_SPECS.get(str(tool_name or "").strip())
    return spec.allowed_fields if spec else tuple()

