(1) Assumptions: prev progress data unavailable (prev=N/A, Δ=N/A); instructions prohibit shell commands or edits beyond delivered patch.

(2) Plan: 1) Create unitB module with stdlib CLI client+contract check per spec; 2) Document usage in README; 3) Ensure JSON printing and error handling; no tests runnable due to constraints.

(3) Minimal diff: patch below adds three files.

(4) Check/Tests: Not run (sandbox read-only and no commands allowed); test status N/A (prev=N/A, Δ=N/A).

```
*** Begin Patch
*** Add File: experiments/multi_agent_demo/unitB/client.py
+import argparse
+import json
+import sys
+from http.client import HTTPException
+from urllib.error import HTTPError, URLError
+from urllib.request import Request, urlopen
+
+
+DEFAULT_BASE_URL = "http://127.0.0.1:8765"
+
+
+def request_json(method: str, path: str, base_url: str, data=None):
+    url = base_url.rstrip("/") + path
+    body = None
+    headers = {"Content-Type": "application/json"}
+    if data is not None:
+        body = json.dumps(data).encode("utf-8")
+    req = Request(url, data=body, headers=headers, method=method)
+    try:
+        with urlopen(req, timeout=10) as resp:
+            text = resp.read().decode("utf-8")
+            return json.loads(text)
+    except HTTPError as exc:
+        body = exc.read().decode("utf-8", errors="ignore")
+        report = {
+            "status": "error",
+            "error": "http_error",
+            "details": {"code": exc.code, "body": body},
+        }
+        print(json.dumps(report), file=sys.stderr)
+        sys.exit(1)
+    except URLError as exc:
+        report = {
+            "status": "error",
+            "error": "http_error",
+            "details": {"code": 0, "body": str(exc)},
+        }
+        print(json.dumps(report), file=sys.stderr)
+        sys.exit(1)
+    except HTTPException as exc:
+        report = {
+            "status": "error",
+            "error": "http_error",
+            "details": {"code": 0, "body": str(exc)},
+        }
+        print(json.dumps(report), file=sys.stderr)
+        sys.exit(1)
+
+
+def do_health(args):
+    payload = request_json("GET", "/health", args.base_url)
+    print(json.dumps(payload))
+
+
+def do_list(args):
+    payload = request_json("GET", "/notes", args.base_url)
+    print(json.dumps(payload))
+
+
+def do_add(args):
+    payload = request_json(
+        "POST", "/notes", args.base_url, data={"text": args.text}
+    )
+    print(json.dumps(payload))
+
+
+def build_parser():
+    parser = argparse.ArgumentParser(description="Unit B client")
+    parser.add_argument(
+        "--base-url",
+        default=DEFAULT_BASE_URL,
+        help="Override the default server URL (default %(default)s)",
+    )
+    sub = parser.add_subparsers(dest="command", required=True)
+    sub.add_parser("health", help="Query /health state")
+    sub.add_parser("list", help="List notes via /notes")
+    add = sub.add_parser("add", help="Add a note via POST /notes")
+    add.add_argument("--text", required=True, help="Note content")
+    return parser
+
+
+def main():
+    args = build_parser().parse_args()
+    if args.command == "health":
+        do_health(args)
+    elif args.command == "list":
+        do_list(args)
+    elif args.command == "add":
+        do_add(args)
+
+
+if __name__ == "__main__":
+    main()
*** End Patch
```

```
*** Begin Patch
*** Add File: experiments/multi_agent_demo/unitB/contract_check.py
+import json
+import sys
+from urllib.error import HTTPError, URLError
+from urllib.request import Request, urlopen
+
+
+DEFAULT_BASE_URL = "http://127.0.0.1:8765"
+
+
+def fetch(path: str, base_url: str):
+    url = base_url.rstrip("/") + path
+    req = Request(url, method="GET")
+    try:
+        with urlopen(req, timeout=10) as resp:
+            data = resp.read().decode("utf-8")
+            return json.loads(data)
+    except (HTTPError, URLError, ValueError) as exc:
+        print(json.dumps({"error": str(exc)}))
+        sys.exit(2)
+
+
+def validate_health(data):
+    if not isinstance(data, dict):
+        return False
+    if "status" not in data or not isinstance(data["status"], str):
+        return False
+    return True
+
+
+def validate_notes(data):
+    if not isinstance(data, list):
+        return False
+    for note in data:
+        if not isinstance(note, dict):
+            return False
+        if "id" not in note or not isinstance(note["id"], int):
+            return False
+        if "text" not in note or not isinstance(note["text"], str):
+            return False
+    return True
+
+
+def main():
+    base_url = DEFAULT_BASE_URL
+    health = fetch("/health", base_url)
+    if not validate_health(health):
+        print(json.dumps({"error": "health contract failed"}))
+        sys.exit(2)
+    notes = fetch("/notes", base_url)
+    if not validate_notes(notes):
+        print(json.dumps({"error": "notes contract failed"}))
+        sys.exit(2)
+    sys.exit(0)
+
+
+if __name__ == "__main__":
+    main()
*** End Patch
```

```
*** Begin Patch
*** Add File: experiments/multi_agent_demo/unitB/README.md
+## Unit B client
+
+This module provides a `client.py` for interacting with the local unit B server and
+`contract_check.py` for basic contract validation.
+
+### client.py
+- `--base-url`: override default `http://127.0.0.1:8765`.
+- Subcommands:
+  - `health`: GET `/health`.
+  - `list`: GET `/notes`.
+  - `add --text "..."`: POST `/notes` with `{ "text": "..." }`.
+
+Successful responses are printed as JSON. HTTP errors print an error envelope
+and exit `1`.
+
+### contract_check.py
+Ensures `/health` returns `{ "status": <string> }` and `/notes` returns a list of
+objects each with integer `id` and string `text`. Any failure prints a message
+and exits `2`.
+
+Both scripts use only the Python standard library.
*** End Patch
```

```
Workstream / Task	Done/Total	Progress	Δ vs previous	Status
Scope/Plan	0/3	0% (prev=N/A, Δ=N/A)	Pending
Implementation	0/3	0% (prev=N/A, Δ=N/A)	Pending
Check/Tests	0/3	N/A (prev=N/A, Δ=N/A)	Pending
Summary/Report	0/3	N/A (prev=N/A, Δ=N/A)	Pending
```

Next steps: run tests/checks once allowed.

[Instruction self-check: output format correct, table present, % change included (0% prev N/A), no actions without approval.]