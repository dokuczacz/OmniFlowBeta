"""
Tests for DEEP context builder module.

Tests cover:
- DEEP mode context pack creation
- Layer structure and content
- Budget configuration
- Token estimation
- Prompt caching efficiency
- Preference application
- Semantic search integration
- Conversation history handling
"""

import pytest
from datetime import datetime, timezone

from backend.tool_call_handler.wp6.deep_context import (
    assemble_comprehensive_context,
    analyze_deep_caching_potential
)
from backend.tool_call_handler.wp6.schemas import (
    ContextBuilderInput,
    ContextPackV1,
    PreferencesV1
)


class TestDeepContextCreation:
    """Test basic DEEP context pack creation."""
    
    def test_basic_deep_context_creation(self):
        """Test creating DEEP context with minimal input."""
        input_data = ContextBuilderInput(
            user_id="user-deep-001",
            message="Explain quantum entanglement in detail"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # Should return valid ContextPackV1
        assert isinstance(pack, ContextPackV1)
        assert pack.mode == "DEEP"
        assert pack.run_id.startswith("exec-")
    
    def test_deep_layer_structure(self):
        """Test that DEEP mode has all required layers."""
        input_data = ContextBuilderInput(
            user_id="user-deep-002",
            message="Comprehensive analysis needed"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # All four layers must exist
        assert "L0" in pack.layers
        assert "L1" in pack.layers
        assert "L2" in pack.layers
        assert "L3" in pack.layers
        
        # L0 should have invariant content
        assert "directive" in pack.layers["L0"]
        assert "capability_catalog" in pack.layers["L0"]
        assert "few_shot_examples" in pack.layers["L0"]
        
        # L3 should have semantic results
        assert "semantic_results" in pack.layers["L3"]
        assert isinstance(pack.layers["L3"]["semantic_results"], list)
    
    def test_deep_budgets_higher_than_fast(self):
        """Test that DEEP mode has higher resource budgets."""
        input_data = ContextBuilderInput(
            user_id="user-deep-003",
            message="Complex query"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # DEEP mode should have generous budgets
        assert pack.budgets["token_limit"] == 8000  # vs 2000 for FAST
        assert pack.budgets["byte_limit"] == 256000  # vs 64000 for FAST
        assert pack.budgets["max_sources"] == 12  # vs 4 for FAST
    
    def test_token_estimation_reasonable(self):
        """Test token estimation is in expected range."""
        input_data = ContextBuilderInput(
            user_id="user-deep-004",
            message="Test message"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # DEEP mode with examples should be larger than FAST
        # Typical range: 3000-5000 tokens
        assert pack.pack_tokens_est > 2000
        assert pack.pack_tokens_est < 10000


class TestDeepCachingEfficiency:
    """Test prompt caching optimization for DEEP mode."""
    
    def test_cache_efficiency_exceeds_target(self):
        """Test that DEEP mode achieves >90% cache efficiency."""
        input_data = ContextBuilderInput(
            user_id="user-deep-005",
            message="Short query"
        )
        
        pack = assemble_comprehensive_context(input_data)
        metrics = analyze_deep_caching_potential(pack)
        
        # DEEP mode target: >90% efficiency
        assert metrics["efficiency_ratio"] > 0.90
        assert metrics["estimated_savings"] > 0.45  # ~50% of 90%
    
    def test_realistic_deep_query_cache_efficiency(self):
        """Test caching with realistic complex query."""
        input_data = ContextBuilderInput(
            user_id="user-deep-006",
            message=(
                "I need a comprehensive analysis of the quarterly financial reports "
                "including revenue trends, expense breakdowns, and year-over-year "
                "comparisons. Please also identify any anomalies or areas of concern "
                "that require immediate attention from the management team."
            )
        )
        
        pack = assemble_comprehensive_context(input_data)
        metrics = analyze_deep_caching_potential(pack)
        
        # Even with longer query, should maintain >88% efficiency
        assert metrics["efficiency_ratio"] > 0.88
        assert metrics["estimated_savings"] > 0.44
    
    def test_cache_breakdown_structure(self):
        """Test that cache analysis provides layer breakdown."""
        input_data = ContextBuilderInput(
            user_id="user-deep-007",
            message="Test"
        )
        
        pack = assemble_comprehensive_context(input_data)
        metrics = analyze_deep_caching_potential(pack)
        
        # Should have detailed breakdown
        assert "cache_breakdown" in metrics
        assert "L0_invariant" in metrics["cache_breakdown"]
        assert "L1_config" in metrics["cache_breakdown"]
        assert "L2_conversation" in metrics["cache_breakdown"]
        assert "L3_semantic" in metrics["cache_breakdown"]
        
        # L0 should be the largest (examples + catalog)
        assert metrics["cache_breakdown"]["L0_invariant"] > metrics["cache_breakdown"]["L1_config"]


class TestPreferencesAndCustomization:
    """Test preference and custom parameter handling."""
    
    def test_preferences_applied_to_layer_1(self):
        """Test user preferences are included in L1."""
        prefs = PreferencesV1(
            user_id="user-deep-008",
            context_mode_preference="DEEP",
            max_recent_turns=6
        )
        
        input_data = ContextBuilderInput(
            user_id="user-deep-008",
            message="Test"
        )
        
        pack = assemble_comprehensive_context(input_data, user_prefs=prefs)
        
        # Preferences should be in L1
        assert pack.layers["L1"]["preferences"]["context_mode_preference"] == "DEEP"
        assert pack.layers["L1"]["preferences"]["max_recent_turns"] == 6
    
    def test_conversation_depth_respects_preferences(self):
        """Test conversation history respects max_recent_turns."""
        prefs = PreferencesV1(
            user_id="user-deep-009",
            context_mode_preference="DEEP",
            max_recent_turns=3  # Limited depth
        )
        
        input_data = ContextBuilderInput(
            user_id="user-deep-009",
            message="Test"
        )
        
        pack = assemble_comprehensive_context(input_data, user_prefs=prefs)
        
        # Should respect limit (3 turns = 6 messages max)
        assert pack.layers["L2"]["depth_limit"] == 3
        assert pack.layers["L2"]["turn_count"] <= 3
    
    def test_custom_token_limit(self):
        """Test custom token limit is respected and capped."""
        input_data = ContextBuilderInput(
            user_id="user-deep-010",
            message="Test"
        )
        
        # Request 10000 tokens (should be capped at 8000)
        pack = assemble_comprehensive_context(
            input_data,
            custom_params={"max_tokens": 10000}
        )
        
        assert pack.budgets["token_limit"] == 8000  # Capped
    
    def test_correlation_id_propagated(self):
        """Test correlation ID is included when provided."""
        input_data = ContextBuilderInput(
            user_id="user-deep-011",
            message="Test",
            correlation_id="corr-abc-123"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        assert pack.correlation_id == "corr-abc-123"
    
    def test_custom_execution_id(self):
        """Test custom execution ID can be provided."""
        input_data = ContextBuilderInput(
            user_id="user-deep-012",
            message="Test"
        )
        
        pack = assemble_comprehensive_context(
            input_data,
            custom_params={"exec_id": "custom-exec-999"}
        )
        
        assert pack.run_id == "custom-exec-999"


class TestSemanticSearchIntegration:
    """Test semantic search L3 layer."""
    
    def test_l3_contains_semantic_results(self):
        """Test L3 layer has semantic search results."""
        input_data = ContextBuilderInput(
            user_id="user-deep-013",
            message="quantum computing applications"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # L3 should have results
        assert "semantic_results" in pack.layers["L3"]
        assert len(pack.layers["L3"]["semantic_results"]) > 0
        
        # Each result should have expected fields
        first_result = pack.layers["L3"]["semantic_results"][0]
        assert "id" in first_result
        assert "score" in first_result
        assert "title" in first_result
    
    def test_semantic_results_limited_by_budget(self):
        """Test semantic results respect max_sources budget."""
        input_data = ContextBuilderInput(
            user_id="user-deep-014",
            message="broad query"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # Should not exceed max_sources
        max_sources = pack.budgets["max_sources"]
        result_count = len(pack.layers["L3"]["semantic_results"])
        assert result_count <= max_sources


class TestSchemaCompliance:
    """Test schema validation and compliance."""
    
    def test_output_is_valid_context_pack_v1(self):
        """Test output validates against ContextPackV1 schema."""
        input_data = ContextBuilderInput(
            user_id="user-deep-015",
            message="Test"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # Should be valid ContextPackV1 (Pydantic validation)
        assert isinstance(pack, ContextPackV1)
        assert pack.schema_version == "omniflow.context_pack.v1"
        assert pack.mode == "DEEP"
    
    def test_timestamp_is_iso8601(self):
        """Test created_utc is valid ISO8601 timestamp."""
        input_data = ContextBuilderInput(
            user_id="user-deep-016",
            message="Test"
        )
        
        pack = assemble_comprehensive_context(input_data)
        
        # Should parse as ISO8601
        timestamp = datetime.fromisoformat(pack.created_utc.replace("Z", "+00:00"))
        assert isinstance(timestamp, datetime)


class TestIntegration:
    """Integration tests combining multiple features."""
    
    def test_input_to_pack_workflow(self):
        """Test complete workflow from input to validated pack."""
        # User input
        input_data = ContextBuilderInput(
            user_id="user-deep-017",
            message="Comprehensive analysis of market trends",
            mode="DEEP",
            correlation_id="workflow-test-001"
        )
        
        # User preferences
        prefs = PreferencesV1(
            user_id="user-deep-017",
            context_mode_preference="DEEP",
            max_recent_turns=8
        )
        
        # Create pack
        pack = assemble_comprehensive_context(input_data, user_prefs=prefs)
        
        # Verify complete workflow
        assert pack.mode == "DEEP"
        assert pack.correlation_id == "workflow-test-001"
        assert pack.layers["L1"]["preferences"]["max_recent_turns"] == 8
        assert len(pack.layers["L3"]["semantic_results"]) > 0
        
        # Analyze caching
        metrics = analyze_deep_caching_potential(pack)
        assert metrics["efficiency_ratio"] > 0.90
    
    def test_deep_vs_fast_comparison(self):
        """Test DEEP mode is more comprehensive than FAST."""
        from backend.tool_call_handler.wp6.fast_context import assemble_quick_context
        
        input_data = ContextBuilderInput(
            user_id="user-compare-001",
            message="Same query for both modes"
        )
        
        fast_pack = assemble_quick_context(input_data)
        deep_pack = assemble_comprehensive_context(input_data)
        
        # DEEP should have higher budgets
        assert deep_pack.budgets["token_limit"] > fast_pack.budgets["token_limit"]
        assert deep_pack.budgets["max_sources"] > fast_pack.budgets["max_sources"]
        
        # DEEP should have examples (FAST doesn't)
        assert "few_shot_examples" in deep_pack.layers["L0"]
        assert "few_shot_examples" not in fast_pack.layers["L0"]
        
        # DEEP should have semantic results (FAST has empty L3)
        assert len(deep_pack.layers["L3"]["semantic_results"]) > 0
        assert len(fast_pack.layers["L3"]) == 0  # Empty dict for FAST
