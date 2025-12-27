from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
from typing import Any, Dict, List, Tuple

import azure.functions as func
from azure.core.exceptions import AzureError
from openai import OpenAI

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.azure_client import AzureBlobClient
from shared.user_manager import extract_user_id
from shared.wp7_indexer import (
    QueueThresholds,
    WP7_SEMANTIC_PREFIX,
    WP7_SEMANTIC_SCHEMA_V1,
    WP7_UNCATEGORIZED_PORTFOLIO_BLOB_NAME,
    WP7_UNCATEGORIZED_SCHEMA_V1,
    append_semantic_index_item,
    append_uncategorized_portfolio_item,
    build_semantic_index_item,
    derive_signal_level,
    download_queue_tail,
    load_indexer_state,
    save_indexer_state,
    utc_now_iso,
)


def _parse_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _now_utc() -> dt.datetime:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)


def _parse_iso(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _iter_jsonl_lines(data: bytes) -> List[Tuple[int, str]]:
    """
    Returns a list of (line_len_bytes, line_str_without_newline).
    Skips the last partial line (no trailing newline) to avoid corrupt reads.
    """
    if not data:
        return []
    lines: List[Tuple[int, str]] = []
    start = 0
    n = len(data)
    while start < n:
        line_start = start
        end = data.find(b"\n", start)
        if end == -1:
            # If the queue ends without a trailing newline, try to treat the tail as a full JSON line.
            raw_tail = data[start:]
            try:
                tail = raw_tail.decode("utf-8").strip()
            except Exception:
                break
            if not tail:
                break
            try:
                json.loads(tail)
            except Exception:
                break
            lines.append((n - line_start, tail))
            break
        raw_line = data[start:end]
        start = end + 1
        try:
            line = raw_line.decode("utf-8").strip()
        except Exception:
            continue
        if not line:
            continue
        lines.append((end + 1 - line_start, line))
    return lines


def _load_thresholds(req: func.HttpRequest) -> QueueThresholds:
    body = {}
    try:
        body = req.get_json() if req.method.lower() == "post" else {}
    except Exception:
        body = {}
    return QueueThresholds(
        target_tokens=_safe_int(body.get("target_tokens") or os.environ.get("WP7_TARGET_BATCH_TOKENS"), 1000),
        hard_min_tokens=_safe_int(body.get("hard_min_tokens") or os.environ.get("WP7_HARD_MIN_BATCH_TOKENS"), 600),
        max_wait_seconds=_safe_int(body.get("max_wait_seconds") or os.environ.get("WP7_MAX_WAIT_SECONDS"), 300),
        max_items_per_run=_safe_int(body.get("max_items_per_run") or os.environ.get("WP7_MAX_ITEMS_PER_RUN"), 25),
        max_user_chars=_safe_int(os.environ.get("WP7_MAX_USER_CHARS"), 2000),
        max_assistant_chars=_safe_int(os.environ.get("WP7_MAX_ASSISTANT_CHARS"), 4000),
    )


def _create_indexer_input(items: List[Dict[str, Any]]) -> str:
    # The Indexer Prompt is responsible for enforcing schema and category enumeration.
    # NOTE: Some OpenAI `text.format: json_object` configurations require the word "json"
    # to appear in the input messages; include a stable hint field to satisfy that constraint.
    payload = {"schema_version": "omniflow.wp7.indexer_input.v1", "format_hint": "json", "items": items}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _resync_offset_to_newline(user_id: str, *, offset: int, lookback: int = 8192) -> int:
    """
    If `offset` points into the middle of a JSONL line (e.g. due to a previously bad offset),
    rewind to the byte right after the previous newline.
    """
    if offset <= 0:
        return 0
    start = max(0, int(offset) - int(lookback))
    try:
        bc = AzureBlobClient.get_blob_client("interactions/indexer_queue.jsonl", user_id)
        chunk = bc.download_blob(offset=start, length=offset - start).readall()
    except Exception:
        return offset
    idx = chunk.rfind(b"\n")
    if idx == -1:
        return 0
    return start + idx + 1


def _call_indexer_model(openai_client: OpenAI, prompt_id: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    input_text = _create_indexer_input(items)
    # Output tokens are typically priced higher; keep a tight, per-item budget.
    # If the prompt is well-formed (strict JSON, short summaries), this cap should be sufficient.
    per_item = _safe_int(os.environ.get("WP7_MAX_OUTPUT_TOKENS_PER_ITEM"), 180)
    max_output_tokens = max(256, min(4096, 128 + (max(1, len(items)) * max(60, per_item))))
    resp = openai_client.responses.create(
        prompt={"id": prompt_id},
        input=input_text,
        tool_choice="none",
        parallel_tool_calls=False,
        max_output_tokens=max_output_tokens,
        metadata={"runtime": "wp7_indexer"},
    )
    output = getattr(resp, "output_text", None) or ""
    if not output:
        raise RuntimeError("Indexer returned empty output_text")
    try:
        parsed = json.loads(output)
    except Exception as e:
        raise RuntimeError(f"Indexer output is not valid JSON: {e}")
    # Prompt may enforce `text.format: json_object` (Dashboard), so accept:
    # - object with `items[]` (preferred)
    # - array (legacy / permissive)
    if isinstance(parsed, dict):
        items_out = parsed.get("items")
        if not isinstance(items_out, list):
            raise RuntimeError("Indexer JSON object output must contain an `items` array")
        return items_out
    if isinstance(parsed, list):
        return parsed
    raise RuntimeError("Indexer output must be a JSON object with `items[]` or a JSON array")


def _write_semantic_artifact(user_id: str, interaction_id: str, artifact: Dict[str, Any]) -> None:
    blob_name = f"{WP7_SEMANTIC_PREFIX}{interaction_id}.json"
    bc = AzureBlobClient.get_blob_client(blob_name, user_id)
    payload = dict(artifact or {})
    payload.setdefault("schema_version", WP7_SEMANTIC_SCHEMA_V1)
    payload.setdefault("interaction_id", interaction_id)
    payload.setdefault("user_id", str(user_id))
    payload.setdefault("timestamp_utc", utc_now_iso())
    payload.setdefault("signal_level", derive_signal_level(payload))
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    bc.upload_blob(data.encode("utf-8"), overwrite=True)

    semantic_blob_path = f"users/{user_id}/{blob_name}"
    try:
        append_semantic_index_item(
            user_id,
            build_semantic_index_item(
                payload,
                user_id=user_id,
                interaction_id=interaction_id,
                semantic_blob_path=semantic_blob_path,
            ),
        )
    except Exception as e:
        logging.warning(f"WP7 semantic index append failed for {interaction_id}: {e}")


def _parse_confidence(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _allowed_categories() -> set:
    raw = os.environ.get("WP7_ALLOWED_CATEGORIES", "PE,UI,ML,LO,PS,TM,SYS,GEN,ID")
    return {c.strip().upper() for c in (raw or "").split(",") if c.strip()}


def _uncategorized_conf_threshold() -> float:
    try:
        return float(os.environ.get("WP7_UNCATEGORIZED_CONFIDENCE_LT", "0.6"))
    except Exception:
        return 0.6


def _should_portfolio_uncategorized(artifact: Dict[str, Any]) -> tuple[bool, list]:
    reasons = []
    cat = str((artifact or {}).get("category") or "").strip()
    conf = _parse_confidence((artifact or {}).get("confidence"))
    allowed = _allowed_categories()
    if not cat:
        reasons.append("missing_category")
    elif cat.upper() not in allowed:
        reasons.append("invalid_category")
    if conf < _uncategorized_conf_threshold():
        reasons.append("low_confidence")
    return (len(reasons) > 0), reasons


def _enqueue_uncategorized_portfolio(user_id: str, artifact: Dict[str, Any], semantic_blob_path: str) -> None:
    item = {
        "schema_version": WP7_UNCATEGORIZED_SCHEMA_V1,
        "timestamp_utc": utc_now_iso(),
        "user_id": str(user_id),
        "interaction_id": str(artifact.get("interaction_id") or "").strip(),
        "category": str(artifact.get("category") or "").strip(),
        "confidence": _parse_confidence(artifact.get("confidence")),
        "tags": artifact.get("tags") if isinstance(artifact.get("tags"), list) else [],
        "summary": str(artifact.get("summary") or "")[:800],
        "semantic_blob_path": semantic_blob_path,
        "portfolio_blob_name": WP7_UNCATEGORIZED_PORTFOLIO_BLOB_NAME,
    }
    append_uncategorized_portfolio_item(user_id, item)


def _semantic_exists(user_id: str, interaction_id: str) -> bool:
    try:
        blob_name = f"{WP7_SEMANTIC_PREFIX}{interaction_id}.json"
        bc = AzureBlobClient.get_blob_client(blob_name, user_id)
        bc.get_blob_properties()
        return True
    except Exception:
        return False


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    WP7 Indexer (batch) - HTTP trigger.
    - Reads per-user interactions/indexer_queue.jsonl from byte offset.
    - If enough tokens (target) or wait exceeded (hard_min + max_wait), runs the indexer prompt once for the batch.
    - Writes semantic artifacts per interaction_id.
    - Advances byte offset only after successful processing (idempotent).
    """
    user_id = extract_user_id(req) or "default"
    thresholds = _load_thresholds(req)

    try:
        body = req.get_json() if req.method.lower() == "post" else {}
    except Exception:
        body = {}
    force = _parse_bool(req.params.get("force") or (body.get("force") if isinstance(body, dict) else None))
    dry_run = _parse_bool(req.params.get("dry_run") or (body.get("dry_run") if isinstance(body, dict) else None))

    prompt_id = os.environ.get("OPENAI_INDEXER_PROMPT_ID", "").strip()
    if not prompt_id and not dry_run:
        return func.HttpResponse(
            json.dumps({"error": "Missing OPENAI_INDEXER_PROMPT_ID", "user_id": user_id}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500,
        )

    state = load_indexer_state(user_id)
    offset = _safe_int(state.get("byte_offset"), 0)
    data, total = download_queue_tail(user_id, offset=offset)
    if offset > total and total > 0:
        logging.warning(f"WP7 state offset beyond queue; resetting offset user_id={user_id} offset={offset} total={total}")
        offset = 0
        state["byte_offset"] = 0
        state["first_pending_at_utc"] = None
        data, total = download_queue_tail(user_id, offset=offset)
    lines = _iter_jsonl_lines(data)

    # Detect "offset in the middle of a JSONL record": the first complete line from this offset
    # will not be valid JSON (it is the suffix of a previous record). Resync once.
    if lines and 0 < offset < total:
        try:
            json.loads(lines[0][1])
        except Exception:
            new_offset = _resync_offset_to_newline(user_id, offset=offset)
            if new_offset != offset:
                logging.warning(f"WP7 resync offset to newline user_id={user_id} old={offset} new={new_offset} total={total}")
                offset = new_offset
                state["byte_offset"] = offset
                data, total = download_queue_tail(user_id, offset=offset)
                lines = _iter_jsonl_lines(data)

    if not lines:
        # If offset points into a line, try to resync to previous newline once.
        if 0 < offset < total:
            new_offset = _resync_offset_to_newline(user_id, offset=offset)
            if new_offset != offset:
                logging.warning(f"WP7 resync offset to newline user_id={user_id} old={offset} new={new_offset} total={total}")
                offset = new_offset
                state["byte_offset"] = offset
                data, total = download_queue_tail(user_id, offset=offset)
                lines = _iter_jsonl_lines(data)

    if not lines:
        # No new complete lines available
        state["first_pending_at_utc"] = None
        save_indexer_state(user_id, state)
        return func.HttpResponse(
            json.dumps(
                {"status": "idle", "user_id": user_id, "byte_offset": offset, "queue_size_bytes": total},
                ensure_ascii=False,
            ),
            mimetype="application/json",
            status_code=200,
        )

    # Build candidate items without advancing offset.
    candidates: List[Tuple[int, Dict[str, Any]]] = []
    token_sum = 0
    for line_len, line in lines:
        if len(candidates) >= thresholds.max_items_per_run:
            break
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        iid = str(item.get("interaction_id") or "").strip()
        if not iid:
            continue
        if _semantic_exists(user_id, iid):
            # Already indexed; we can safely advance past it after the run.
            candidates.append((line_len, {"_skip": True, "interaction_id": iid}))
            continue
        token_sum += _safe_int(item.get("estimated_tokens"), 0)
        candidates.append((line_len, item))
        if token_sum >= thresholds.target_tokens:
            break

    now = _now_utc()
    first_pending_at = _parse_iso(state.get("first_pending_at_utc"))
    if first_pending_at is None:
        first_pending_at = now
        state["first_pending_at_utc"] = first_pending_at.isoformat().replace("+00:00", "Z")

    elapsed_s = int((now - first_pending_at).total_seconds())
    should_run = force or token_sum >= thresholds.target_tokens or (
        elapsed_s >= thresholds.max_wait_seconds and token_sum >= thresholds.hard_min_tokens
    )

    if not should_run:
        save_indexer_state(user_id, state)
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "waiting",
                    "user_id": user_id,
                    "byte_offset": offset,
                    "queue_size_bytes": total,
                    "candidate_items": len(candidates),
                    "tokens_sum": token_sum,
                    "target_tokens": thresholds.target_tokens,
                    "hard_min_tokens": thresholds.hard_min_tokens,
                    "max_wait_seconds": thresholds.max_wait_seconds,
                    "elapsed_seconds": elapsed_s,
                },
                ensure_ascii=False,
            ),
            mimetype="application/json",
            status_code=200,
        )

    # Prepare batch items (skip markers removed from model input)
    batch_items: List[Dict[str, Any]] = []
    for _, item in candidates:
        if item.get("_skip"):
            continue
        batch_items.append(item)

    if dry_run:
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "dry_run",
                    "user_id": user_id,
                    "byte_offset": offset,
                    "queue_size_bytes": total,
                    "batch_items": len(batch_items),
                    "tokens_sum": token_sum,
                },
                ensure_ascii=False,
            ),
            mimetype="application/json",
            status_code=200,
        )

    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not openai_key:
        return func.HttpResponse(
            json.dumps({"error": "Missing OPENAI_API_KEY", "user_id": user_id}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500,
        )

    openai_client = OpenAI(api_key=openai_key)

    try:
        artifacts = _call_indexer_model(openai_client, prompt_id, batch_items)
    except Exception as e:
        logging.error(f"WP7 indexer call failed: {e}")
        # keep first_pending_at_utc to measure waiting window, do not advance offset
        save_indexer_state(user_id, state)
        return func.HttpResponse(
            json.dumps({"status": "error", "error": str(e), "user_id": user_id}, ensure_ascii=False),
            mimetype="application/json",
            status_code=500,
        )

    # Map artifacts by interaction_id
    by_id: Dict[str, Dict[str, Any]] = {}
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        iid = str(art.get("interaction_id") or "").strip()
        if iid:
            by_id[iid] = art

    advanced_bytes = 0
    indexed = 0
    skipped = 0
    missing = 0

    for line_len, item in candidates:
        if item.get("_skip"):
            advanced_bytes += line_len
            skipped += 1
            continue
        iid = str(item.get("interaction_id") or "").strip()
        if not iid:
            continue
        art = by_id.get(iid)
        if art is None:
            # Do not advance offset past an item we didn't get an output for.
            missing += 1
            break
        try:
            semantic_blob_path = f"users/{user_id}/{WP7_SEMANTIC_PREFIX}{iid}.json"
            _write_semantic_artifact(user_id, iid, art)
            should_portfolio, reasons = _should_portfolio_uncategorized(art)
            if should_portfolio:
                try:
                    art = dict(art or {})
                    art.setdefault("interaction_id", iid)
                    art["portfolio_reasons"] = reasons
                    _enqueue_uncategorized_portfolio(user_id, art, semantic_blob_path)
                except Exception as pe:
                    logging.warning(f"WP7 uncategorized portfolio append failed for {iid}: {pe}")
            indexed += 1
            advanced_bytes += line_len
        except AzureError as e:
            logging.error(f"WP7 failed writing semantic artifact for {iid}: {e}")
            break

    if advanced_bytes > 0:
        state["byte_offset"] = offset + advanced_bytes
        state["first_pending_at_utc"] = None
        save_indexer_state(user_id, state)
    else:
        save_indexer_state(user_id, state)

    return func.HttpResponse(
        json.dumps(
            {
                "status": "ok",
                "user_id": user_id,
                "indexed": indexed,
                "skipped_existing": skipped,
                "missing_outputs": missing,
                "advanced_bytes": advanced_bytes,
                "byte_offset": state.get("byte_offset", offset),
                "queue_size_bytes": total,
                "tokens_sum": token_sum,
            },
            ensure_ascii=False,
        ),
        mimetype="application/json",
        status_code=200,
    )
