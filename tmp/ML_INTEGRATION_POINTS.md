# OmniFlow – ML Integration Points Mapping
## Precise Code Locations & Substitution Points

**Purpose**: Mapa XXX konkretnych miejsc w kodzie gdzie LLM będzie zastępowany ML/RL/Planner.

---

## 1. INTENT RECOGNITION (User Message → Intent Vector)

### 1.1 Current LLM Path
**File**: `backend/tool_call_handler/__init__.py`  
**Lines**: ~200-250 (in `_pa_run_intention_step()`)  

```python
# LLM CALL - Current:
response = openai_client.beta.threads.create_and_run(
    assistant_id=ASSISTANT_ID,
    thread_id=thread_id,
    messages=[{"role": "user", "content": prompt}],
    # ... parsing intent from response text
)
intent_text = response["choices"][0]["message"]["content"]
intent_dict = json.loads(intent_text)  # Intent label from LLM
```

### 1.2 ML Substitution Point
**New Location**: `labs/ml_lab/4_imitation/intent_classifier.py`

```python
class IntentClassifier:
    def __init__(self, model_path: str):
        self.model = joblib.load(model_path)  # sklearn LogisticRegression
        self.encoder = joblib.load(model_path.replace("model", "encoder"))
    
    def predict(self, user_message: str) -> Dict[str, Any]:
        """
        Input: "sprawdź moje zadania"
        Output: {"intent_id": "PA-01", "confidence": 0.95, "label": "task_read"}
        """
        embedding = self.encoder.transform([user_message])
        logits = self.model.predict_proba(embedding)[0]
        intent_id = self.model.classes_[np.argmax(logits)]
        confidence = np.max(logits)
        
        return {
            "intent_id": intent_id,
            "intent_name": INTENT_LABELS[intent_id],
            "confidence": confidence,
            "schema_version": "omniflow.intent.v1"
        }
```

**Integration Point** (3 files to modify):

**File 1**: `backend/tool_call_handler/__init__.py`  
**Function**: `_pa_run_intention_step()` or new `_ml_classify_intent()`

```python
# BEFORE (LLM):
intent_text = openai_client.beta.threads.messages.list(...)["data"][0]["content"][0]["text"]

# AFTER (ML - Flag Gated):
if USE_ML_INTENT_CLASSIFIER and INTENT_CLASSIFIER is not None:
    intent_result = INTENT_CLASSIFIER.predict(user_message)
    intent_dict = intent_result
else:
    # fallback to LLM
    intent_text = ...  # existing code
```

**Environment Variables** (add to `local.settings.json`):
```json
{
  "USE_ML_INTENT_CLASSIFIER": "0",
  "INTENT_CLASSIFIER_MODEL_PATH": "/path/to/labs/ml_lab/models/intent_classifier.pkl"
}
```

---

## 2. CONTEXT ROUTING (FAST vs DEEP Decision)

### 2.1 Current LLM Path
**File**: `backend/tool_call_handler/wp6/deep_context.py`  
**Lines**: ~150-200 (in `decide_routing()` or similar)

```python
# LLM decides:
routing_response = openai_client.chat.completions.create(
    model="gpt-5-mini",
    messages=[{
        "role": "user",
        "content": f"Is deep context needed? {user_message}..."
    }],
    response_format={"type": "json_object"}
)
routing_decision = json.loads(routing_response.choices[0].message.content)
# {"need_deep": true, "why": "..."}
```

### 2.2 ML Substitution Point
**New Location**: `labs/ml_lab/5_offline_rl/context_router.py`

```python
class ContextRouter:
    """Contextual bandit for FAST vs DEEP routing."""
    
    def __init__(self, model_path: str):
        self.qnn = joblib.load(model_path)  # trained Q-network
        self.scaler = joblib.load(model_path.replace("qnn", "scaler"))
    
    def route(self, state: np.ndarray, user_message: str) -> Dict[str, Any]:
        """
        Input: state_vector (from TM+PS+LO), user_message
        Output: {"mode": "FAST" | "DEEP", "confidence": 0.82, "q_value": 0.15}
        """
        x = np.hstack([state, self.encode_message(user_message)])
        x_scaled = self.scaler.transform(x.reshape(1, -1))
        
        q_fast, q_deep = self.qnn.predict(x_scaled)[0]
        mode = "DEEP" if q_deep > q_fast else "FAST"
        confidence = abs(q_deep - q_fast) / (abs(q_fast) + abs(q_deep) + 1e-6)
        
        return {
            "mode": mode,
            "confidence": min(confidence, 1.0),
            "q_fast": float(q_fast),
            "q_deep": float(q_deep),
            "schema_version": "omniflow.routing.v1"
        }
```

