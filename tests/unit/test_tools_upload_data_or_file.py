import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_module():
    return importlib.import_module("tools.upload_data_or_file")


def test_tools_upload_data_or_file_delegates_to_service(monkeypatch):
    def fake_core(user_id, target_blob_name, file_content, raise_on_error=True):
        return {"status": "success", "blob_name": target_blob_name, "size": len(str(file_content))}, 200

    module = _load_module()
    monkeypatch.setattr(module, "upload_data_or_file_core", fake_core)
    result = module.upload_data_or_file({"target_blob_name": "notes.json", "file_content": {"foo": "bar"}}, "alice")
    assert result["status"] == "success"
    assert result["blob_name"] == "notes.json"


def test_tools_upload_data_or_file_handles_missing_fields(monkeypatch):
    from tools.upload_data_or_file import upload_data_or_file as upload

    def fake_core(*args, **kwargs):
        return {"status": "error"}, 400

    module = _load_module()
    monkeypatch.setattr(module, "upload_data_or_file_core", fake_core)
    assert upload({"file_content": "ok"}, "bob")["status"] == "error"
