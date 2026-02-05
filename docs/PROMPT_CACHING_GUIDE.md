# Prompt Caching Best Practices for OmniFlowBeta

**Version**: 1.0  
**Last Updated**: 2026-02-05  
**Owner**: Tool Handler Refactor Team

---

## Executive Summary

Prompt caching in OpenAI's API allows reusing identical prompt prefixes across requests, reducing costs by 50-90% for cached tokens and improving latency. This guide outlines how to implement caching best practices in OmniFlowBeta's Tool Handler, WP6 (context builder), and WP7 (semantic indexer).

**Key Benefits:**
- **Cost Savings**: Cached tokens are billed at ~50% discount (varies by model)
- **Latency Reduction**: Cached prefixes skip computation, reducing response time
- **Automatic**: Works for prompts >1024 tokens without special flags
- **Org-Scoped**: Caches shared within organization

---

## How Prompt Caching Works

### Automatic Activation
- **Threshold**: Prompts > 1024 tokens automatically eligible
- **Prefix Matching**: API checks if prompt start matches cached prefix
- **Cache Hit**: Reuses computation for matching prefix
- **Cache Miss**: Processes full prompt, creates new cache entry

### What Gets Cached
- **Input tokens only**: System prompts, tool schemas, long context
- **Not output**: Newly generated responses are always computed fresh
- **Prefix-based**: Only the **beginning** of prompts; dynamic content at end doesn't break cache

### Cache Scope
- **Organization-level**: Shared across all API keys in same org
- **TTL**: Caches expire after period of inactivity (typically 5-10 minutes)
- **Automatic management**: No manual cache invalidation needed

### Reported in API Response
```json
{
  "usage": {
    "prompt_tokens": 2500,
    "completion_tokens": 150,
    "total_tokens": 2650,
    "prompt_tokens_details": {
      "cached_tokens": 2000,      // ← Cached portion (cheaper)
      "cached_tokens_details": {...}
    }
  }
}
```

---

## Best Practices for OmniFlowBeta

### 1. Structure Prompts for Caching

**✅ DO: Static content first, dynamic content last**

```python
# GOOD: Cacheable prefix
prompt_parts = [
    # 1. System instructions (static) ← CACHEABLE
    "You are an AI assistant for OmniFlowBeta...",
    
    # 2. Tool schemas (static) ← CACHEABLE
    json.dumps(TOOL_SPECS),
    
    # 3. Long context/examples (static) ← CACHEABLE
    few_shot_examples,
    
    # 4. Current conversation (dynamic) ← NOT CACHED (but that's OK!)
    f"User: {current_message}"
]

final_prompt = "\n\n".join(prompt_parts)
```

**❌ DON'T: Dynamic content early in prompt**

```python
# BAD: Breaks caching
prompt = f"""
Current time: {datetime.now()}  # ← Changes every request!
User ID: {user_id}  # ← Changes per user!

System: You are an AI assistant...
Tool schemas: {json.dumps(TOOL_SPECS)}
"""
```

### 2. Keep Static Content Identical

**Critical for cache hits:**
- Tool schemas in **same order** across requests
- System instructions **exactly the same** (no timestamps, no user IDs)
- Few-shot examples **verbatim** (no randomization early in prompt)

**Example: WP6 Context Builder**

```python
def build_wp6_context(user_id, message, context_mode="AUTO"):
    """Build WP6 context with cacheable structure."""
    
    # STATIC PREFIX (cacheable)
    static_prefix = [
        # 1. System instructions
        get_system_prompt(),  # Must be deterministic!
        
        # 2. Tool schemas (always in same order)
        json.dumps(get_tool_schemas(), sort_keys=True),
        
        # 3. Context mode instructions
        get_context_mode_instructions(context_mode),
        
        # 4. Few-shot examples (if used)
        get_few_shot_examples() if context_mode == "DEEP" else ""
    ]
    
    # DYNAMIC SUFFIX (not cached, but cheap)
    dynamic_suffix = [
        # 5. User-specific context (recent turns)
        get_recent_turns(user_id, max_turns=8),
        
        # 6. Current message
        f"User: {message}",
        
        # 7. Metadata (timestamp, etc.)
        f"Timestamp: {datetime.now().isoformat()}"
    ]
    
    # Combine: static first, dynamic last
    return "\n\n".join(static_prefix + dynamic_suffix)
```

### 3. Tool Schemas: Maintain Order

