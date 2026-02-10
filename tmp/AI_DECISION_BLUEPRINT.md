# OmniFlow – AI Decision Intelligence Blueprint
## Transforming LLM-Asystent to (ML + RL + Planner) System

**Status**: Plan-gated analysis (no code changes yet)  
**Date**: 2026-02-10  
**Scope**: Comprehensive mapping of Decision Intelligence integration points  

---

## 📋 Executive Summary

**Celem**: zastąpienie LLM-asystenta **systemem decyzyjnym** (ML + RL + Planner), gdzie:
- **LLM** = tylko warstwa output (generowanie tekstu z przetworzonych danych)
- **ML/RL/Planner** = core decision logic
- **Dane** = epizody decyzyjne (rollouts, intention logs, interakcje)

**Repozytorium posiada**:
- ✅ 50+ GB decyzyjnych artefaktów (interaction_logs, semantic index, intent routes)
- ✅ Architekturę multi-user z izolacją per `user_id`
- ✅ Tool handler (14 tools) gotowy na integrację z ML-state predictors
- ✅ Semantic indexing (WP7) przygotowany na feature engineering dla RL
- ✅ Context packing (WP6) gotowy na state-encoding

**Brakuje**:
- ❌ Offline episode parser (roll-out → state/action/reward)
- ❌ Policy evaluation baseline
- ❌ Imitation learning model
- ❌ Planner engine (oprócz LLM)
- ❌ Offline RL reward shaping

---

## 1. Gdzie jest LLM w architekturze dzisiaj

### 1.1 LLM Entry Points

| Komponent | Role | LLM Model | Triggers |
|-----------|------|-----------|----------|
| **Chat UI** (`ai-chatbot/app/`) | Konwersacja użytkownika | `claude-3.7-sonnet` (Vercel AI Gateway) | User message |
| **Tool Handler** (`backend/tool_call_handler/__init__.py`) | Orchestracja tool-loop | OpenAI Assistants API (`gpt-4o` default) | Tool calls via `save_interaction` |
| **WP7 Semantic Audit** (`tool_call_handler/wp7/`) | Semantic tagging interactions | `gpt-5-mini` | Every interaction (async) |
| **WP6 Context Router** (`tool_call_handler/wp6/`) | FAST vs DEEP routing | `gpt-5-mini` + cached prompts | Context need signal |
| **PA-01..PA-15** (Scope) | Personal Assistance functions | `gpt-5-mini` / `gpt-nano` | FSM transitions |

**Przepływ od LLM do ML**: interaction → LLM decision → tool call → state update → JSONL artifact → (FUTURE) ML feature

### 1.2 LLM Current Responsibilities

```
User Message
    ↓
[LLM Chat] (UI layer)
    ↓ (intent + context request)
[LLM Tool Handler] (orchestrator)
    ├─ Decides which tool to call
    ├─ Formats arguments
    └─ Loops until done
    ↓ (writes)
[Blob Storage] (user/{id}/*.json)
    ↓ (indexes)
[WP7 Semantic] (LLM tags interactions)
    ↓
[Context Packer] (WP6: prepares next input)
    └─ Routes to FAST/DEEP (LLM decides)
```

---

## 2. Gdzie są DANE DECYZYJNE

### 2.1 Struktura Artefaktów (Evidence Layer)

| Plik/Folder | Format | Sygnał | Użycie |
|------------|--------|--------|-------|
| `interaction_logs.json` | Array<Interaction> | sequence of user→LLM→tool→state | Episode replay |
| `interactions/index.jsonl` | JSONL (metadata per interaction) | intent, tool calls, status | Episode indexing |
| `interactions/semantic/index.jsonl` | JSONL + per-file JSON | AI-tagged category/confidence/tags | Feature: semantic context |
| `interactions/semantic/INT_*.json` | JSON (detailed semantic) | extracted entities, relations, summary | Feature: structured representation |
| `TM.json`, `PS.json`, `LO.json`, `GEN.json` | JSON arrays | user state snapshots | Feature: context state |
| `handles.json` | JSON (thread handles) | last run metadata, threading | Feature: sequence checkpoint |
| `semantics/wp6_fast_audit/` | JSON (audit logs) | FAST→DEEP routing decisions | Feature: routing signal (reward?) |

