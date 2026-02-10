"""
E2E PA verification (live OpenAI, no mock agent).

Focus:
- TM: must persist to TM.json (not just a text claim).
- Gmail: must call gmail_action and persist intent artifact under semantics/intents/.

This script is intentionally small and operator-friendly; it prints only non-secret signals.
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

import urllib.request
import urllib.error


AZURITE_CONN = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
    "TableEndpoint=http://127.0.0.1:10002/devstoreaccount1"
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class EnvCfg:
    name: str
    tool_handler_url: str
    function_key: str
    storage_conn: str
    container: str


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


def load_tm_from_storage(cfg: EnvCfg, user_id: str) -> Dict[str, Any]:
    from azure.storage.blob import BlobServiceClient  # type: ignore

    svc = BlobServiceClient.from_connection_string(cfg.storage_conn)
    container = svc.get_container_client(cfg.container)
    blob = container.get_blob_client(f"users/{user_id}/TM.json")
    raw = blob.download_blob().readall().decode("utf-8", "replace")
    return json.loads(raw)


def list_intent_artifacts(cfg: EnvCfg, user_id: str) -> List[Tuple[str, str]]:
    """Return (name,last_modified_iso) for semantics/intents/* for this user."""
    from azure.storage.blob import BlobServiceClient  # type: ignore

    svc = BlobServiceClient.from_connection_string(cfg.storage_conn)
    container = svc.get_container_client(cfg.container)
    out: List[Tuple[str, str]] = []
    prefix = f"users/{user_id}/semantics/intents/"
    for b in container.list_blobs(name_starts_with=prefix):
        lm = getattr(b, "last_modified", None)
        out.append((b.name, (lm.isoformat() if lm else "")))
    out.sort(key=lambda x: x[1])
    return out


def load_json_blob(cfg: EnvCfg, blob_name: str) -> Dict[str, Any]:
    raw = _blob_bytes(cfg, blob_name).decode("utf-8", "replace")
    j = json.loads(raw)
    return j if isinstance(j, dict) else {"_non_dict": True}


def _blob_bytes(cfg: EnvCfg, blob_name: str) -> bytes:
    from azure.storage.blob import BlobServiceClient  # type: ignore

    svc = BlobServiceClient.from_connection_string(cfg.storage_conn)
    container = svc.get_container_client(cfg.container)
    return container.get_blob_client(blob_name).download_blob().readall()


def latest_interaction_entry(cfg: EnvCfg, user_id: str, thread_id: str, *, since_iso: str) -> Optional[Dict[str, Any]]:
    """
    Find the latest interaction entry (full blob) for a thread since a given timestamp.
    Uses interactions/index.jsonl as the primary index.
    """
    idx_blob = f"users/{user_id}/interactions/index.jsonl"
    try:
        raw = _blob_bytes(cfg, idx_blob).decode("utf-8", "replace")
    except Exception:
        return None

    def ts_ok(ts: str) -> bool:
        try:
            # stored timestamp is naive isoformat from datetime.utcnow(); treat as UTC.
            a = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(since_iso).replace("Z", "+00:00"))
            return a >= b
        except Exception:
            return True

    best: Optional[Dict[str, Any]] = None
    for line in [ln for ln in raw.splitlines() if ln.strip()]:
        try:
            j = json.loads(line)
        except Exception:
            continue
        if str(j.get("thread_id") or "") != str(thread_id):
            continue
        if not ts_ok(str(j.get("timestamp") or "")):
            continue
        if best is None or str(j.get("timestamp") or "") >= str(best.get("timestamp") or ""):
            best = j

    if not best:
        return None
    storage_path = str(best.get("storage_path") or "")
    if not storage_path:
        return None
    try:
        full = json.loads(_blob_bytes(cfg, storage_path).decode("utf-8", "replace"))
        return full if isinstance(full, dict) else None
    except Exception:
        return None


def ensure_pa_init(cfg: EnvCfg, *, user_id: str, thread_id: str) -> None:
    headers = {"Content-Type": "application/json"}
    if cfg.function_key:
        headers["x-functions-key"] = cfg.function_key
    status, body = http_post_json(
        cfg.tool_handler_url,
        {"action": "pa_init", "user_id": user_id, "thread_id": thread_id, "params": {"confirm_create": True}},
        headers=headers,
        timeout_s=60,
    )
    if status != 200:
        raise RuntimeError(f"pa_init_failed status={status} body={body}")


def assert_has_tool_call(body: Dict[str, Any], tool_name: str) -> None:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=["local", "prod"], required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--tool-handler-url", default="")
    ap.add_argument("--container", default="agent-knowledge-base")
    args = ap.parse_args()

    if args.env == "local":
        cfg = EnvCfg(
            name="local",
            tool_handler_url=args.tool_handler_url or "http://localhost:7071/api/tool_call_handler",
            function_key="",
            storage_conn=AZURITE_CONN,
            container=args.container,
        )
    else:
        # For prod, prefer explicit env vars. Do not print secrets.
        tool_url = args.tool_handler_url or os.environ.get("OMNIFLOW_BACKEND_URL_PROD") or ""
        if not tool_url:
            tool_url = "https://agentbackendservice-dfcpcudzeah4b6ae.northeurope-01.azurewebsites.net/api/tool_call_handler"
        key = (os.environ.get("OMNIFLOW_AZFUNC_FUNCTION_KEY") or "").strip()
        if not key:
            raise SystemExit("Missing env: OMNIFLOW_AZFUNC_FUNCTION_KEY (prod function key)")
        storage_conn = (os.environ.get("AZURE_STORAGE_CONNECTION_STRING_PROD") or "").strip()
        if not storage_conn:
            raise SystemExit("Missing env: AZURE_STORAGE_CONNECTION_STRING_PROD (for artifact assertions)")
        cfg = EnvCfg(
            name="prod",
            tool_handler_url=tool_url,
            function_key=key,
            storage_conn=storage_conn,
            container=args.container,
        )

    user_id = str(args.user)
    thread_id = f"e2e_{cfg.name}_{uuid.uuid4().hex[:8]}"
    start_iso = utc_now_iso()

    headers = {"Content-Type": "application/json"}
    if cfg.function_key:
        headers["x-functions-key"] = cfg.function_key

    # Precondition: PA initialized (explicit confirmation).
    ensure_pa_init(cfg, user_id=user_id, thread_id=thread_id)

    # --- TM E2E ---
    tm_before = load_tm_from_storage(cfg, user_id)
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
        headers=headers,
    )
    if status != 200:
        raise RuntimeError(f"tm_add_failed status={status} body={body}")
    assert_has_tool_call(body, "add_new_data")

    # Give storage a moment (esp. prod).
    time.sleep(1.0)
    tm_after = load_tm_from_storage(cfg, user_id)
    after_n = len(tm_after.get("items") or [])
    if after_n <= before_n:
        raise AssertionError(f"TM.json not updated: before_items={before_n} after_items={after_n}")

    entry_tm = latest_interaction_entry(cfg, user_id, thread_id, since_iso=start_iso)
    if not entry_tm:
        raise AssertionError("could not locate TM interaction entry in interactions/index.jsonl")
    assert_interaction_has_tools(entry_tm, expected_any=["add_new_data", "update_data_entry", "upload_data_or_file"])
    meta_tm = entry_tm.get("metadata") or {}
    if not isinstance(meta_tm, dict) or not meta_tm.get("prompt_id"):
        raise AssertionError("missing prompt_id in interaction metadata (provenance logging)")

    # --- Gmail E2E (requires already-authorized token) ---
    intents_before = list_intent_artifacts(cfg, user_id)
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
        headers=headers,
        timeout_s=240,
    )
    if status != 200:
        raise RuntimeError(f"gmail_failed status={status} body={body}")
    assert_has_tool_call(body, "gmail_action")

    time.sleep(1.0)
    intents_after = list_intent_artifacts(cfg, user_id)
    if len(intents_after) <= len(intents_before):
        raise AssertionError("Expected a new intent artifact under semantics/intents/, but count did not increase.")

    # Validate intent contract v2 contains PA architecture fields.
    latest_intent = intents_after[-1][0] if intents_after else ""
    if latest_intent:
        intent_art = load_json_blob(cfg, latest_intent)
        if str(intent_art.get("schema_version") or "") != "omniflow.pa.intention.v2":
            raise AssertionError(f"unexpected intent schema_version={intent_payload.get('schema_version')}")
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

    entry_g = latest_interaction_entry(cfg, user_id, thread_id, since_iso=start_iso)
    if not entry_g:
        raise AssertionError("could not locate Gmail interaction entry in interactions/index.jsonl")
    assert_interaction_has_tools(entry_g, expected_any=["gmail_action"])

    print(json.dumps(
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
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
