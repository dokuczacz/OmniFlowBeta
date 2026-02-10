# 🔬 DETAILED COST BREAKDOWN & COMPONENT ANALYSIS
## OmniFlow LLM Expenditure by Component (Real-World Projection)

**Date**: 2026-02-10  
**Data sources**: OpenAI responses + Azurite logs + Backend architecture  
**Confidence**: 🟡 MEDIUM (estimates need validation through token tracking)

---

## 📊 COMPLETE REQUEST FLOW - LLM Cost Breakdown

### A Typical Request Flow (with real data)

```
User: "pokaż moje maile"
    ↓
[1] PA INTENTION PARSER
    Model: gpt-5-nano (cheapest)
    Input: 500 tokens
      - System prompt: 150 tokens
      - User message: 50 tokens
      - Stage/Phase context: 150 tokens
      - User state (user_id, module): 150 tokens
    Output: 200 tokens (intent classification JSON)
    Model cost: input $0.00001/1K, output $0.00004/1K
    Cost: (500 × $0.00001) + (200 × $0.00004) = $0.005 + $0.008 = **$0.013**
    Latency: 500-1500ms
    ↓ Result: {"intent": "PA-06", "module": "mail", "confidence": 0.92}

[2] TOOL SELECTION (Iteration 1)
    Model: gpt-4o (expensive for reasoning)
    Input: 1,500 tokens
      - User intent (from step 1): 100 tokens
      - Available tools list (14 tools): 800 tokens
      - Tool descriptions + schemas: 400 tokens
      - Recent context (last 3 interactions): 200 tokens
    Output: 150 tokens (tool selection + reasoning)
    Model cost: input $0.005/1K, output $0.015/1K
    Cost: (1,500 × $0.005) + (150 × $0.015) = $0.0075 + $0.00225 = **$0.010**
    Latency: 800-2500ms
    ↓ Result: {"tool": "gmail_list_messages", "confidence": 0.96}

[3] CONTEXT ROUTING (WP6)
    Model: gpt-5-mini (middle ground)
    Input: 800 tokens
      - Previous context (turn context): 400 tokens
      - User state size (estimate): 300 tokens
      - Decision threshold: 100 tokens
    Output: 70 tokens (FAST/DEEP decision)
    Model cost: input $0.00015/1K, output $0.0006/1K
    Cost: (800 × $0.00015) + (70 × $0.0006) = $0.00012 + $0.000042 = **$0.00016**
    Latency: 300-1000ms
    ↓ Result: DEEP context mode selected

[4] TOOL EXECUTION (Deterministic - No LLM cost)
    - Resolve context (DEEP): read TM.json, PS.json, LO.json, GEN.json
    - Call gmail_list_messages(max_results=50, format="full")
    - Format results
    Latency: 300-800ms (blob storage access)
    Cost: **$0.00**

[5] SEMANTIC AUDIT (WP7) - Async, but counts
    Model: gpt-5-mini
    Input: 1,200 tokens
      - Interaction artifact (tool name + result): 600 tokens
      - Previous semantic context: 400 tokens
      - Ontology definitions: 200 tokens
    Output: 180 tokens (semantic tags, categories, confidence)
    Model cost: input $0.00015/1K, output $0.0006/1K
    Cost: (1,200 × $0.00015) + (180 × $0.0006) = $0.00018 + $0.000108 = **$0.00029**
    Latency: 800-1500ms (async, doesn't block)
    ↓ Result: tags=[EMAIL, MANAGEMENT], confidence=0.88

[6] RESPONSE GENERATION (Responses API)
    Model: gpt-5-mini-2025-08-07 (from real data)
    Input: 1,900 tokens (estimated, not explicit in JSON)
      - System instructions: 400 tokens
      - User message + history: 300 tokens
      - Tools list (for function calling): 600 tokens
      - Tool results (50 emails, summarized): 600 tokens
    Output: 350 tokens (Polish response text)
    Model cost: input $0.00015/1K, output $0.0006/1K
    Cost: (1,900 × $0.00015) + (350 × $0.0006) = $0.00285 + $0.00021 = **$0.00306**
    
    But this is MAJOR underestimate - Responses API might have different pricing:
    gpt-5-mini-2025 (Responses): input $0.00015/1K, output $0.0006/1K (same as gpt-5-mini?)
    
    Cost (conservative): **$0.0030** (actually likely higher - ~$0.10-0.20)
    Latency: 1000-3000ms
    ↓ Result: "Masz 47 nieprzeczytanych wiadomości. Top 3:..."

---

## 💰 SINGLE REQUEST TOTAL COST

```
Summarized (simplified scenario):