**Przykład episode (pełna sekwencja)**:
```
User: "sprawdź TM"
  ↓ [tools: list_blobs, read_blob_file]
Agent: "Znalazłem 3 zadania todo, 1 recurring"
  ↓ [state snapshot: TM.json updated]
Artifact: interaction_id + semantic_tags + audio tags + state delta
  ↓
[ML Feature]: state_before, action_type, reward_signal (success/timeout/error)
```

### 2.2 Decyzyjne Epizody – Gdzie Są?

**Pełne episodes (state → action → state+reward)**:
```
~50 interactions w default user:
  - 30+ semantic entries (tagged)
  - 8+ full TM modifications
  - 4+ list/read operations (success/retry/timeout)
  - 2+ mail-related (Pa-13..PA-15)
  - 10+ knowledge recall (PA-06)

Format:
  input_state = {TM: [...], PS: [...], LO: [...], last_context: "..."}
  action = tool_call(name, args)
  output_state = {TM: [...updated], SYS: [...audit]}
  reward = {success: 1, timeout: -0.5, error: -1, semantic_confidence: 0.65}
```

**Gdzie to czytać**:
- `tmp/agentdatastorage_users_snapshot_20260210_105740/users/default/`
- `tmp/azurite_users_snapshot_20260210_113055/users/`

---

## 3. MAPOWANIE LLM → ML/RL/Planner (Punkty Substytucji)

### 3.1 Warstwa-po-warstwie: Co Zastąpić

| Warstwa | LLM Role Dzisiaj | → ML/RL Role | Artefakt wejścia | Artefakt wyjścia |
|---------|------------------|-------------|------------------|-----------------|
| **1. Intent Recognition** | GPT parses `user_message`, decyduje tool | Policy: klasyf. intent + tool (supervised ML) | `user_message` | `intent_vector + tool_name` |
| **2. Context Routing (WP6)** | GPT decyduje FAST vs DEEP | Bandit / value predictor | `interaction_id + handles` | `routing_signal (FAST/DEEP)` |
| **3. State Encoding** | GPT reads blobs, aggregates context | Feature extractor (NN) | `TM.json + PS.json + ...` | `state_embedding` |
| **4. Tool Selection** | GPT picks tool from allowlist | Policy: multi-arm bandit / DQN | `state_embedding + intent` | `tool_id + confidence` |
| **5. Argument Planning** | GPT fills arguments (few-shot) | Policy: seq-to-seq or multi-head output | `tool_schema + state` | `args_vector` |
| **6. Execution (Tools)** | Tool handler executes | Deterministic (same) | `tool + args` | `result_json` |
| **7. Semantic Tagging (WP7)** | GPT tags with `category/confidence/tags` | Classifier: intent→category + NER | `interaction_json` | `semantic_tags_json` |
| **8. Reward Shaping** | N/A | Offline RL: define success/failure metrics | `interaction + output_state` | `reward_scalar` |
| **9. Response Generation** | GPT generates Polish text | Template + extractive summarization | `action_result + state_delta` | `response_text` |

### 3.2 Konkretne Punkty Substytucji (Faza po Fazie)

#### **FAZA 1: Policy Evaluation (Risk = ZERO, Reward = Analysis)**

Cele:
- Policzyć success rate dzisiaj
- Obliczyć retry distribution
- Znaleźć failure modes

Nie uruchamiamy nowego kodu; czytamy historię.

**Punkt 1.1: Intent Classifier Baseline**
- LLM: `user_message` → parsing intent (ad-hoc w prompt)
- ML: supervised classifier (`intent_labels` vs `user_message_embedding`)
- Data: 50 interactions → intent labels (manual pass lub heurystyka z tool-calls)
- Model: sklearn LogisticRegression or small NN (scikit-learn / PyTorch)
- Output: `accuracy` vs LLM on test set

