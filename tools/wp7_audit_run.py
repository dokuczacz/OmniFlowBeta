import argparse
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

import requests


WP7_AUDIT_SYSTEM_PROMPT = """\
You are an auditor agent for OmniFlow WP7 (Semantic Indexer) quality.

Context (backend-aware):
- WP7 produces a semantic index JSONL at `interactions/semantic/index.jsonl` and semantic artifacts at `interactions/semantic/<interaction_id>.json`.
- WP6 FAST later reads candidates from the WP7 index, fetches artifacts, and selects top sources. If WP7 is noisy, duplicated, inconsistent, or poorly grounded to raw interactions, WP6 FAST loses coverage/top_sources quality.

Task:
Given an input JSON containing:
- `run_id`
- `index_entries` (>=50) taken from WP7 semantic index
- `artifacts` (>=50) corresponding semantic artifacts (full JSON)

Audit WP7 for:
1) Integrity (index<->artifact mapping correctness)
2) Schema/format consistency
3) Duplication/noise patterns (ticker/timer/heartbeat, near-duplicates)
4) Signal validity (does signal_level + confidence correlate with usefulness?)
5) Semantic usefulness for WP6 FAST (coverage/top_sources)

Rules:
- Output JSON only. No markdown. No extra text.
- If evidence is insufficient (counts < 50 or cannot map index_entries to artifacts), gate='X' and explain in issue_classes + recommendations.
- Be technical. Prefer evidence-based claims. Do not invent missing files/fields.
"""


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


def _extract_output_text(resp: Dict[str, Any]) -> str:
    chunks: List[str] = []
    for item in (resp.get("output") or []):
        if item.get("type") == "message":
            for c in item.get("content") or []:
                if c.get("type") == "output_text" and c.get("text"):
                    chunks.append(c.get("text"))
    if chunks:
        return "".join(chunks)
    return str(resp.get("output_text") or "")


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    _load_env_from_local_settings(repo_root)

    parser = argparse.ArgumentParser(description="Run WP7 semantic index audit via OpenAI Responses API.")
    parser.add_argument("--input", default="tools/out/wp7_audit_input_MarioBros_50_50.json")
    parser.add_argument("--model", required=True)
    parser.add_argument("--reasoning", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--max-output-tokens", type=int, default=8000)
    args = parser.parse_args()

    api_key = str(os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise SystemExit("Missing OPENAI_API_KEY")

    input_path = Path(args.input)
    payload_in = json.loads(input_path.read_text(encoding="utf-8"))

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "run_id": {"type": "string"},
            "gate": {"type": "string", "enum": ["OK", "X"]},
            "integrity_metrics": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "index_entries_total": {"type": "integer", "minimum": 0},
                    "artifacts_total": {"type": "integer", "minimum": 0},
                    "mapped_pairs_total": {"type": "integer", "minimum": 0},
                    "missing_artifacts_percent": {"type": "number", "minimum": 0},
                    "orphan_artifacts_percent": {"type": "number", "minimum": 0},
                    "duplicates_percent": {"type": "number", "minimum": 0},
                    "invalid_schema_percent": {"type": "number", "minimum": 0},
                },
                "required": [
                    "index_entries_total",
                    "artifacts_total",
                    "mapped_pairs_total",
                    "missing_artifacts_percent",
                    "orphan_artifacts_percent",
                    "duplicates_percent",
                    "invalid_schema_percent",
                ],
            },
            "quality_summary": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "overall_assessment": {"type": "string"},
                    "top_strengths": {"type": "array", "items": {"type": "string"}},
                    "top_weaknesses": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["overall_assessment", "top_strengths", "top_weaknesses"],
            },
            "issue_classes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "code": {"type": "string"},
                        "severity": {"type": "string", "enum": ["P0", "P1", "P2"]},
                        "description": {"type": "string"},
                        "evidence_examples": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["code", "severity", "description", "evidence_examples"],
                },
            },
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
                        "area": {
                            "type": "string",
                            "enum": ["indexing", "artifact_schema", "dedup", "ranking", "logging", "validation"],
                        },
                        "recommendation": {"type": "string"},
                        "expected_impact": {"type": "string"},
                        "verification": {"type": "string"},
                    },
                    "required": ["priority", "area", "recommendation", "expected_impact", "verification"],
                },
            },
            "wp6_impact": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "expected_change_in_top_sources_quality": {"type": "string"},
                    "expected_change_in_coverage": {"type": "string"},
                    "risks_if_unchanged": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "expected_change_in_top_sources_quality",
                    "expected_change_in_coverage",
                    "risks_if_unchanged",
                ],
            },
        },
        "required": ["run_id", "gate", "integrity_metrics", "quality_summary", "issue_classes", "recommendations", "wp6_impact"],
    }

    payload = {
        "model": args.model,
        "reasoning": {"effort": args.reasoning},
        "max_output_tokens": int(args.max_output_tokens),
        "text": {"format": {"type": "json_schema", "name": "wp7_semantic_index_audit", "strict": True, "schema": schema}},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": WP7_AUDIT_SYSTEM_PROMPT}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload_in, ensure_ascii=False)}]},
        ],
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = "https://api.openai.com/v1/responses"

    start = time.time()
    r = requests.post(url, headers=headers, json=payload, timeout=600)
    elapsed = time.time() - start
    print("status", r.status_code, "elapsed_s", round(elapsed, 2))
    if r.status_code >= 400:
        print(r.text[:4000])
        raise SystemExit(2)

    resp = r.json()
    out_dir = repo_root / "tools" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / f"wp7_audit_openai_raw_{args.model}.json"
    raw_path.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")

    out_text = _extract_output_text(resp)
    out_text_path = out_dir / f"wp7_audit_output_text_{args.model}.txt"
    out_text_path.write_text(out_text, encoding="utf-8")

    audit = json.loads(out_text)
    out_path = out_dir / f"wp7_audit_results_{args.model}.json"
    out_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", out_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

