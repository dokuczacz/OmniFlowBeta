from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_RE_CATEGORY = re.compile(r"CATEGORY:\s*([A-Z]{2,4})\b")
_RE_USER_HEADER = re.compile(r"USER INPUT\b")
_RE_GPT_HEADER = re.compile(r"GPT RESPONSE\b")
_RE_TAGS = re.compile(r"TAGS\]\s*(.*)$")
_RE_ID = re.compile(r"\b([A-Z]{2,4}\.\d+\.\d{6,})\b")

_RE_TS = re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?Z?\b")
_RE_LONG_NUM = re.compile(r"\b\d{6,}\b")
_RE_ID_INLINE = re.compile(r"\b[A-Z]{2,4}\.\d+\.\d+\b")
_RE_NON_WORD = re.compile(r"[^a-z0-9]+")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_intent(text: str) -> str:
    s = (text or "").strip().lower()
    s = _RE_TS.sub(" ", s)
    s = _RE_ID_INLINE.sub(" ", s)
    s = _RE_LONG_NUM.sub(" ", s)
    s = _RE_NON_WORD.sub(" ", s)
    return " ".join(s.split())


@dataclass
class Entry:
    category: str = ""
    user_input: str = ""
    gpt_response: str = ""
    tags: list[str] = field(default_factory=list)
    entry_id: str = ""


def parse_pa_v2_text(text: str) -> list[Entry]:
    entries: list[Entry] = []
    current: Entry | None = None
    section: str | None = None  # "user" | "gpt" | None

    def flush() -> None:
        nonlocal current, section
        if current is None:
            return
        current.user_input = current.user_input.strip()
        current.gpt_response = current.gpt_response.strip()
        current.tags = [t for t in (t.strip() for t in current.tags) if t]
        if current.category and (current.user_input or current.gpt_response):
            entries.append(current)
        current = None
        section = None

    for raw in text.splitlines():
        line = raw.rstrip("\n")

        m_cat = _RE_CATEGORY.search(line)
        if m_cat:
            flush()
            current = Entry(category=m_cat.group(1))
            continue

        if current is None:
            continue

        if _RE_USER_HEADER.search(line):
            section = "user"
            continue
        if _RE_GPT_HEADER.search(line):
            section = "gpt"
            continue

        m_tags = _RE_TAGS.search(line)
        if m_tags:
            tags_raw = (m_tags.group(1) or "").strip()
            if tags_raw:
                current.tags.extend([t.strip() for t in tags_raw.split(",")])
            continue

        m_id = _RE_ID.search(line)
        if m_id and not current.entry_id:
            current.entry_id = m_id.group(1)
            continue

        if not line.strip():
            continue

        if section == "user":
            current.user_input += (line.strip() + "\n")
        elif section == "gpt":
            current.gpt_response += (line.strip() + "\n")

    flush()
    return entries


def build_minbase(
    entries: list[Entry],
    *,
    source_name: str,
    max_source_ids: int,
    include_provenance: bool,
    include_hashes: bool,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for e in entries:
        intent_norm = normalize_intent(e.user_input)
        key = (e.category, intent_norm)
        bucket = grouped.get(key)
        if bucket is None:
            bucket = {
                "schema": "pa_minbase_v1",
                "created_at": _utc_now_iso(),
                "category": e.category,
                "intent_norm": intent_norm,
                "user_input_template": e.user_input.strip(),
                "response_template": e.gpt_response.strip(),
                "tags": set(e.tags),
            }
            if include_hashes:
                bucket["intent_hash"] = _sha256_hex(f"{e.category}:{intent_norm}")
            if include_provenance:
                bucket["source"] = {
                    "source_name": source_name,
                    "source_entry_ids": [],
                    "source_count": 0,
                }
            grouped[key] = bucket

        bucket["tags"].update(e.tags)
        if include_provenance:
            bucket["source"]["source_count"] += 1
            if e.entry_id and len(bucket["source"]["source_entry_ids"]) < max_source_ids:
                bucket["source"]["source_entry_ids"].append(e.entry_id)

    out: list[dict[str, Any]] = []
    for bucket in grouped.values():
        bucket["tags"] = sorted(bucket["tags"])
        out.append(bucket)

    out.sort(key=lambda x: (x["category"], x["intent_norm"]))
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract a minimal semantic base from PA_DB v2 category files.")
    p.add_argument("--input", required=True, help="Path to pa_*_clean_entries_v2.txt")
    p.add_argument("--output", required=True, help="Output JSONL path (repo-relative or absolute).")
    p.add_argument("--max-source-ids", type=int, default=10, help="Max source IDs to keep per archetype.")
    p.add_argument(
        "--include-provenance",
        action="store_true",
        help="Include provenance fields (source_name, source_entry_ids, source_count).",
    )
    p.add_argument(
        "--include-hashes",
        action="store_true",
        help="Include deterministic intent_hash field (useful as stable ID).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()

    text = input_path.read_text(encoding="utf-8", errors="replace")
    entries = parse_pa_v2_text(text)
    minbase = build_minbase(
        entries,
        source_name=str(input_path),
        max_source_ids=int(args.max_source_ids),
        include_provenance=bool(args.include_provenance),
        include_hashes=bool(args.include_hashes),
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        for obj in minbase:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")

    print(json.dumps({"input": str(input_path), "entries": len(entries), "archetypes": len(minbase), "output": str(output_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
