import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_module():
    return importlib.import_module("tools.read_many_blobs")


def test_tools_read_many_blobs_calls_service(monkeypatch):
    captured = {}

    def fake_core(user_id, files, tail_lines, tail_bytes, max_bytes_per_file, parse_json, max_files, raise_on_error=True):
        captured["args"] = (user_id, tuple(files), tail_lines, max_bytes_per_file, parse_json, max_files)
        return {"status": "success"}, 200

    module = _load_module()
    monkeypatch.setattr(module, "read_many_blobs_core", fake_core)

    payload = module.read_many_blobs(
        {"files": ["a.json"], "tail_lines": 3, "max_bytes_per_file": 100},
        "alice",
    )
    assert payload["status"] == "success"
    assert captured["args"] == ("alice", ("a.json",), 3, 100, None, None)


def test_tools_read_many_blobs_handles_parse_flag(monkeypatch):
    def fake_core(*args, **kwargs):
        return {"status": "ok", "parse_json": kwargs.get("parse_json")}, 200

    module = _load_module()
    monkeypatch.setattr(module, "read_many_blobs_core", fake_core)

    result = module.read_many_blobs({"files": ["a"], "parse_json": False}, "bob")
    assert result["parse_json"] is False
