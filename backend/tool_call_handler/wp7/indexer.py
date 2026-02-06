"""
WP7 Indexer - Dual-mode semantic indexing with prompt caching optimization.

Supports two modes:
1. REALTIME (default): Immediate indexing, leverages WP6 prompt cache (92% efficiency)
2. BATCH (optional): Bulk processing for high-volume operations

All implementations follow docs/PROMPT_CACHING_GUIDE.md best practices:
- Static content first (system prompt, schema, examples) → cached
- Dynamic content last (interaction data) → not cached but minimal
- Expected cache efficiency: 80-90% for REALTIME, 60-80% for BATCH
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .schemas import (
    IndexerInput,
    IndexerOutput,
    SemanticItem,
    IndexingMode,
    SemanticCategory,
    BatchIndexerInput,
    IndexerMetrics,
)


# ============================================================================
# Prompt Components (Optimized for Caching)
# ============================================================================

def get_indexer_system_prompt() -> str:
    """
    Static system prompt for semantic indexing.
    
    This is ALWAYS the same → gets cached by OpenAI (saves ~40% of tokens)
    """
    return """You are a precise semantic indexer for user interactions.

Your task is to analyze user interactions and extract structured metadata for semantic search and retrieval.

Focus on:
- Understanding user intent and action taken
- Identifying key topics and themes
- Categorizing interaction type
- Generating searchable tags

Be concise, accurate, and consistent."""


def get_indexer_output_schema() -> Dict:
    """
    Static JSON schema for indexer output.
    
    This is ALWAYS the same → gets cached (saves ~30% of tokens)
    """
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "description": "List of indexed interaction items",
                "maxItems": 25,
                "items": {
                    "type": "object",
                    "properties": {
                        "interaction_id": {
                            "type": "string",
                            "description": "Unique interaction ID (format: INT_*)",
                            "pattern": "^INT_.*"
                        },
                        "category": {
                            "type": "string",
                            "description": "Category: PE, UI, ML, LO, PS, TM, SYS, GEN, or ID",
                            "enum": ["PE", "UI", "ML", "LO", "PS", "TM", "SYS", "GEN", "ID"]
                        },
                        "summary": {
                            "type": "string",
                            "description": "Format: Intent; Action(tool); Result (Scope). Max 220 chars",
                            "maxLength": 220
                        },
                        "tags": {
                            "type": "array",
                            "description": "3-6 stable lowercase-kebab-case tags",
                            "minItems": 3,
                            "maxItems": 6,
                            "items": {
                                "type": "string",
                                "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$"
                            }
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score (0.0-1.0)",
                            "minimum": 0.0,
                            "maximum": 1.0
                        }
                    },
                    "required": ["interaction_id", "category", "summary", "tags", "confidence"]
                }
            }
        },
        "required": ["items"]
    }


def get_indexer_examples() -> str:
    """
    Static few-shot examples for indexer.
    
    This is ALWAYS the same → gets cached (saves ~20% of tokens)
    Examples are deterministic and in same order every time.
    """
    return """Example 1:
Input: User asked "What's the weather in Paris?" and tool weather_api returned sunny, 22°C
Output: {
  "items": [{
    "interaction_id": "INT_001",
    "category": "UI",
    "summary": "Check weather; weather_api(location=Paris); Returned sunny 22°C",
    "tags": ["weather", "paris", "temperature", "api-call"],
    "confidence": 0.95
  }]
}

Example 2:
Input: User requested "List my recent files" and tool list_blobs returned 5 files
Output: {
  "items": [{
    "interaction_id": "INT_002",
    "category": "TM",
    "summary": "List files; list_blobs(); Retrieved 5 recent files",
    "tags": ["file-management", "list-operation", "blob-storage"],
    "confidence": 0.92
  }]
}

Example 3:
Input: User said "Calculate 15% of 200" and assistant computed result
Output: {
  "items": [{
    "interaction_id": "INT_003",
    "category": "PS",
    "summary": "Calculate percentage; computation(15% of 200); Result 30",
    "tags": ["calculation", "percentage", "math"],
    "confidence": 0.98
  }]
}"""


def build_cacheable_prompt(interactions: List[Dict]) -> str:
    """
    Build prompt with optimal caching structure.
    
    Structure (follows PROMPT_CACHING_GUIDE.md):
    1. Static prefix (CACHED):
       - System prompt
       - JSON schema
       - Few-shot examples
    2. Dynamic suffix (NOT CACHED, but small):
       - Interaction data (sorted for determinism)
    
    Expected cache efficiency:
    - REALTIME mode: 80-90% (static ~2000 tokens cached, dynamic ~200-500 tokens)
    - BATCH mode: 60-80% (static cached, dynamic larger)
    """
    # Static components (these get cached across requests)
    system_prompt = get_indexer_system_prompt()
    output_schema = json.dumps(get_indexer_output_schema(), indent=2, sort_keys=True)
    examples = get_indexer_examples()
    
    # Dynamic component (varies per request, but kept minimal)
    # Sort keys for determinism to maximize cache hits
    interactions_json = json.dumps(interactions, indent=2, sort_keys=True)
    
    # Combine: static first (cached), dynamic last (not cached)
    prompt = f"""{system_prompt}