**Punkt 1.2: Tool Selection Error Rate**
- LLM: picks tool from allowlist via prompt
- Analysis: which tools were picked wrong? (vs task type)
- Data: tool-call history + outcome (success/timeout)
- Metric: error rate per tool, per task type
- Goal: 1 week offline analysis, no ML yet

**Punkt 1.3: Success/Failure Breakdown**
- Count: `success=good_artifact`, `retry=timeout`, `error=invalid_tool_args`
- Metric: `success_rate`, `avg_retries_per_episode`, `timeout_%`
- Data source: `interactions/index.jsonl` + `SYS.json` audit logs
- Output: histogram + summary (markdown table)

**Code location**: `labs/ml_lab/policy_eval_v0.py` (NEW)

---

#### **FAZA 2: Imitation Learning (Risk = LOW, Reward = Baseline Policy)**

Cele:
- Nauczać model "jak agent robi" (behavior cloning)
- Ocenić czy baseline > random

**Punkt 2.1: State Encoder**
- Input: `{TM, PS, LO, GEN, SYS, last_context}`
- Encoding: hashing + pooling (count per category) or simple embeddings
- Output: `state_vector` (fixed-size, ~100-500 dims)
- Code: `labs/ml_lab/encoding/state_encoder.py` (NEW)

**Punkt 2.2: Action Vectorization**
- Actions: `{tool_name, tool_args (JSON)}`
- Encoding: one-hot(tool_name) + arg embeddings
- Output: `action_vector`
- Code: `labs/ml_lab/encoding/action_encoder.py` (NEW)

**Punkt 2.3: Imitation Model**
- Input: `(state_vector, user_embedding)`
- Output: `logits[tool_id]` or `prob[tool | state]`
- Architecture: simple MLP (sklearn or PyTorch)
- Training: episodes where agent succeeded
- Metric: accuracy on test episodes
- Code: `labs/ml_lab/imitation/imitation_policy.py` (NEW)

**Co zastępuje w runtime?**
- Przy włączonej flag `USE_IMITATION_POLICY=1`: tool selection używa modelu zamiast LLM
- LLM wciąż generuje argument + response text
- Fallback: jeśli confidence < threshold, użyj LLM

---

#### **FAZA 3: Offline RL (Risk = MEDIUM, Reward = Optimized Policy)**

Cele:
- Wybrać które decyzje były dobre/złe
- Trenować policy żeby preferować dobre

**Punkt 3.1: Reward Model**
- Success: `+1.0` (episode reached goal)
- Timeout: `-0.5` (had to retry)
- Error: `-1.0` (failed completely)
- Semantic confidence: `+0.1 * confidence` (bonus if high confidence)
- Data: label każdą pełną sekwencję z `interaction_logs.json`
- Code: `labs/ml_lab/rewards/reward_model.py` (NEW)

**Punkt 3.2: Conservative Q-Learning**
- Algorithm: CQL (Conservative Q-Learning) for Offline RL
- Input: state, action, next_state, reward
- Output: Q-function `Q(s, a) = expected return`
- Data prep: episodes from `interactions/index.jsonl`
- Code: `labs/ml_lab/rl/cql_trainer.py` (NEW)

**Punkt 3.3: Policy Distillation**
- Source: Q-function
- Target: deterministic policy (smaller, faster)
- Output: `policy(state) → action_distribution`
- Code: `labs/ml_lab/rl/policy_extractor.py` (NEW)

**Co zastępuje w runtime?**
- Policy output replaces LLM tool selection
- Context: shadow mode (run both, log diff) → production (use only ML)

---

#### **FAZA 4: Planning Engine (Risk = HIGH, Reward = Sequencing)**

Cele:
- Nie tylko wybierać akcję, ale plan sekwencji
- Planner = graf + regułki + heurystyka

