import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


from shared.agent_functions_catalog import allowed_fields_for_tool  # noqa: E402


def test_allowed_fields_for_tool_reads_manifest():
    fields = allowed_fields_for_tool("read_many_blobs")
    assert isinstance(fields, tuple)
    assert "files" in fields
    assert "tail_lines" in fields
    assert "max_bytes_per_file" in fields


def test_allowed_fields_for_tool_handles_unknown():
    assert allowed_fields_for_tool("does_not_exist") == tuple()


def test_allowed_fields_for_tool_includes_optional_query_params():
    fields = allowed_fields_for_tool("list_blobs")
    assert "prefix" in fields
    assert "include_meta" in fields

