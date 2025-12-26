#!/usr/bin/env python3
"""Smoke-test `/api/tool_call_handler` runtime switching (assistants|responses|auto).

This script is intentionally lightweight and validates only the HTTP contract:
- accepts `runtime` in request body
- returns `runtime_used` on success
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests


def _default_url() -> str:
    base = os.getenv("FUNCTION_URL_BASE", "http://localhost:7071").rstrip("/")
    return f"{base}/api/tool_call_handler"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test tool_call_handler runtimes.")
    parser.add_argument("--url", "-u", default=None, help="Full URL to the tool_call_handler endpoint.")
    parser.add_argument("--user-id", "-U", default="test_user", help="User ID to send with the request.")
    parser.add_argument("--thread-id", default=None, help="Optional thread_id/handle.")
    parser.add_argument("--timeout", "-t", type=float, default=30.0, help="Seconds to wait for a response.")
    parser.add_argument("--runtime", "-r", action="append", default=None, help="Runtime to test (repeatable).")
    parser.add_argument(
        "--message",
        "-m",
        default="Ping (smoke test). If you need tools, call get_current_time.",
        help="Message content.",
    )
    return parser.parse_args()


def call_handler(url: str, user_id: str, timeout: float, body: dict) -> requests.Response:
    headers = {"X-User-Id": user_id, "Content-Type": "application/json"}
    return requests.post(url, headers=headers, json=body, timeout=timeout)


def main() -> int:
    args = parse_args()
    url = args.url or _default_url()
    runtimes = args.runtime or ["assistants", "responses", "auto"]

    failed = False
    for runtime in runtimes:
        body = {
            "message": args.message,
            "runtime": runtime,
            "thread_id": args.thread_id,
            "log_interaction": False,
        }
        resp = call_handler(url, args.user_id, args.timeout, body)
        try:
            payload = resp.json()
        except ValueError:
            payload = {"raw": resp.text}

        runtime_used = payload.get("runtime_used") if isinstance(payload, dict) else None
        not_configured = isinstance(payload, dict) and payload.get("status") == "not_configured"

        print(f"[{runtime}] status={resp.status_code} runtime_used={runtime_used!r} not_configured={not_configured}")
        if resp.status_code >= 500:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

