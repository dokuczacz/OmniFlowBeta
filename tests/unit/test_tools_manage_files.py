import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_module():
    return importlib.import_module("tools.manage_files")


def test_tools_manage_files_calls_service(monkeypatch):
    captured = {}

    def fake_core(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return {"status": "success"}, 200

    module = _load_module()
    monkeypatch.setattr(module, "manage_files_core", fake_core)

    result = module.manage_files({"operation": "delete", "source_name": "data.json"}, "alice")
    assert result["status"] == "success"
    assert captured["kwargs"]["user_id"] == "alice"
    assert captured["kwargs"]["operation"] == "delete"
    assert captured["kwargs"]["source_name"] == "data.json"
    assert captured["kwargs"]["raise_on_error"] is False


def test_tools_manage_files_supports_aliases(monkeypatch):
    captured = {}

    def fake_core(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return {"status": "ok"}, 200

    module = _load_module()
    monkeypatch.setattr(module, "manage_files_core", fake_core)

    module.manage_files(
        {
            "op": "rename",
            "source_blob": "old.txt",
            "target": "new.txt",
            "path_prefix": "docs/",
        },
        "bob",
    )

    assert captured["kwargs"]["user_id"] == "bob"
    assert captured["kwargs"]["operation"] == "rename"
    assert captured["kwargs"]["source_name"] == "old.txt"
    assert captured["kwargs"]["target_name"] == "new.txt"
    assert captured["kwargs"]["prefix"] == "docs/"
