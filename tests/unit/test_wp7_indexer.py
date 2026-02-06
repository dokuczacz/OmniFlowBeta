"""
Tests for WP7 Semantic Indexer

Tests cover:
- Schema validation
- REALTIME mode indexing
- BATCH mode indexing
- Prompt caching efficiency
- Deduplication
- Performance metrics
"""

import pytest
from datetime import datetime, timezone

from backend.tool_call_handler.wp7.schemas import (
    IndexerInput,
    IndexerOutput,
    SemanticItem,
    IndexingMode,
    SemanticCategory,
    BatchIndexerInput,
    IndexerMetrics,
)
from backend.tool_call_handler.wp7.indexer import (
    index_interaction,
    index_interactions_batch,
    get_indexer_system_prompt,
    get_indexer_output_schema,
    get_indexer_examples,
    build_cacheable_prompt,
    compute_dedup_key,
    estimate_cache_efficiency,
    analyze_indexer_performance,
)


# ============================================================================
# Schema Tests
# ============================================================================

def test_semantic_item_valid():
    """Test valid semantic item creation"""
    item = SemanticItem(
        interaction_id="INT_001",
        category=SemanticCategory.UI,
        summary="Test interaction; tool_call(); Result success",
        tags=["test", "semantic", "valid"],
        confidence=0.95,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    assert item.interaction_id == "INT_001"
    assert item.category == SemanticCategory.UI
    assert 0.0 <= item.confidence <= 1.0


def test_semantic_item_invalid_interaction_id():
    """Test semantic item rejects invalid interaction ID"""
    with pytest.raises(Exception):  # Pydantic ValidationError
        SemanticItem(
            interaction_id="INVALID_ID",  # Should start with INT_
            category=SemanticCategory.UI,
            summary="Test summary",
            tags=["test", "invalid", "id"],
            confidence=0.9,
            timestamp=datetime.now(timezone.utc).isoformat()
        )


def test_semantic_item_invalid_tags():
    """Test semantic item rejects invalid tag format"""
    with pytest.raises(Exception):  # Pydantic ValidationError
        SemanticItem(
            interaction_id="INT_001",
            category=SemanticCategory.UI,
            summary="Test summary",
            tags=["test", "UPPERCASE", "invalid"],  # Must be lowercase
            confidence=0.9,
            timestamp=datetime.now(timezone.utc).isoformat()
        )


def test_semantic_item_tags_count():
    """Test semantic item validates tag count (3-6)"""
    # Too few tags
    with pytest.raises(Exception):
        SemanticItem(
            interaction_id="INT_001",
            category=SemanticCategory.UI,
            summary="Test summary",
            tags=["only", "two"],  # Min 3 required
            confidence=0.9,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
    
    # Too many tags
    with pytest.raises(Exception):
        SemanticItem(
            interaction_id="INT_001",
            category=SemanticCategory.UI,
            summary="Test summary",
            tags=["one", "two", "three", "four", "five", "six", "seven"],  # Max 6
            confidence=0.9,
            timestamp=datetime.now(timezone.utc).isoformat()
        )


def test_indexer_input_valid():
    """Test valid indexer input creation"""
    input_data = IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Test message",
        tool_calls=[{"name": "test_tool", "result": "success"}],
        mode=IndexingMode.REALTIME
    )
    assert input_data.user_id == "user123"
    assert input_data.mode == IndexingMode.REALTIME


def test_indexer_input_default_mode():
    """Test indexer input defaults to REALTIME mode"""
    input_data = IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Test message"
    )
    assert input_data.mode == IndexingMode.REALTIME


def test_indexer_input_empty_message():
    """Test indexer input rejects empty message"""
    with pytest.raises(Exception):  # Pydantic ValidationError
        IndexerInput(
            user_id="user123",
            interaction_id="INT_001",
            message="   ",  # Empty after stripping
            mode=IndexingMode.REALTIME
        )