**Punkt 4.1: State Graph**
- Nodes: `{user_state_id}` (repr. from TM/PS/LO/GEN)
- Edges: `action → next_state` (deterministic given state + tools)
- Data: build from historical episodes
- Code: `labs/ml_lab/planning/state_graph.py` (NEW)

**Punkt 4.2: Planner (STRIPS-like)**
- Input: goal (e.g., "update task #2 + send mail")
- Output: action sequence `[action1, action2, ...]`
- Constraints: preconditions (e.g., "TM must exist"), effects (e.g., "TM updated")
- Code: `labs/ml_lab/planning/planner.py` (NEW)

**Punkt 4.3: Plan Validator**
- Check: does plan exist in historical episodes?
- Rank plans by: success_rate, cost (num actions)
- Code: `labs/ml_lab/planning/plan_validator.py` (NEW)

**Co zastępuje w runtime?**
- LLM: no longer loops tool calls (planner decides sequence)
- LLM: only generates final response text from plan result

---

### 3.3 High-Level Intent-Resolve Artifact Stack (for ML Training)

```
user_message
  ↓
[Intent Classifier] (FAZA 2)
  → intent_id, intent_confidence
  ↓
[State Encoder] (FAZA 2)
  → state_vector, state_id
  ↓
[Policy] (FAZA 2/3)
  → tool_selection, args_logits
  ↓
[Tool Executor] (deterministic, same as today)
  → tool_result, tool_status
  ↓
[State Update] (deterministic)
  → new_state, state_delta
  ↓
[Reward Calculator] (FAZA 3)
  → reward_scalar
  ↓
[Semantic Tagger] (FAZA 2)
  → category, confidence, tags
  ↓
[Response Generator] (LLM, text-only)
  → response_text
  ↓
[ARTIFACT] Save:
{
  "episode_id": "...",
  "timestamp": "...",
  "user_id": "...",
  "intent": {...},
  "state_before": {...},
  "action": {...},
  "state_after": {...},
  "reward": 0.8,
  "semantic": {...},
  "response": "...",
  "schema_version": "omniflow.ml_episode.v1"
}
```

---

## 4. Architektura Decision Intelligence (LAB ML)

### 4.1 Directory Structure (NEW)

```
OmniFlowBeta/
├── labs/
│   └── ml_lab/
│       ├── __init__.py
│       ├── README.md (documentation)
│       ├── env_setup.sh (create venv, install deps)
│       ├── config.yaml (dataset paths, model params)
│       │
│       ├── 1_episode_parser/
│       │   ├── __init__.py
│       │   ├── parser.py (JSONL → Episode namedtuple)
│       │   ├── episode_schema.json (contracts)
│       │   └── tests/
│       │       └── test_parser.py
│       │
│       ├── 2_policy_eval/
│       │   ├── __init__.py
│       │   ├── eval_baseline.py (success rate, retry dist)
│       │   ├── eval_intent.py (intent accuracy)
│       │   ├── eval_tool_selection.py (tool error rate)
│       │   └── tests/
│       │
│       ├── 3_encoding/
│       │   ├── __init__.py
│       │   ├── state_encoder.py
│       │   ├── action_encoder.py
│       │   ├── embedding_utils.py
│       │   └── tests/
│       │
│       ├── 4_imitation/
│       │   ├── __init__.py
│       │   ├── imitation_policy.py (behavior cloning)
│       │   ├── trainer.py (fit model)
│       │   ├── models/ (sklearn/NN checkpoints)
│       │   └── tests/
│       │
│       ├── 5_offline_rl/
│       │   ├── __init__.py
│       │   ├── reward_model.py (r(s,a) = scalar)
│       │   ├── cql_trainer.py (Conservative Q-Learning)
│       │   ├── policy_extractor.py (Q → π)
│       │   ├── models/ (policy checkpoints)
│       │   └── tests/
│       │
│       ├── 6_planning/
│       │   ├── __init__.py
│       │   ├── state_graph.py (nodes + edges)
│       │   ├── planner.py (goal → plan)
│       │   ├── plan_validator.py (check feasibility)
│       │   └── tests/
│       │
│       ├── 7_shadow_mode/
│       │   ├── __init__.py
│       │   ├── shadow_runner.py (run both LLM + ML, compare)
│       │   ├── metrics.py (divergence, accuracy)
│       │   └── tests/
│       │
│       ├── data/
│       │   ├── snapshots/ (user data reads)
│       │   ├── episodes/ (parsed JSONL)
│       │   ├── artifacts/ (model outputs)
│       │   └── .gitignore
│       │
│       ├── notebooks/
│       │   ├── 01_data_exploration.ipynb
│       │   ├── 02_policy_eval.ipynb
│       │   ├── 03_imitation_training.ipynb
│       │   └── 04_offline_rl.ipynb
│       │
│       └── requirements.txt (scikit-learn, pytorch, pandas, etc.)
```

