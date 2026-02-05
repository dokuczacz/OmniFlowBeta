import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_module():
    return importlib.import_module("tools.update_data_entry")


def test_tools_update_data_entry_calls_service(monkeypatch):
    captured = {}

    def fake_core(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return {"status": "success"}, 200

    module = _load_module()
    monkeypatch.setattr(module, "update_data_entry_core", fake_core)

    result = module.update_data_entry(
        {
            "target_blob_name": "data.json",
            "find_key": "id",
            "find_value": "42",
            "update_key": "status",
            "update_value": "ok",
        },
        "alice",
    )
    assert result["status"] == "success"
    assert captured["kwargs"]["user_id"] == "alice"
    assert captured["kwargs"]["target_blob_name"] == "data.json"
    assert captured["kwargs"]["raise_on_error"] is False


def test_tools_update_data_entry_supports_file_name_alias(monkeypatch):
    captured = {}

    def fake_core(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return {"status": "ok"}, 200

    module = _load_module()
    monkeypatch.setattr(module, "update_data_entry_core", fake_core)

    module.update_data_entry(
        {
            "file_name": "notes.json",
            "find_key": "key",
            "find_value": "abc",
            "update_key": "flag",
            "update_value": True,
        },
        "bob",
    )
    assert captured["kwargs"]["user_id"] == "bob"
    assert captured["kwargs"]["target_blob_name"] == "notes.json"
