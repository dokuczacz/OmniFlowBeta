import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_env_from_local_settings(repo_root: Path) -> None:
    path = repo_root / "backend" / "local.settings.json"
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    values = (data.get("Values") or {}) if isinstance(data, dict) else {}
    if not isinstance(values, dict):
        return
    for k, v in values.items():
        if k and k not in os.environ and v is not None:
            os.environ[k] = str(v)


def _download_jsonl_lines(user_id: str, blob_name: str) -> List[Dict[str, Any]]:
    from backend.shared.azure_client import AzureBlobClient

    bc = AzureBlobClient.get_blob_client(blob_name, user_id=user_id)
    text = bc.download_blob().content_as_text(encoding="utf-8")
    out: List[Dict[str, Any]] = []
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def _semantic_rel_path(index_entry: Dict[str, Any], interaction_id: str) -> str:
    p = str((index_entry or {}).get("semantic_blob_path") or "").strip()
    if p.startswith("users/"):
        parts = p.split("/", 2)
        if len(parts) >= 3:
            return parts[2]
    return f"interactions/semantic/{interaction_id}.json"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in os.sys.path:
        os.sys.path.insert(0, str(repo_root))

    _load_env_from_local_settings(repo_root)

    parser = argparse.ArgumentParser(description="Prepare WP7 audit input: 50 index entries + 50 artifacts.")
    parser.add_argument("--user-id", default="MarioBros")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--out", default="tools/out/wp7_audit_input_MarioBros_50_50.json")
    args = parser.parse_args()

    from backend.shared.azure_client import AzureBlobClient

    user_id = str(args.user_id)
    count = max(1, int(args.count))

    entries = _download_jsonl_lines(user_id, "interactions/semantic/index.jsonl")

    # Select most recent unique interaction_ids.
    seen = set()
    selected: List[Dict[str, Any]] = []
    for e in reversed(entries):
        iid = str((e or {}).get("interaction_id") or "").strip()
        if not iid or iid in seen:
            continue
        seen.add(iid)
        selected.append(e)
        if len(selected) >= count * 2:
            break
    selected = list(reversed(selected))

    kept_entries: List[Dict[str, Any]] = []
    artifacts: List[Dict[str, Any]] = []

    for e in selected:
        iid = str((e or {}).get("interaction_id") or "").strip()
        if not iid:
            continue
        rel = _semantic_rel_path(e, iid)
        try:
            bc = AzureBlobClient.get_blob_client(rel, user_id=user_id)
            atext = bc.download_blob().content_as_text(encoding="utf-8")
            art = json.loads(atext)
        except Exception:
            continue
        kept_entries.append(e)
        artifacts.append(art)
        if len(kept_entries) >= count:
            break

    out_obj = {
        "run_id": f"wp7_audit_input::{user_id}::{count}_{count}",
        "index_entries": kept_entries,
        "artifacts": artifacts,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print("user_id", user_id)
    print("index_entries", len(kept_entries))
    print("artifacts", len(artifacts))
    print("out", out_path.as_posix())

    if len(kept_entries) < 50 or len(artifacts) < 50:
        raise SystemExit("Insufficient evidence: expected >=50 index_entries and >=50 artifacts")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