**✅ DO: Use sorted keys, consistent order**

```python
# GOOD: Deterministic ordering
tools = json.dumps(TOOL_SPECS, sort_keys=True, indent=2)

# OR: Explicit ordering
tool_order = [
    "get_current_time",
    "list_blobs",
    "read_blob_file",
    # ... etc in fixed order
]
tools = "\n".join(json.dumps(TOOL_SPECS[name]) for name in tool_order)
```

**❌ DON'T: Random/unstable ordering**

```python
# BAD: Dictionary iteration order may vary
tools = "\n".join(json.dumps(spec) for spec in TOOL_SPECS.values())

# BAD: Timestamp in tool schema
tool_with_timestamp = {
    "name": "read_blob",
    "updated_at": datetime.now().isoformat()  # ← Breaks caching!
}
```

### 4. Batch Operations (WP7)

For WP7 semantic indexing with batch operations:

**✅ DO: Consistent prompt structure per batch**

```python
def build_wp7_batch_prompt(items, prompt_id):
    """Build WP7 indexer prompt with caching in mind."""
    
    # STATIC (cached across batches)
    static_parts = [
        get_indexer_system_prompt(prompt_id),  # Deterministic
        get_indexer_output_schema(),  # JSON schema (static)
        get_indexer_examples()  # Few-shot (static)
    ]
    
    # DYNAMIC (varies per batch)
    batch_data = json.dumps(items, sort_keys=True)
    
    return "\n\n".join(static_parts + [f"Items to index:\n{batch_data}"])
```

**Key insight**: Even though `items` change, the large static prefix gets cached, saving cost on system prompt + schema + examples.

### 5. Context Mode Routing (WP6)

**FAST mode** (minimal context):
```python
# Smaller prompt, less likely to hit 1024 token threshold
# Cache still helps if system + tools exceed 1024 tokens
fast_context = [
    system_prompt,      # ~500 tokens
    tool_schemas,       # ~1500 tokens ← Cached!
    recent_turns(3),    # ~200 tokens
    current_message     # ~50 tokens
]
# Total: ~2250 tokens, ~2000 cached
```

**DEEP mode** (rich context):
```python
# Larger prompt, more benefit from caching
deep_context = [
    system_prompt,          # ~500 tokens
    tool_schemas,           # ~1500 tokens ← Cached!
    few_shot_examples,      # ~3000 tokens ← Cached!
    semantic_context,       # ~2000 tokens ← Cached if deterministic
    recent_turns(10),       # ~800 tokens
    current_message         # ~50 tokens
]
# Total: ~7850 tokens, ~7000 cached!
# Cost savings: ~90% of input cost
```

---

## Implementation Strategy

### Phase 1: Measure Current Caching

**Add usage tracking to existing code:**

```python
def _openai_call(fn, *args, **kwargs):
    """Enhanced with cache metrics."""
    global _openai_count, _cache_hits, _cache_misses
    
    resp = fn(*args, **kwargs)
    
    # Track caching metrics
    usage = getattr(resp, 'usage', None)
    if usage:
        prompt_details = getattr(usage, 'prompt_tokens_details', {})
        cached = getattr(prompt_details, 'cached_tokens', 0)
        total_prompt = getattr(usage, 'prompt_tokens', 0)
        
        if cached > 0:
            _cache_hits += 1
            logger.info(f"Cache hit: {cached}/{total_prompt} tokens cached ({cached/total_prompt*100:.1f}%)")
        else:
            _cache_misses += 1
        
        # Store metrics for reporting
        _cache_metrics.append({
            "timestamp": datetime.now().isoformat(),
            "cached_tokens": cached,
            "total_prompt_tokens": total_prompt,
            "cache_hit_rate": cached / total_prompt if total_prompt > 0 else 0
        })
    
    return resp
```

### Phase 2: Optimize Prompt Structure

**WP6 Context Builder:**
1. Extract system prompt to separate function (ensure deterministic)
2. Serialize TOOL_SPECS with `sort_keys=True`
3. Move user-specific content to end
4. Add cache metrics logging

**WP7 Semantic Indexer:**
1. Consistent batch prompt structure
2. Static indexer schema/examples at start
3. Dynamic items at end
4. Track cache hit rates per batch

### Phase 3: Monitor and Iterate

**Metrics to track:**
- Cache hit rate (% of requests with cached_tokens > 0)
- Average cached token percentage
- Cost savings (cached tokens * discount rate)
- Latency improvements

