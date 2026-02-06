"""
Tests for WP6 schemas (ContextPackV1, PreferencesV1, ContextBuilderInput)

Phase 4 Work Unit 1: Schema validation
"""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from tool_call_handler.wp6.schemas import (
    ContextPackV1,
    PreferencesV1,
    ContextBuilderInput
)


class TestContextPackV1:
    """Tests for ContextPackV1 pydantic model."""
    
    def test_valid_context_pack_fast(self):
        """Test creating a valid FAST mode context pack."""
        pack = ContextPackV1(
            run_id="run-123",
            mode="FAST",
            budgets={
                "token_limit": 2000,
                "byte_limit": 64000,
                "max_sources": 4
            },
            layers={
                "L0": {"system": "prompt"},
                "L1": {"preferences": {}},
                "L2": {"recent": []},
                "L3": {"semantic": []}
            },
            created_utc=datetime.now(timezone.utc).isoformat(),
            pack_tokens_est=1500
        )
        
        assert pack.schema_version == "omniflow.context_pack.v1"
        assert pack.mode == "FAST"
        assert pack.budgets["token_limit"] == 2000
        assert pack.pack_tokens_est == 1500
    
    def test_valid_context_pack_deep(self):
        """Test creating a valid DEEP mode context pack."""
        pack = ContextPackV1(
            run_id="run-456",
            correlation_id="corr-789",
            mode="DEEP",
            budgets={
                "token_limit": 16000,
                "byte_limit": 128000,
                "max_sources": 12
            },
            layers={
                "L0": {"system": "prompt"},
                "L1": {"preferences": {"mode": "DEEP"}},
                "L2": {"recent": ["turn1", "turn2"]},
                "L3": {"semantic": ["doc1", "doc2", "doc3"]}
            },
            preferences={"enable_semantic": True},
            created_utc=datetime.now(timezone.utc).isoformat(),
            pack_tokens_est=15000,
            cache_metrics={"cached_tokens": 8000, "total_tokens": 10000}
        )
        
        assert pack.mode == "DEEP"
        assert pack.correlation_id == "corr-789"
        assert pack.cache_metrics["cached_tokens"] == 8000
    
    def test_missing_required_fields(self):
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextPackV1(
                run_id="run-123",
                mode="FAST"
                # Missing budgets, layers, created_utc, pack_tokens_est
            )
        
        error = exc_info.value
        assert "budgets" in str(error)
        assert "layers" in str(error)
    
    def test_invalid_mode(self):
        """Test that invalid mode raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextPackV1(
                run_id="run-123",
                mode="INVALID",  # Not "FAST" or "DEEP"
                budgets={"token_limit": 2000, "byte_limit": 64000, "max_sources": 4},
                layers={"L0": {}, "L1": {}, "L2": {}, "L3": {}},
                created_utc=datetime.now(timezone.utc).isoformat(),
                pack_tokens_est=1000
            )
        
        assert "mode" in str(exc_info.value)
    
    def test_missing_budget_fields(self):
        """Test that missing budget fields raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextPackV1(
                run_id="run-123",
                mode="FAST",
                budgets={"token_limit": 2000},  # Missing byte_limit, max_sources
                layers={"L0": {}, "L1": {}, "L2": {}, "L3": {}},
                created_utc=datetime.now(timezone.utc).isoformat(),
                pack_tokens_est=1000
            )
        
        error_str = str(exc_info.value)
        assert "budget" in error_str.lower()
    
    def test_missing_layers(self):
        """Test that missing layers raise validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextPackV1(
                run_id="run-123",
                mode="FAST",
                budgets={"token_limit": 2000, "byte_limit": 64000, "max_sources": 4},
                layers={"L0": {}, "L1": {}},  # Missing L2, L3
                created_utc=datetime.now(timezone.utc).isoformat(),
                pack_tokens_est=1000
            )
        
        error_str = str(exc_info.value)
        assert "layer" in error_str.lower()
    
    def test_invalid_timestamp(self):
        """Test that invalid timestamp raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextPackV1(
                run_id="run-123",
                mode="FAST",
                budgets={"token_limit": 2000, "byte_limit": 64000, "max_sources": 4},
                layers={"L0": {}, "L1": {}, "L2": {}, "L3": {}},
                created_utc="not-a-timestamp",
                pack_tokens_est=1000
            )
        
        assert "timestamp" in str(exc_info.value).lower()
    
    def test_negative_token_estimate(self):
        """Test that negative token estimate raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextPackV1(
                run_id="run-123",
                mode="FAST",
                budgets={"token_limit": 2000, "byte_limit": 64000, "max_sources": 4},
                layers={"L0": {}, "L1": {}, "L2": {}, "L3": {}},
                created_utc=datetime.now(timezone.utc).isoformat(),
                pack_tokens_est=-100
            )
        
        assert "pack_tokens_est" in str(exc_info.value)
    
    def test_schema_version_immutable(self):
        """Test that schema version is set correctly and immutable."""
        pack = ContextPackV1(
            run_id="run-123",
            mode="FAST",
            budgets={"token_limit": 2000, "byte_limit": 64000, "max_sources": 4},
            layers={"L0": {}, "L1": {}, "L2": {}, "L3": {}},
            created_utc=datetime.now(timezone.utc).isoformat(),
            pack_tokens_est=1000
        )
        
        assert pack.schema_version == "omniflow.context_pack.v1"
    
    def test_json_serialization(self):
        """Test that context pack can be serialized to JSON."""
        pack = ContextPackV1(
            run_id="run-123",
            mode="FAST",
            budgets={"token_limit": 2000, "byte_limit": 64000, "max_sources": 4},
            layers={"L0": {}, "L1": {}, "L2": {}, "L3": {}},
            created_utc=datetime.now(timezone.utc).isoformat(),
            pack_tokens_est=1000
        )
        
        json_str = pack.model_dump_json()
        assert isinstance(json_str, str)
        assert "omniflow.context_pack.v1" in json_str
        assert "run-123" in json_str


class TestPreferencesV1:
    """Tests for PreferencesV1 pydantic model."""
    
    def test_valid_preferences(self):
        """Test creating valid user preferences."""
        prefs = PreferencesV1(
            user_id="user-123",
            context_mode_preference="DEEP",
            max_recent_turns=10,
            enable_semantic_search=True,
            updated_utc=datetime.now(timezone.utc).isoformat()
        )
        
        assert prefs.schema_version == "omniflow.wp6.preferences.v1"
        assert prefs.user_id == "user-123"
        assert prefs.context_mode_preference == "DEEP"
        assert prefs.max_recent_turns == 10
    
    def test_minimal_preferences(self):
        """Test creating preferences with only required fields."""
        prefs = PreferencesV1(
            user_id="user-456",
            updated_utc=datetime.now(timezone.utc).isoformat()
        )
        
        assert prefs.user_id == "user-456"
        assert prefs.context_mode_preference is None
        assert prefs.custom_settings == {}
    
    def test_invalid_context_mode(self):
        """Test that invalid context mode raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            PreferencesV1(
                user_id="user-123",
                context_mode_preference="INVALID",
                updated_utc=datetime.now(timezone.utc).isoformat()
            )
        
        assert "context_mode_preference" in str(exc_info.value)
    
    def test_max_turns_out_of_range(self):
        """Test that max_recent_turns outside valid range raises error."""
        with pytest.raises(ValidationError) as exc_info:
            PreferencesV1(
                user_id="user-123",
                max_recent_turns=50,  # Exceeds max of 20
                updated_utc=datetime.now(timezone.utc).isoformat()
            )
        
        assert "max_recent_turns" in str(exc_info.value)
    
    def test_custom_settings(self):
        """Test that custom settings can store arbitrary data."""
        prefs = PreferencesV1(
            user_id="user-123",
            custom_settings={"theme": "dark", "language": "en"},
            updated_utc=datetime.now(timezone.utc).isoformat()
        )
        
        assert prefs.custom_settings["theme"] == "dark"
        assert prefs.custom_settings["language"] == "en"