**Integration Point**:

**File**: `backend/tool_call_handler/__init__.py`  
**Function**: `_wp6_route_context_mode()` (existing)

```python
# BEFORE (LLM):
mode_initial = "DEEP" if "complex" in user_message else "FAST"

# AFTER (ML):
if USE_ML_CONTEXT_ROUTER and CONTEXT_ROUTER is not None:
    state_vec = encode_state(user_id)  # from TM/PS/LO
    routing = CONTEXT_ROUTER.route(state_vec, user_message)
    mode_initial = routing["mode"]
    wp6_meta["ml_routing"] = routing
else:
    # fallback to heuristic
    mode_initial = "DEEP" if ...
```

**Environment Variables**:
```json
{
  "USE_ML_CONTEXT_ROUTER": "0",
  "CONTEXT_ROUTER_MODEL_PATH": "/path/to/labs/ml_lab/models/router_qnn.pkl"
}
```

---

## 3. STATE ENCODING (Raw Blobs → Feature Vector)

### 3.1 Current Ad-Hoc Approach
**File**: `backend/tool_call_handler/wp6/deep_context.py`  
**Lines**: ~300-400 (in `assemble_comprehensive_context()`)

```python
# Manual aggregation:
context_pack = {
    "tm_count": len(tm_json),
    "ps_count": len(ps_json),
    "recent_interactions": recent_5,
    "last_tool": handles.get("last_tool"),
    # ... ad-hoc aggregations
}
# No principled encoding; passed as JSON to LLM
```

### 3.2 ML Substitution Point
**New Location**: `labs/ml_lab/3_encoding/state_encoder.py`

```python
class StateEncoder:
    """Encodes user state (TM, PS, LO, GEN, SYS, recent context) → fixed vector."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.feature_names = [
            "tm_count", "tm_overdue_pct", "tm_priority_avg",
            "ps_okr_completion", "ps_milestones_active",
            "lo_energy_level", "lo_sleep_hours",
            "gen_entries_count", "gen_recent_topics",
            "sys_error_rate", "sys_timeout_pct",
            "recency_hours",
            "semantic_confidence_avg",
        ]
    
    def encode(self, user_state: Dict[str, Any]) -> np.ndarray:
        """
        Input: {"TM": [...], "PS": {...}, "LO": {...}, ...}
        Output: np.array of shape (13,) or configured dim
        """
        features = [
            len(user_state.get("TM", [])),  # tm_count
            self._calc_overdue_pct(user_state.get("TM", [])),
            self._calc_priority_avg(user_state.get("TM", [])),
            # ... more features
        ]
        return np.array(features, dtype=np.float32)
    
    def decode_features(self) -> List[str]:
        """For interpretability & feature importance."""
        return self.feature_names
```

**Integration Point**:

**File**: `backend/tool_call_handler/__init__.py`  
**New Function**: `_encode_user_state(user_id: str) -> np.ndarray`

```python
def _encode_user_state(user_id: str) -> Optional[np.ndarray]:
    """Cache-friendly state encoding for ML models."""
    if STATE_ENCODER is None:
        return None
    
    tm_json = read_blob_file(user_id, "TM.json")
    ps_json = read_blob_file(user_id, "PS.json")
    lo_json = read_blob_file(user_id, "LO.json")
    gen_json = read_blob_file(user_id, "GEN.json")
    sys_json = read_blob_file(user_id, "SYS.json")
    
    user_state = {
        "TM": tm_json or [],
        "PS": ps_json or {},
        "LO": lo_json or {},
        "GEN": gen_json or [],
        "SYS": sys_json or {}
    }
    
    return STATE_ENCODER.encode(user_state)
```

---

## 4. TOOL SELECTION (LLM Decision → Multi-Armed Bandit)

### 4.1 Current LLM Path
**File**: `backend/tool_call_handler/__init__.py`  
**Lines**: ~1200-1400 (in `main()` function, tool call dispatch)

```python
# LLM picks from allowlist via function_calling:
response = openai_client.beta.threads.create_and_run(
    ...
    tools=[...available tools...],
)
# LLM selects: response.choices[0]["message"]["tool_calls"][0]["function"]["name"]
selected_tool = tool_name  # e.g., "read_blob_file"
```

