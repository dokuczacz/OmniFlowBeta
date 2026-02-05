"""
Tests for WP6 FAST Context Builder

Phase 4 Work Unit 2: FAST context assembly with caching optimization
"""

import unittest
from datetime import datetime, timezone
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from tool_call_handler.wp6.fast_context import (
    assemble_quick_context,
    analyze_caching_potential,
    QUICK_MODE_DIRECTIVE
)
from tool_call_handler.wp6.schemas import (
    ContextBuilderInput,
    PreferencesV1,
    ContextPackV1
)
from pydantic import ValidationError


class TestAssembleQuickContext(unittest.TestCase):
    """Test suite for quick context assembly function"""
    
    def test_minimal_input_creates_valid_package(self):
        """Test that minimal input produces valid ContextPackV1"""
        builder_input = ContextBuilderInput(
            user_id="tester-001",
            message="Hello there"
        )
        
        result = assemble_quick_context(builder_input)
        
        self.assertIsInstance(result, ContextPackV1)
        self.assertEqual(result.mode, "FAST")
        self.assertTrue(result.run_id.startswith("exec-quick-"))
        self.assertIn("L0", result.layers)
        self.assertIn("L1", result.layers)
        self.assertIn("L2", result.layers)
        self.assertIn("L3", result.layers)
    
    def test_layer_zero_contains_directive_and_catalog(self):
        """Test L0 layer structure for cache-friendly content"""
        builder_input = ContextBuilderInput(
            user_id="tester-002",
            message="Query text"
        )
        
        result = assemble_quick_context(builder_input)
        
        self.assertIn("directive", result.layers["L0"])
        self.assertIn("capability_catalog", result.layers["L0"])
        self.assertEqual(result.layers["L0"]["directive"], QUICK_MODE_DIRECTIVE.strip())
        self.assertIn("read_blob_file", result.layers["L0"]["capability_catalog"])
    
    def test_preferences_populate_layer_one(self):
        """Test that user preferences are correctly placed in L1"""
        builder_input = ContextBuilderInput(
            user_id="tester-003",
            message="Test message"
        )
        prefs = PreferencesV1(
            context_mode="FAST",
            max_recent_turns=3,
            custom_settings={"theme": "dark"}
        )
        
        result = assemble_quick_context(builder_input, user_prefs=prefs)
        
        self.assertEqual(result.layers["L1"]["mode_preference"], "FAST")
        self.assertEqual(result.layers["L1"]["conversation_depth"], 3)
        self.assertEqual(result.layers["L1"]["extensions"], {"theme": "dark"})
    
    def test_chat_history_limited_to_depth(self):
        """Test conversation history respects depth limit"""
        builder_input = ContextBuilderInput(
            user_id="tester-004",
            message="Current question"
        )
        history = [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Response 2"},
            {"role": "user", "content": "Turn 3"},
            {"role": "assistant", "content": "Response 3"},
            {"role": "user", "content": "Turn 4"},
            {"role": "assistant", "content": "Response 4"},
            {"role": "user", "content": "Turn 5"},
        ]
        
        result = assemble_quick_context(builder_input, chat_history=history)
        
        # Default depth is 4, should take last 4 items
        self.assertEqual(len(result.layers["L2"]), 4)
        self.assertEqual(result.layers["L2"][0]["content"], "Response 3")
    
    def test_preferences_override_conversation_depth(self):
        """Test that preferences can override default conversation depth"""
        builder_input = ContextBuilderInput(
            user_id="tester-005",
            message="Question"
        )
        prefs = PreferencesV1(max_recent_turns=2)
        history = [
            {"role": "user", "content": "A"},
            {"role": "assistant", "content": "B"},
            {"role": "user", "content": "C"},
            {"role": "assistant", "content": "D"},
        ]
        
        result = assemble_quick_context(builder_input, user_prefs=prefs, chat_history=history)
        
        self.assertEqual(len(result.layers["L2"]), 2)
        self.assertEqual(result.layers["L2"][0]["content"], "C")
    
    def test_layer_three_empty_in_quick_mode(self):
        """Test that L3 (semantic retrieval) is empty for FAST mode"""
        builder_input = ContextBuilderInput(
            user_id="tester-006",
            message="Test"
        )
        
        result = assemble_quick_context(builder_input)
        
        self.assertEqual(result.layers["L3"], [])
    
    def test_budget_constraints_set_correctly(self):
        """Test resource budgets match FAST mode specifications"""
        builder_input = ContextBuilderInput(
            user_id="tester-007",
            message="Budget test"
        )
        
        result = assemble_quick_context(builder_input)
        
        self.assertEqual(result.budgets["token_limit"], 2000)
        self.assertEqual(result.budgets["byte_limit"], 64000)
        self.assertEqual(result.budgets["max_sources"], 4)
    
    def test_custom_token_limit_respected(self):
        """Test that custom max_tokens overrides default but caps at 2000"""
        builder_input_low = ContextBuilderInput(
            user_id="tester-008",
            message="Low limit",
            max_tokens=1500
        )
        builder_input_high = ContextBuilderInput(
            user_id="tester-009",
            message="High limit",
            max_tokens=5000
        )
        
        result_low = assemble_quick_context(builder_input_low)
        result_high = assemble_quick_context(builder_input_high)
        
        self.assertEqual(result_low.budgets["token_limit"], 1500)
        self.assertEqual(result_high.budgets["token_limit"], 2000)  # Capped
    
    def test_token_estimation_reasonable(self):
        """Test that token estimation produces sensible values"""
        builder_input = ContextBuilderInput(
            user_id="tester-010",
            message="This is a test message with several words"
        )
        
        result = assemble_quick_context(builder_input)
        
        # Should be > 0 and < 2000 for FAST mode
        self.assertGreater(result.pack_tokens_est, 0)
        self.assertLess(result.pack_tokens_est, 2000)
    
    def test_correlation_id_propagated(self):
        """Test that correlation_id from input appears in output"""
        builder_input = ContextBuilderInput(
            user_id="tester-011",
            message="Correlation test",
            correlation_id="trace-12345"
        )
        
        result = assemble_quick_context(builder_input)
        
        self.assertEqual(result.correlation_id, "trace-12345")
    
    def test_execution_id_generation(self):
        """Test automatic execution ID generation"""
        builder_input = ContextBuilderInput(
            user_id="tester-012",
            message="ID test"
        )
        
        result = assemble_quick_context(builder_input)
        
        self.assertTrue(result.run_id.startswith("exec-quick-"))
        self.assertGreater(len(result.run_id), 15)  # Should include timestamp
    
    def test_custom_execution_id_used(self):
        """Test that provided execution_id is used instead of generated"""
        builder_input = ContextBuilderInput(
            user_id="tester-013",
            message="Custom ID"
        )
        custom_id = "my-custom-run-id-999"
        
        result = assemble_quick_context(builder_input, execution_id=custom_id)
        
        self.assertEqual(result.run_id, custom_id)
    
    def test_timestamp_format_iso8601(self):
        """Test that created_utc follows ISO8601 format"""
        builder_input = ContextBuilderInput(
            user_id="tester-014",
            message="Timestamp test"
        )
        
        result = assemble_quick_context(builder_input)
        
        # Should parse as ISO8601
        parsed = datetime.fromisoformat(result.created_utc.replace('Z', '+00:00'))
        self.assertIsNotNone(parsed.tzinfo)
    
    def test_empty_chat_history_handled(self):
        """Test that empty chat history doesn't cause errors"""
        builder_input = ContextBuilderInput(
            user_id="tester-015",
            message="Empty history test"
        )
        
        result = assemble_quick_context(builder_input, chat_history=[])
        
        self.assertEqual(result.layers["L2"], [])
    
    def test_none_chat_history_handled(self):
        """Test that None chat history doesn't cause errors"""
        builder_input = ContextBuilderInput(
            user_id="tester-016",
            message="None history test"
        )
        
        result = assemble_quick_context(builder_input, chat_history=None)
        
        self.assertEqual(result.layers["L2"], [])