class TestContextBuilderInput:
    """Tests for ContextBuilderInput pydantic model."""
    
    def test_valid_input_minimal(self):
        """Test creating valid input with minimal fields."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Hello, assistant!"
        )
        
        assert input_data.user_id == "user-123"
        assert input_data.message == "Hello, assistant!"
        assert input_data.mode == "AUTO"  # Default
    
    def test_valid_input_full(self):
        """Test creating valid input with all fields."""
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="Hello, assistant!",
            mode="DEEP",
            run_id="run-456",
            correlation_id="corr-789",
            max_tokens=8000,
            preferences_override={"enable_semantic": True}
        )
        
        assert input_data.mode == "DEEP"
        assert input_data.run_id == "run-456"
        assert input_data.correlation_id == "corr-789"
        assert input_data.max_tokens == 8000
        assert input_data.preferences_override["enable_semantic"] is True
    
    def test_empty_user_id(self):
        """Test that empty user_id raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextBuilderInput(
                user_id="",  # Empty string
                message="Hello!"
            )
        
        assert "user_id" in str(exc_info.value)
    
    def test_empty_message(self):
        """Test that empty message raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextBuilderInput(
                user_id="user-123",
                message=""  # Empty string
            )
        
        assert "message" in str(exc_info.value)
    
    def test_invalid_mode(self):
        """Test that invalid mode raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextBuilderInput(
                user_id="user-123",
                message="Hello!",
                mode="INVALID"
            )
        
        assert "mode" in str(exc_info.value)
    
    def test_negative_max_tokens(self):
        """Test that negative max_tokens raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextBuilderInput(
                user_id="user-123",
                message="Hello!",
                max_tokens=-1000
            )
        
        assert "max_tokens" in str(exc_info.value)
    
    def test_zero_max_tokens(self):
        """Test that zero max_tokens raises validation error."""
        with pytest.raises(ValidationError) as exc_info:
            ContextBuilderInput(
                user_id="user-123",
                message="Hello!",
                max_tokens=0
            )
        
        assert "max_tokens" in str(exc_info.value)


class TestSchemaIntegration:
    """Integration tests for schema interactions."""
    
    def test_builder_input_to_context_pack(self):
        """Test workflow from builder input to context pack."""
        # Create builder input
        input_data = ContextBuilderInput(
            user_id="user-123",
            message="What's the weather?",
            mode="FAST",
            run_id="run-789"
        )
        
        # Simulate creating context pack from input
        pack = ContextPackV1(
            run_id=input_data.run_id,
            mode="FAST",  # Resolved from AUTO or used directly
            budgets={"token_limit": 2000, "byte_limit": 64000, "max_sources": 4},
            layers={"L0": {}, "L1": {}, "L2": {}, "L3": {}},
            created_utc=datetime.now(timezone.utc).isoformat(),
            pack_tokens_est=500
        )
        
        assert pack.run_id == input_data.run_id
        assert pack.mode == "FAST"
    
    def test_preferences_influence_context_pack(self):
        """Test that preferences can influence context pack creation."""
        # Create preferences
        prefs = PreferencesV1(
            user_id="user-123",
            context_mode_preference="DEEP",
            max_recent_turns=15,
            enable_semantic_search=True,
            updated_utc=datetime.now(timezone.utc).isoformat()
        )
        
        # Simulate using preferences in context pack
        pack = ContextPackV1(
            run_id="run-123",
            mode=prefs.context_mode_preference,  # Use preferred mode
            budgets={"token_limit": 16000, "byte_limit": 128000, "max_sources": 12},
            layers={
                "L0": {},
                "L1": {"max_recent_turns": prefs.max_recent_turns},
                "L2": {},
                "L3": {}
            },
            preferences=prefs.model_dump(exclude={"schema_version", "user_id", "updated_utc"}),
            created_utc=datetime.now(timezone.utc).isoformat(),
            pack_tokens_est=12000
        )
        
        assert pack.mode == "DEEP"
        assert pack.preferences["max_recent_turns"] == 15


# Test summary
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