def test_indexer_output_valid():
    """Test valid indexer output creation"""
    item = SemanticItem(
        interaction_id="INT_001",
        category=SemanticCategory.UI,
        summary="Test; action(); result",
        tags=["test", "output", "valid"],
        confidence=0.95,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    output = IndexerOutput(
        items=[item],
        mode_used=IndexingMode.REALTIME,
        cached_tokens=1800,
        total_tokens=2000,
        processing_time_ms=150.5,
        dedup_key="abc123"
    )
    
    assert len(output.items) == 1
    assert output.mode_used == IndexingMode.REALTIME
    assert output.cached_tokens == 1800
    assert output.total_tokens == 2000


def test_batch_indexer_input_valid():
    """Test valid batch indexer input"""
    input_data = BatchIndexerInput(
        user_id="user123",
        interactions=[
            {"id": "INT_001", "message": "Test 1"},
            {"id": "INT_002", "message": "Test 2"}
        ],
        batch_size_multiplier=9,
        target_tokens=4000
    )
    assert len(input_data.interactions) == 2
    assert input_data.batch_size_multiplier == 9


def test_batch_indexer_input_limits():
    """Test batch indexer enforces limits"""
    # Too many interactions
    with pytest.raises(Exception):
        BatchIndexerInput(
            user_id="user123",
            interactions=[{"id": f"INT_{i:03d}", "message": f"Test {i}"} for i in range(30)],  # Max 25
        )
    
    # Batch multiplier too high
    with pytest.raises(Exception):
        BatchIndexerInput(
            user_id="user123",
            interactions=[{"id": "INT_001", "message": "Test"}],
            batch_size_multiplier=25  # Max 20
        )


# ============================================================================
# Prompt Building Tests
# ============================================================================

def test_get_indexer_system_prompt():
    """Test system prompt is deterministic"""
    prompt1 = get_indexer_system_prompt()
    prompt2 = get_indexer_system_prompt()
    
    assert prompt1 == prompt2
    assert len(prompt1) > 100  # Has substantial content
    assert "semantic indexer" in prompt1.lower()


def test_get_indexer_output_schema():
    """Test output schema is valid JSON"""
    schema = get_indexer_output_schema()
    
    assert schema["type"] == "object"
    assert "items" in schema["properties"]
    assert schema["properties"]["items"]["type"] == "array"


def test_get_indexer_examples():
    """Test examples are deterministic"""
    examples1 = get_indexer_examples()
    examples2 = get_indexer_examples()
    
    assert examples1 == examples2
    assert "Example 1" in examples1
    assert "Example 2" in examples1
    assert "INT_" in examples1  # Contains interaction IDs


def test_build_cacheable_prompt_structure():
    """Test prompt has correct structure for caching"""
    interactions = [
        {
            "interaction_id": "INT_001",
            "user_message": "Test message",
            "tool_calls": [],
            "timestamp": "2024-01-01T00:00:00Z"
        }
    ]
    
    prompt = build_cacheable_prompt(interactions)
    
    # Static components should come first
    assert prompt.index("semantic indexer") < prompt.index("INT_001")
    assert prompt.index("Output Schema") < prompt.index("INT_001")
    assert prompt.index("Example 1") < prompt.index("INT_001")
    
    # Dynamic content (interaction data) should be last
    assert "INT_001" in prompt
    assert "Test message" in prompt


def test_build_cacheable_prompt_determinism():
    """Test prompt is deterministic for same input"""
    interactions = [
        {
            "interaction_id": "INT_001",
            "user_message": "Test",
            "tool_calls": [],
            "timestamp": "2024-01-01T00:00:00Z"
        }
    ]
    
    prompt1 = build_cacheable_prompt(interactions)
    prompt2 = build_cacheable_prompt(interactions)
    
    assert prompt1 == prompt2


# ============================================================================
# Deduplication Tests
# ============================================================================

def test_compute_dedup_key_deterministic():
    """Test dedup key is deterministic for same input"""
    key1 = compute_dedup_key("INT_001", "UI", "Test summary", ["tag1", "tag2", "tag3"])
    key2 = compute_dedup_key("INT_001", "UI", "Test summary", ["tag1", "tag2", "tag3"])
    
    assert key1 == key2
    assert len(key1) == 32  # MD5 hash length


def test_compute_dedup_key_tag_order_invariant():
    """Test dedup key is same regardless of tag order"""
    key1 = compute_dedup_key("INT_001", "UI", "Test", ["tag1", "tag2", "tag3"])
    key2 = compute_dedup_key("INT_001", "UI", "Test", ["tag3", "tag1", "tag2"])
    
    assert key1 == key2  # Tags are sorted internally


def test_compute_dedup_key_case_insensitive_summary():
    """Test dedup key normalizes summary case"""
    key1 = compute_dedup_key("INT_001", "UI", "Test Summary", ["tag"])
    key2 = compute_dedup_key("INT_001", "UI", "TEST SUMMARY", ["tag"])
    
    assert key1 == key2  # Summary is lowercased


def test_compute_dedup_key_different_content():
    """Test dedup key changes with different content"""
    key1 = compute_dedup_key("INT_001", "UI", "Summary A", ["tag1", "tag2", "tag3"])
    key2 = compute_dedup_key("INT_001", "UI", "Summary B", ["tag1", "tag2", "tag3"])
    
    assert key1 != key2  # Different summaries


# ============================================================================
# Cache Efficiency Tests
# ============================================================================

def test_estimate_cache_efficiency_single_interaction():
    """Test cache efficiency estimation for single interaction"""
    interactions = [
        {
            "interaction_id": "INT_001",
            "user_message": "Short query",
            "tool_calls": [],
            "timestamp": "2024-01-01T00:00:00Z"
        }
    ]
    
    cache_eff, cost_savings = estimate_cache_efficiency("", interactions)
    
    # For single interaction, expect high cache efficiency (80-90%)
    assert 0.7 <= cache_eff <= 0.95
    assert 35.0 <= cost_savings <= 47.5  # 50% of cache_eff


def test_estimate_cache_efficiency_batch():
    """Test cache efficiency for batch (lower than single)"""
    interactions = [
        {
            "interaction_id": f"INT_{i:03d}",
            "user_message": f"Query {i} with some content",
            "tool_calls": [],
            "timestamp": "2024-01-01T00:00:00Z"
        }
        for i in range(10)
    ]
    
    cache_eff, cost_savings = estimate_cache_efficiency("", interactions)
    
    # Batch should still have decent cache efficiency (60-80%)
    assert 0.5 <= cache_eff <= 0.85
    assert 25.0 <= cost_savings <= 42.5


# ============================================================================
# REALTIME Mode Tests
# ============================================================================

def test_index_interaction_realtime_mode():
    """Test single interaction indexing in REALTIME mode"""
    input_data = IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="What's the weather?",
        tool_calls=[{"name": "weather_api", "result": "sunny"}],
        mode=IndexingMode.REALTIME
    )
    
    output = index_interaction(input_data, use_mock=True)
    
    assert output.mode_used == IndexingMode.REALTIME
    assert len(output.items) == 1
    assert output.items[0].interaction_id == "INT_001"
    assert output.cached_tokens > 0
    assert output.total_tokens > 0
    assert output.dedup_key is not None


