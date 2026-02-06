"""
WP6 Routing Logic - Intelligent mode selection for context building.

This module implements the AUTO mode routing logic that determines whether
to use FAST or DEEP context building based on query characteristics.

Routing Strategy:
- AUTO mode: Analyzes query complexity and selects FAST or DEEP
- Explicit modes: Respects user/preference override
- Deterministic: Same query → same mode selection
"""

from typing import Dict, Any, Optional, Tuple
from .schemas import ContextBuilderInput, PreferencesV1


def analyze_query_complexity(message: str) -> Dict[str, Any]:
    """
    Analyze query to determine complexity indicators.
    
    Args:
        message: User's query message
        
    Returns:
        Dictionary with complexity metrics:
        - word_count: Number of words in message
        - has_question_marks: Whether message contains questions
        - has_multi_part: Whether message has multiple sentences
        - technical_keywords: Count of technical/complex terms
        - complexity_score: Overall score (0-100)
    """
    words = message.split()
    word_count = len(words)
    
    # Check for question indicators
    has_question_marks = '?' in message
    
    # Check for multi-part queries (multiple sentences)
    sentences = [s.strip() for s in message.replace('?', '.').replace('!', '.').split('.') if s.strip()]
    has_multi_part = len(sentences) > 1
    
    # Check for technical/complex keywords
    technical_terms = [
        'analyze', 'compare', 'explain', 'detail', 'comprehensive',
        'complex', 'relationship', 'pattern', 'trend', 'summarize',
        'integrate', 'correlation', 'implication', 'evaluate'
    ]
    message_lower = message.lower()
    technical_keywords = sum(1 for term in technical_terms if term in message_lower)
    
    # Calculate complexity score (0-100)
    complexity_score = 0
    
    # Word count contribution (0-30 points)
    if word_count > 50:
        complexity_score += 30
    elif word_count > 30:
        complexity_score += 20
    elif word_count > 15:
        complexity_score += 10
    
    # Multi-part query (0-25 points)
    if has_multi_part:
        complexity_score += 25
    
    # Technical keywords (0-30 points)
    complexity_score += min(technical_keywords * 10, 30)
    
    # Question complexity (0-15 points)
    if has_question_marks:
        question_count = message.count('?')
        if question_count > 2:
            complexity_score += 15
        elif question_count > 1:
            complexity_score += 10
        else:
            complexity_score += 5
    
    return {
        'word_count': word_count,
        'has_question_marks': has_question_marks,
        'has_multi_part': has_multi_part,
        'technical_keywords': technical_keywords,
        'complexity_score': min(complexity_score, 100)
    }


def select_context_mode(
    input_data: ContextBuilderInput,
    user_prefs: Optional[PreferencesV1] = None,
    complexity_threshold: int = 50
) -> Tuple[str, Dict[str, Any]]:
    """
    Select appropriate context building mode (FAST or DEEP).
    
    Routing Logic:
    1. If mode explicitly set in input_data → use it
    2. If user preference set → use it (unless AUTO)
    3. If AUTO or no preference → analyze query complexity
       - complexity_score >= threshold → DEEP
       - complexity_score < threshold → FAST
    
    Args:
        input_data: Validated context builder input
        user_prefs: Optional user preferences
        complexity_threshold: Score threshold for DEEP mode (default: 50)
        
    Returns:
        Tuple of (selected_mode, routing_metadata)
        - selected_mode: "FAST" or "DEEP"
        - routing_metadata: Dict with routing decision info
    """
    routing_metadata = {
        'input_mode': input_data.mode,
        'preference_mode': user_prefs.context_mode_preference if user_prefs else None,
        'routing_method': None,
        'complexity_analysis': None,
        'selected_mode': None
    }
    
    # Priority 1: Explicit mode in input (overrides all)
    if input_data.mode in ('FAST', 'DEEP'):
        routing_metadata['routing_method'] = 'explicit_input'
        routing_metadata['selected_mode'] = input_data.mode
        return input_data.mode, routing_metadata
    
    # Priority 2: User preference (if not AUTO)
    if user_prefs and user_prefs.context_mode_preference in ('FAST', 'DEEP'):
        routing_metadata['routing_method'] = 'user_preference'
        routing_metadata['selected_mode'] = user_prefs.context_mode_preference
        return user_prefs.context_mode_preference, routing_metadata
    
    # Priority 3: AUTO mode - analyze query complexity
    complexity = analyze_query_complexity(input_data.message)
    routing_metadata['complexity_analysis'] = complexity
    routing_metadata['routing_method'] = 'complexity_analysis'
    
    # Decision: DEEP if complex, FAST otherwise
    if complexity['complexity_score'] >= complexity_threshold:
        selected_mode = 'DEEP'
    else:
        selected_mode = 'FAST'
    
    routing_metadata['selected_mode'] = selected_mode
    routing_metadata['threshold'] = complexity_threshold
    
    return selected_mode, routing_metadata


def build_context_with_routing(
    input_data: ContextBuilderInput,
    user_prefs: Optional[PreferencesV1] = None,
    custom_params: Optional[Dict[str, Any]] = None,
    complexity_threshold: int = 50
):
    """
    Build context pack with intelligent mode routing.
    
    This is the main entry point that:
    1. Selects appropriate mode (FAST/DEEP)
    2. Builds context using selected builder
    3. Returns context pack with routing metadata
    
    Args:
        input_data: Validated context builder input
        user_prefs: Optional user preferences
        custom_params: Optional custom parameters
        complexity_threshold: Complexity threshold for DEEP mode
        
    Returns:
        Tuple of (context_pack, routing_metadata)
    """
    from .fast_context import assemble_quick_context
    from .deep_context import assemble_comprehensive_context
    
    # Select mode
    selected_mode, routing_metadata = select_context_mode(
        input_data,
        user_prefs,
        complexity_threshold
    )
    
    # Build context with selected mode
    if selected_mode == 'DEEP':
        context_pack = assemble_comprehensive_context(
            input_data,
            user_prefs,
            custom_params
        )
    else:  # FAST
        context_pack = assemble_quick_context(
            input_data,
            user_prefs,
            custom_params
        )
    
    return context_pack, routing_metadata


def get_routing_explanation(routing_metadata: Dict[str, Any]) -> str:
    """
    Generate human-readable explanation of routing decision.
    
    Args:
        routing_metadata: Routing metadata from select_context_mode()
        
    Returns:
        Human-readable explanation string
    """
    method = routing_metadata.get('routing_method')
    selected = routing_metadata.get('selected_mode')
    
    if method == 'explicit_input':
        return f"Mode {selected} explicitly requested in input"
    
    elif method == 'user_preference':
        return f"Mode {selected} selected from user preference"
    
    elif method == 'complexity_analysis':
        complexity = routing_metadata.get('complexity_analysis', {})
        score = complexity.get('complexity_score', 0)
        threshold = routing_metadata.get('threshold', 50)
        
        explanation = f"Mode {selected} selected by complexity analysis (score: {score}/{threshold})"
        
        # Add key factors
        factors = []
        if complexity.get('word_count', 0) > 30:
            factors.append(f"{complexity['word_count']} words")
        if complexity.get('has_multi_part'):
            factors.append("multi-part query")
        if complexity.get('technical_keywords', 0) > 0:
            factors.append(f"{complexity['technical_keywords']} technical terms")
        
        if factors:
            explanation += f" - {', '.join(factors)}"
        
        return explanation
    
    return f"Mode {selected} selected (method: {method})"