### 4.2 ML Substitution Point
**New Location**: `labs/ml_lab/4_imitation/tool_selector.py`

```python
class ToolSelector:
    """Multi-armed bandit: state + intent → tool selection."""
    
    def __init__(self, model_path: str):
        self.policy = joblib.load(model_path)  # sklearn Pipeline or custom
        self.tool_id_to_name = {
            0: "list_blobs",
            1: "read_blob_file",
            2: "read_many_blobs",
            3: "get_filtered_data",
            4: "save_interaction",
            # ... etc (14 tools total)
        }
    
    def select(self, state: np.ndarray, intent_id: str) -> Dict[str, Any]:
        """
        Input: state_vector, intent_id (PA-01, PA-02, ...)
        Output: {"tool": "read_blob_file", "confidence": 0.87, "alt_tools": [...]}
        """
        x = np.hstack([
            state,
            self._encode_intent(intent_id)
        ])
        
        logits = self.policy.predict_proba([x])[0]  # [prob_tool0, prob_tool1, ...]
        top_k = np.argsort(logits)[-3:][::-1]  # top 3
        
        selected_idx = top_k[0]
        selected_tool = self.tool_id_to_name[selected_idx]
        confidence = logits[selected_idx]
        
        return {
            "tool": selected_tool,
            "confidence": float(confidence),
            "top_k_tools": [
                (self.tool_id_to_name[i], float(logits[i])) for i in top_k
            ],
            "schema_version": "omniflow.tool_selection.v1"
        }
```

**Integration Point**:

**File**: `backend/tool_call_handler/__init__.py`  
**Function**: `main()` around line 1250

```python
# BEFORE (LLM):
tool_name = response.choices[0]["message"]["tool_calls"][0]["function"]["name"]

# AFTER (ML, flag-gated):
if USE_ML_TOOL_SELECTOR and TOOL_SELECTOR is not None:
    state_vec = _encode_user_state(user_id)
    if state_vec is not None:
        tool_selection = TOOL_SELECTOR.select(state_vec, intent_id)
        selected_tool_name = tool_selection["tool"]
        ml_tool_confidence = tool_selection["confidence"]
        
        if ml_tool_confidence < TOOL_SELECTOR_FALLBACK_THRESHOLD:
            # Use LLM
            selected_tool_name = get_llm_tool_selection(...)
            ml_tool_confidence = -1  # sentinel
        
        # Log for artifact
        artifact_meta["ml_tool_selection"] = tool_selection
    else:
        # Fallback
        selected_tool_name = get_llm_tool_selection(...)
else:
    # Original LLM path
    selected_tool_name = get_llm_tool_selection(...)
```

**Environment Variables**:
```json
{
  "USE_ML_TOOL_SELECTOR": "0",
  "TOOL_SELECTOR_MODEL_PATH": "/path/to/labs/ml_lab/models/tool_selector.pkl",
  "TOOL_SELECTOR_FALLBACK_THRESHOLD": "0.5"
}
```

---

## 5. SEMANTIC TAGGING (WP7 Audit via LLM → ML Classifier)

### 5.1 Current LLM Path
**File**: `backend/tool_call_handler/__init__.py` (WP7 async section)  
**Lines**: ~2800-2900

```python
# LLM classifies interaction:
semantic_response = openai_client.chat.completions.create(
    model="gpt-5-mini",
    messages=[{
        "role": "user",
        "content": f"Classify this interaction: {interaction_json}..."
    }],
    response_format={"type": "json_object"}
)
semantic_result = json.loads(semantic_response.choices[0].message.content)
# {"category": "TM", "confidence": 0.72, "tags": ["task", "read"]}
```

### 5.2 ML Substitution Point
**New Location**: `labs/ml_lab/4_imitation/semantic_classifier.py`

