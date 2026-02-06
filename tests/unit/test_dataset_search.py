"""
Tests for dataset_search module (Phase 3 - Datasearch Engine).

Tests dataset_search(), filtering, pagination, and helper functions.
"""
import pytest
import json
import base64
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import sys
import os

# Add backend to path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# Import using importlib to avoid dependency issues
import importlib.util
spec = importlib.util.spec_from_file_location(
    "dataset_search_module",
    os.path.join(backend_path, "tools/dataset_search.py")
)
dataset_search_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dataset_search_module)

dataset_search = dataset_search_module.dataset_search
_apply_filters = dataset_search_module._apply_filters
_sort_items = dataset_search_module._sort_items
_paginate = dataset_search_module._paginate
_add_snippets = dataset_search_module._add_snippets
_parse_timestamp = dataset_search_module._parse_timestamp

from shared.error_codes import ToolError


# Sample manifest data for testing
SAMPLE_MANIFEST = [
    {
        "blob_name": "file1.json",
        "name": "Tax Documents 2024",
        "description": "Tax forms and receipts for 2024",
        "summary": "Comprehensive tax documentation including W-2, 1099, and receipts",
        "tags": ["financial", "tax", "2024"],
        "category": "finance",
        "updated_at": "2024-03-15T10:30:00Z"
    },
    {
        "blob_name": "file2.json",
        "name": "Budget Planning",
        "description": "Annual budget and financial planning",
        "summary": "Budget spreadsheet with projections",
        "tags": ["financial", "budget", "2024"],
        "category": "finance",
        "updated_at": "2024-02-10T14:20:00Z"
    },
    {
        "blob_name": "file3.json",
        "name": "Meeting Notes",
        "description": "Team meeting notes from Q1",
        "summary": "Discussion points and action items",
        "tags": ["meetings", "team", "2024"],
        "category": "work",
        "updated_at": "2024-01-20T09:15:00Z"
    },
    {
        "blob_name": "file4.json",
        "name": "Project Proposal",
        "description": "New project proposal draft",
        "summary": "Detailed proposal for Q2 initiative",
        "tags": ["project", "proposal"],
        "category": "work",
        "updated_at": "2024-03-01T16:45:00Z"
    }
]


class TestDatasetSearch:
    """Test dataset_search main function."""
    
    def test_basic_search(self):
        """Test basic search without filters."""
        # Mock the load_manifest function directly in the module
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123", limit=10)
        
        assert result["status"] == "success"
        assert result["total_matched"] == 4
        assert result["total_returned"] == 4
        assert result["has_more"] is False
        assert len(result["items"]) == 4
        
    def test_text_query_search(self):
        """Test text query filtering."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123", q="tax")
        
        assert result["total_matched"] == 1
        assert result["items"][0]["name"] == "Tax Documents 2024"
        
    def test_category_filter(self):
        """Test category filtering."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123", category="finance")
        
        assert result["total_matched"] == 2
        assert all(item["category"] == "finance" for item in result["items"])
        
    def test_tags_any_filter(self):
        """Test tags_any filtering (match ANY tag)."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123", tags_any=["tax", "budget"])
        
        assert result["total_matched"] == 2
        # Should match both tax and budget items
        
    def test_tags_all_filter(self):
        """Test tags_all filtering (match ALL tags)."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123", tags_all=["financial", "2024"])
        
        assert result["total_matched"] == 2
        # Should only match items with BOTH tags
        
    def test_limit_enforcement(self):
        """Test that limit is enforced."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123", limit=2)
        
        assert result["total_matched"] == 4
        assert result["total_returned"] == 2
        assert result["has_more"] is True
        assert len(result["items"]) == 2
        
    def test_pagination_with_cursor(self):
        """Test cursor-based pagination."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            # First page
            result1 = dataset_search("user123", limit=2)
            assert result1["has_more"] is True
            assert result1["cursor"] is not None
            
            # Second page
            result2 = dataset_search("user123", limit=2, cursor=result1["cursor"])
            assert len(result2["items"]) == 2
            assert result2["cursor"] is not None or not result2["has_more"]
        
    def test_limit_too_small_raises_error(self):
        """Test that limit < 1 raises error."""
        with pytest.raises(ToolError) as exc_info:
            dataset_search("user123", limit=0)
        
        assert exc_info.value.code == "VALIDATION_FAILED"
        
    def test_limit_too_large_raises_error(self):
        """Test that limit > 100 raises error."""
        with pytest.raises(ToolError) as exc_info:
            dataset_search("user123", limit=101)
        
        assert exc_info.value.code == "VALIDATION_FAILED"
        
    def test_include_snippets(self):
        """Test that snippets are included when requested."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123", include_snippets=True)
        
        # Should have snippets
        assert "snippet" in result["items"][0]
        
    def test_combined_filters(self):
        """Test combining multiple filters."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search(
                "user123",
                q="2024",
                category="finance",
                tags_any=["financial"]
            )
        
        # Should match items meeting all criteria
        assert result["total_matched"] >= 1