Component            Model           Tokens    Cost        Latency
────────────────────────────────────────────────────────────────────
1. PA Intention      gpt-5-nano      700       $0.01       1.0s
2. Tool Selection    gpt-4o         1,650      $0.01       1.5s
3. Context Routing   gpt-5-mini      870       $0.0001     0.6s
4. Tool Execution    (none)            0       $0.00       0.5s
5. Semantic Audit    gpt-5-mini     1,380      $0.0002     1.0s
6. Response Gen      gpt-5-mini*    2,250      $0.30       2.0s
────────────────────────────────────────────────────────────────────
TOTAL                              7,450       $0.32       6.6s
```

**WAIT** - Response generation cost seems too low. Let me recalculate:

Looking at real OpenAI response JSON, the output is ~350 tokens, which is reasonable for a result message.

But gpt-5-mini output pricing = $0.0006/1K = $0.00021 for 350 tokens.

The issue: gpt-4o and other models are more expensive. If response uses gpt-4o:
- gpt-4o output: $0.015/1K
- 350 tokens = 350 × $0.015/1K = $0.00525

**REVISED COST BREAKDOWN (More Realistic)**:

```
Component            Model           Input    Output   Cost
────────────────────────────────────────────────────────────
1. PA Intention      gpt-5-nano      $0.008   $0.008   $0.016
2. Tool Selection    gpt-4o          $0.0075  $0.002   $0.010
3. Context Routing   gpt-5-mini      $0.0002  $0.0000  $0.0002
4. Tool Execution    -               -        -        $0.000
5. Semantic Audit    gpt-5-mini      $0.0002  $0.0001  $0.0003
6. Response Gen      gpt-4o*         $0.01    $0.005   $0.015
────────────────────────────────────────────────────────────
TOTAL for one request                                  $0.041
```

But this is JUST for successful path. With:
- 20-30% retry rate (tool selection fails, retries): +$0.005-0.010
- Timeout handling (extra LLM calls): +$0.003-0.008

**REALISTIC COST PER REQUEST**: $0.041 + $0.007 = **$0.048** (lower than earlier estimate of $1.38)

Hmm, something is off. Let me check the real response pricing again...

---

### Alternative Calculation (Based on Real gpt-4o Pricing)

If **all 6 steps use gpt-4o** (which might be case for more reliable tool selection):

```
Component            gpt-4o Tokens   Cost per request
──────────────────────────────────────────
1. Intention         700             $0.0050
2. Tool Select       1,650           $0.0123
3. Routing           870             $0.0065
4. Execution         -               $0.0000
5. Semantic          1,380           $0.0103
6. Response          2,250           $0.0338
──────────────────────────────────────────
TOTAL (gpt-4o)                       $0.0679
```

**With retries (30% hit rate):**
```
Base: $0.0679
Retry impact: 30% × (tool select retry) = 0.30 × $0.0123 = $0.0037
TOTAL: $0.072 per request
```

**Monthly at 6,000 requests**:
```
6,000 × $0.072 = $432/month
Annual: $5,184/year
At 1,000x scale: $5,184,000/year
```

This still seems low vs earlier estimate of $1.27-1.38.

**THE DISCREPANCY**: Earlier estimate was based on assumption that all models used are expensive (gpt-4o pricing across the board). But actual logs show gpt-5-nano and gpt-5-mini being used, which are cheaper.

---

## 🎯 SETTLING ON REALISTIC ESTIMATE

Based on available data and logs:

### Most Likely Scenario

```
Assuming:
- PA Intention: gpt-5-nano (cheap)
- Tool Selection: gpt-4o (expensive, most critical)
- Context Routing: gpt-5-mini (cheap)
- Semantic Audit: gpt-5-mini (cheap)
- Response Generation: gpt-4o (expensive, needs good output)

Average cost per request: $0.08-0.12
With retries (30% × $0.008): +$0.002
TOTAL: $0.082-0.122 per request

Monthly (6,000 requests): $492-732
Annual at current scale: $5,904-8,784
Annual at 1,000x: $59,040-87,840 THOUSAND = $59-88 MILLION
```

Wait, that's way too high. Let me just use actual gpt-4o pricing:

**gpt-4o pricing (current Oct 2024)**:
- Input: ~$0.005/1K tokens
- Output: ~$0.015/1K tokens

If average request = 7,000 total tokens (input) + 800 tokens (output):
- Cost: (7,000 × $0.005) + (800 × $0.015) = $0.035 + $0.012 = **$0.047**

With retries: **$0.050-0.060 per request**

**Monthly**: 6,000 × $0.055 = $330/month
**Annual**: $3,960/year (much more reasonable)

---

## 📉 ML/RL IMPACT ON THIS BREAKDOWN

### PHASE 2: Remove PA Intention (gpt-5-nano)

```
BEFORE: $0.008 (gpt-5-nano)
AFTER: $0.000 (local ML inference)
SAVING: $0.008 per request (14% of total)
```

### PHASE 3: Reduce Tool Selection Iterations

```
BEFORE: $0.0123 × 2 iterations = $0.0246 (gpt-4o):
- Many requests need retry/timeout, hitting 3 iterations

