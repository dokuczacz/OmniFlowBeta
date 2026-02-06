import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_tools_list_blobs_calls_core(monkeypatch):
    captured = {}

    def fake_core(user_id, prefix, include_meta, raise_on_error=True):
        captured["args"] = (user_id, prefix, include_meta, raise_on_error)
        return {"status": "success", "user_id": user_id}

    import importlib
    list_blobs_module = importlib.import_module("tools.list_blobs")
    monkeypatch.setattr(list_blobs_module, "list_blobs_core", fake_core)
    from tools import list_blobs

    result = list_blobs({"prefix": "notes", "include_meta": "yes"}, "alice")
    assert result == {"status": "success", "user_id": "alice"}
    assert captured["args"] == ("alice", "notes", True, False)


def test_tools_list_blobs_handles_falsey_include_meta(monkeypatch):
    def fake_core(user_id, prefix, include_meta, raise_on_error=True):
        return {"status": "success", "include_meta": include_meta}

    import importlib
    list_blobs_module = importlib.import_module("tools.list_blobs")
    monkeypatch.setattr(list_blobs_module, "list_blobs_core", fake_core)
    from tools import list_blobs

    result = list_blobs({"prefix": "notes", "include_meta": ""}, "bob")
    assert result["include_meta"] is False