class TestApplyFilters:
    """Test _apply_filters function."""
    
    def test_no_filters_returns_all(self):
        """Test that no filters returns all items."""
        result = _apply_filters(SAMPLE_MANIFEST)
        
        assert len(result) == len(SAMPLE_MANIFEST)
        
    def test_text_query_filter(self):
        """Test text query filtering."""
        result = _apply_filters(SAMPLE_MANIFEST, q="budget")
        
        assert len(result) == 1
        assert result[0]["name"] == "Budget Planning"
        
    def test_text_query_case_insensitive(self):
        """Test that text query is case-insensitive."""
        result = _apply_filters(SAMPLE_MANIFEST, q="TAX")
        
        assert len(result) == 1
        assert "tax" in result[0]["name"].lower()
        
    def test_category_filter(self):
        """Test category filtering."""
        result = _apply_filters(SAMPLE_MANIFEST, category="work")
        
        assert len(result) == 2
        assert all(item["category"] == "work" for item in result)
        
    def test_tags_any_filter(self):
        """Test tags_any filtering."""
        result = _apply_filters(SAMPLE_MANIFEST, tags_any=["tax"])
        
        assert len(result) == 1
        assert "tax" in result[0]["tags"]
        
    def test_tags_all_filter(self):
        """Test tags_all filtering."""
        result = _apply_filters(SAMPLE_MANIFEST, tags_all=["financial", "2024"])
        
        # Should only match items with both tags
        for item in result:
            assert "financial" in item["tags"]
            assert "2024" in item["tags"]
            
    def test_since_filter(self):
        """Test since (after) timestamp filter."""
        result = _apply_filters(SAMPLE_MANIFEST, since="2024-03-01T00:00:00Z")
        
        # Should only include items updated after March 1
        assert len(result) == 2  # file1 and file4
        
    def test_until_filter(self):
        """Test until (before) timestamp filter."""
        result = _apply_filters(SAMPLE_MANIFEST, until="2024-02-15T00:00:00Z")
        
        # Should only include items updated before Feb 15
        assert len(result) == 2  # file2 and file3


class TestSortItems:
    """Test _sort_items function."""
    
    def test_sorts_by_updated_at_desc(self):
        """Test that items are sorted by updated_at descending."""
        sorted_items = _sort_items(SAMPLE_MANIFEST)
        
        # First item should be most recent
        assert sorted_items[0]["blob_name"] == "file1.json"  # 2024-03-15
        assert sorted_items[-1]["blob_name"] == "file3.json"  # 2024-01-20
        
    def test_stable_secondary_sort(self):
        """Test that secondary sort by name is stable."""
        # Create items with same timestamp
        items = [
            {"blob_name": "zzz.json", "name": "Z", "updated_at": "2024-01-01T00:00:00Z"},
            {"blob_name": "aaa.json", "name": "A", "updated_at": "2024-01-01T00:00:00Z"},
            {"blob_name": "mmm.json", "name": "M", "updated_at": "2024-01-01T00:00:00Z"},
        ]
        
        sorted_items = _sort_items(items)
        
        # Should be alphabetically sorted by name
        assert sorted_items[0]["blob_name"] == "aaa.json"
        assert sorted_items[1]["blob_name"] == "mmm.json"
        assert sorted_items[2]["blob_name"] == "zzz.json"


