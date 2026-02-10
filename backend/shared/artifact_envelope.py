"""
Helpers for working with "enveloped" JSON artifacts.

Goal:
- Allow artifacts to be either:
  1) legacy list (e.g. TM.json = [ {...}, {...} ])
  2) envelope dict with schema + items (e.g. {"schema_version": "...", "items": [ ... ]})

This lets us add schema_version + timestamps for starter packs without breaking
existing CRUD-style tools that expect a list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ArtifactEnvelope:
    schema_version: str
    created_utc: str
    updated_utc: str
    items_key: str = "items"
    extra: Dict[str, Any] | None = None

    def to_dict(self, items: List[Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
            self.items_key: items,
        }
        if self.extra:
            payload.update(self.extra)
        return payload


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def extract_items(payload: Any, *, items_key: str = "items") -> Tuple[Optional[Dict[str, Any]], List[Any]]:
    """
    Return (envelope_dict_or_none, items_list).

    - If payload is an envelope dict containing items_key -> list, return that dict and the list.
    - If payload is a legacy list/object, return (None, normalized_list).
    """
    if isinstance(payload, dict) and items_key in payload and isinstance(payload.get(items_key), list):
        return payload, list(payload.get(items_key) or [])
    return None, _as_list(payload)


def merge_items_back(original_envelope: Optional[Dict[str, Any]], items: List[Any], *, items_key: str = "items") -> Any:
    """
    Rebuild the JSON payload with updated items.

    - If original_envelope exists, keep all fields and replace items_key.
    - Else return a plain list (legacy behavior).
    """
    if isinstance(original_envelope, dict):
        out = dict(original_envelope)
        out[items_key] = list(items)
        return out
    return list(items)