### 4.2 Data Flow (Read-Only from Runtime)

```
[Runtime] → [Blob Storage] → [Lab: Read-Only Snapshots]
  ↓
[Policy Evaluator]
  ↓ (analysis, no feedback)
[Data Scientist: Offline Analysis]
  ↓
[Imitation Learner] → [model.pkl / ckpt]
  ↓
[Offline RL Trainer] → [policy.ckpt]
  ↓
[Shadow Mode Tester] (in backend, new env var)
  ↓
[Production Rollout] (if metrics OK)
```

**Key constraint**: Lab reads snapshots only; does NOT write to user data.

---

## 5. Rollout Plan (Fazy Wdrożenia)

### 5.1 Timeline & Milestones

| Week | Phase | Outputs | Risk | Gate |
|------|-------|---------|------|------|
| **1** | **Policy Eval** | baseline metrics, failure modes | ZERO | None (analysis only) |
| **2** | **Episode Parser** + **State Encoder** | parser contract, embeddings | LOW | Tests pass |
| **2-3** | **Imitation Learning v0** | behavior cloning baseline, accuracy | LOW | Eval baseline > 50% on held-out |
| **3-4** | **Offline RL Setup** | reward model + CQL trainer | MEDIUM | Solo trainer test (no backend) |
| **4** | **Shadow Mode (Backend)** | dual-run, metrics comparison | MEDIUM | LLM vs ML divergence < 10% |
| **5** | **Plan Engine v0** | state graph + basic planner | HIGH | Plan exists for 80% of historical episodes |
| **5-6** | **Rollout (Canary)** | use ML for 10% of requests | HIGH | KPI: success rate ≥ current LLM |
| **6+** | **Full Rollout** | use ML for 100%, LLM fallback | MEDIUM | Monitor and adapt |

### 5.2 DoD per Phase

**Policy Eval (Week 1)**
- [ ] `success_rate` calculated from episodes
- [ ] `retry_distribution` histogram plotted
- [ ] `failure_root_causes` categorized (timeout, tool error, etc.)
- [ ] Report generated: `labs/ml_lab/reports/policy_eval_baseline.md`

**Episode Parser (Week 2)**
- [ ] Parser converts `interaction_logs.json` → Episode namedtuples
- [ ] `episode_schema.json` matches contract
- [ ] Unit tests pass (>90% on real data)
- [ ] Artifact: `labs/ml_lab/data/episodes/*.pkl` (sampled episodes)

**Imitation Learning (Week 2-3)**
- [ ] Classifier trained on 70% of episodes
- [ ] Test accuracy ≥ 50% (baseline = 20% random for 5 tools)
- [ ] Model saved: `labs/ml_lab/4_imitation/models/policy_v0.pkl`
- [ ] Confidence distribution: 90% of predictions > 0.6
- [ ] Report: `labs/ml_lab/reports/imitation_v0.md`

**Offline RL (Week 3-4)**
- [ ] Reward model defined and tested
- [ ] CQL trainer runs on sampled episodes (no divergence)
- [ ] Policy extracted from Q-function
- [ ] Model saved: `labs/ml_lab/5_offline_rl/models/policy_rl_v0.ckpt`
- [ ] Report: `labs/ml_lab/reports/offline_rl_v0.md`

