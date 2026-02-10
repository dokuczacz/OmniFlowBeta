"""
E2E PA verification (live OpenAI, no mock agent).

Focus:
- TM: must persist to TM.json (not just a text claim).
- Gmail: must call gmail_action and persist intent artifact under semantics/intents/.

Design:
- For prod, do NOT require local Azure Storage credentials. We validate persisted artifacts by
  calling the backend's read-only `tool_exec` action (read_blob_file, list_blobs).
- This script prints only non-secret signals.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import urllib.error
import urllib.request


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_dt(value: str) -> Optional[datetime]:
    v = str(value or "").strip()
    if not v:
        return None
    try:
        # stored timestamp is often naive isoformat from datetime.utcnow(); treat as UTC.
        if v.endswith("Z"):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


@dataclass
class EnvCfg:
    name: str
    tool_handler_url: str
    function_key: str


def http_post_json(url: str, payload: Dict[str, Any], *, headers: Dict[str, str], timeout_s: int = 180) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"_non_json": True, "raw_excerpt": raw[:400]}
    except urllib.error.HTTPError as e:
        raw = (e.read() or b"").decode("utf-8", "replace")
        try:
            return int(e.code), json.loads(raw)
        except Exception:
            return int(e.code), {"_non_json": True, "raw_excerpt": raw[:400]}


def _headers(cfg: EnvCfg) -> Dict[str, str]:
    h = {"Content-Type": "application/json"}
    if cfg.function_key:
        h["x-functions-key"] = cfg.function_key
    return h


def tool_exec(cfg: EnvCfg, user_id: str, *, tool_name: str, tool_arguments: Dict[str, Any], timeout_s: int = 180) -> Dict[str, Any]:
    status, body = http_post_json(
        cfg.tool_handler_url,
        {
            "user_id": user_id,
            "action": "tool_exec",
            "params": {
                "confirm": True,
                "tool_name": tool_name,
                "tool_arguments": tool_arguments,
            },
            "log_interaction": False,
        },
        headers=_headers(cfg),
        timeout_s=timeout_s,
    )
    if status != 200:
        raise RuntimeError(f"tool_exec_failed tool={tool_name} status={status} body={body}")
    if not isinstance(body, dict) or body.get("status") != "success":
        raise RuntimeError(f"tool_exec_unexpected tool={tool_name} body={body}")
    return body


def read_blob_json(cfg: EnvCfg, user_id: str, file_name: str) -> Dict[str, Any]:
    body = tool_exec(cfg, user_id, tool_name="read_blob_file", tool_arguments={"file_name": file_name}, timeout_s=180)
    res = body.get("result")
    if isinstance(res, dict):
        return res
    if isinstance(res, str):
        j = json.loads(res)
        return j if isinstance(j, dict) else {"_non_dict": True}
    # Fallback: attempt parse from excerpt
    raw = str(body.get("result_excerpt") or "")
    j2 = json.loads(raw)
    return j2 if isinstance(j2, dict) else {"_non_dict": True}


def list_blobs_meta(cfg: EnvCfg, user_id: str, *, prefix: str) -> List[Dict[str, Any]]:
    body = tool_exec(cfg, user_id, tool_name="list_blobs", tool_arguments={"prefix": prefix, "include_meta": True}, timeout_s=180)
    res = body.get("result")
    if not isinstance(res, dict):
        return []
    blobs_meta = res.get("blobs_meta")
    if not isinstance(blobs_meta, list):
        return []
    out = [x for x in blobs_meta if isinstance(x, dict) and x.get("name")]
    out.sort(key=lambda x: str(x.get("last_modified") or ""))
    return out


def ensure_pa_init(cfg: EnvCfg, *, user_id: str, thread_id: str) -> None:
    status, body = http_post_json(
        cfg.tool_handler_url,
        {"action": "pa_init", "user_id": user_id, "thread_id": thread_id, "params": {"confirm_create": True}},
        headers=_headers(cfg),
        timeout_s=60,
    )
    if status != 200:
        raise RuntimeError(f"pa_init_failed status={status} body={body}")


def assert_has_tool_call(body: Dict[str, Any]) -> None:
    count = int(body.get("tool_calls_count") or 0)
    if count <= 0:
        raise AssertionError(f"expected tool calls, got tool_calls_count={count}")


def assert_interaction_has_tools(entry: Dict[str, Any], expected_any: List[str]) -> None:
    tools = entry.get("tool_calls") or []
    names = []
    for t in tools:
        if isinstance(t, dict) and t.get("tool_name"):
            names.append(str(t.get("tool_name") or ""))
        elif isinstance(t, dict) and t.get("name"):
            names.append(str(t.get("name") or ""))
    names = [n for n in names if n]
    if not names:
        raise AssertionError("interaction entry contains no tool_calls")
    if not any(n in expected_any for n in names):
        raise AssertionError(f"expected one of tools={expected_any}, got={sorted(set(names))}")


def find_latest_interaction_entry(cfg: EnvCfg, user_id: str, thread_id: str, *, since_iso: str, max_scan: int = 30) -> Optional[Dict[str, Any]]:
    since_dt = _parse_dt(since_iso) or datetime.min.replace(tzinfo=timezone.utc)
    metas = list_blobs_meta(cfg, user_id, prefix="interactions/")
    # Scan newest first.
    metas = list(reversed(metas))[: int(max_scan or 30)]
    for m in metas:
        name = str(m.get("name") or "").strip()
        if not name.endswith(".json"):
            continue
        try:
            entry = read_blob_json(cfg, user_id, name)
        except Exception:
            continue
        if str(entry.get("thread_id") or "") != str(thread_id):
            continue
        ts = _parse_dt(str(entry.get("timestamp") or "")) or since_dt
        if ts < since_dt:
            continue
        return entry
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["local", "prod"], required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--tool-handler-url", default="")
    args = ap.parse_args()

    if args.env == "local":
        cfg = EnvCfg(
            name="local",
            tool_handler_url=args.tool_handler_url or "http://localhost:7071/api/tool_call_handler",
            function_key="",
        )
    else:
        tool_url = args.tool_handler_url or (os.environ.get("OMNIFLOW_BACKEND_URL_PROD") or "").strip()
        if not tool_url:
            tool_url = "https://agentbackendservice-dfcpcudzeah4b6ae.northeurope-01.azurewebsites.net/api/tool_call_handler"
        key = (os.environ.get("OMNIFLOW_AZFUNC_FUNCTION_KEY") or "").strip()
        if not key:
            raise SystemExit("Missing env: OMNIFLOW_AZFUNC_FUNCTION_KEY (prod function key)")
        cfg = EnvCfg(name="prod", tool_handler_url=tool_url, function_key=key)

    user_id = str(args.user)
    thread_id = f"e2e_{cfg.name}_{uuid.uuid4().hex[:8]}"
    start_iso = utc_now_iso()

    # Precondition: PA initialized (explicit confirmation).
    ensure_pa_init(cfg, user_id=user_id, thread_id=thread_id)

    # --- TM E2E ---
    tm_before = read_blob_json(cfg, user_id, "TM.json")
    before_n = len(tm_before.get("items") or [])

    status, body = http_post_json(
        cfg.tool_handler_url,
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "message": (
                "Dodaj zadanie do TM.json. Wymagane: uzyj narzedzia add_new_data "
                "z target_blob_name='TM.json' i new_entry zawierajacym co najmniej title='E2E: Kup mleko' "
                "oraz status='open'. Potem potwierdz."
            ),
        },
        headers=_headers(cfg),
        timeout_s=240,
    )
    if status != 200:
        raise RuntimeError(f"tm_add_failed status={status} body={body}")
    assert_has_tool_call(body)

    time.sleep(1.0)
    tm_after = read_blob_json(cfg, user_id, "TM.json")
    after_n = len(tm_after.get("items") or [])
    if after_n <= before_n:
        raise AssertionError(f"TM.json not updated: before_items={before_n} after_items={after_n}")

    entry_tm = find_latest_interaction_entry(cfg, user_id, thread_id, since_iso=start_iso)
    if not entry_tm:
        raise AssertionError("could not locate TM interaction entry")
    assert_interaction_has_tools(entry_tm, expected_any=["add_new_data", "update_data_entry", "upload_data_or_file"])
    meta_tm = entry_tm.get("metadata") or {}
    if not isinstance(meta_tm, dict) or not meta_tm.get("prompt_id"):
        raise AssertionError("missing prompt_id in interaction metadata (provenance logging)")

    # --- Gmail E2E (requires already-authorized token) ---
    intents_before = list_blobs_meta(cfg, user_id, prefix="semantics/intents/")
    status, body = http_post_json(
        cfg.tool_handler_url,
        {
            "user_id": user_id,
            "thread_id": thread_id,
            "message": (
                "Sprawdz Gmail INBOX: najpierw uzyj gmail_action oauth_status. "
                "Jesli authorized=true, uzyj gmail_action gmail_list max_results=3 label=INBOX, "
                "potem podaj 3 ostatnie wiadomosci (nadawca+temat)."
            ),
        },
        headers=_headers(cfg),
        timeout_s=300,
    )
    if status != 200:
        raise RuntimeError(f"gmail_failed status={status} body={body}")
    assert_has_tool_call(body)

    time.sleep(1.0)
    intents_after = list_blobs_meta(cfg, user_id, prefix="semantics/intents/")
    if len(intents_after) <= len(intents_before):
        raise AssertionError("Expected a new intent artifact under semantics/intents/, but count did not increase.")

    # Validate latest intent contract v2 contains PA architecture fields.
    latest_intent_name = str((intents_after[-1] or {}).get("name") or "").strip()
    if latest_intent_name:
        intent_art = read_blob_json(cfg, user_id, latest_intent_name)
        if str(intent_art.get("schema_version") or "") != "omniflow.pa.intention.v2":
            raise AssertionError(f"unexpected intent schema_version={intent_art.get('schema_version')}")
        intent_payload = intent_art.get("intention") if isinstance(intent_art.get("intention"), dict) else {}
        for k in (
            "pa_function_id",
            "pa_function_name",
            "target_artifacts",
            "required_tools",
            "intent",
            "requires_internet",
        ):
            if k not in intent_payload:
                raise AssertionError(f"missing field in intent payload: {k}")

    entry_g = find_latest_interaction_entry(cfg, user_id, thread_id, since_iso=start_iso)
    if not entry_g:
        raise AssertionError("could not locate Gmail interaction entry")
    assert_interaction_has_tools(entry_g, expected_any=["gmail_action"])

    print(
        json.dumps(
            {
                "status": "ok",
                "env": cfg.name,
                "user_id": user_id,
                "thread_id": thread_id,
                "started_utc": start_iso,
                "tm_items_before": before_n,
                "tm_items_after": after_n,
                "intent_artifacts_before": len(intents_before),
                "intent_artifacts_after": len(intents_after),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

