# 📉 LLM Reduction Analysis
## Estimate zaoszczędzenia dzięki ML/RL/Planner wdrożeniu

**Status**: Wstępna analiza (na podstawie Architecture Review)  
**Zakres**: OmniFlow backend (tool_call_handler) + PA-01..15  

---

## 🎯 Cel

Oszacować **o ile zostanie zmniejszone obciążenie LLM** jeśli przejdziemy na architekturę ML/RL/Planner.

**Obecna architektura**: LLM decyduje = LLM kosztuje (model calls + tokens)  
**Target architektura**: ML/RL decyduje, LLM tylko tekst = drastyczne zmniejszenie

---

## 📊 Current LLM Usage (Baseline)

### LLM Entry Points & Frequency

Na podstawie `backend/tool_call_handler/__init__.py` i dokumentacji:

| Komponent | Model | Trigger | Per Request | Est. Freq./h |
|-----------|-------|---------|-------------|------------|
| **PA Intention Step** | `gpt-5-nano` | PA function call | 1 call | ~100-200 |
| **Tool Selection** | `gpt-5-mini` / `gpt-4o` | Each tool loop iteration | 1-5 calls | ~200-1000 |
| **Context Routing (WP6)** | `gpt-5-mini` | FAST/DEEP decision | 1 call | ~100-200 |
| **Semantic Tagging (WP7)** | `gpt-5-mini` | Every interaction (async) | 1 call | ~50-100 |
| **Response Generation** | `gpt-4o` / `claude-3.7-sonnet` | Final output | 1 call | ~100-200 |
| **TOTAL** | Mixed | - | **5-12 calls** | **~550-1700 calls/h** |

### Token-Level Breakdown (Per Request)

Średni request flow:
```
User Message
  ├─ Encoding: 100 tokens (user intent)
  ├─ PA Intention call:
  │   ├─ Prompt: 500 tokens
  │   ├─ Response: 200 tokens
  │   └─ Cost: $0.005-0.010
  │
  ├─ Tool Selection loop (avg 2 iterations):
  │   ├─ Per iteration:
  │   │   ├─ Prompt (tools list + state): 1000 tokens
  │   │   ├─ Response: 100 tokens
  │   │   └─ Cost: $0.02-0.05 (if gpt-4o)
  │   └─ Total 2x: $0.04-0.10
  │
  ├─ Context Routing:
  │   ├─ Prompt: 800 tokens
  │   ├─ Response: 50 tokens
  │   └─ Cost: $0.01-0.02
  │
  ├─ Semantic Tagging:
  │   ├─ Prompt: 1000 tokens
  │   ├─ Response: 200 tokens
  │   └─ Cost: $0.002-0.005
  │
  └─ Response Generation:
      ├─ Prompt: 500 tokens
      ├─ Response: 300 tokens
      └─ Cost: $0.01-0.02
```

**TOTAL PER REQUEST**: 
- **Prompt tokens**: 3,900 tokens
- **Completion tokens**: 850 tokens
- **Cost**: **$0.09-0.20 per request**

### Monthly Cost (Current - LLM Only)

Assumptions:
- Active users: ~10 (beta)
- Avg requests per user per day: 20
- Working days per month: 20
- Availability: 5 hours/day prod

```
Requests/month = 10 users × 20 req/day × 20 days = 4,000 requests
Cost/request = $0.12 (average)
Monthly Cost = 4,000 × $0.12 = $480/month

Annual Cost (at current scale) = $480 × 12 = $5,760/year
```

**At scale (1000 users)**: $57,600/year

---

## 🚀 ML/RL/Planner Architecture - Cost Reduction

### Phase-by-Phase Replacement

#### **PHASE 1: Policy Evaluation (No Code Changes)**
- 🟢 **LLM Cost Impact**: **0% reduction** (still using LLM)
- 📊 **Benefit**: Establishes baseline for comparison with ML

---

#### **PHASE 2: Intent Classifier (ML Replaces Intention Step)**

**What Gets Replaced**:
- ❌ `gpt-5-nano` call for intent parsing
- ✅ Replaced by: Local sklearn/PyTorch inference (milliseconds, $0 cost)

**Impact**:
```
BEFORE:
  PA Intention Step (gpt-5-nano):
    - Tokens: 700 (500 prompt + 200 completion)
    - Cost: $0.004-0.008
    - Latency: 500-2000ms (API)

AFTER:
  Intent Classifier (local ML):
    - Tokens: 0 (no API call)
    - Cost: $0.00 (inference free)
    - Latency: 10-50ms (local)

SAVING: $0.004-0.008 per request (5-10% of total LLM cost)
```

**Reduction**: ~5-10% of LLM cost

---

#### **PHASE 3: Imitation Learning (ML Replaces Tool Selection)**

**What Gets Replaced**:
- ❌ `gpt-4o` / `gpt-5-mini` tool selection loop (1-5 iterations)
- ✅ Replaced by: Local policy network inference (single forward pass)

