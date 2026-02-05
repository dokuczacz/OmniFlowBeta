import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_module():
    return importlib.import_module("tools.get_filtered_data")


def test_tools_get_filtered_data_uses_service(monkeypatch):
    def fake_core(user_id, target_blob_name, filter_key=None, filter_value=None, raise_on_error=True):
        return {"status": "success", "file": target_blob_name, "filter": {"key": filter_key, "value": filter_value}}, 200

    module = _load_module()
    monkeypatch.setattr(module, "get_filtered_data_core", fake_core)
    result = module.get_filtered_data(
        {"target_blob_name": "data.json", "filter_key": "status", "filter_value": "ok"},
        "alice",
    )
    assert result["file"] == "data.json"
    assert result["filter"]["value"] == "ok"


def test_tools_get_filtered_data_supports_file_name_alias(monkeypatch):
    def fake_core(user_id, target_blob_name, filter_key=None, filter_value=None, raise_on_error=True):
        return {"status": "ok", "file": target_blob_name}, 200

    module = _load_module()
    monkeypatch.setattr(module, "get_filtered_data_core", fake_core)
    result = module.get_filtered_data({"file_name": "notes.json"}, "bob")
    assert result["file"] == "notes.json"
