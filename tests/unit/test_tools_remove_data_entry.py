import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_module():
    return importlib.import_module("tools.remove_data_entry")


def test_tools_remove_data_entry_calls_service(monkeypatch):
    captured = {}

    def fake_core(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return {"status": "success"}, 200

    module = _load_module()
    monkeypatch.setattr(module, "remove_data_entry_core", fake_core)

    result = module.remove_data_entry(
        {
            "target_blob_name": "data.json",
            "key_to_find": "id",
            "value_to_find": "42",
        },
        "alice",
    )
    assert result["status"] == "success"
    assert captured["kwargs"]["user_id"] == "alice"
    assert captured["kwargs"]["target_blob_name"] == "data.json"
    assert captured["kwargs"]["raise_on_error"] is False


def test_tools_remove_data_entry_supports_aliases(monkeypatch):
    captured = {}

    def fake_core(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return {"status": "ok"}, 200

    module = _load_module()
    monkeypatch.setattr(module, "remove_data_entry_core", fake_core)

    module.remove_data_entry(
        {
            "file_name": "notes.json",
            "find_key": "category",
            "find_value": "todo",
        },
        "bob",
    )

    assert captured["kwargs"]["user_id"] == "bob"
    assert captured["kwargs"]["target_blob_name"] == "notes.json"
    assert captured["kwargs"]["key_to_find"] == "category"
    assert captured["kwargs"]["value_to_find"] == "todo"