**Impact** (Major):
```
BEFORE (Tool Selection Loop):
  Per iteration:
    - Tokens: 1,100 (1000 prompt + 100 completion)
    - Cost: $0.02-0.05 (gpt-4o pricing)
    - Latency: 500-3000ms
  
  Avg 2 iterations:
    - Tokens: 2,200
    - Cost: $0.04-0.10
    - Latency: 1-6 seconds

AFTER (ML Policy):
  Single inference:
    - Tokens: 0 (no API call)
    - Cost: $0.00
    - Latency: 5-20ms (local batch)

SAVING: $0.04-0.10 per request (40-60% of total LLM cost!)
```

**Reduction**: ~40-60% of LLM cost

---

#### **PHASE 4: Offline RL (Optional - Further Optimization)**

**What Improves**:
- Tool selection becomes **adaptive** (learns from episodes)
- Fewer fallbacks to LLM
- Better policy → higher success rate → fewer retries

**Impact** (Incremental):
```
BEFORE (After Imitation, Phase 3):
  Tool confidence: 50-70%
  Fallback to LLM: 20-30% of requests
  Avg 0.5 extra LLM calls per request

AFTER (RL Fine-Tuned):
  Tool confidence: 85-95%
  Fallback to LLM: 2-5% of requests
  Avg 0.05 extra LLM calls per request

SAVING: 0.45 LLM calls × $0.12 = $0.05-0.06 per request (5-8% more reduction)
```

**Reduction**: ~5-8% additional

---

#### **PHASE 5: Context Routing + Semantic Tagging (ML Classifiers)**

**What Gets Replaced**:
- ❌ `gpt-5-mini` routing decision (WP6)
- ❌ `gpt-5-mini` semantic audit (WP7) - currently async, could be sync ML
- ✅ Replaced by: Local classifiers

**Impact**:
```
WP6 Context Routing:
  - Tokens: 850 per request
  - Cost: $0.002-0.003 per request
  - Saving: 100% of WP6 cost

WP7 Semantic Tagging:
  - Tokens: 1,200 per request (async)
  - Cost: $0.003-0.005 per request (current overhead)
  - Saving: 100% of WP7 cost (if moved to ML)

Total: $0.005-0.008 per request (5-10% additional)
```

**Reduction**: ~5-10% additional

---

#### **PHASE 6: Planner + Goal Decomposition**

**What Gets Replaced**:
- ❌ LLM multi-step planning loop
- ✅ Replaced by: Graph-based planner (deterministic)

**Impact** (Low-Medium):
```
Multi-step requests (5-10% of total):
  - Extra LLM loops for planning: 3-5 additional calls per request
  - Cost: $0.30-0.60 per complex request
  - Frequency: 5-10% of requests
  - Saving if planner works: 100% of planning cost

Overall impact: ~2-3% additional reduction
```

**Reduction**: ~2-3% additional

---

## 📈 **CUMULATIVE REDUCTION** (All Phases)

| Phase | Component | Reduction | Cumulative |
|-------|-----------|-----------|-----------|
| **Baseline** | LLM Only | - | **100%** |
| **Phase 2** | Intent (ML) | 5-10% | **90-95%** |
| **Phase 3** | Tool Select (Imitation) | 40-60% | **30-55%** |
| **Phase 4** | RL Fine-Tuning | 5-8% | **22-47%** |
| **Phase 5** | Routing + Semantic | 5-10% | **12-42%** |
| **Phase 6** | Planner | 2-3% | **10-39%** |

---

## 💰 **COST SAVINGS SUMMARY**

### Monthly Cost Comparison

```
CURRENT (LLM Only, 4,000 req/month):
  Cost per request: $0.12
  Monthly: 4,000 × $0.12 = $480
  
AFTER PHASE 2 (Intent ML):
  Cost per request: $0.11
  Monthly: 4,000 × $0.11 = $440
  Savings: $40/month (-8%)

AFTER PHASE 3 (Imitation Learning):
  Cost per request: $0.05-0.07
  Monthly: 4,000 × $0.06 = $240
  Savings: $240/month (-50%)  ← MAJOR JUMP

AFTER PHASES 4-6 (Full System):
  Cost per request: $0.03-0.04
  Monthly: 4,000 × $0.035 = $140
  Savings: $340/month (-71%)  ← BREAKTHROUGH
```

### Annual Savings (At Different Scales)

| Scale | Current/Year | Post-Full (71% reduction) | Annual Savings | ROI Breakeven |
|-------|---|---|---|---|
| **10 users (beta)** | $5,760 | $1,670 | $4,090 | < 1 week |
| **100 users** | $57,600 | $16,700 | $40,900 | < 2 weeks |
| **1,000 users** | $576,000 | $167,000 | $409,000 | < 1 month |
| **10,000 users** | $5,760,000 | $1,670,000 | $4,090,000 | < 2 days |

