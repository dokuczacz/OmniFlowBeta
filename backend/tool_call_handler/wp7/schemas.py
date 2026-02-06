"""
WP7 Schemas - Pydantic V2 validation schemas for semantic indexing.

All schemas follow strict validation with comprehensive type safety.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IndexingMode(str, Enum):
    """Indexing execution mode"""
    REALTIME = "REALTIME"  # Immediate indexing (default, leverages WP6 cache)
    BATCH = "BATCH"  # Bulk processing (optional, for high volume)


class SemanticCategory(str, Enum):
    """Interaction categories for semantic indexing"""
    PE = "PE"  # Personal
    UI = "UI"  # User Interface
    ML = "ML"  # Machine Learning
    LO = "LO"  # Logging/Operations
    PS = "PS"  # Problem Solving
    TM = "TM"  # Task Management
    SYS = "SYS"  # System
    GEN = "GEN"  # General
    ID = "ID"  # Identification


class SemanticItem(BaseModel):
    """Single semantic index item (output from indexer)"""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    interaction_id: str = Field(
        ...,
        description="Unique interaction ID (format: INT_*)",
        pattern=r"^INT_.*"
    )
    
    category: SemanticCategory = Field(
        ...,
        description="Interaction category"
    )
    
    summary: str = Field(
        ...,
        description="Concise summary: Intent; Action(tool); Result (Scope). Max 220 chars",
        max_length=220,
        min_length=10
    )
    
    tags: List[str] = Field(
        ...,
        description="3-6 stable lowercase-kebab-case tags",
        min_length=3,
        max_length=6
    )
    
    confidence: float = Field(
        ...,
        description="Confidence score (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp"
    )
    
    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Validate tags are lowercase-kebab-case"""
        import re
        pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        for tag in v:
            if not pattern.match(tag):
                raise ValueError(f"Invalid tag format: {tag}. Must be lowercase-kebab-case")
        return v


class IndexerInput(BaseModel):
    """Input for semantic indexer"""
    
    model_config = ConfigDict(extra="forbid")
    
    user_id: str = Field(
        ...,
        description="User identifier",
        min_length=1
    )
    
    interaction_id: str = Field(
        ...,
        description="Interaction ID to index",
        pattern=r"^INT_.*"
    )
    
    message: str = Field(
        ...,
        description="User message/query",
        min_length=1
    )
    
    tool_calls: List[Dict] = Field(
        default_factory=list,
        description="Tool calls made during interaction"
    )
    
    mode: IndexingMode = Field(
        default=IndexingMode.REALTIME,
        description="Indexing mode (REALTIME or BATCH)"
    )
    
    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Ensure message is not empty after stripping"""
        if not v.strip():
            raise ValueError("Message cannot be empty")
        return v


class IndexerOutput(BaseModel):
    """Output from semantic indexer"""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    items: List[SemanticItem] = Field(
        ...,
        description="Indexed semantic items",
        min_length=1,
        max_length=25
    )
    
    mode_used: IndexingMode = Field(
        ...,
        description="Indexing mode that was used"
    )
    
    cached_tokens: int = Field(
        default=0,
        description="Number of tokens from cache (prompt caching)",
        ge=0
    )
    
    total_tokens: int = Field(
        ...,
        description="Total tokens used",
        ge=0
    )
    
    processing_time_ms: float = Field(
        ...,
        description="Processing time in milliseconds",
        ge=0.0
    )
    
    dedup_key: Optional[str] = Field(
        default=None,
        description="Deduplication key (for idempotency)"
    )


class BatchIndexerInput(BaseModel):
    """Input for batch indexing (multiple interactions)"""
    
    model_config = ConfigDict(extra="forbid")
    
    user_id: str = Field(
        ...,
        description="User identifier",
        min_length=1
    )
    
    interactions: List[Dict] = Field(
        ...,
        description="List of interactions to index",
        min_length=1,
        max_length=25
    )
    
    batch_size_multiplier: int = Field(
        default=9,
        description="Batch size multiplier",
        ge=1,
        le=20
    )
    
    target_tokens: int = Field(
        default=4000,
        description="Target tokens per batch",
        ge=1000,
        le=10000
    )


class IndexerMetrics(BaseModel):
    """Metrics for indexer performance tracking"""
    
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    cache_efficiency: float = Field(
        ...,
        description="Cache hit efficiency (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
    
    cost_savings_pct: float = Field(
        ...,
        description="Estimated cost savings from caching (%)",
        ge=0.0,
        le=100.0
    )
    
    avg_processing_time_ms: float = Field(
        ...,
        description="Average processing time per item (ms)",
        ge=0.0
    )
    
    dedup_rate: float = Field(
        default=0.0,
        description="Deduplication rate (0.0-1.0)",
        ge=0.0,
        le=1.0
    )