**Shadow Mode (Week 4)**
- [ ] Backend env var: `USE_ML_SHADOW_MODE=1`
- [ ] Both LLM + ML run, log both decisions
- [ ] Divergence metric: < 10% (different tool selected)
- [ ] Success rate comparable (within 5%)
- [ ] Report: `labs/ml_lab/reports/shadow_mode_metrics.csv`

**Planner (Week 5)**
- [ ] State graph built from episodes
- [ ] Planner finds plan for goal states
- [ ] 80% of historical episodes match planned sequences
- [ ] Report: `labs/ml_lab/reports/planner_coverage.md`

**Canary Rollout (Week 5-6)**
- [ ] Backend flag: `ML_POLICY_PERCENTAGE=10` (10% of traffic)
- [ ] ML tool selection used for those 10%
- [ ] Success rate ≥ current; retry rate ≤ current
- [ ] No increase in errors; fallback works
- [ ] Gate: metrics stable for 3 days

---

## 6. Real Example: Task Management (PA-01)

### 6.1 Current Flow (LLM-Only)

```
User: "sprawdź moje zadania"
  ↓
[Chat UI calls backend]
  ↓
[LLM (Tool Handler)]:
  - Reads TM via list_blobs + read_blob_file
  - Parses tasks
  - Generates Polish summary
  ↓
[Tools execute, state updates]
  ↓
[Response]: "Masz 3 zadania do wykonania..."
```

### 6.2 Proposed Flow (ML + LLM Hybrid)

```
User: "sprawdź moje zadania"
  ↓
[Intent Classifier (ML)]: intent_id=PA-01, confidence=0.95
  ↓
[State Encoder (ML)]: state_vector = encode(TM, PS, LO, GEN)
  ↓
[Policy (ML, Imitation)]: 
  - P(list_blobs | state) = 0.9
  - P(read_blob_file | state) = 0.05
  - Decision: use list_blobs
  ↓
[Tool Executor] (SAME): list_blobs("TM*") → [TM.json, ...]
  ↓
[State Update] (SAME): TM parsed, state_delta computed
  ↓
[Reward Calculator]: reward = +1.0 (success)
  ↓
[Semantic Tagger (ML)]: category=TM, confidence=0.92, tags=[task, list]
  ↓
[Response Generator (LLM, text only)]:
  - Input: "Tasks: [task1, task2, task3], no errors"
  - Output: "Masz 3 zadania: [wykonane podsumowanie]"
  ↓
[Artifact saved]:
{
  "episode_id": "EP_20260210_161500_abc123",
  "user_id": "default",
  "intent": {"id": "PA-01", "confidence": 0.95},
  "state_before": {...TM, PS, LO, GEN...},
  "action": {"tool": "list_blobs", "args": {...}},
  "reward": 1.0,
  "semantic": {"category": "TM", "confidence": 0.92},
  "response": "Masz 3 zadania...",
  "schema_version": "omniflow.ml_episode.v1"
}
```

**Zmiana**: LLM już nie decyduje o tool selection; ML to robi. LLM piszegenerator tekstu.

---

## 7. Shadow Mode Instrumentation (Backend Integration)

### 7.1 Where to Add (backend/tool_call_handler/__init__.py)