```python
class SemanticClassifier:
    """Classifies interaction → PA category + tags."""
    
    CATEGORIES = ["TM", "PS", "LO", "GEN", "UI", "SYS", "MAIL"]
    
    def __init__(self, model_path: str):
        self.category_clf = joblib.load(model_path)  # classifier for category
        self.tag_clf = joblib.load(model_path.replace("category", "tag"))  # multi-label
        self.encoder = joblib.load(model_path.replace("category", "encoder"))
    
    def classify(self, interaction: Dict[str, Any]) -> Dict[str, Any]:
        """
        Input: {"user_message": "...", "assistant_response": "...", "tool_calls": [...]}
        Output: {"category": "TM", "confidence": 0.78, "tags": ["task", "read", "planning"]}
        """
        text = f"{interaction.get('user_message', '')} {interaction.get('assistant_response', '')}"
        embedding = self.encoder.transform([text])
        
        # Category prediction
        cat_logits = self.category_clf.predict_proba(embedding)[0]
        category_idx = np.argmax(cat_logits)
        category = self.CATEGORIES[category_idx]
        confidence = cat_logits[category_idx]
        
        # Tags multi-label
        tag_logits = self.tag_clf.predict(embedding)[0]  # shape (num_tags,)
        tags = [tag for i, tag in enumerate(ALL_TAGS) if tag_logits[i] > 0.5]
        
        return {
            "category": category,
            "confidence": float(confidence),
            "tags": tags,
            "schema_version": "omniflow.wp7.semantic.v1"
        }
```

**Integration Point**:

**File**: `backend/tool_call_handler/__init__.py`  
**Async Function**: `_emit_semantic_audit()` or similar

```python
# BEFORE (LLM):
semantic_json = await openai_client.chat.completions.create(...)

# AFTER (ML):
if USE_ML_SEMANTIC_CLASSIFIER and SEMANTIC_CLASSIFIER is not None:
    semantic_result = SEMANTIC_CLASSIFIER.classify(interaction_json)
    semantic_audit = semantic_result
else:
    # fallback to LLM
    semantic_json = await openai_client.chat.completions.create(...)
```

---

## 6. RESPONSE GENERATION (Still LLM, But Input is Processed)

### 6.1 Current Path
**File**: `backend/tool_call_handler/__init__.py`  
**Lines**: ~1800-1900

```python
# LLM generates final response:
response = openai_client.chat.completions.create(
    model="gpt-5-mini",
    messages=[
        {"role": "system", "content": PA_SYSTEM_PROMPT},
        {"role": "user", "content": f"Generate response for: {action_result}..."}
    ]
)
response_text = response.choices[0]["message"]["content"]
```

### 6.2 No Substitution (Stays LLM)