def test_index_interaction_cache_efficiency():
    """Test REALTIME mode achieves target cache efficiency"""
    input_data = IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Test query for cache efficiency",
        mode=IndexingMode.REALTIME
    )
    
    output = index_interaction(input_data, use_mock=True)
    
    cache_eff = output.cached_tokens / output.total_tokens
    
    # Target: 80-90% cache efficiency for REALTIME
    assert cache_eff >= 0.80, f"Cache efficiency {cache_eff:.2%} below 80% target"
    assert cache_eff <= 0.95


def test_index_interaction_processing_time():
    """Test REALTIME mode completes quickly"""
    input_data = IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Quick test",
        mode=IndexingMode.REALTIME
    )
    
    output = index_interaction(input_data, use_mock=True)
    
    # Should be fast (mock mode)
    assert output.processing_time_ms < 100.0


# ============================================================================
# BATCH Mode Tests
# ============================================================================

def test_index_interactions_batch_mode():
    """Test batch indexing in BATCH mode"""
    input_data = BatchIndexerInput(
        user_id="user123",
        interactions=[
            {"id": "INT_001", "message": "Query 1", "tools": []},
            {"id": "INT_002", "message": "Query 2", "tools": []},
            {"id": "INT_003", "message": "Query 3", "tools": []},
        ]
    )
    
    output = index_interactions_batch(input_data, use_mock=True)
    
    assert output.mode_used == IndexingMode.BATCH
    assert len(output.items) == 3
    assert output.cached_tokens > 0
    assert output.total_tokens > output.cached_tokens


def test_index_interactions_batch_cache_efficiency():
    """Test BATCH mode achieves target cache efficiency"""
    input_data = BatchIndexerInput(
        user_id="user123",
        interactions=[
            {"id": f"INT_{i:03d}", "message": f"Query {i}", "tools": []}
            for i in range(1, 6)
        ]
    )
    
    output = index_interactions_batch(input_data, use_mock=True)
    
    cache_eff = output.cached_tokens / output.total_tokens
    
    # Target: 60-80% cache efficiency for BATCH
    assert cache_eff >= 0.60, f"Batch cache efficiency {cache_eff:.2%} below 60% target"
    assert cache_eff <= 0.85


def test_index_interactions_batch_no_single_dedup_key():
    """Test batch mode doesn't set single dedup key"""
    input_data = BatchIndexerInput(
        user_id="user123",
        interactions=[
            {"id": "INT_001", "message": "Query 1"},
            {"id": "INT_002", "message": "Query 2"},
        ]
    )
    
    output = index_interactions_batch(input_data, use_mock=True)
    
    # Batch doesn't have single dedup key (multiple items)
    assert output.dedup_key is None


