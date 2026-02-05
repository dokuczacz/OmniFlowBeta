"""
WP6 Context Pack Schemas

Pydantic models for strict schema validation of context packs.
Implements ContextPack v1 specification.

Reference: IMPLEMENTATION_PLAN_UPDATED.md Phase 4
"""

from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime


class ContextPackV1(BaseModel):
    """
    Context Pack v1 - Strict schema for WP6 context building output.
    
    This ensures deterministic, validated context packs for both FAST and DEEP modes.
    """
    
    schema_version: Literal["omniflow.context_pack.v1"] = Field(
        default="omniflow.context_pack.v1",
        description="Schema version identifier"
    )
    
    run_id: str = Field(
        ...,
        description="Unique identifier for this context building run"
    )
    
    correlation_id: Optional[str] = Field(
        None,
        description="Optional correlation ID for tracing across services"
    )
    
    mode: Literal["FAST", "DEEP"] = Field(
        ...,
        description="Context mode: FAST (quick, limited) or DEEP (comprehensive)"
    )
    
    budgets: Dict[str, int] = Field(
        ...,
        description="Resource budgets: token_limit, byte_limit, max_sources"
    )
    
    layers: Dict[str, Any] = Field(
        ...,
        description="Context layers: L0 (system), L1 (user prefs), L2 (recent), L3 (semantic)"
    )
    
    preferences: Dict[str, Any] = Field(
        default_factory=dict,
        description="User preferences and settings"
    )
    
    created_utc: str = Field(
        ...,
        description="ISO8601 timestamp when pack was created"
    )
    
    pack_tokens_est: int = Field(
        ...,
        ge=0,
        description="Estimated token count for this context pack"
    )
    
    cache_metrics: Optional[Dict[str, Any]] = Field(
        None,
        description="Cache hit/miss metrics for this request"
    )
    
    @field_validator('budgets')
    @classmethod
    def validate_budgets(cls, v):
        """Ensure required budget fields are present."""
        required = ['token_limit', 'byte_limit', 'max_sources']
        missing = [k for k in required if k not in v]
        if missing:
            raise ValueError(f"Missing required budget fields: {missing}")
        return v
    
    @field_validator('layers')
    @classmethod
    def validate_layers(cls, v):
        """Ensure all layers (L0-L3) are present."""
        required_layers = ['L0', 'L1', 'L2', 'L3']
        missing = [k for k in required_layers if k not in v]
        if missing:
            raise ValueError(f"Missing required layers: {missing}")
        return v
    
    @field_validator('created_utc')
    @classmethod
    def validate_timestamp(cls, v):
        """Validate ISO8601 timestamp format."""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError as e:
            raise ValueError(f"Invalid ISO8601 timestamp: {e}")
        return v
    
    model_config = ConfigDict(
        # Ensure JSON serialization is deterministic
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )


class PreferencesV1(BaseModel):
    """
    User Preferences v1 - Schema for user preference storage.
    """
    
    schema_version: Literal["omniflow.wp6.preferences.v1"] = Field(
        default="omniflow.wp6.preferences.v1"
    )
    
    user_id: str = Field(..., description="User identifier")
    
    context_mode_preference: Optional[Literal["AUTO", "FAST", "DEEP"]] = Field(
        None,
        description="Preferred context mode"
    )
    
    max_recent_turns: Optional[int] = Field(
        None,
        ge=0,
        le=20,
        description="Maximum number of recent conversation turns to include"
    )
    
    enable_semantic_search: Optional[bool] = Field(
        None,
        description="Whether to enable semantic search in DEEP mode"
    )
    
    custom_settings: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional custom settings"
    )
    
    updated_utc: str = Field(
        ...,
        description="ISO8601 timestamp of last update"
    )


class ContextBuilderInput(BaseModel):
    """
    Input schema for context builder functions.
    
    Validates inputs before context building begins.
    """
    
    user_id: str = Field(..., min_length=1, description="User identifier")
    
    message: str = Field(..., min_length=1, description="User message")
    
    mode: Literal["AUTO", "FAST", "DEEP"] = Field(
        default="AUTO",
        description="Requested context mode"
    )
    
    run_id: Optional[str] = Field(
        None,
        description="Unique run identifier (generated if not provided)"
    )
    
    correlation_id: Optional[str] = Field(
        None,
        description="Optional correlation ID for tracing"
    )
    
    max_tokens: Optional[int] = Field(
        None,
        gt=0,
        description="Optional token limit override"
    )
    
    preferences_override: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional preferences to override user's stored preferences"
    )
