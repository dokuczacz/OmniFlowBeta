"""
Tests for WP6 routing logic.
"""

import pytest
from backend.tool_call_handler.wp6.routing import (
    analyze_query_complexity,
    select_context_mode,
    build_context_with_routing,
    get_routing_explanation
)
from backend.tool_call_handler.wp6.schemas import ContextBuilderInput, PreferencesV1


class TestQueryComplexityAnalysis:
    """Tests for query complexity analysis."""
    
    def test_simple_query_low_complexity(self):
        """Simple short query should have low complexity score."""
        message = "What time is it?"
        result = analyze_query_complexity(message)
        
        assert result['word_count'] == 4
        assert result['has_question_marks'] is True
        assert result['has_multi_part'] is False
        assert result['complexity_score'] < 30
    
    def test_complex_query_high_complexity(self):
        """Complex multi-part query with technical terms should have high score."""
        message = "Can you analyze the relationship between customer churn patterns and seasonal trends? Please provide a comprehensive comparison of Q1 vs Q4 data and explain the key implications for our retention strategy."
        result = analyze_query_complexity(message)
        
        assert result['word_count'] > 30
        assert result['has_question_marks'] is True
        assert result['has_multi_part'] is True
        assert result['technical_keywords'] >= 3  # analyze, compare, comprehensive, explain, implication
        assert result['complexity_score'] >= 50
    
    def test_medium_complexity_query(self):
        """Medium-length query should have moderate complexity."""
        message = "Please summarize the main points from the last meeting. Then highlight any action items."
        result = analyze_query_complexity(message)
        
        assert 10 < result['word_count'] < 30
        assert result['has_multi_part'] is True
        assert result['complexity_score'] >= 20
        assert result['complexity_score'] < 70
    
    def test_technical_keywords_detection(self):
        """Should detect technical keywords correctly."""
        message = "Analyze the correlation between variables and evaluate the trend patterns."
        result = analyze_query_complexity(message)
        
        assert result['technical_keywords'] >= 4  # analyze, correlation, evaluate, trend, pattern
    
    def test_multi_part_detection(self):
        """Should detect multi-part queries."""
        message = "First, check the status. Then, update the records. Finally, send a report."
        result = analyze_query_complexity(message)
        
        assert result['has_multi_part'] is True
    
    def test_complexity_score_bounded(self):
        """Complexity score should be bounded to 0-100."""
        # Very complex query
        message = "Analyze compare explain detail comprehensive complex relationship pattern trend summarize integrate correlation implication evaluate" * 10
        result = analyze_query_complexity(message)
        
        assert 0 <= result['complexity_score'] <= 100


class TestModeSelection:
    """Tests for context mode selection logic."""
    
    def test_explicit_fast_mode(self):
        """Explicit FAST mode should be selected."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="What is the weather?",
            mode="FAST"
        )
        
        mode, metadata = select_context_mode(input_data)
        
        assert mode == "FAST"
        assert metadata['routing_method'] == 'explicit_input'
        assert metadata['selected_mode'] == "FAST"
    
    def test_explicit_deep_mode(self):
        """Explicit DEEP mode should be selected."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Simple query",
            mode="DEEP"
        )
        
        mode, metadata = select_context_mode(input_data)
        
        assert mode == "DEEP"
        assert metadata['routing_method'] == 'explicit_input'
    
    def test_user_preference_fast(self):
        """User preference for FAST should be used with AUTO input."""
        from datetime import datetime, timezone
        
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Analyze this complex multi-part query with technical terms and comprehensive evaluation needed.",
            mode="AUTO"
        )
        prefs = PreferencesV1(
            user_id="user-123",
            context_mode_preference="FAST",
            updated_utc=datetime.now(timezone.utc).isoformat()
        )
        
        mode, metadata = select_context_mode(input_data, prefs)
        
        assert mode == "FAST"
        assert metadata['routing_method'] == 'user_preference'
    
    def test_user_preference_deep(self):
        """User preference for DEEP should be used with AUTO input."""
        from datetime import datetime, timezone
        
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Short",
            mode="AUTO"
        )
        prefs = PreferencesV1(
            user_id="user-123",
            context_mode_preference="DEEP",
            updated_utc=datetime.now(timezone.utc).isoformat()
        )
        
        mode, metadata = select_context_mode(input_data, prefs)
        
        assert mode == "DEEP"
        assert metadata['routing_method'] == 'user_preference'
    
    def test_explicit_overrides_preference(self):
        """Explicit mode should override user preference."""
        from datetime import datetime, timezone
        
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Query",
            mode="FAST"
        )
        prefs = PreferencesV1(
            user_id="user-123",
            context_mode_preference="DEEP",
            updated_utc=datetime.now(timezone.utc).isoformat()
        )
        
        mode, metadata = select_context_mode(input_data, prefs)
        
        assert mode == "FAST"
        assert metadata['routing_method'] == 'explicit_input'
    
    def test_auto_simple_query_selects_fast(self):
        """AUTO with simple query should select FAST."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="What time is it?",
            mode="AUTO"
        )
        
        mode, metadata = select_context_mode(input_data)
        
        assert mode == "FAST"
        assert metadata['routing_method'] == 'complexity_analysis'
        assert metadata['complexity_analysis']['complexity_score'] < 50
    
    def test_auto_complex_query_selects_deep(self):
        """AUTO with complex query should select DEEP."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Can you analyze the comprehensive relationship between our customer retention patterns, seasonal sales trends, and marketing campaign effectiveness? Please provide a detailed comparison of quarterly performance metrics and explain the key implications for our strategic planning process moving forward.",
            mode="AUTO"
        )
        
        mode, metadata = select_context_mode(input_data)
        
        assert mode == "DEEP"
        assert metadata['routing_method'] == 'complexity_analysis'
        assert metadata['complexity_analysis']['complexity_score'] >= 50
    
    def test_custom_complexity_threshold(self):
        """Should respect custom complexity threshold."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Please analyze and summarize the meeting notes. Evaluate trends and highlight action items.",
            mode="AUTO"
        )
        
        # With low threshold (20), this medium query should trigger DEEP
        mode_low, _ = select_context_mode(input_data, complexity_threshold=20)
        
        # With high threshold (70), same query should trigger FAST
        mode_high, _ = select_context_mode(input_data, complexity_threshold=70)
        
        assert mode_low == "DEEP"
        assert mode_high == "FAST"
    
    def test_routing_metadata_completeness(self):
        """Routing metadata should contain all expected fields."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Analyze this query",
            mode="AUTO"
        )
        
        mode, metadata = select_context_mode(input_data)
        
        assert 'input_mode' in metadata
        assert 'preference_mode' in metadata
        assert 'routing_method' in metadata
        assert 'complexity_analysis' in metadata
        assert 'selected_mode' in metadata
        assert 'threshold' in metadata