**Target success criteria:**
- Cache hit rate > 80% for WP6 FAST mode
- Cache hit rate > 90% for WP6 DEEP mode
- Average 60%+ tokens cached when hit occurs

---

## Common Pitfalls

### ❌ Pitfall 1: User ID in Prefix

```python
# BAD: Breaks caching per user
prompt = f"""User: {user_id}
System: You are an assistant...
Tools: {tools}
Message: {msg}"""
```

**Fix**: Move user ID to suffix:
```python
# GOOD: Cache system + tools
prompt = f"""System: You are an assistant...
Tools: {tools}

User {user_id}: {msg}"""
```

### ❌ Pitfall 2: Timestamp in Prefix

```python
# BAD: Changes every request
prompt = f"""[{datetime.now()}]
System instructions...
"""
```

**Fix**: Move timestamp to suffix or remove entirely.

### ❌ Pitfall 3: Randomized Examples

```python
# BAD: Different examples each time
examples = random.sample(all_examples, k=3)
prompt = f"""Examples:\n{examples}\n\nUser: {msg}"""
```

**Fix**: Use consistent examples:
```python
# GOOD: Same examples every time (or deterministic selection)
examples = all_examples[:3]  # Always first 3
prompt = f"""Examples:\n{examples}\n\nUser: {msg}"""
```

### ❌ Pitfall 4: Tool Order Instability

```python
# BAD: Dict iteration order
tools = "\n".join(json.dumps(t) for t in TOOL_SPECS.values())
```

**Fix**: Explicit ordering:
```python
# GOOD: Sorted keys
tools = json.dumps(TOOL_SPECS, sort_keys=True)
```

---

## Expected Impact

### Cost Savings Estimation

**Current state** (no optimization):
- WP6 FAST: ~2000 tokens/request × $0.01/1K = $0.02/request
- WP6 DEEP: ~8000 tokens/request × $0.01/1K = $0.08/request
- WP7 batch: ~5000 tokens/batch × $0.01/1K = $0.05/batch

**With caching** (80% cache hit rate, 70% cached tokens):
- Cached tokens: 70% × 50% discount = 35% cost reduction
- Overall savings: 80% hit rate × 35% reduction = **28% total savings**

**For 10,000 requests/day:**
- Current cost: 10K × $0.03 avg = $300/day = $9K/month
- With caching: $300 × (1 - 0.28) = $216/day = **$6.5K/month**
- **Savings: $2.5K/month** (~$30K/year)

### Latency Improvements

- Cache hits: ~20-40% faster response time
- Especially beneficial for DEEP mode (large prefixes)

---

## References

- **OpenAI Prompt Caching 101**: https://cookbook.openai.com/examples/Prompt_Caching101.ipynb
- **Best practices**:
  - Static content first, dynamic content last
  - Maintain identical ordering for tools/images
  - Prefix must be >1024 tokens to activate
  - Caches are org-scoped, automatic TTL

---

## Action Items for Refactor

### Phase 4: WP6 Enhancement
- [ ] Refactor `build_wp6_context()` with cacheable structure
- [ ] Ensure TOOL_SPECS serialized with `sort_keys=True`
- [ ] Move user-specific content to end
- [ ] Add cache metrics tracking
- [ ] Target: >80% cache hit rate for FAST, >90% for DEEP

### Phase 5: WP7 Enhancement
- [ ] Restructure WP7 batch prompts (static first)
- [ ] Ensure indexer schema/examples are deterministic
- [ ] Add batch-level cache tracking
- [ ] Target: >70% tokens cached per batch

### Monitoring
- [ ] Add `cached_tokens` tracking to `_openai_call()`
- [ ] Log cache hit rates to metrics
- [ ] Create dashboard for cache performance
- [ ] Alert if cache hit rate drops below threshold

---

## Summary

**Prompt caching** is a powerful cost and latency optimization that requires **structured prompts**:

1. **Static prefix** (system prompt, tool schemas, examples) → **Cached**
2. **Dynamic suffix** (user message, context, metadata) → **Not cached**

By following these patterns in WP6 and WP7, OmniFlowBeta can achieve:
- **28-40% cost reduction** on API calls
- **20-40% latency improvement** for cached requests
- **Automatic benefits** with minimal code changes

The key is **deterministic ordering** and **static-first structure**.
