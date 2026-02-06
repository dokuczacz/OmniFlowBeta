Assumptions: No files were modified in place; I am only producing the requested patch text because the sandbox is read-only and I must obey higher-level instructions (so I’m including the patch inside the required response structure).

Plan: Scope is creating a minimal Unit A HTTP server (server.py) and documenting it (README) for `experiments/multi_agent_demo/unitA/`; inputs are the outlined API requirements and Python 3 stdlib only, outputs are the two files described, acceptance is a runnable `python server.py` with the correct endpoints/HTTP behavior and README describing usage; estimated files touched 2, estimated diff ~250 LOC, classification GREEN (≤5 files, ≤1200 LOC).

Minimal diff:
*** Begin Patch
*** Add File: experiments/multi_agent_demo/unitA/server.py
+import json
+import os
+from datetime import datetime, timezone
+from http.server import BaseHTTPRequestHandler, HTTPServer
+
+HOST = "127.0.0.1"
+DEFAULT_PORT = 8765
+
+_notes = []
+_next_note_id = 1
+
+
+def _current_utc_isostr():
+    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
+
+
+class UnitAHandler(BaseHTTPRequestHandler):
+    server_version = "unitA/0.1.0"
+
+    def _write_json(self, status_code, payload):
+        body = json.dumps(payload).encode("utf-8")
+        self.send_response(status_code)
+        self.send_header("Content-Type", "application/json")
+        self.send_header("Content-Length", str(len(body)))
+        self.end_headers()
+        self.wfile.write(body)
+
+    def _not_found(self):
+        self._write_json(404, {"status": "error", "error": "not_found"})
+
+    def _invalid_json(self):
+        self._write_json(400, {"status": "error", "error": "invalid_json"})
+
+    def _missing_text(self):
+        self._write_json(400, {"status": "error", "error": "missing_text"})
+
+    def do_GET(self):
+        if self.path == "/health":
+            self._write_json(
+                200,
+                {"status": "ok", "service": "unitA", "version": "0.1.0"},
+            )
+            return
+
+        if self.path == "/notes":
+            self._write_json(200, {"items": list(_notes)})
+            return
+
+        self._not_found()
+
+    def do_POST(self):
+        if self.path != "/notes":
+            self._not_found()
+            return
+
+        length = int(self.headers.get("Content-Length") or 0)
+        body = self.rfile.read(length) if length > 0 else b""
+
+        try:
+            payload = json.loads(body.decode("utf-8"))
+        except (json.JSONDecodeError, UnicodeDecodeError):
+            self._invalid_json()
+            return
+
+        text = payload.get("text") if isinstance(payload, dict) else None
+        if not isinstance(text, str):
+            self._missing_text()
+            return
+
+        text = text.strip()
+        if not text:
+            self._missing_text()
+            return
+
+        global _next_note_id
+        item = {
+            "id": _next_note_id,
+            "text": text,
+            "created_utc": _current_utc_isostr(),
+        }
+        _next_note_id += 1
+        _notes.append(item)
+
+        self._write_json(201, {"status": "created", "item": item})
+
+    def log_message(self, format, *args):
+        return
+
+
+def _port():
+    env = os.environ.get("PORT")
+    if not env:
+        return DEFAULT_PORT
+
+    try:
+        return int(env)
+    except ValueError:
+        return DEFAULT_PORT
+
+
+def run_server():
+    server = HTTPServer((HOST, _port()), UnitAHandler)
+    print(f"Unit A server listening on {HOST}:{server.server_address[1]}")
+
+    try:
+        server.serve_forever()
+    except KeyboardInterrupt:
+        pass
+    finally:
+        server.server_close()
+
+
+if __name__ == "__main__":
+    run_server()
*** End Patch
*** Begin Patch
*** Add File: experiments/multi_agent_demo/unitA/README.md
+# Unit A – HTTP note service
+
+- **Run**: `python server.py` (defaults to `127.0.0.1:8765`, override with the `PORT` env var)
+- **Dependencies**: Python 3 standard library only
+
+## Endpoints
+
+- `GET /health` → `{ "status": "ok", "service": "unitA", "version": "0.1.0" }`
+- `GET /notes` → `{ "items": [ { "id": <int>, "text": <str>, "created_utc": <ISO-timestamp> }, ... ] }`
+- `POST /notes` with JSON body `{ "text": "..." }` → `{ "status": "created", "item": { ... } }`
+
+## Error responses
+
+- Unknown path or method → `404` with `{ "status": "error", "error": "not_found" }`
+- Invalid JSON body → `400` with `{ "status": "error", "error": "invalid_json" }`
+- Missing or empty `text` → `400` with `{ "status": "error", "error": "missing_text" }`
*** End Patch

Check/Tests: Not run (sandbox is read-only); testing would be to `curl` `/health`, `/notes`, and POST with valid/invalid bodies and verify JSON responses.

Workstream / Task	Done/Total	Progress	Δ vs previous	Status
Scope/Plan	1/1 (prev N/A, Δ N/A)	100% (prev N/A, Δ N/A)	N/A (baseline)	Done
Server implementation	1/3 (prev N/A, Δ N/A)	33% (prev N/A, Δ N/A)	N/A (baseline)	In progress
Documentation	0/1 (prev N/A, Δ N/A)	0% (prev N/A, Δ N/A)	N/A (baseline)	Pending
Check/Tests	0/1 (prev N/A, Δ N/A)	0% (prev N/A, Δ N/A)	N/A (baseline)	Pending