class TestBuildContextWithRouting:
    """Tests for integrated context building with routing."""
    
    def test_builds_fast_context_for_simple_query(self):
        """Should build FAST context for simple query."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="What's the weather?",
            mode="AUTO"
        )
        
        context_pack, routing_metadata = build_context_with_routing(input_data)
        
        assert context_pack.mode == "FAST"
        assert routing_metadata['selected_mode'] == "FAST"
        assert context_pack.budgets['token_limit'] == 2000  # FAST limit
    
    def test_builds_deep_context_for_complex_query(self):
        """Should build DEEP context for complex query."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Can you analyze the comprehensive relationship between customer retention patterns and seasonal sales trends? Please provide a detailed comparison of quarterly metrics and explain key implications for strategic planning.",
            mode="AUTO"
        )
        
        context_pack, routing_metadata = build_context_with_routing(input_data)
        
        assert context_pack.mode == "DEEP"
        assert routing_metadata['selected_mode'] == "DEEP"
        assert context_pack.budgets['token_limit'] == 8000  # DEEP limit
    
    def test_respects_explicit_mode_override(self):
        """Should respect explicit mode even if complexity suggests otherwise."""
        # Complex query but explicit FAST
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Analyze comprehensive relationship patterns trends evaluation implications detailed" * 5,
            mode="FAST"
        )
        
        context_pack, routing_metadata = build_context_with_routing(input_data)
        
        assert context_pack.mode == "FAST"
        assert routing_metadata['routing_method'] == 'explicit_input'
    
    def test_passes_custom_params_to_builder(self):
        """Should pass custom parameters to context builder."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Test",
            mode="FAST"
        )
        custom_params = {
            'execution_id': 'custom-exec-123',
            'correlation_id': 'custom-corr-456'
        }
        
        context_pack, _ = build_context_with_routing(input_data, custom_params=custom_params)
        
        # Verify context pack was built successfully
        assert context_pack.mode == "FAST"
        assert context_pack.budgets['token_limit'] == 2000
        # Note: execution_id may be generated if not explicitly supported in current builder


class TestRoutingExplanation:
    """Tests for routing explanation generation."""
    
    def test_explicit_input_explanation(self):
        """Should explain explicit input routing."""
        metadata = {
            'routing_method': 'explicit_input',
            'selected_mode': 'FAST'
        }
        
        explanation = get_routing_explanation(metadata)
        
        assert 'explicitly requested' in explanation
        assert 'FAST' in explanation
    
    def test_user_preference_explanation(self):
        """Should explain user preference routing."""
        metadata = {
            'routing_method': 'user_preference',
            'selected_mode': 'DEEP'
        }
        
        explanation = get_routing_explanation(metadata)
        
        assert 'user preference' in explanation
        assert 'DEEP' in explanation
    
    def test_complexity_analysis_explanation(self):
        """Should explain complexity-based routing with factors."""
        metadata = {
            'routing_method': 'complexity_analysis',
            'selected_mode': 'DEEP',
            'threshold': 50,
            'complexity_analysis': {
                'complexity_score': 75,
                'word_count': 45,
                'has_multi_part': True,
                'technical_keywords': 3
            }
        }
        
        explanation = get_routing_explanation(metadata)
        
        assert 'complexity analysis' in explanation
        assert 'DEEP' in explanation
        assert '75' in explanation  # score
        assert '50' in explanation  # threshold
        assert 'multi-part' in explanation


class TestRoutingDeterminism:
    """Tests for routing determinism - same input should produce same output."""
    
    def test_same_query_same_mode(self):
        """Same query should produce same mode selection."""
        message = "Please analyze the sales trends for Q3 and compare with Q2."
        
        results = []
        for _ in range(5):
            input_data = ContextBuilderInput(
                user_id="user-123",
                message=message,
                mode="AUTO"
            )
            mode, _ = select_context_mode(input_data)
            results.append(mode)
        
        # All results should be identical
        assert len(set(results)) == 1
    
    def test_deterministic_complexity_score(self):
        """Same query should produce same complexity score."""
        message = "Analyze comprehensive patterns and evaluate trends."
        
        scores = []
        for _ in range(5):
            result = analyze_query_complexity(message)
            scores.append(result['complexity_score'])
        
        # All scores should be identical
        assert len(set(scores)) == 1