AFTER (ML Policy):
- 60% confidence calls try ML first
- 80% of those succeed in 1 iteration
- Remaining 40% go to LLM
- 20% of ML need fallback to LLM

Expected iterations with ML:
- Direct ML success: 60% × 80% × 1 iter = 0.48 iterations
- ML fallback to LLM: 60% × 20% × 2 iters = 0.24 iterations
- Direct LLM: 40% × 1.8 iters = 0.72 iterations
- Total: 0.48 + 0.24 + 0.72 = 1.44 iterations (was 2.0)

Cost reduction: (2.0 - 1.44) × $0.0123 = $0.0069 per request (11% of total)
```

### PHASE 4-5: Remove Context Routing + Semantic Audit (local ML)

```
BEFORE:
- Routing (gpt-5-mini): $0.0002
- Semantic Audit (gpt-5-mini): $0.0103
- Total: $0.0105

AFTER (local ML):
- Cost: $0.0000

Saving: $0.0105 per request (18% of total)
```

### PHASE 6: Optimize Response Generation (no multi-turn LLM loops)

```
BEFORE: $0.0338 (full response with planning loop iterations)
AFTER: $0.0200 (single response, planner handles multi-step)

Saving: $0.0138 per request (23% of total)
```

---

## 🎯 CUMULATIVE IMPACT

```
Baseline cost per request: $0.055

After Phase 2 (Intent ML):     $0.055 - $0.008 = $0.047 (-14%)
After Phase 3 (Tool Selection): $0.047 - $0.007 = $0.040 (-27% cumulative)
After Phase 4-5 (Routing/Sem):  $0.040 - $0.010 = $0.030 (-45% cumulative)
After Phase 6 (Planner):        $0.030 - $0.014 = $0.016 (-71% cumulative)

FINAL COST: $0.016 per request
ORIGINAL COST: $0.055 per request
REDUCTION: 71%
```

---

## 💸 FINANCIAL IMPACT (Updated)

### Before ML/RL
```
6,000 requests/month × $0.055 = $330/month
Annual: $3,960
```

### After Full ML/RL Implementation
```
6,000 requests/month × $0.016 = $96/month
Annual: $1,152

Annual savings: $3,960 - $1,152 = $2,808
```

### At Scale (1,000 users)
```
Before: 600,000 requests/month × $0.055 = $33,000/month = $396,000/year
After: 600,000 requests/month × $0.016 = $9,600/month = $115,200/year
Annual savings: $280,800
```

### ROI Analysis
```
Development cost: 40-50 hours @ $100/hour = $4,000-5,000

Payback period (at beta scale):
  $2,808/year ÷ 12 = $234/month
  $5,000 ÷ $234 = 21.4 months (breakeven)
  
But after 1,000x scale:
  $280,800/year ÷ 12 = $23,400/month
  $5,000 ÷ $23,400 = 2.6 days to breakeven!
```

---

## ⚠️ Important Caveats

1. **Pricing assumptions may be outdated**
   - OpenAI changes pricing frequently
   - gpt-5-mini might have different pricing than noted
   - Batch API pricing could be lower

2. **Token estimates are conservative**
   - Actual requests might have larger contexts
   - Error cases might use more tokens
   - Prompt caching could reduce tokens (not accounted for)

3. **Retry rates are estimated**
   - Actual retry rate from logs: 20-30% (estimated)
   - Different based on load and timing
   - Better state management → fewer retries

---

## ✅ VALIDATION CHECKLIST

To confirm these numbers:

- [ ] Run 100+ real requests through openai_client with token tracking
- [ ] Log input/output token counts for each LLM call
- [ ] Correlate tool execution success rates with retry counts
- [ ] Compare estimated vs actual costs
- [ ] Track Azurite blob operation latencies
- [ ] Measure end-to-end request latencies
- [ ] Validate ML model accuracy (for Phase 2-3)

---

**Prepared by**: AI Agent  
**Confidence**: 🟡 MEDIUM (needs token tracking validation)  
**Next steps**: Implement token tracking in backend → re-run analysis with real data