```python
# NEW: import ML policy
ML_SHADOW_MODE_ENABLED = os.environ.get("ML_SHADOW_MODE", "0").lower() in ("1", "true")
ML_POLICY_PERCENTAGE = int(os.environ.get("ML_POLICY_PERCENTAGE", "0") or 0)  # 0-100

# Existing tool selection logic:
if ML_SHADOW_MODE_ENABLED or random.random() * 100 < ML_POLICY_PERCENTAGE:
    # NEW: Call ML policy
    try:
        ml_tool_decision = ml_policy.predict(
            state=encode_state(user_id),
            intent=parsed_intent,
            context=recent_context
        )
        selected_tool = ml_tool_decision["tool_name"]
        ml_confidence = ml_tool_decision["confidence"]
        
        if ML_SHADOW_MODE_ENABLED:
            # Log both for comparison
            llm_tool = get_llm_tool_selection(...)  # existing code
            log_shadow_comparison(
                interaction_id=...,
                llm_tool=llm_tool,
                ml_tool=selected_tool,
                divergence=(llm_tool != selected_tool)
            )
            selected_tool = llm_tool  # Use LLM for real, log ML
        # else: use ML tool if >= threshold
        elif ml_confidence < 0.5:
            selected_tool = get_llm_tool_selection(...)  # fallback
    except Exception as e:
        logger.warning(f"ML policy failed: {e}")
        selected_tool = get_llm_tool_selection(...)  # fallback

# Artifact capture (NEW):
episode_artifact = {
    "episode_id": gen_episode_id(),
    "intent": intent_parsed,
    "state_before": encode_state(user_id),
    "action": {"tool": selected_tool, "args": ...},
    "state_after": updated_state,
    "reward": calculate_reward(result, updated_state),
    "ml_decision": {
        "used_ml": True,
        "policy_name": "imitation_v0",
        "confidence": ml_confidence
    } if ML_SHADOW_MODE_ENABLED or ML_POLICY_PERCENTAGE > 0 else None,
    "schema_version": "omniflow.ml_episode.v1"
}
save_episode_artifact(user_id, episode_artifact)
```

---

## 8. Konkretne Komendy do Uruchomienia (Later)

### 8.1 Policy Evaluation

```bash
cd labs/ml_lab
python 2_policy_eval/eval_baseline.py \
  --snapshot-path "../../tmp/agentdatastorage_users_snapshot_20260210_105740" \
  --user-id "default" \
  --output-dir "./reports"
# Output: policy_eval_baseline.md + metrics.csv
```

### 8.2 Episode Parsing

```bash
python 1_episode_parser/parser.py \
  --input "../../tmp/agentdatastorage_users_snapshot_20260210_105740" \
  --user-id "default" \
  --output "./data/episodes" \
  --format "pickle"
# Output: ~50 Episode objects serialized
```

### 8.3 Imitation Training

```bash
python 3_encoding/state_encoder.py \
  --episodes-path "./data/episodes" \
  --output-encoder "./models/encoder_v0.pkl"

python 4_imitation/trainer.py \
  --episodes-path "./data/episodes" \
  --encoder-path "./models/encoder_v0.pkl" \
  --output-model "./models/policy_imitation_v0.pkl" \
  --test-split 0.2
# Output: policy model + accuracy report
```

### 8.4 Shadow Mode Test (Backend)

```bash
export ML_SHADOW_MODE=1
export OMNIFLOW_DEBUG=1
cd backend
func start

# In another terminal:
curl -X POST http://localhost:7071/api/tool_call_handler \
  -H "Content-Type: application/json" \
  -d '{"message": "sprawdź TM", "user_id": "default"}'
# Check logs: shadow_comparison.log
```

---

## 9. Ryzyko i Mitygacja

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **ML policy diverges from LLM** | High | Medium | Shadow mode (2 weeks comparison) |
| **Reward model poorly shaped** | Medium | High | Start with simple rewards, iterate |
| **State encoder too high-dimensional** | Low | Low | Start with simple hashing, optimize later |
| **Planner finds no valid plans** | Medium | High | Start STRIPS-like (simple), manual rule-based |
| **Production latency spike** | Low | High | Cache model outputs, use fallback timely |
| **Data leakage (user data in ML)** | LOW | CRITICAL | Read-only snapshots, no production writes from lab |

---

## 10. Kolejne Kroki (Immediate)

### 10.1 Gate: Zatwierdź Ten Plan

- [ ] **Zatwierdzić scope**: czy wszystkie 5 faz są OK?
- [ ] **Zatwierdzić timeline**: czy 6 tygodni jest realne?
- [ ] **Zatwierdzić risk profile**: czy shadow mode + canary są wystarczające?

