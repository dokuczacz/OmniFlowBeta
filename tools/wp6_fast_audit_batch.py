import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_local_settings(repo_root: Path) -> Dict[str, Any]:
    path = repo_root / "backend" / "local.settings.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ensure_env_from_local_settings(repo_root: Path) -> None:
    data = _load_local_settings(repo_root)
    values = data.get("Values") if isinstance(data, dict) else None
    if not isinstance(values, dict):
        return
    for k, v in values.items():
        if k and k not in os.environ and v is not None:
            os.environ[k] = str(v)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_batch_output_jsonl(text: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw_line": line})
    return out


def _download_openai_file_text(client: OpenAI, file_id: str) -> str:
    # OpenAI SDK returns a binary-like object for files content.
    content = client.files.content(file_id)
    try:
        data = content.read()
    except Exception:
        data = bytes(content)
    try:
        return data.decode("utf-8", errors="replace")
    except Exception:
        return str(data)


def _make_audit_request(prompt_id: str, payload: Dict[str, Any], *, custom_id: str) -> Dict[str, Any]:
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/responses",
        "body": {
            "prompt": {"id": prompt_id},
            "input": json.dumps(payload, ensure_ascii=False),
            "max_output_tokens": 1200,
            "metadata": {"runtime": "wp6_fast_audit", "custom_id": custom_id},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-audit WP6 FAST packs and outputs (reads wp6_fast_audit blobs; submits OpenAI Batch)."
    )
    parser.add_argument("--user-id", required=True, help="User namespace (users/{user_id}/...).")
    parser.add_argument("--count", type=int, default=10, help="How many recent FAST audits to include (pairs in/out).")
    parser.add_argument(
        "--prompt-id",
        default=(os.getenv("OPENAI_WP6_AUDIT_PROMPT_ID") or "").strip(),
        help="Auditor prompt id (pmpt_...). Default: env OPENAI_WP6_AUDIT_PROMPT_ID.",
    )
    parser.add_argument(
        "--prefix",
        default="semantics/wp6_fast_audit/",
        help="Blob prefix under user namespace.",
    )
    parser.add_argument("--completion-window", default="24h", help="Batch completion window, e.g. 24h.")
    parser.add_argument("--wait", action="store_true", help="Wait for batch completion and print results.")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--out", default="", help="Optional path to write combined results JSON.")
    args = parser.parse_args()

    repo_root = _repo_root()
    _ensure_env_from_local_settings(repo_root)

    if not args.prompt_id:
        raise SystemExit("Missing --prompt-id (or set OPENAI_WP6_AUDIT_PROMPT_ID).")
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        raise SystemExit("Missing OPENAI_API_KEY (env or backend/local.settings.json).")

    # Import backend shared Azure client after env is hydrated.
    os.environ.setdefault("PYTHONPATH", "backend")
    import sys

    sys.path.append(str(repo_root / "backend"))
    from shared.azure_client import AzureBlobClient

    user_id = str(args.user_id).strip()
    prefix = str(args.prefix or "").strip()
    blob_names = AzureBlobClient.list_user_blobs(user_id, prefix=prefix)

    # Pick most recent audit pairs by filename (timestamp prefix in name).
    in_files = sorted([b for b in blob_names if "_fast_in_" in b], reverse=True)[: max(1, int(args.count))]
    audit_ids: List[str] = []
    for name in in_files:
        # name: semantics/wp6_fast_audit/<thread>/YYYYmmdd_HHMMSS_<audit_id>_fast_in_<suffix>.json
        parts = Path(name).name.split("_")
        if len(parts) >= 4:
            audit_ids.append(parts[2])

    selected: List[str] = []
    for aid in audit_ids:
        selected.extend([b for b in blob_names if f"_{aid}_fast_in_" in b])
        selected.extend([b for b in blob_names if f"_{aid}_fast_out_" in b])
    selected = sorted(list(dict.fromkeys(selected)), reverse=True)

    payloads: List[Tuple[str, Dict[str, Any]]] = []
    for blob in selected:
        bc = AzureBlobClient.get_blob_client(blob, user_id)
        raw = bc.download_blob().readall()
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception:
            obj = {"raw": raw.decode("utf-8", errors="replace")}
        payloads.append((blob, obj if isinstance(obj, dict) else {"data": obj}))

    # Build 1 request per audit JSON blob (user wanted ~20 JSONs => ~20 responses).
    requests_jsonl: List[Dict[str, Any]] = []
    for blob, obj in payloads:
        custom_id = f"wp6_fast_audit::{Path(blob).name}"
        requests_jsonl.append(
            _make_audit_request(
                args.prompt_id,
                {
                    "schema_version": "omniflow.wp6.audit_request.v1",
                    "blob_path": blob,
                    "audit_payload": obj,
                    "requested_at_utc": _utc_now_iso(),
                },
                custom_id=custom_id,
            )
        )

    client = OpenAI(api_key=(os.getenv("OPENAI_API_KEY") or "").strip())
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".jsonl") as f:
        for req in requests_jsonl:
            f.write(json.dumps(req, ensure_ascii=False) + "\n")
        jsonl_path = f.name

    try:
        uploaded = client.files.create(file=open(jsonl_path, "rb"), purpose="batch")
        batch = client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/responses",
            completion_window=str(args.completion_window),
            metadata={"runtime": "wp6_fast_audit", "user_id": user_id},
        )
        print(json.dumps({"status": "submitted", "batch_id": batch.id, "input_file_id": uploaded.id}, ensure_ascii=False))

        if not args.wait:
            return 0

        while True:
            b = client.batches.retrieve(batch.id)
            status = str(getattr(b, "status", "") or "")
            print(json.dumps({"status": status, "batch_id": batch.id}, ensure_ascii=False))
            if status in ("completed", "failed", "expired", "canceled"):
                break
            time.sleep(max(1, int(args.poll_seconds)))

        output_file_id = str(getattr(b, "output_file_id", "") or "").strip()
        if not output_file_id:
            print(json.dumps({"status": "done", "batch_id": batch.id, "batch_status": status}, ensure_ascii=False))
            return 0

        out_text = _download_openai_file_text(client, output_file_id)
        parsed = _parse_batch_output_jsonl(out_text)

        bundle = {
            "status": "completed",
            "batch_id": batch.id,
            "batch_status": status,
            "output_file_id": output_file_id,
            "items_submitted": len(requests_jsonl),
            "results": parsed,
        }
        if args.out:
            Path(args.out).write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0
    finally:
        try:
            os.unlink(jsonl_path)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

