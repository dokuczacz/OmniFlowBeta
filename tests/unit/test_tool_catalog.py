import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from shared.tool_catalog import apply_param_aliases


def test_apply_param_aliases_keeps_legacy_flagged():
    params = {"file_name": "notes.json"}
    result = apply_param_aliases("read_blob", params, keep_legacy=True)
    assert result["name"] == "notes.json"
    assert result["file_name"] == "notes.json"


def test_apply_param_aliases_defaults_remove_legacy():
    params = {"file_name": "notes.json"}
    result = apply_param_aliases("read_blob", params)
    assert result["name"] == "notes.json"
    assert "file_name" not in result