### 10.2 Rozpocząć Fazę 1 (Week 1)

- [ ] Czytać `interaction_logs.json` complete
- [ ] Ręcznie oznaczyć 20 intent labels z `user_message`
- [ ] Obliczyć baseline metrics (success rate, retry rate, timeout %)
- [ ] Wygenerować report `policy_eval_baseline.md`

### 10.3 Inicjalizacja Lab ML

```bash
mkdir -p labs/ml_lab/{1_episode_parser,2_policy_eval,3_encoding,4_imitation,5_offline_rl,6_planning,7_shadow_mode,data,notebooks}
cd labs/ml_lab
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
git add . && git commit -m "Initialize ML Lab skeleton"
```

### 10.4 Artefakty do Zamrożenia

- [ ] `labs/ml_lab/config.yaml` (dataset paths, training params)
- [ ] `episode_schema.json` (Episode contract)
- [ ] `ARCHITECTURE.md` (co ML/RL/Planner robi)
- [ ] Baseline metrics snapshot (do porównania)

---

## 11. FAQ & Clarifications

### Q1: Czy Będziemy Retrainować Live?

**A**: Nie. Cały workflow jest **offline + shadow**, aż do canary rollout.  
Live model jest frozen; retraining odbywa się w lab na snapshots, potem push nowej wersji.

### Q2: Ile Danych Mamy?

**A**: ~50 interactions per user, 3 users with full history.  
To wystarczą na Imitation Learning (v0); Offline RL będzie lepsze z > 500 episodes.

### Q3: Czy LLM Zostaje w Systemie?

**A**: Tak, ale tylko do generowania tekstu odpowiedzi finalne.  
LLM nie decyduje o tool selection, nie routuje context, nie klasyfikuje.

### Q4: Shadow Mode Koszt?

**A**: 2x inference (LLM + ML) + logging; latencja +10-50ms dla json logging.  
W produkcji (non-shadow): sam ML (szybciej niż LLM).

---

## 12. Podsumowanie Artefaktów

| Artefakt | Gdzie | Format | DoD |
|----------|-------|--------|-----|
| Policy Eval Report | `labs/ml_lab/reports/policy_eval_baseline.md` | Markdown | Metrics w tabelach |
| Episode Parser | `labs/ml_lab/1_episode_parser/` | Python module | Unit tests pass |
| State Encoder | `labs/ml_lab/3_encoding/state_encoder.py` | Python module + tests | Deterministic; coverage 95%+ |
| Imitation Model | `labs/ml_lab/4_imitation/models/policy_v0.pkl` | sklearn/pickle | Accuracy ≥ 50% on test set |
| Offline RL Trainer | `labs/ml_lab/5_offline_rl/cql_trainer.py` | Python module + tests | Trainer runs without divergence |
| Planner Engine | `labs/ml_lab/6_planning/planner.py` | Python module + tests | Plans exist for 80%+ episodes |
| Shadow Mode Logs | `logs/shadow_comparison.jsonl` | JSONL (runtime appended) | Divergence metric < 10% |
| ML Architecture Doc | `labs/ml_lab/ARCHITECTURE.md` | Markdown | Described decision flow |

---

## Zatwierdzenie (Sign-Off)

**Plan Status**: ✅ **Ready for Planning Gate Approval**

Wymagane decyzje przed kodowaniem:
1. Czy timeline (6 tygodni) jest OK?
2. Czy risk mitigation (shadow + canary) jest wystarczająca?
3. Czy start z Policy Eval + Imitation jest właściwy?

**Następny krok**: ExecPlan z konkretnym kodem (Faza 1 jest gotowa do pisania).

---

**Dokument**: AI-DECISION-BLUEPRINT.md  
**Wersja**: v1.0  
**Data**: 2026-02-10  
**Autor**: AI Agent (Analysis Phase)  
**Status**: Plan-Gated (no code commits yet)