**Note**: Response generation stays as LLM (text generation is LLM's strength). However, input to LLM is now **deterministic** (from ML pipeline, not ad-hoc context packing).

**Input Pre-Processing** (NEW):

```python
# Instead of context packing in LLM, format cleanly before passing:
response_input = {
    "action": selected_tool,
    "action_result": tool_result,
    "state_delta": state_update,
    "error": error_if_any,
    "semantic_tags": semantic_tags_from_ml
}

# LLM only has job: generate Polish text summary
response_prompt = f"""
Streszcz wynik akcji:
- Akcja: {response_input['action']}
- Wynik: {response_input['action_result']}
- Kategoria (z AI): {response_input['semantic_tags']['category']}

Wygeneruj krótka, naturalną odpowiedź po polsku:
"""

response_text = openai_client.chat.completions.create(
    model="gpt-5-mini",
    messages=[{"role": "user", "content": response_prompt}],
    max_tokens=200
).choices[0]["message"]["content"]
```

---

## 7. REWARD CALCULATION (NEW – for Offline RL Training)

### 7.1 New Location
**File**: `labs/ml_lab/5_offline_rl/reward_model.py`

```python
class RewardModel:
    """Compute reward for state → action → state' transition."""
    
    @staticmethod
    def compute(
        action: str,
        result_status: str,  # success, timeout, error
        semantic_confidence: float,
        state_delta_size: int
    ) -> float:
        """
        Reward factors:
        - Success: +1.0
        - Timeout/Retry: -0.5
        - Error: -1.0
        - Bonus for high semantic confidence: +0.1 * confidence
        """
        base_reward = {
            "success": 1.0,
            "retry": -0.5,
            "timeout": -0.5,
            "error": -1.0
        }.get(result_status, 0.0)
        
        confidence_bonus = 0.1 * semantic_confidence
        
        return base_reward + confidence_bonus
```

**Integration Point**:

**File**: `backend/tool_call_handler/__init__.py`  
**New Function**: `_calculate_episode_reward()`

```python
def _calculate_episode_reward(
    tool_name: str,
    tool_result: Dict[str, Any],
    semantic_result: Dict[str, Any]
) -> float:
    """Calculate reward for ML episode artifact."""
    
    status_map = {
        "success": "success",
        "timeout": "timeout",
        "error": "error",
        "incomplete": "retry"
    }
    
    result_status = status_map.get(tool_result.get("status"), "error")
    semantic_conf = semantic_result.get("confidence", 0.5)
    
    reward = REWARD_MODEL.compute(
        action=tool_name,
        result_status=result_status,
        semantic_confidence=semantic_conf,
        state_delta_size=len(str(tool_result))
    )
    
    return reward
```

---

## 8. ARTIFACT CAPTURE (ML Episode Recording)

### 8.1 New Structure
**File**: `backend/tool_call_handler/__init__.py`  
**New Function**: `_save_ml_episode()`

```python
def _save_ml_episode(
    user_id: str,
    interaction_id: str,
    episode_data: Dict[str, Any]
) -> str:
    """
    Save episode for offline ML analysis.
    
    Schema:
    {
        "episode_id": "EP_...",
        "timestamp": "2026-02-10T...",
        "user_id": "...",
        "interaction_id": "...",
        "intent": {...},
        "state_before": {...},
        "action": {...},
        "state_after": {...},
        "reward": 0.8,
        "semantic": {...},
        "ml_decision": {...},  # if ML used
        "schema_version": "omniflow.ml_episode.v1"
    }
    """
    episode_artifact = {
        "episode_id": f"EP_{datetime.utcnow().isoformat()}_{uuid.uuid4().hex[:8]}",
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "interaction_id": interaction_id,
        "intent": episode_data.get("intent", {}),
        "state_before": episode_data.get("state_before", {}),
        "action": episode_data.get("action", {}),
        "state_after": episode_data.get("state_after", {}),
        "reward": episode_data.get("reward", 0.0),
        "semantic": episode_data.get("semantic", {}),
        "ml_decision": episode_data.get("ml_decision"),
        "response": episode_data.get("response", ""),
        "schema_version": "omniflow.ml_episode.v1"
    }
    
    # Save to: users/{user_id}/episodes/EP_*.json
    blob_path = f"users/{user_id}/episodes/{episode_artifact['episode_id']}.json"
    blob_client.upload_blob(
        blob_path,
        json.dumps(episode_artifact, indent=2),
        overwrite=True
    )
    
    return blob_path
```

---

## 9. PLANNER ROUTING (PA Multiple Steps)

### 9.1 Multi-Step Decision (NEW – Faza 4)
**File**: `labs/ml_lab/6_planning/planner.py`

```python
class SimpleStripsPlanner:
    """Basic planner: goal → action sequence."""
    
    def __init__(self, state_graph: Dict[str, Any]):
        self.state_graph = state_graph
        self.action_preconditions = self._build_preconditions()
    
    def plan(self, goal: str, current_state: np.ndarray) -> List[str]:
        """
        Input: goal (e.g., "update_task_2_and_send_mail")
        Output: ["read_blob_file(TM)", "update_data_entry(TM)", "save_interaction()"]
        """
        # Decompose goal
        subgoals = self._decompose_goal(goal)  # [task_update, mail_send]
        
        # Find action sequence
        plan = []
        current = current_state
        for subgoal in subgoals:
            actions = self._find_actions_for_goal(subgoal, current)
            if not actions:
                return []  # No plan found
            plan.extend(actions)
            # Update state (mock)
            current = self._simulate_state_transition(current, actions[-1])
        
        return plan
```

**Integration Point** (Future, Faza 4):

When multi-step goals detected, call planner instead of looping LLM:

```python
if USE_ML_PLANNER and PLANNER is not None:
    goal = detect_multi_step_goal(user_message)  # heuristic
    if goal:
        action_plan = PLANNER.plan(goal, state_vector)
        # Execute plan sequentially instead of tool-loop
        for action in action_plan:
            execute_action(action)
    else:
        # Single-step: use existing tool selector
        ...
```

---

## 10. SUMMARY TABLE: File Locations & Changes

| Component | File | Function | Change Type | Priority |
|-----------|------|----------|-------------|----------|
| **Intent Classifier** | `tool_call_handler/__init__.py` | `_pa_run_intention_step()` | Wrap with ML call | P1 |
| **State Encoder** | `tool_call_handler/__init__.py` | `_encode_user_state()` (NEW) | New function | P1 |
| **Tool Selector** | `tool_call_handler/__init__.py` | `main()` @ 1250 | Branching logic | P1 |
| **Context Router** | `tool_call_handler/wp6/` | `decide_routing()` | Branching logic | P2 |
| **Semantic Classifier** | `tool_call_handler/__init__.py` | `_emit_semantic_audit()` | Branching logic | P2 |
| **Response Generator** | `tool_call_handler/__init__.py` | main() @ 1800 | Input pre-processing only | P3 |
| **Reward Calculator** | `tool_call_handler/__init__.py` | `main()` | New artifact field | P2 |
| **Episode Recorder** | `tool_call_handler/__init__.py` | `main()` (end of request) | New artifact save | P2 |
| **Planner** | N/A (future) | N/A | Not yet integrated | P4 |

---

## 11. Environment Variables (New)

Add to `backend/local.settings.json`:

```json
{
  "USE_ML_INTENT_CLASSIFIER": "0",
  "USE_ML_TOOL_SELECTOR": "0",
  "USE_ML_CONTEXT_ROUTER": "0",
  "USE_ML_SEMANTIC_CLASSIFIER": "0",
  "ML_SHADOW_MODE": "0",
  "ML_POLICY_PERCENTAGE": "0",
  
  "INTENT_CLASSIFIER_MODEL_PATH": "/labs/ml_lab/models/intent_classifier.pkl",
  "TOOL_SELECTOR_MODEL_PATH": "/labs/ml_lab/models/tool_selector.pkl",
  "CONTEXT_ROUTER_MODEL_PATH": "/labs/ml_lab/models/router.pkl",
  "SEMANTIC_CLASSIFIER_MODEL_PATH": "/labs/ml_lab/models/semantic_classifier.pkl",
  "STATE_ENCODER_CONFIG_PATH": "/labs/ml_lab/models/state_encoder_config.json",
  
  "TOOL_SELECTOR_FALLBACK_THRESHOLD": "0.5",
  "INTENT_CLASSIFIER_FALLBACK_THRESHOLD": "0.4",
  "ML_LOG_DECISIONS": "1",
  "ML_ARTIFACTS_PATH": "users/{user_id}/episodes"
}
```

---

## 12. Module Import Points (New)

**File**: `backend/tool_call_handler/__init__.py` (top)

```python
# ML imports (lazy-loaded, with fallback)
try:
    from labs.ml_lab.models import load_intent_classifier, load_tool_selector, load_state_encoder
    ML_MODELS_AVAILABLE = True
except ImportError:
    ML_MODELS_AVAILABLE = False

# Global singletons (loaded on startup)
INTENT_CLASSIFIER = None
TOOL_SELECTOR = None
STATE_ENCODER = None
CONTEXT_ROUTER = None
SEMANTIC_CLASSIFIER = None

def initialize_ml_models():
    global INTENT_CLASSIFIER, TOOL_SELECTOR, STATE_ENCODER
    
    try:
        INTENT_CLASSIFIER = load_intent_classifier(
            os.environ.get("INTENT_CLASSIFIER_MODEL_PATH", "")
        ) if USE_ML_INTENT_CLASSIFIER else None
        
        # ... repeat for other models
        
        logger.info("ML models loaded successfully")
    except Exception as e:
        logger.warning(f"Failed to load ML models: {e}")
        # Continue with LLM-only mode
```

---

## 13. Testing & Validation Points

**Contract Tests** (must pass):

```python
# labs/ml_lab/tests/test_ml_contracts.py

def test_intent_classifier_output_schema():
    classifier = load_intent_classifier("models/intent_classifier.pkl")
    result = classifier.predict("sprawdź moje zadania")
    assert "intent_id" in result
    assert "confidence" in result
    assert 0 <= result["confidence"] <= 1
    assert result.get("schema_version") == "omniflow.intent.v1"

def test_tool_selector_determinism():
    selector = load_tool_selector("models/tool_selector.pkl")
    state = np.random.randn(13)  # fixed state
    result1 = selector.select(state, "PA-01")
    result2 = selector.select(state, "PA-01")
    assert result1["tool"] == result2["tool"]  # Same result for same input
```

---

## 14. Rollout Strategy

**Phase 1**: Deploy with all flags = 0  
- ML models loaded & cached, but not used
- Benchmarks: latency, error logs

**Phase 2**: Shadow Mode (ML_SHADOW_MODE=1)  
- Both LLM + ML run, log divergence
- Gate: divergence < 10%

**Phase 3**: Canary (ML_POLICY_PERCENTAGE=10)  
- 10% of requests use ML, 90% use LLM
- Gate: success_rate_ml ≥ success_rate_llm

**Phase 4**: Full Rollout  
- ML_POLICY_PERCENTAGE=100
- LLM fallback only for low-confidence decisions

---

**Document**: ML-INTEGRATION-POINTS.md  
**Version**: v1.0  
**Status**: Planning Phase (ready for implementation)