# ============================================================================
# Performance Metrics Tests
# ============================================================================

def test_analyze_indexer_performance_single():
    """Test performance analysis for single output"""
    input_data = IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Test",
        mode=IndexingMode.REALTIME
    )
    
    output = index_interaction(input_data, use_mock=True)
    metrics = analyze_indexer_performance([output])
    
    assert 0.0 <= metrics.cache_efficiency <= 1.0
    assert 0.0 <= metrics.cost_savings_pct <= 100.0
    assert metrics.avg_processing_time_ms > 0.0


def test_analyze_indexer_performance_multiple():
    """Test performance analysis across multiple outputs"""
    outputs = []
    for i in range(5):
        input_data = IndexerInput(
            user_id="user123",
            interaction_id=f"INT_{i:03d}",
            message=f"Query {i}",
            mode=IndexingMode.REALTIME
        )
        output = index_interaction(input_data, use_mock=True)
        outputs.append(output)
    
    metrics = analyze_indexer_performance(outputs)
    
    assert metrics.cache_efficiency >= 0.80  # REALTIME target
    assert metrics.cost_savings_pct >= 40.0
    assert metrics.dedup_rate == 1.0  # All REALTIME have dedup_key


def test_analyze_indexer_performance_mixed_modes():
    """Test performance analysis with mixed REALTIME and BATCH"""
    outputs = []
    
    # Add REALTIME outputs
    for i in range(3):
        input_data = IndexerInput(
            user_id="user123",
            interaction_id=f"INT_{i:03d}",
            message=f"Query {i}",
            mode=IndexingMode.REALTIME
        )
        output = index_interaction(input_data, use_mock=True)
        outputs.append(output)
    
    # Add BATCH output
    batch_input = BatchIndexerInput(
        user_id="user123",
        interactions=[
            {"id": "INT_010", "message": "Batch 1"},
            {"id": "INT_011", "message": "Batch 2"},
        ]
    )
    batch_output = index_interactions_batch(batch_input, use_mock=True)
    outputs.append(batch_output)
    
    metrics = analyze_indexer_performance(outputs)
    
    # Should have reasonable efficiency (mix of REALTIME + BATCH)
    assert metrics.cache_efficiency >= 0.70
    assert metrics.cost_savings_pct >= 35.0


def test_analyze_indexer_performance_empty():
    """Test performance analysis handles empty input"""
    metrics = analyze_indexer_performance([])
    
    assert metrics.cache_efficiency == 0.0
    assert metrics.cost_savings_pct == 0.0
    assert metrics.avg_processing_time_ms == 0.0
    assert metrics.dedup_rate == 0.0


# ============================================================================
# Integration Tests
# ============================================================================

def test_realtime_to_batch_comparison():
    """Test REALTIME vs BATCH mode efficiency comparison"""
    # Single interaction in REALTIME
    realtime_input = IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Test query for comparison",
        mode=IndexingMode.REALTIME
    )
    realtime_output = index_interaction(realtime_input, use_mock=True)
    realtime_eff = realtime_output.cached_tokens / realtime_output.total_tokens
    
    # Same interaction in BATCH
    batch_input = BatchIndexerInput(
        user_id="user123",
        interactions=[
            {"id": "INT_001", "message": "Test query for comparison"}
        ]
    )
    batch_output = index_interactions_batch(batch_input, use_mock=True)
    batch_eff = batch_output.cached_tokens / batch_output.total_tokens
    
    # REALTIME should have equal or better cache efficiency than BATCH
    assert realtime_eff >= batch_eff * 0.95  # Allow 5% variance


def test_prompt_caching_consistency():
    """Test prompt structure is consistent for caching"""
    interactions1 = [{"interaction_id": "INT_001", "user_message": "Test"}]
    interactions2 = [{"interaction_id": "INT_002", "user_message": "Different"}]
    
    prompt1 = build_cacheable_prompt(interactions1)
    prompt2 = build_cacheable_prompt(interactions2)
    
    # Static prefix should be identical (cached part)
    system_prompt = get_indexer_system_prompt()
    schema_str = "Output Schema:"
    
    prefix1_end = prompt1.index("Now index these interactions:")
    prefix2_end = prompt2.index("Now index these interactions:")
    
    prefix1 = prompt1[:prefix1_end]
    prefix2 = prompt2[:prefix2_end]
    
    # Static prefixes must be identical for caching to work
    assert prefix1 == prefix2, "Static prompt prefix varies - breaks caching!"
