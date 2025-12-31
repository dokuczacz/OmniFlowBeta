#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict

from local_jsonl_store import append_jsonl_line
from schema_v1 import ReportEntryInputV1, ReportEntryV1


DEFAULT_REPORTS_PATH = os.path.join(os.path.dirname(__file__), "reports.jsonl")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append a strict WP9 report entry to a local JSONL file.")
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_REPORTS_PATH,
        help="Target JSONL file path (default: docs/workflow/wp9_reporting/reports.jsonl).",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to a JSON file matching ReportEntryInputV1 (strict).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the JSONL line without saving.")
    return parser.parse_args()


def load_input(path: str) -> Dict[str, Any]:
    # Accept UTF-8 BOM (common on Windows) to avoid breaking deterministic tooling.
    with open(path, "r", encoding="utf-8-sig") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("Input JSON must be an object.")
    return payload


def main() -> int:
    args = parse_args()
    raw = load_input(args.input)
    entry_input = ReportEntryInputV1.parse_obj(raw)
    entry = ReportEntryV1.from_input(entry_input)
    line = json.dumps(entry.dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    if args.dry_run:
        print(line)
        return 0

    append_jsonl_line(args.output, line)
    print(f"OK appended entry_id={entry.entry_id} to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
