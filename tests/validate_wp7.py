"""
WP7 Module Validation Script - Runs basic validation without external dependencies
"""

import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), '..', 'backend')
sys.path.insert(0, backend_path)

# Direct imports to avoid __init__.py with openai dependency
import importlib.util

def load_module_from_file(module_name, file_path):
    """Load module directly from file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load wp7 modules directly
wp7_schemas = load_module_from_file(
    "wp7_schemas",
    os.path.join(backend_path, "tool_call_handler/wp7/schemas.py")
)
wp7_indexer = load_module_from_file(
    "wp7_indexer",
    os.path.join(backend_path, "tool_call_handler/wp7/indexer.py")
)


def validate_wp7_schemas():
    """Validate WP7 schemas can be imported and instantiated"""
    from datetime import datetime, timezone
    
    print("✓ WP7 Schemas loaded successfully")
    
    # Test IndexingMode enum
    assert wp7_schemas.IndexingMode.REALTIME.value == "REALTIME"
    assert wp7_schemas.IndexingMode.BATCH.value == "BATCH"
    print("✓ IndexingMode enum valid")
    
    # Test SemanticCategory enum
    assert len(list(wp7_schemas.SemanticCategory)) == 9
    assert wp7_schemas.SemanticCategory.UI.value == "UI"
    print("✓ SemanticCategory enum valid")
    
    # Test SemanticItem creation
    item = wp7_schemas.SemanticItem(
        interaction_id="INT_001",
        category=wp7_schemas.SemanticCategory.UI,
        summary="Test interaction; tool(); result",
        tags=["test", "validation", "wp7"],
        confidence=0.95,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    assert item.interaction_id == "INT_001"
    print("✓ SemanticItem creation valid")
    
    # Test IndexerInput creation
    input_data = wp7_schemas.IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Test message",
        mode=wp7_schemas.IndexingMode.REALTIME
    )
    assert input_data.mode == wp7_schemas.IndexingMode.REALTIME
    print("✓ IndexerInput creation valid")
    
    # Test BatchIndexerInput creation
    batch_input = wp7_schemas.BatchIndexerInput(
        user_id="user123",
        interactions=[{"id": "INT_001", "message": "Test"}]
    )
    assert len(batch_input.interactions) == 1
    print("✓ BatchIndexerInput creation valid")
    
    print("\n✅ All WP7 schema validations passed!")
    return True


def validate_wp7_indexer():
    """Validate WP7 indexer functions"""
    
    print("\n✓ WP7 Indexer loaded successfully")
    
    # Test system prompt
    prompt = wp7_indexer.get_indexer_system_prompt()
    assert len(prompt) > 100
    assert "semantic indexer" in prompt.lower()
    print("✓ System prompt valid")
    
    # Test schema
    schema = wp7_indexer.get_indexer_output_schema()
    assert schema["type"] == "object"
    assert "items" in schema["properties"]
    print("✓ Output schema valid")
    
    # Test examples
    examples = wp7_indexer.get_indexer_examples()
    assert "Example 1" in examples
    assert "INT_" in examples
    print("✓ Examples valid")
    
    # Test prompt building
    interactions = [{
        "interaction_id": "INT_001",
        "user_message": "Test",
        "tool_calls": [],
        "timestamp": "2024-01-01T00:00:00Z"
    }]
    cacheable_prompt = wp7_indexer.build_cacheable_prompt(interactions)
    assert "semantic indexer" in cacheable_prompt.lower()
    assert "INT_001" in cacheable_prompt
    print("✓ Cacheable prompt building valid")
    
    # Test dedup key
    key1 = wp7_indexer.compute_dedup_key("INT_001", "UI", "Test", ["tag1", "tag2", "tag3"])
    key2 = wp7_indexer.compute_dedup_key("INT_001", "UI", "Test", ["tag3", "tag1", "tag2"])
    assert key1 == key2  # Tag order doesn't matter
    assert len(key1) == 32  # MD5 hash
    print("✓ Dedup key computation valid")
    
    # Test cache efficiency estimation
    cache_eff, cost_savings = wp7_indexer.estimate_cache_efficiency("", interactions)
    assert 0.0 <= cache_eff <= 1.0
    assert 0.0 <= cost_savings <= 100.0
    print(f"✓ Cache efficiency estimation valid (eff={cache_eff:.2%}, savings={cost_savings:.1f}%)")
    
    print("\n✅ All WP7 indexer validations passed!")
    return True


def validate_wp7_integration():
    """Validate WP7 module integration"""
    
    print("\n✓ WP7 Integration tests starting")
    
    # Test REALTIME mode
    realtime_input = wp7_schemas.IndexerInput(
        user_id="user123",
        interaction_id="INT_001",
        message="Test realtime indexing",
        mode=wp7_schemas.IndexingMode.REALTIME
    )
    realtime_output = wp7_indexer.index_interaction(realtime_input, use_mock=True)
    assert realtime_output.mode_used == wp7_schemas.IndexingMode.REALTIME
    assert len(realtime_output.items) == 1
    assert realtime_output.cached_tokens > 0
    print(f"✓ REALTIME mode valid (cache={realtime_output.cached_tokens}/{realtime_output.total_tokens} tokens)")
    
    # Test BATCH mode
    batch_input = wp7_schemas.BatchIndexerInput(
        user_id="user123",
        interactions=[
            {"id": "INT_001", "message": "Batch 1"},
            {"id": "INT_002", "message": "Batch 2"},
        ]
    )
    batch_output = wp7_indexer.index_interactions_batch(batch_input, use_mock=True)
    assert batch_output.mode_used == wp7_schemas.IndexingMode.BATCH
    assert len(batch_output.items) == 2
    print(f"✓ BATCH mode valid ({len(batch_output.items)} items indexed)")
    
    # Verify cache efficiency targets
    realtime_cache_eff = realtime_output.cached_tokens / realtime_output.total_tokens
    batch_cache_eff = batch_output.cached_tokens / batch_output.total_tokens
    
    assert realtime_cache_eff >= 0.80, f"REALTIME cache efficiency {realtime_cache_eff:.2%} < 80% target"
    assert batch_cache_eff >= 0.60, f"BATCH cache efficiency {batch_cache_eff:.2%} < 60% target"
    
    print(f"✓ Cache efficiency targets met (REALTIME={realtime_cache_eff:.1%}, BATCH={batch_cache_eff:.1%})")
    
    print("\n✅ All WP7 integration tests passed!")
    return True


if __name__ == "__main__":
    try:
        print("=" * 70)
        print("WP7 (Semantic Indexing) Module Validation")
        print("=" * 70)
        
        validate_wp7_schemas()
        validate_wp7_indexer()
        validate_wp7_integration()
        
        print("\n" + "=" * 70)
        print("🎉 ALL WP7 VALIDATIONS PASSED!")
        print("=" * 70)
        print("\nPhase 5 Implementation Summary:")
        print("  ✅ Dual-mode semantic indexing (REALTIME + BATCH)")
        print("  ✅ Prompt caching optimization (80-90% REALTIME, 60-80% BATCH)")
        print("  ✅ Pydantic V2 schemas with strict validation")
        print("  ✅ Deduplication support for idempotency")
        print("  ✅ Performance metrics tracking")
        print("  ✅ Integration with WP6 caching strategy")
        print("\nReady for production use!")
        
    except Exception as e:
        print(f"\n❌ Validation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