class TestAnalyzeCachingPotential(unittest.TestCase):
    """Test suite for cache analysis function"""
    
    def test_cache_analysis_returns_required_fields(self):
        """Test that all expected metrics are returned"""
        builder_input = ContextBuilderInput(
            user_id="tester-017",
            message="Analysis test"
        )
        package = assemble_quick_context(builder_input)
        
        metrics = analyze_caching_potential(package)
        
        self.assertIn("cacheable_tokens", metrics)
        self.assertIn("ephemeral_tokens", metrics)
        self.assertIn("efficiency_ratio", metrics)
        self.assertIn("savings_estimate", metrics)
        self.assertIn("total_token_count", metrics)
    
    def test_efficiency_ratio_above_target(self):
        """Test that FAST mode achieves >80% cacheability target"""
        builder_input = ContextBuilderInput(
            user_id="tester-018",
            message="Short query"
        )
        package = assemble_quick_context(builder_input)
        
        metrics = analyze_caching_potential(package)
        
        # FAST mode should have >80% of tokens cacheable
        self.assertGreater(metrics["efficiency_ratio"], 0.80)
    
    def test_savings_estimate_calculation(self):
        """Test that savings estimate is half of efficiency ratio"""
        builder_input = ContextBuilderInput(
            user_id="tester-019",
            message="Savings test"
        )
        package = assemble_quick_context(builder_input)
        
        metrics = analyze_caching_potential(package)
        
        expected_savings = metrics["efficiency_ratio"] * 0.5
        self.assertAlmostEqual(metrics["savings_estimate"], expected_savings, places=3)
    
    def test_token_counts_sum_to_total(self):
        """Test that cacheable + ephemeral = total"""
        builder_input = ContextBuilderInput(
            user_id="tester-020",
            message="Sum test"
        )
        package = assemble_quick_context(builder_input)
        
        metrics = analyze_caching_potential(package)
        
        calculated_total = metrics["cacheable_tokens"] + metrics["ephemeral_tokens"]
        self.assertEqual(calculated_total, metrics["total_token_count"])
    
    def test_zero_token_package_handled(self):
        """Test edge case of zero tokens (shouldn't happen but handle gracefully)"""
        # Create a mock package with zero tokens
        builder_input = ContextBuilderInput(
            user_id="tester-021",
            message=""
        )
        package = assemble_quick_context(builder_input)
        package.pack_tokens_est = 0  # Force zero for test
        
        metrics = analyze_caching_potential(package)
        
        # Should not crash, ratio should be 0
        self.assertEqual(metrics["efficiency_ratio"], 0)


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple components"""
    
    def test_full_workflow_with_all_options(self):
        """Test complete workflow with all optional parameters"""
        builder_input = ContextBuilderInput(
            user_id="integration-001",
            message="Full workflow test",
            mode="FAST",
            correlation_id="int-trace-456",
            max_tokens=1800
        )
        prefs = PreferencesV1(
            context_mode="AUTO",
            max_recent_turns=3,
            custom_settings={"feature_flags": {"beta": True}}
        )
        history = [
            {"role": "user", "content": "Previous question 1"},
            {"role": "assistant", "content": "Previous answer 1"},
            {"role": "user", "content": "Previous question 2"},
            {"role": "assistant", "content": "Previous answer 2"},
        ]
        execution_id = "integration-exec-999"
        
        package = assemble_quick_context(
            builder_input,
            user_prefs=prefs,
            chat_history=history,
            execution_id=execution_id
        )
        
        # Validate all aspects
        self.assertEqual(package.run_id, execution_id)
        self.assertEqual(package.correlation_id, "int-trace-456")
        self.assertEqual(package.budgets["token_limit"], 1800)
        self.assertEqual(len(package.layers["L2"]), 3)  # Capped by prefs
        self.assertTrue(package.layers["L1"]["extensions"]["feature_flags"]["beta"])
        
        # Analyze caching
        metrics = analyze_caching_potential(package)
        self.assertGreater(metrics["efficiency_ratio"], 0.75)
    
    def test_schema_validation_catches_invalid_package(self):
        """Test that ContextPackV1 schema validates correctly"""
        builder_input = ContextBuilderInput(
            user_id="validation-001",
            message="Validation test"
        )
        
        package = assemble_quick_context(builder_input)
        
        # This should not raise - package is valid
        self.assertEqual(package.schema_version, "omniflow.context_pack.v1")
        self.assertEqual(package.mode, "FAST")
        
        # Attempting to create invalid package should fail
        with self.assertRaises(ValidationError):
            ContextPackV1(
                run_id="test",
                mode="INVALID_MODE",  # Invalid mode
                budgets={},
                layers={},
                created_utc=datetime.now(timezone.utc).isoformat(),
                pack_tokens_est=100
            )


if __name__ == '__main__':
    unittest.main()
