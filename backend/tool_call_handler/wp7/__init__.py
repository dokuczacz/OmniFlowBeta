"""
WP7 (Semantic Indexing) Module

This module provides dual-mode semantic indexing with prompt caching optimization:
- Real-time mode: Immediate indexing with WP6 prompt cache reuse
- Batch mode: Bulk processing for high-volume operations

All modules follow best practices from docs/PROMPT_CACHING_GUIDE.md
"""

from .schemas import (
    IndexerInput,
    IndexerOutput,
    SemanticItem,
    IndexingMode,
)
from .indexer import (
    index_interaction,
    index_interactions_batch,
)

__all__ = [
    "IndexerInput",
    "IndexerOutput",
    "SemanticItem",
    "IndexingMode",
    "index_interaction",
    "index_interactions_batch",
]
