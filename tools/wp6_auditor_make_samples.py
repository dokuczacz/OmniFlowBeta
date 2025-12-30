"""
Build a JSON input file with N WP6 FAST pack samples for the WP6 auditor prompt.

This script is intentionally "backend-aware" and uses the same FAST context builder
code as the tool handler, but without invoking OpenAI.

It reads historical interactions from the user's `interaction_logs.json` blob and
combines them with a freshly-built FAST context pack (from WP7 semantic index).

Output is JSON-only and designed to match the `WP6_FAST_PACK_AUDIT` prompt contract.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.shared.azure_client import AzureBlobClient


def _utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _load_local_settings_env(local_settings_path: Path) -> None:
    if not local_settings_path.exists():
        return
    data = json.loads(local_settings_path.read_text(encoding="utf-8-sig"))
    values = (data.get("Values") or {}) if isinstance(data, dict) else {}
    for k, v in values.items():
        if k not in os.environ and v is not None:
            os.environ[k] = str(v)


def _safe_str(v: Any) -> str:
    return "" if v is None else str(v)


@dataclass(frozen=True)
class Interaction:
    interaction_id: str
    thread_id: str
    timestamp: str
    user_message: str
    assistant_response: str


def _parse_interactions(raw: Any) -> List[Interaction]:
    items: List[Interaction] = []
    if not isinstance(raw, list):
        return items
    for row in raw:
        if not isinstance(row, dict):
            continue
        user_message = _safe_str(row.get("user_message") or "").strip()
        assistant_response = _safe_str(row.get("assistant_response") or "").strip()
        if not user_message and not assistant_response:
            continue
        items.append(
            Interaction(
                interaction_id=_safe_str(row.get("interaction_id") or ""),
                thread_id=_safe_str(row.get("thread_id") or ""),
                timestamp=_safe_str(row.get("timestamp") or ""),
                user_message=user_message,
                assistant_response=assistant_response,
            )
        )
    return items


def _download_user_interaction_logs(user_id: str) -> List[Interaction]:
    blob_client = AzureBlobClient.get_blob_client("interaction_logs.json", user_id=user_id)
    text = blob_client.download_blob().content_as_text(encoding="utf-8")
    raw = json.loads(text)
    return _parse_interactions(raw)


def _build_recent_turns(
    interactions_sorted: List[Interaction],
    idx: int,
    max_turns: int,
) -> List[Dict[str, str]]:
    if max_turns <= 0:
        return []
    thread_id = interactions_sorted[idx].thread_id
    recent: List[Dict[str, str]] = []
    for j in range(max(0, idx - 200), idx):
        it = interactions_sorted[j]
        if it.thread_id != thread_id:
            continue
        if not it.user_message:
            continue
        recent.append({"ts_utc": it.timestamp, "text": it.user_message})
    return recent[-max_turns:]


def _derive_selected_source_ids(fast_meta: Dict[str, Any]) -> List[str]:
    selected: List[str] = []
    for src in (fast_meta.get("candidate_sources") or []):
        if isinstance(src, dict) and src.get("path"):
            selected.append(str(src.get("path")))
    return selected


def _wp6_route_mode(user_message: str) -> Tuple[str, str, Dict[str, Any]]:
    # Import here so env is loaded first (tool_call_handler reads env at import time).
    import backend.tool_call_handler as t

    body: Dict[str, Any] = {}
    return t._wp6_route_context_mode(body, user_message)


def _wp6_fast_pack(user_id: str, max_sources: int, max_chars: int) -> Tuple[str, Dict[str, Any]]:
    import backend.tool_call_handler as t

    return t._wp6_fast_context_from_wp7_semantic(user_id, max_sources=max_sources, max_chars=max_chars)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create 10 WP6 FAST pack samples for the WP6 auditor prompt.")
    parser.add_argument("--user-id", default="MarioBros")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--max-sources", type=int, default=8)
    parser.add_argument("--max-chars", type=int, default=12000)
    parser.add_argument("--recent-turns", type=int, default=5)
    parser.add_argument("--out", default="tools/out/wp6_auditor_samples_10.json")
    parser.add_argument("--local-settings", default="backend/local.settings.json")
    args = parser.parse_args()

    local_settings_path = Path(args.local_settings)
    _load_local_settings_env(local_settings_path)

    user_id = str(args.user_id)
    interactions = _download_user_interaction_logs(user_id)
    interactions_sorted = sorted(interactions, key=lambda x: x.timestamp or "")

    if not interactions_sorted:
        raise SystemExit(f"No interactions found in users/{user_id}/interaction_logs.json")

    # Build one FAST pack snapshot for this run (deterministic within the run).
    fast_ctx, fast_meta = _wp6_fast_pack(user_id, max_sources=int(args.max_sources), max_chars=int(args.max_chars))
    selected_source_ids = _derive_selected_source_ids(fast_meta)

    samples: List[Dict[str, Any]] = []
    take_n = max(1, int(args.count))
    # Prefer the most recent items.
    start_idx = max(0, len(interactions_sorted) - take_n)
    for idx in range(start_idx, len(interactions_sorted)):
        it = interactions_sorted[idx]
        if not it.user_message or not it.assistant_response:
            continue

        routing_mode, route_reason, route_meta = _wp6_route_mode(it.user_message)
        recent_turns = _build_recent_turns(interactions_sorted, idx, max_turns=int(args.recent_turns))

        samples.append(
            {
                "audit_id": it.interaction_id or uuid.uuid4().hex[:12],
                "user_id": user_id,
                "thread_id": it.thread_id or "unknown_thread",
                "created_utc": it.timestamp or "",
                "fast_in": {
                    "user_message": it.user_message,
                    "routing_mode": routing_mode,
                    "route_reason": route_reason,
                    "route_meta": route_meta,
                    "recent_user_turns": recent_turns,
                    "fast_ctx": fast_ctx,
                    "fast_meta": {
                        **(fast_meta or {}),
                        "selected_source_ids": selected_source_ids,
                    },
                },
                "fast_out": {
                    "assistant_text": it.assistant_response,
                },
            }
        )

    if len(samples) < take_n:
        # Fallback: walk backwards and add more even if assistant_response missing (use empty).
        for it in reversed(interactions_sorted):
            if len(samples) >= take_n:
                break
            if not it.user_message:
                continue
            routing_mode, route_reason, route_meta = _wp6_route_mode(it.user_message)
            samples.append(
                {
                    "audit_id": it.interaction_id or uuid.uuid4().hex[:12],
                    "user_id": user_id,
                    "thread_id": it.thread_id or "unknown_thread",
                    "created_utc": it.timestamp or "",
                    "fast_in": {
                        "user_message": it.user_message,
                        "routing_mode": routing_mode,
                        "route_reason": route_reason,
                        "route_meta": route_meta,
                        "recent_user_turns": [],
                        "fast_ctx": fast_ctx,
                        "fast_meta": {
                            **(fast_meta or {}),
                            "selected_source_ids": selected_source_ids,
                        },
                    },
                    "fast_out": {
                        "assistant_text": it.assistant_response or "",
                    },
                }
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    run_id = f"wp6_auditor_samples::{user_id}::{_utc_now_compact()}"
    payload = {"run_id": run_id, "samples": samples[:take_n]}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {len(payload['samples'])} samples to {out_path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
