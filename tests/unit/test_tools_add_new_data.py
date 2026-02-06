import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_module():
    return importlib.import_module("tools.add_new_data")


def test_tools_add_new_data_calls_service(monkeypatch):
    def fake_core(user_id, target_blob_name, new_entry, raise_on_error=True):
        return {"status": "success", "count": 1}, 200

    module = _load_module()
    monkeypatch.setattr(module, "add_new_data_core", fake_core)
    result = module.add_new_data({"target_blob_name": "list.json", "new_entry": {"foo": "bar"}}, "alice")
    assert result["status"] == "success"


def test_tools_add_new_data_missing_fields(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "add_new_data_core", lambda **kwargs: ({"status": "ok"}, 200))
    assert module.add_new_data({"new_entry": {}}, "bob")["status"] == "error"
