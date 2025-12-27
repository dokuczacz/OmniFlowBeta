from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import tempfile
import uuid
from typing import Any, Dict, List, Tuple

import azure.functions as func
from azure.core.exceptions import AzureError
from openai import OpenAI
from openai._legacy_response import HttpxBinaryResponseContent

# Add parent directory to path for shared imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.azure_client import AzureBlobClient
from shared.wp7_indexer import (
    QueueThresholds,
    WP7_QUEUE_BLOB_NAME,
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


WP7_BATCH_STATE_BLOB_NAME = "interactions/indexer_batch_state.json"
WP7_BATCH_STATE_SCHEMA_V1 = "omniflow.wp7.batch_state.v1"


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
    if not data:
        return []
    lines: List[Tuple[int, str]] = []
    start = 0
    n = len(data)
    while start < n:
        line_start = start
        end = data.find(b"\n", start)
        if end == -1:
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


def _wp7_mode() -> str:
    return str(os.environ.get("WP7_INDEXER_MODE") or "sync").strip().lower()


def _discover_user_ids_with_queue() -> list[str]:
    """
    Discover user IDs that have a WP7 queue blob present.

    This is used for timer-triggered indexing, where we do not have an HTTP header
    to infer `user_id`. For safety, this only discovers users that already have
    `users/{user_id}/interactions/indexer_queue.jsonl`.
    """
    cc = AzureBlobClient.get_container_client()
    suffix = f"/{WP7_QUEUE_BLOB_NAME}"
    users: set[str] = set()
    try:
        for blob in cc.list_blobs(name_starts_with="users/"):
            name = str(getattr(blob, "name", "") or "")
            if not name.endswith(suffix):
                continue
            parts = name.split("/")
            if len(parts) >= 2 and parts[0] == "users" and parts[1].strip():
                users.add(parts[1].strip())
    except Exception as e:
        logging.warning(f"WP7: user discovery failed: {e}")
        return []
    return sorted(users)


def _load_batch_state(user_id: str) -> Dict[str, Any]:
    bc = AzureBlobClient.get_blob_client(WP7_BATCH_STATE_BLOB_NAME, user_id)
    try:
        raw = bc.download_blob().readall()
    except Exception:
        return {
            "schema_version": WP7_BATCH_STATE_SCHEMA_V1,
            "user_id": str(user_id),
            "status": "none",
            "updated_at_utc": utc_now_iso(),
        }
    try:
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("batch_state is not an object")
        payload.setdefault("schema_version", WP7_BATCH_STATE_SCHEMA_V1)
        payload.setdefault("user_id", str(user_id))
        payload.setdefault("status", "none")
        payload.setdefault("updated_at_utc", utc_now_iso())
        return payload
    except Exception:
        return {
            "schema_version": WP7_BATCH_STATE_SCHEMA_V1,
            "user_id": str(user_id),
            "status": "none",
            "updated_at_utc": utc_now_iso(),
        }


def _save_batch_state(user_id: str, state: Dict[str, Any]) -> None:
    bc = AzureBlobClient.get_blob_client(WP7_BATCH_STATE_BLOB_NAME, user_id)
    payload = dict(state or {})
    payload["schema_version"] = WP7_BATCH_STATE_SCHEMA_V1
    payload["user_id"] = str(user_id)
    payload["updated_at_utc"] = utc_now_iso()
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    bc.upload_blob(data.encode("utf-8"), overwrite=True)


def _clear_batch_state(user_id: str) -> None:
    _save_batch_state(
        user_id,
        {
            "schema_version": WP7_BATCH_STATE_SCHEMA_V1,
            "user_id": str(user_id),
            "status": "none",
        },
    )


def _is_active_batch_state(state: Dict[str, Any]) -> bool:
    status = str((state or {}).get("status") or "").strip().lower()
    batch_id = str((state or {}).get("batch_id") or "").strip()
    return bool(batch_id and status in ("submitted", "queued", "validating", "in_progress", "finalizing"))


def _semantic_exists(user_id: str, interaction_id: str) -> bool:
    try:
        blob_name = f"{WP7_SEMANTIC_PREFIX}{interaction_id}.json"
        bc = AzureBlobClient.get_blob_client(blob_name, user_id)
        bc.get_blob_properties()
        return True
    except Exception:
        return False


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


def _create_indexer_input(items: List[Dict[str, Any]]) -> str:
    payload = {"schema_version": "omniflow.wp7.indexer_input.v1", "format_hint": "json", "items": items}
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _output_text_from_response_body(body: Any) -> str:
    if isinstance(body, dict):
        direct = body.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct
        output = body.get("output")
        if isinstance(output, list):
            parts: List[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            t = c.get("text")
                            if isinstance(t, str) and t:
                                parts.append(t)
            joined = "".join(parts).strip()
            if joined:
                return joined
    if isinstance(body, str):
        return body
    return ""


def _write_temp_jsonl(content_utf8: str) -> str:
    raw = content_utf8.encode("utf-8")
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    try:
        tf.write(raw)
        tf.flush()
    finally:
        tf.close()
    return tf.name


def _submit_openai_batch(
    openai_client: OpenAI,
    *,
    prompt_id: str,
    user_id: str,
    batch_items: List[Dict[str, Any]],
    offset_start: int,
    candidates_count: int,
    submitted_ids: List[str],
    candidate_ids: List[str],
    planned_advance_bytes: int,
) -> Dict[str, Any]:
    input_text = _create_indexer_input(batch_items)
    per_item = _safe_int(os.environ.get("WP7_MAX_OUTPUT_TOKENS_PER_ITEM"), 180)
    max_output_tokens = max(256, min(4096, 128 + (max(1, len(batch_items)) * max(60, per_item))))

    model = str(os.environ.get("OPENAI_INDEXER_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5-mini").strip()
    body = {
        "model": model,
        "prompt": {"id": prompt_id},
        "input": input_text,
        "tool_choice": "none",
        "parallel_tool_calls": False,
        "max_output_tokens": max_output_tokens,
        "metadata": {"runtime": "wp7_indexer_timer_batch", "user_id": str(user_id)},
    }
    custom_id = f"wp7:{user_id}:{uuid.uuid4().hex}"
    line = json.dumps(
        {"custom_id": custom_id, "method": "POST", "url": "/v1/responses", "body": body},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    tmp_path = _write_temp_jsonl(line + "\n")
    try:
        with open(tmp_path, "rb") as fh:
            file_obj = openai_client.files.create(file=fh, purpose="batch")
        batch = openai_client.batches.create(
            completion_window="24h",
            endpoint="/v1/responses",
            input_file_id=file_obj.id,
            metadata={"kind": "wp7_indexer", "user_id": str(user_id)},
        )
        logging.info(
            "WP7: batch_submitted user_id=%s batch_id=%s input_file_id=%s model=%s custom_id=%s",
            user_id,
            getattr(batch, "id", None),
            getattr(file_obj, "id", None),
            model,
            custom_id,
        )
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    state = {
        "schema_version": WP7_BATCH_STATE_SCHEMA_V1,
        "user_id": str(user_id),
        "status": str(getattr(batch, "status", None) or "submitted"),
        "batch_id": str(getattr(batch, "id", None) or ""),
        "input_file_id": str(getattr(file_obj, "id", None) or ""),
        "custom_id": custom_id,
        "requested_at_utc": utc_now_iso(),
        "offset_start": int(offset_start),
        "planned_advance_bytes": int(planned_advance_bytes),
        "candidate_count": int(candidates_count),
        "candidate_interaction_ids": candidate_ids,
        "submitted_interaction_ids": submitted_ids,
    }
    _save_batch_state(user_id, state)
    return {
        "status": "batch_submitted",
        "user_id": user_id,
        "batch_id": state["batch_id"],
        "batch_status": state["status"],
        "offset_start": offset_start,
        "planned_advance_bytes": planned_advance_bytes,
        "candidate_count": candidates_count,
        "submitted_items": len(submitted_ids),
        "custom_id": custom_id,
    }


def _download_openai_file_text(openai_client: OpenAI, file_id: str) -> str:
    content: HttpxBinaryResponseContent = openai_client.files.content(file_id)
    return content.text


def _ingest_batch_output(
    openai_client: OpenAI,
    *,
    user_id: str,
    batch_state: Dict[str, Any],
    output_text: str,
) -> Dict[str, Any]:
    # Parse output JSONL. Expect at least one line for our custom_id.
    records: List[Dict[str, Any]] = []
    for raw_line in str(output_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            records.append(rec)

    custom_id = str(batch_state.get("custom_id") or "").strip()
    rec = next((r for r in records if str(r.get("custom_id") or "") == custom_id), None)
    if rec is None and records:
        rec = records[0]
    if rec is None:
        raise RuntimeError("Batch output file contained no JSONL records")

    resp = rec.get("response")
    if not isinstance(resp, dict):
        raise RuntimeError("Batch output record missing `response` object")
    status_code = int(resp.get("status_code") or 0)
    if status_code != 200:
        raise RuntimeError(f"Batch response status_code={status_code}")

    body = resp.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            pass

    out = _output_text_from_response_body(body)
    if not out:
        raise RuntimeError("Batch response body had no output text")

    parsed = json.loads(out)
    if isinstance(parsed, dict):
        items_out = parsed.get("items")
        if not isinstance(items_out, list):
            raise RuntimeError("Indexer JSON object output must contain an `items` array")
        artifacts = items_out
    elif isinstance(parsed, list):
        artifacts = parsed
    else:
        raise RuntimeError("Indexer output must be a JSON object with `items[]` or a JSON array")

    by_id: Dict[str, Dict[str, Any]] = {}
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        iid = str(art.get("interaction_id") or "").strip()
        if iid:
            by_id[iid] = art

    # Re-read the original candidate slice from the queue to compute exact byte advances.
    offset_start = _safe_int(batch_state.get("offset_start"), 0)
    planned_advance = _safe_int(batch_state.get("planned_advance_bytes"), 0)
    data, total = download_queue_tail(user_id, offset=offset_start)
    if planned_advance > 0 and planned_advance < len(data):
        data = data[:planned_advance]
    lines = _iter_jsonl_lines(data)

    submitted_ids = set(batch_state.get("submitted_interaction_ids") or [])
    advanced_bytes = 0
    indexed = 0
    skipped_existing = 0
    missing = 0

    for line_len, line in lines:
        try:
            item = json.loads(line)
        except Exception:
            break
        if not isinstance(item, dict):
            advanced_bytes += line_len
            continue
        iid = str(item.get("interaction_id") or "").strip()
        if not iid:
            advanced_bytes += line_len
            continue

        # Items already indexed are safe to advance.
        if _semantic_exists(user_id, iid):
            skipped_existing += 1
            advanced_bytes += line_len
            continue

        # Items not submitted to the model should never appear (but are safe to advance only if already indexed).
        if iid not in submitted_ids:
            # Stop: we cannot safely advance beyond an unsubmitted, unindexed item.
            break

        art = by_id.get(iid)
        if art is None:
            missing += 1
            break
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

    # Advance the main state cursor only after successful ingestion.
    state = load_indexer_state(user_id)
    state["byte_offset"] = offset_start + advanced_bytes
    state["first_pending_at_utc"] = None
    save_indexer_state(user_id, state)
    _clear_batch_state(user_id)

    return {
        "status": "batch_ingested",
        "user_id": user_id,
        "indexed": indexed,
        "skipped_existing": skipped_existing,
        "missing_outputs": missing,
        "advanced_bytes": advanced_bytes,
        "byte_offset": state.get("byte_offset", offset_start),
        "queue_size_bytes": total,
        "planned_advance_bytes": planned_advance,
    }


def _resync_offset_to_newline(user_id: str, *, offset: int, lookback: int = 8192) -> int:
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
    per_item = _safe_int(os.environ.get("WP7_MAX_OUTPUT_TOKENS_PER_ITEM"), 180)
    max_output_tokens = max(256, min(4096, 128 + (max(1, len(items)) * max(60, per_item))))
    resp = openai_client.responses.create(
        prompt={"id": prompt_id},
        input=input_text,
        tool_choice="none",
        parallel_tool_calls=False,
        max_output_tokens=max_output_tokens,
        metadata={"runtime": "wp7_indexer_timer"},
    )
    output = getattr(resp, "output_text", None) or ""
    if not output:
        raise RuntimeError("Indexer returned empty output_text")
    parsed = json.loads(output)
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


def _thresholds_from_env() -> QueueThresholds:
    return QueueThresholds(
        target_tokens=_safe_int(os.environ.get("WP7_TARGET_BATCH_TOKENS"), 1000),
        hard_min_tokens=_safe_int(os.environ.get("WP7_HARD_MIN_BATCH_TOKENS"), 600),
        max_wait_seconds=_safe_int(os.environ.get("WP7_MAX_WAIT_SECONDS"), 300),
        max_items_per_run=_safe_int(os.environ.get("WP7_MAX_ITEMS_PER_RUN"), 25),
        max_user_chars=_safe_int(os.environ.get("WP7_MAX_USER_CHARS"), 2000),
        max_assistant_chars=_safe_int(os.environ.get("WP7_MAX_ASSISTANT_CHARS"), 4000),
    )


def _run_for_user(openai_client: OpenAI, prompt_id: str, user_id: str, thresholds: QueueThresholds) -> Dict[str, Any]:
    mode = _wp7_mode()
    logging.info(f"WP7: tick user_id={user_id} mode={mode}")
    if mode == "batch":
        bs = _load_batch_state(user_id)
        if _is_active_batch_state(bs):
            batch_id = str(bs.get("batch_id") or "").strip()
            logging.info(f"WP7: batch_poll user_id={user_id} batch_id={batch_id}")
            try:
                batch = openai_client.batches.retrieve(batch_id)
            except Exception as e:
                logging.warning(f"WP7 batch poll failed user_id={user_id} batch_id={batch_id}: {e}")
                return {"status": "batch_poll_failed", "user_id": user_id, "batch_id": batch_id}

            status = str(getattr(batch, "status", None) or "").strip().lower()
            bs["status"] = status or bs.get("status") or "submitted"
            bs["last_polled_at_utc"] = utc_now_iso()
            _save_batch_state(user_id, bs)
            logging.info(f"WP7: batch_poll_done user_id={user_id} batch_id={batch_id} status={status}")

            if status != "completed":
                if status in ("failed", "expired", "canceled"):
                    logging.error(f"WP7 batch ended status={status} user_id={user_id} batch_id={batch_id}")
                    _clear_batch_state(user_id)
                    # Do not advance cursor; allow the next tick to re-submit.
                    return {"status": "batch_failed", "user_id": user_id, "batch_id": batch_id, "batch_status": status}
                return {"status": "batch_waiting", "user_id": user_id, "batch_id": batch_id, "batch_status": status}

            output_file_id = str(getattr(batch, "output_file_id", None) or "").strip()
            if not output_file_id:
                logging.error(f"WP7 batch completed but missing output_file_id user_id={user_id} batch_id={batch_id}")
                return {"status": "batch_missing_output_file", "user_id": user_id, "batch_id": batch_id}

            try:
                logging.info(f"WP7: batch_completed user_id={user_id} batch_id={batch_id} output_file_id={output_file_id}")
                logging.info(
                    f"WP7: batch_ingest_start user_id={user_id} batch_id={batch_id} output_file_id={output_file_id}"
                )
                out_text = _download_openai_file_text(openai_client, output_file_id)
                result = _ingest_batch_output(
                    openai_client,
                    user_id=user_id,
                    batch_state=bs,
                    output_text=out_text,
                )
                logging.info(
                    "WP7: batch_ingest_done user_id=%s batch_id=%s indexed=%s skipped=%s missing=%s advanced_bytes=%s byte_offset=%s",
                    user_id,
                    batch_id,
                    result.get("indexed"),
                    result.get("skipped_existing"),
                    result.get("missing_outputs"),
                    result.get("advanced_bytes"),
                    result.get("byte_offset"),
                )
                return result
            except Exception as e:
                logging.error(f"WP7 batch ingest failed user_id={user_id} batch_id={batch_id}: {e}")
                _clear_batch_state(user_id)
                return {"status": "batch_ingest_failed", "user_id": user_id, "batch_id": batch_id, "error": str(e)}

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
        if 0 < offset < total:
            new_offset = _resync_offset_to_newline(user_id, offset=offset)
            if new_offset != offset:
                logging.warning(f"WP7 resync offset to newline user_id={user_id} old={offset} new={new_offset} total={total}")
                offset = new_offset
                state["byte_offset"] = offset
                data, total = download_queue_tail(user_id, offset=offset)
                lines = _iter_jsonl_lines(data)

    if not lines:
        state["first_pending_at_utc"] = None
        save_indexer_state(user_id, state)
        logging.info(f"WP7: idle user_id={user_id} mode={mode} queue_size_bytes={total} byte_offset={offset}")
        return {"status": "idle", "user_id": user_id, "byte_offset": offset, "queue_size_bytes": total}

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

    should_run = token_sum >= thresholds.target_tokens or (
        elapsed_s >= thresholds.max_wait_seconds and token_sum >= thresholds.hard_min_tokens
    )
    logging.info(
        "WP7: queue_check user_id=%s mode=%s queue_size_bytes=%s byte_offset=%s candidates=%s tokens_sum=%s elapsed_s=%s should_run=%s",
        user_id,
        mode,
        total,
        offset,
        len(candidates),
        token_sum,
        elapsed_s,
        should_run,
    )
    if not should_run:
        save_indexer_state(user_id, state)
        return {
            "status": "waiting",
            "user_id": user_id,
            "byte_offset": offset,
            "queue_size_bytes": total,
            "candidate_items": len(candidates),
            "tokens_sum": token_sum,
            "elapsed_seconds": elapsed_s,
        }

    batch_items: List[Dict[str, Any]] = [it for _, it in candidates if not it.get("_skip")]

    if mode == "batch":
        candidate_ids: List[str] = []
        submitted_ids: List[str] = []
        planned_advance = 0
        for line_len, item in candidates:
            planned_advance += line_len
            iid = str(item.get("interaction_id") or "").strip()
            if iid:
                candidate_ids.append(iid)
            if not item.get("_skip") and iid:
                submitted_ids.append(iid)
        logging.info(
            "WP7: batch_submit user_id=%s candidates=%s submitted=%s tokens_sum=%s planned_advance_bytes=%s",
            user_id,
            len(candidate_ids),
            len(submitted_ids),
            token_sum,
            planned_advance,
        )
        return _submit_openai_batch(
            openai_client,
            prompt_id=prompt_id,
            user_id=user_id,
            batch_items=batch_items,
            offset_start=offset,
            candidates_count=len(candidates),
            submitted_ids=submitted_ids,
            candidate_ids=candidate_ids,
            planned_advance_bytes=planned_advance,
        )

    artifacts = _call_indexer_model(openai_client, prompt_id, batch_items)

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
            missing += 1
            break
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

    if advanced_bytes > 0:
        state["byte_offset"] = offset + advanced_bytes
        state["first_pending_at_utc"] = None
    save_indexer_state(user_id, state)
    logging.info(
        "WP7: sync_done user_id=%s indexed=%s skipped=%s missing=%s advanced_bytes=%s byte_offset=%s",
        user_id,
        indexed,
        skipped,
        missing,
        advanced_bytes,
        state.get("byte_offset", offset),
    )

    return {
        "status": "ok",
        "user_id": user_id,
        "indexed": indexed,
        "skipped_existing": skipped,
        "missing_outputs": missing,
        "advanced_bytes": advanced_bytes,
        "byte_offset": state.get("byte_offset", offset),
        "queue_size_bytes": total,
        "tokens_sum": token_sum,
    }


def main(timer: func.TimerRequest) -> None:
    user_ids_env = str(os.environ.get("WP7_INDEXER_USER_IDS", "default") or "").strip()
    if user_ids_env.lower() in ("auto", "*"):
        user_ids = _discover_user_ids_with_queue()
        if not user_ids:
            # No queues present; avoid doing any work.
            logging.info("WP7: timer_start user_ids=none (auto)")
            return
    else:
        user_ids = [u.strip() for u in user_ids_env.split(",") if u.strip()]
        if not user_ids:
            user_ids = ["default"]

    prompt_id = os.environ.get("OPENAI_INDEXER_PROMPT_ID", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if not (prompt_id and openai_key):
        logging.warning("WP7 indexer timer disabled (missing OPENAI_INDEXER_PROMPT_ID or OPENAI_API_KEY)")
        return

    thresholds = _thresholds_from_env()
    openai_client = OpenAI(api_key=openai_key)
    logging.info(
        "WP7: timer_start user_ids=%s mode=%s target_tokens=%s hard_min_tokens=%s max_wait_s=%s max_items=%s",
        ",".join(user_ids),
        _wp7_mode(),
        thresholds.target_tokens,
        thresholds.hard_min_tokens,
        thresholds.max_wait_seconds,
        thresholds.max_items_per_run,
    )

    for user_id in user_ids:
        try:
            result = _run_for_user(openai_client, prompt_id, user_id, thresholds)
            logging.info(f"WP7 indexer tick: {json.dumps(result, ensure_ascii=False)}")
        except AzureError as e:
            logging.error(f"WP7 indexer tick AzureError user_id={user_id}: {e}")
        except Exception as e:
            logging.error(f"WP7 indexer tick error user_id={user_id}: {e}")