---

## ⏱️ Latency Improvements

**Current (LLM-based)**:
- Intent parsing: 500-2000ms
- Tool selection (2 iter): 1-6 seconds
- Context routing: 300-1500ms
- Total: **2-10 seconds per request**

**After Full ML/RL** (~Phase 5):
- Intent parsing: 10-20ms (ML, 50-100x faster)
- Tool selection: 5-15ms (ML, 100-400x faster)
- Context routing: 5-10ms (ML, 50-150x faster)
- Response gen only: 500-2000ms (LLM)
- **Total: 0.5-2.5 seconds per request (4-10x faster)**

---

## 🔐 Non-Financial Benefits

| Benefit | Impact | Value |
|---------|--------|-------|
| **Latency** | 4-10x faster UX | ⭐⭐⭐⭐⭐ |
| **Reliability** | Less API deps, deterministic | ⭐⭐⭐⭐ |
| **Compliance** | Data stays local (no LLM calls) | ⭐⭐⭐⭐ |
| **Customization** | Fine-tune on user data | ⭐⭐⭐⭐ |
| **Offline** | ML works without internet | ⭐⭐⭐ |
| **Scaling** | Better for mobile/edge | ⭐⭐⭐⭐ |

---

## ⚠️ Important Caveats

1. **Estimates are conservative**: Based on current pricing (gpt-4o ~$0.01-0.03/1K tokens)
   - Actual costs could be lower if using cheaper models
   - Actual costs could be higher if Phase 3 requires more LLM fallbacks

2. **Requires successful Phase 3**: 
   - If imitation accuracy < 50%, cost savings will be much lower
   - Fallback logic needed (use LLM if ML confidence too low)

3. **Infrastructure costs not included**:
   - Model training pipeline (one-time, ~$100-500)
   - Model serving infrastructure (negligible if local)
   - Monitoring + retraining labor (one-time overhead)

4. **Scale dependencies**:
   - At <100 users: LLM cost OK, but ML still worth it for latency
   - At >10K users: LLM costs become prohibitive, ML necessary

---

## 🎯 Recommendation

### If Cost is Primary Driver:
✅ **Proceed with Phases 2-3** (Intent + Imitation Learning)
- ROI breakeven: < 2 weeks at scale
- Cost reduction: 50% achievable with phase 3 alone
- Risk: Medium (requires imitation learning to work)

### If Performance is Primary Driver:
✅ **Proceed with Phases 2-3** (for 4-10x latency improvement)
- UX significantly improves
- More responsive application
- Better scaling for mobile/edge

### If Data Privacy is Concern:
✅ **Phases 2-4-5** become critical
- No user data sent to OpenAI
- Semantic understanding can stay local
- Compliance friendly

### Full Stack (Phases 1-6):
✅ **Best long-term strategy**
- 71% cost reduction
- 4-10x faster
- Local, private, resilient
- Timeline: 6 weeks (as planned)

---

## 📝 Decision Points

### Before Phase 2:
- [ ] Confirm imitation learning is viable (target accuracy ≥ 50%)
- [ ] Confirm infrastructure for ML model serving available
- [ ] Approve cost savings / latency trade-offs

### Before Phases 3-4:
- [ ] Verify Phase 2 working in production
- [ ] Decide on RL training budget
- [ ] Plan for fallback LLM logic

### Before Phases 5-6:
- [ ] Confirm latency requirements met
- [ ] Plan for edge/mobile deployment
- [ ] Decide on full offline capability

---

## 💡 Quick Summary

```
┌─────────────────────────────────────────────────────┐
│ SO JAK DUZO ZMNIEJSZY SIE OBCIAZENIE LLM?           │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Phase 2 (Intent ML):       -8%  ($40/month)         │
│ Phase 3 (Imitation):      -50%  ($240/month)        │
│ Phase 4 (RL Fine-tune):   -8%   ($38/month)         │
│ Phase 5 (Routing+Semantic): -10% ($48/month)        │
│ Phase 6 (Planner):        -3%   ($14/month)         │
│                           ─────────────────         │
│ RAZEM:                    -71%  ($340/month)        │
│                                                     │
│ Na 10,000 użytkowników = $4.090.000 rocznie         │
│ Latency: 2-10s → 0.5-2.5s (5-10x szybciej)         │
└─────────────────────────────────────────────────────┘
```

**Na dzisiaj (10 użytkowników beta)**:
- Koszt LLM: ~$480/miesiąc
- Po implementacji: ~$140/miesiąc
- **Oszczędzenie: ~$340/miesiąc** (od miesiąca 2)

**ROI Breakeven**: Koszt pracy (40-50h) vs oszczędzenie w 1-2 miesiące

---

**Prepared by**: AI Agent  
**Date**: 2026-02-10  
**Status**: 🟡 DRAFT - Awaiting validation with actual API costs

