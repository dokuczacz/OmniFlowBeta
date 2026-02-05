from __future__ import annotations

from typing import Dict

MANAGE_FILES_ALIAS_MAP: Dict[str, str] = {
    "op": "operation",
    "source_blob": "source_name",
    "source": "source_name",
    "target_blob": "target_name",
    "target": "target_name",
    "path_prefix": "prefix",
}

def normalize_manage_files_params(
    params: Dict[str, object] | None, *, keep_legacy: bool = False
) -> Dict[str, object]:
    if not params:
        return {}
    normalized = dict(params)
    for alias, canonical in MANAGE_FILES_ALIAS_MAP.items():
        if alias in normalized and canonical not in normalized:
            normalized[canonical] = normalized[alias]
            if not keep_legacy:
                normalized.pop(alias, None)
    return normalized