class TestPaginate:
    """Test _paginate function."""
    
    def test_first_page(self):
        """Test getting first page."""
        items = SAMPLE_MANIFEST
        
        page, cursor, has_more = _paginate(items, limit=2)
        
        assert len(page) == 2
        assert cursor is not None
        assert has_more is True
        
    def test_second_page(self):
        """Test getting second page with cursor."""
        items = SAMPLE_MANIFEST
        
        # Get first page
        _, cursor, _ = _paginate(items, limit=2)
        
        # Get second page
        page, cursor2, has_more = _paginate(items, cursor=cursor, limit=2)
        
        assert len(page) == 2
        assert page[0] != items[0]  # Different from first page
        
    def test_last_page_no_cursor(self):
        """Test that last page has no next cursor."""
        items = SAMPLE_MANIFEST
        
        page, cursor, has_more = _paginate(items, limit=10)
        
        assert len(page) == 4
        assert cursor is None
        assert has_more is False
        
    def test_cursor_format(self):
        """Test that cursor is properly formatted."""
        items = SAMPLE_MANIFEST
        
        _, cursor, _ = _paginate(items, limit=2)
        
        # Should be base64-encoded JSON
        decoded = json.loads(base64.b64decode(cursor).decode())
        assert "offset" in decoded
        assert decoded["offset"] == 2


class TestAddSnippets:
    """Test _add_snippets function."""
    
    def test_adds_snippet_from_summary(self):
        """Test that snippet is added from summary."""
        items = [SAMPLE_MANIFEST[0]]
        
        result = _add_snippets(items)
        
        assert "snippet" in result[0]
        assert len(result[0]["snippet"]) > 0
        
    def test_truncates_long_snippets(self):
        """Test that long snippets are truncated."""
        items = [{
            "name": "Test",
            "summary": "A" * 300
        }]
        
        result = _add_snippets(items)
        
        assert len(result[0]["snippet"]) <= 203  # 200 + "..."
        assert result[0]["snippet"].endswith("...")
        
    def test_fallback_to_description(self):
        """Test fallback to description if no summary."""
        items = [{
            "name": "Test",
            "description": "Description text"
        }]
        
        result = _add_snippets(items)
        
        assert "snippet" in result[0]
        assert "Description" in result[0]["snippet"]


class TestParseTimestamp:
    """Test _parse_timestamp function."""
    
    def test_parse_iso8601_with_z(self):
        """Test parsing ISO8601 with Z suffix."""
        ts = "2024-03-15T10:30:00Z"
        
        result = _parse_timestamp(ts)
        
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        
    def test_parse_iso8601_with_offset(self):
        """Test parsing ISO8601 with timezone offset."""
        ts = "2024-03-15T10:30:00+00:00"
        
        result = _parse_timestamp(ts)
        
        assert isinstance(result, datetime)
        
    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        result = _parse_timestamp(None)
        
        assert result is None
        
    def test_parse_invalid_returns_none(self):
        """Test that invalid timestamp returns None."""
        result = _parse_timestamp("not a timestamp")
        
        assert result is None


class TestDatasetSearchContract:
    """Test that dataset_search follows standard contracts."""
    
    def test_response_structure(self):
        """Test that response has required fields."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123")
        
        # Required fields
        assert "status" in result
        assert "total_matched" in result
        assert "total_returned" in result
        assert "items" in result
        assert "cursor" in result
        assert "has_more" in result
        assert "user_id" in result
        
    def test_response_is_json_serializable(self):
        """Test that response can be JSON serialized."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            result = dataset_search("user123")
        
        # Should not raise
        json_str = json.dumps(result)
        assert json_str
        
        # Should be deserializable
        parsed = json.loads(json_str)
        assert parsed["status"] == "success"


class TestDatasetSearchIntegration:
    """Test dataset_search integration scenarios."""
    
    def test_scan_confirm_fetch_workflow(self):
        """Test the Scan → Confirm → Fetch workflow."""
        with patch.object(dataset_search_module, '_load_manifest', return_value=SAMPLE_MANIFEST):
            # 1. Scan: Search without content
            scan_result = dataset_search(
                "user123",
                q="tax",
                fetch_content=False
            )
            assert scan_result["total_matched"] > 0
            assert "_content_available" not in scan_result["items"][0]
            
            # 2. Confirm: User reviews results
            # (application logic)
            
            # 3. Fetch: Load content for specific item
            fetch_result = dataset_search(
                "user123",
                q="tax",
                fetch_content=True,
                limit=1
            )
            # Content flag should be set (actual content loading mocked)
            assert "_content_available" in fetch_result["items"][0]