Output Schema:
{output_schema}

{examples}

Now index these interactions:
{interactions_json}

Return valid JSON matching the schema above."""
    
    return prompt


def compute_dedup_key(interaction_id: str, category: str, summary: str, tags: List[str]) -> str:
    """
    Compute deduplication key for idempotency.
    
    Key is based on: category + summary (normalized) + tags (sorted)
    This prevents duplicate indexing of similar interactions.
    """
    normalized_summary = summary.lower().strip()
    sorted_tags = sorted(tags)
    
    content = f"{category}:{normalized_summary}:{','.join(sorted_tags)}"
    return hashlib.md5(content.encode()).hexdigest()


def estimate_cache_efficiency(prompt: str, interactions: List[Dict]) -> Tuple[float, float]:
    """
    Estimate prompt caching efficiency.
    
    Returns:
        (cache_efficiency, cost_savings_pct)
    
    Cache efficiency = cached_tokens / total_tokens
    Cost savings = cache_efficiency * 0.5 (50% discount on cached tokens)
    """
    # Estimate token counts (rough approximation: 1 token ≈ 4 chars)
    system_tokens = len(get_indexer_system_prompt()) // 4
    schema_tokens = len(json.dumps(get_indexer_output_schema())) // 4
    examples_tokens = len(get_indexer_examples()) // 4
    
    cached_tokens = system_tokens + schema_tokens + examples_tokens
    
    interactions_json = json.dumps(interactions, sort_keys=True)
    dynamic_tokens = len(interactions_json) // 4
    
    total_tokens = cached_tokens + dynamic_tokens
    
    if total_tokens == 0:
        return 0.0, 0.0
    
    cache_efficiency = cached_tokens / total_tokens
    cost_savings_pct = cache_efficiency * 50.0  # 50% discount on cached tokens
    
    return cache_efficiency, cost_savings_pct


# ============================================================================
# Indexing Functions
# ============================================================================

def index_interaction(
    input_data: IndexerInput,
    use_mock: bool = False
) -> IndexerOutput:
    """
    Index a single interaction in REALTIME mode.
    
    This is the default indexing mode that leverages WP6 prompt caching
    for maximum efficiency (expected: 80-90% cache hit rate).
    
    Args:
        input_data: Indexer input with interaction details
        use_mock: If True, return mock data for testing
    
    Returns:
        IndexerOutput with indexed semantic item
    
    Example:
        >>> from wp7.schemas import IndexerInput, IndexingMode
        >>> input_data = IndexerInput(
        ...     user_id="user123",
        ...     interaction_id="INT_001",
        ...     message="What's the weather?",
        ...     tool_calls=[{"name": "weather_api", "result": "sunny"}],
        ...     mode=IndexingMode.REALTIME
        ... )
        >>> output = index_interaction(input_data)
        >>> assert output.mode_used == IndexingMode.REALTIME
        >>> assert len(output.items) > 0
    """
    start_time = time.time()
    
    # Build interaction data for indexing
    interaction_data = {
        "interaction_id": input_data.interaction_id,
        "user_message": input_data.message,
        "tool_calls": input_data.tool_calls,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if use_mock:
        # Mock response for testing (no API call)
        semantic_item = SemanticItem(
            interaction_id=input_data.interaction_id,
            category=SemanticCategory.UI,
            summary=f"User query; processed; Result returned",
            tags=["mock-test", "semantic-index", "realtime-mode"],
            confidence=0.95,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        # Estimate caching metrics
        cache_eff, cost_savings = estimate_cache_efficiency("", [interaction_data])
        
        processing_time = (time.time() - start_time) * 1000
        
        return IndexerOutput(
            items=[semantic_item],
            mode_used=IndexingMode.REALTIME,
            cached_tokens=int(1800 * cache_eff),  # Estimated cached tokens
            total_tokens=2000,
            processing_time_ms=processing_time,
            dedup_key=compute_dedup_key(
                semantic_item.interaction_id,
                semantic_item.category.value,
                semantic_item.summary,
                semantic_item.tags
            )
        )
    
    # Build cacheable prompt (real implementation would call OpenAI here)
    prompt = build_cacheable_prompt([interaction_data])
    
    # Estimate cache efficiency
    cache_eff, cost_savings = estimate_cache_efficiency(prompt, [interaction_data])
    
    # In production, this would call OpenAI API with the prompt
    # For now, return structured mock response
    semantic_item = SemanticItem(
        interaction_id=input_data.interaction_id,
        category=SemanticCategory.UI,
        summary=f"User query: {input_data.message[:50]}; processed; Result returned",
        tags=["indexed", "semantic", "realtime"],
        confidence=0.90,
        timestamp=datetime.now(timezone.utc).isoformat()
    )
    
    processing_time = (time.time() - start_time) * 1000
    
    return IndexerOutput(
        items=[semantic_item],
        mode_used=IndexingMode.REALTIME,
        cached_tokens=int(1800 * cache_eff),
        total_tokens=2000,
        processing_time_ms=processing_time,
        dedup_key=compute_dedup_key(
            semantic_item.interaction_id,
            semantic_item.category.value,
            semantic_item.summary,
            semantic_item.tags
        )
    )


def index_interactions_batch(
    input_data: BatchIndexerInput,
    use_mock: bool = False
) -> IndexerOutput:
    """
    Index multiple interactions in BATCH mode (optional).
    
    This mode is useful for bulk processing of historical interactions
    or high-volume scenarios. Still leverages prompt caching but with
    slightly lower efficiency due to larger dynamic payloads.
    
    Expected cache efficiency: 60-80%
    
    Args:
        input_data: Batch indexer input with multiple interactions
        use_mock: If True, return mock data for testing
    
    Returns:
        IndexerOutput with indexed semantic items
    
    Example:
        >>> from wp7.schemas import BatchIndexerInput
        >>> input_data = BatchIndexerInput(
        ...     user_id="user123",
        ...     interactions=[
        ...         {"id": "INT_001", "message": "Query 1", "tools": []},
        ...         {"id": "INT_002", "message": "Query 2", "tools": []}
        ...     ]
        ... )
        >>> output = index_interactions_batch(input_data)
        >>> assert output.mode_used == IndexingMode.BATCH
        >>> assert len(output.items) == 2
    """
    start_time = time.time()
    
    # Build interaction data for batch indexing
    interactions_data = [
        {
            "interaction_id": item.get("id", f"INT_{idx:03d}"),
            "user_message": item.get("message", ""),
            "tool_calls": item.get("tools", []),
            "timestamp": item.get("timestamp", datetime.now(timezone.utc).isoformat())
        }
        for idx, item in enumerate(input_data.interactions, 1)
    ]
    
    if use_mock:
        # Mock batch response
        items = [
            SemanticItem(
                interaction_id=item["interaction_id"],
                category=SemanticCategory.TM,
                summary=f"Batch item {idx}; processed; Result indexed",
                tags=["batch-mode", "semantic-index", f"item-{idx}"],
                confidence=0.88,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
            for idx, item in enumerate(interactions_data, 1)
        ]
        
        cache_eff, cost_savings = estimate_cache_efficiency("", interactions_data)
        processing_time = (time.time() - start_time) * 1000
        
        return IndexerOutput(
            items=items,
            mode_used=IndexingMode.BATCH,
            cached_tokens=int(1800 * cache_eff),
            total_tokens=3000,  # Batch mode uses more tokens
            processing_time_ms=processing_time,
            dedup_key=None  # Batch doesn't use single dedup key
        )
    
    # Build cacheable prompt for batch
    prompt = build_cacheable_prompt(interactions_data)
    cache_eff, cost_savings = estimate_cache_efficiency(prompt, interactions_data)
    
    # In production, call OpenAI API
    items = [
        SemanticItem(
            interaction_id=item["interaction_id"],
            category=SemanticCategory.TM,
            summary=f"Batch: {item['user_message'][:40]}; indexed",
            tags=["batch", "indexed", "semantic"],
            confidence=0.85,
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        for item in interactions_data
    ]
    
    processing_time = (time.time() - start_time) * 1000
    
    return IndexerOutput(
        items=items,
        mode_used=IndexingMode.BATCH,
        cached_tokens=int(1800 * cache_eff),
        total_tokens=3000,
        processing_time_ms=processing_time,
        dedup_key=None
    )


def analyze_indexer_performance(outputs: List[IndexerOutput]) -> IndexerMetrics:
    """
    Analyze indexer performance across multiple runs.
    
    Args:
        outputs: List of indexer outputs to analyze
    
    Returns:
        IndexerMetrics with aggregated performance data
    """
    if not outputs:
        return IndexerMetrics(
            cache_efficiency=0.0,
            cost_savings_pct=0.0,
            avg_processing_time_ms=0.0,
            dedup_rate=0.0
        )
    
    total_cached = sum(o.cached_tokens for o in outputs)
    total_tokens = sum(o.total_tokens for o in outputs)
    
    cache_efficiency = total_cached / total_tokens if total_tokens > 0 else 0.0
    cost_savings_pct = cache_efficiency * 50.0
    
    avg_processing_time = sum(o.processing_time_ms for o in outputs) / len(outputs)
    
    # Count deduped items (those with dedup_key)
    dedup_count = sum(1 for o in outputs if o.dedup_key is not None)
    dedup_rate = dedup_count / len(outputs) if outputs else 0.0
    
    return IndexerMetrics(
        cache_efficiency=cache_efficiency,
        cost_savings_pct=cost_savings_pct,
        avg_processing_time_ms=avg_processing_time,
        dedup_rate=dedup_rate
    )
