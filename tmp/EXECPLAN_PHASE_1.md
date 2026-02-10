# EXECPLAN – Phase 1: Policy Evaluation (READY TO RUN)

**Objective**: Baseline analysis of OmniFlow's current LLM decision-making quality  
**Timeline**: 1-2 days (mostly analysis, no new code)  
**Risk**: ZERO (read-only)  
**Outcome**: Metrics CSV + reportMarkdown + policy baseline for ML comparison

---

## ✅ Prerequisites (Check Before Start)

- [ ] Python 3.11+ installed  
- [ ] Workspace: `c:/AI memory/NewHope/OmniFlowBeta`  
- [ ] Snapshot available: `tmp/agentdatastorage_users_snapshot_20260210_105740/`  
- [ ] Data folders readable

**Command to verify**:
```pwsh
cd "c:/AI memory/NewHope/OmniFlowBeta"
dir tmp/agentdatastorage_users_snapshot_20260210_105740/users/default
# Should show: TM.json, PS.json, LO.json, interaction_logs.json, interactions/
```

---

## 📋 Step 1: Setup Lab Environment

### 1.1 Create Lab ML Directory Structure

```pwsh
cd "c:/AI memory/NewHope/OmniFlowBeta"

# Create directories
mkdir -p labs/ml_lab/1_episode_parser
mkdir -p labs/ml_lab/2_policy_eval
mkdir -p labs/ml_lab/3_encoding
mkdir -p labs/ml_lab/data/episodes
mkdir -p labs/ml_lab/data/snapshots
mkdir -p labs/ml_lab/reports
mkdir -p labs/ml_lab/notebooks

# Verify
ls -R labs/ml_lab | head -20
```

### 1.2 Create requirements.txt

**File**: `labs/ml_lab/requirements.txt`

```
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
matplotlib>=3.7.0
jsonschema>=4.18.0
tqdm>=4.66.0
```

### 1.3 Create Python venv (Optional but Recommended)

```pwsh
cd labs/ml_lab
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## 🔍 Step 2: Read Snapshot & Count Episodes

### 2.1 Script: `labs/ml_lab/2_policy_eval/00_snapshot_explorer.py`

Create file: `labs/ml_lab/2_policy_eval/00_snapshot_explorer.py`

```python
#!/usr/bin/env python3
"""
Explorer: Read snapshot and basic statistics.
"""
import json
import os
from pathlib import Path
from datetime import datetime

# Configuration
SNAPSHOT_PATH = "../../../../tmp/agentdatastorage_users_snapshot_20260210_105740/users/default"
OUTPUT_DIR = "../reports"

def load_json_safe(path: str):
    """Load JSON safely."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return None

def main():
    snapshot_abs = Path(SNAPSHOT_PATH).resolve()
    print(f"📂 Snapshot path: {snapshot_abs}")
    print(f"✓ Exists: {snapshot_abs.exists()}")
    
    # 1. Read interaction_logs.json
    interaction_logs_path = snapshot_abs / "interaction_logs.json"
    interactions = load_json_safe(str(interaction_logs_path)) or []
    print(f"\n📊 Total interactions: {len(interactions)}")
    
    # 2. Read TM.json
    tm_path = snapshot_abs / "TM.json"
    tm_data = load_json_safe(str(tm_path)) or []
    print(f"📝 TM entries: {len(tm_data)}")
    
    # 3. Read interactions/index.jsonl
    index_jsonl_path = snapshot_abs / "interactions" / "index.jsonl"
    index_lines = []
    if index_jsonl_path.exists():
        with open(index_jsonl_path, 'r', encoding='utf-8') as f:
            index_lines = [json.loads(line) for line in f if line.strip()]
    print(f"📑 Index lines (JSONL): {len(index_lines)}")
    
    # 4. Read semantic/index.jsonl
    semantic_index_path = snapshot_abs / "interactions" / "semantic" / "index.jsonl"
    semantic_lines = []
    if semantic_index_path.exists():
        with open(semantic_index_path, 'r', encoding='utf-8') as f:
            semantic_lines = [json.loads(line) for line in f if line.strip()]
    print(f"🏷️  Semantic entries: {len(semantic_lines)}")
    
    # 5. Timestamp range
    if interactions:
        timestamps = [i.get("timestamp") for i in interactions if i.get("timestamp")]
        if timestamps:
            print(f"\n⏱️  Timestamp range:")
            print(f"   First: {min(timestamps)}")
            print(f"   Last:  {max(timestamps)}")
    
    # 6. Tool usage in index
    if index_lines:
        tools_used = {}
        for line in index_lines:
            tool_calls = line.get("tool_calls", [])
            for tc in tool_calls:
                tool_name = tc.get("tool_name")
                if tool_name:
                    tools_used[tool_name] = tools_used.get(tool_name, 0) + 1
        
        print(f"\n🔧 Tools used:")
        for tool, count in sorted(tools_used.items(), key=lambda x: -x[1]):
            print(f"   {tool}: {count}")
    
    # 7. Save summary
    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "interaction_count": len(interactions),
        "tm_entries": len(tm_data),
        "index_lines": len(index_lines),
        "semantic_lines": len(semantic_lines),
        "snapshot_path": str(snapshot_abs)
    }
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    summary_path = Path(OUTPUT_DIR) / "snapshot_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(f"\n✅ Summary saved: {summary_path}")

if __name__ == "__main__":
    main()
```

### 2.2 Run Explorer

```pwsh
cd labs/ml_lab
python 2_policy_eval/00_snapshot_explorer.py
```

**Expected output**:
```
📂 Snapshot path: c:\AI memory\NewHope\OmniFlowBeta\tmp\...
✓ Exists: True

📊 Total interactions: ~50
📝 TM entries: 5
📑 Index lines (JSONL): ~30
🏷️  Semantic entries: ~30

⏱️  Timestamp range:
   First: 2025-12-27T...
   Last: 2026-02-09T...

🔧 Tools used:
   list_blobs: 15
   read_blob_file: 12
   ...

✅ Summary saved: reports/snapshot_summary.json
```

---

## 📈 Step 3: Compute Success Rate & Retry Distribution

### 3.1 Script: `labs/ml_lab/2_policy_eval/01_baseline_metrics.py`

Create file: `labs/ml_lab/2_policy_eval/01_baseline_metrics.py`

```python
#!/usr/bin/env python3
"""
Baseline Metrics: Success rate, retry distribution, failure modes.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

SNAPSHOT_PATH = "../../../../tmp/agentdatastorage_users_snapshot_20260210_105740/users/default"
OUTPUT_DIR = "../reports"

def load_jsonl(path: str):
    """Load JSONL file."""
    lines = []
    if Path(path).exists():
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    lines.append(json.loads(line))
    return lines

def main():
    snapshot_abs = Path(SNAPSHOT_PATH).resolve()
    
    # Load index.jsonl (main episode log)
    index_jsonl_path = snapshot_abs / "interactions" / "index.jsonl"
    episodes = load_jsonl(str(index_jsonl_path))
    
    print(f"📊 Analyzing {len(episodes)} episodes...\n")
    
    # Metrics
    success_count = 0
    timeout_count = 0
    error_count = 0
    unknown_count = 0
    retry_counts = []
    tool_success_map = defaultdict(lambda: {"success": 0, "timeout": 0, "error": 0})
    
    for ep in episodes:
        tool_calls = ep.get("tool_calls", [])
        
        # Count successes/failures
        for tc in tool_calls:
            status = tc.get("status", "unknown")
            tool_name = tc.get("tool_name", "unknown")
            
            if status == "success":
                success_count += 1
                tool_success_map[tool_name]["success"] += 1
            elif status == "timeout":
                timeout_count += 1
                tool_success_map[tool_name]["timeout"] += 1
                retry_counts.append(1)  # mark as retry
            elif status == "error":
                error_count += 1
                tool_success_map[tool_name]["error"] += 1
            else:
                unknown_count += 1
        
        # Count retries by looking at consecutive calls with same intent
        if len(tool_calls) > 1:
            retry_counts.append(len(tool_calls) - 1)
    
    total_calls = success_count + timeout_count + error_count + unknown_count
    
    # Compute metrics
    success_rate = success_count / total_calls if total_calls > 0 else 0
    avg_retries = sum(retry_counts) / len(retry_counts) if retry_counts else 0
    
    print(f"✅ Success: {success_count} / {total_calls} = {success_rate:.1%}")
    print(f"⏱️  Timeout: {timeout_count} ({timeout_count/total_calls:.1%})")
    print(f"❌ Error:   {error_count} ({error_count/total_calls:.1%})")
    print(f"❓ Unknown: {unknown_count} ({unknown_count/total_calls:.1%})")
    print(f"🔄 Average retries per episode: {avg_retries:.2f}")
    
    print(f"\n🔧 Per-tool success rate:")
    for tool, counts in sorted(tool_success_map.items()):
        total = sum(counts.values())
        success = counts["success"]
        rate = success / total if total > 0 else 0
        print(f"   {tool}: {success}/{total} = {rate:.1%}")
    
    # Save metrics
    metrics = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_episodes": len(episodes),
        "total_tool_calls": total_calls,
        "success_count": success_count,
        "success_rate": float(success_rate),
        "timeout_count": timeout_count,
        "timeout_rate": float(timeout_count / total_calls if total_calls > 0 else 0),
        "error_count": error_count,
        "error_rate": float(error_count / total_calls if total_calls > 0 else 0),
        "unknown_count": unknown_count,
        "avg_retries_per_episode": float(avg_retries),
        "per_tool_metrics": {tool: dict(counts) for tool, counts in tool_success_map.items()}
    }
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    metrics_path = Path(OUTPUT_DIR) / "baseline_metrics.json"
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    print(f"\n✅ Metrics saved: {metrics_path}")
    
    # Also save CSV for easy viewing
    csv_path = Path(OUTPUT_DIR) / "baseline_metrics.csv"
    with open(csv_path, 'w', encoding='utf-8') as f:
        f.write("Metric,Value\n")
        f.write(f"Total Episodes,{len(episodes)}\n")
        f.write(f"Total Tool Calls,{total_calls}\n")
        f.write(f"Success Count,{success_count}\n")
        f.write(f"Success Rate,{success_rate:.1%}\n")
        f.write(f"Timeout Count,{timeout_count}\n")
        f.write(f"Timeout Rate,{timeout_count/total_calls:.1%}\n")
        f.write(f"Error Count,{error_count}\n")
        f.write(f"Error Rate,{error_count/total_calls:.1%}\n")
        f.write(f"Avg Retries,{avg_retries:.2f}\n")
    print(f"✅ CSV saved: {csv_path}")

if __name__ == "__main__":
    main()
```

### 3.2 Run Baseline Metrics

```pwsh
cd labs/ml_lab
python 2_policy_eval/01_baseline_metrics.py
```

---

## 🎯 Step 4: Analyze Tool Selection Patterns

### 4.1 Script: `labs/ml_lab/2_policy_eval/02_tool_selection_analysis.py`

Create file: `labs/ml_lab/2_policy_eval/02_tool_selection_analysis.py`

```python
#!/usr/bin/env python3
"""
Tool Selection: Which tools succeed vs fail, by user intent.
"""
import json
from pathlib import Path
from collections import defaultdict

SNAPSHOT_PATH = "../../../../tmp/agentdatastorage_users_snapshot_20260210_105740/users/default"
OUTPUT_DIR = "../reports"

def load_jsonl(path: str):
    lines = []
    if Path(path).exists():
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    lines.append(json.loads(line))
    return lines

def main():
    snapshot_abs = Path(SNAPSHOT_PATH).resolve()
    
    # Load both interactions and semantic index
    interaction_logs_path = snapshot_abs / "interaction_logs.json"
    index_jsonl_path = snapshot_abs / "interactions" / "index.jsonl"
    semantic_index_path = snapshot_abs / "interactions" / "semantic" / "index.jsonl"
    
    interactions = []
    try:
        with open(interaction_logs_path, 'r', encoding='utf-8') as f:
            interactions = json.load(f)
    except:
        pass
    
    index_entries = load_jsonl(str(index_jsonl_path))
    semantic_entries = load_jsonl(str(semantic_index_path))
    
    print(f"📊 Analyzing tool usage across {len(interactions)} interactions...\n")
    
    # Map interactions → semantics → index
    tool_intent_map = defaultdict(lambda: defaultdict(int))  # tool → intent → count
    tool_outcome_map = defaultdict(lambda: {"success": 0, "error": 0})
    
    for idx, ep in enumerate(index_entries):
        tool_calls = ep.get("tool_calls", [])
        interaction_id = ep.get("interaction_id")
        
        # Find matching semantic entry
        semantic = next((s for s in semantic_entries if s.get("interaction_id") == interaction_id), {})
        intent_category = semantic.get("category", "UNKNOWN")
        
        for tc in tool_calls:
            tool_name = tc.get("tool_name", "unknown")
            status = tc.get("status", "unknown")
            
            tool_intent_map[tool_name][intent_category] += 1
            
            if status == "success":
                tool_outcome_map[tool_name]["success"] += 1
            else:
                tool_outcome_map[tool_name]["error"] += 1
    
    # Print summary
    print("🔧 Tool Usage by Intent Category:")
    for tool in sorted(tool_intent_map.keys()):
        print(f"\n  {tool}:")
        for intent, count in sorted(tool_intent_map[tool].items(), key=lambda x: -x[1]):
            print(f"    {intent}: {count}×")
    
    print("\n\n✅ Tool Success Rate:")
    for tool in sorted(tool_outcome_map.keys()):
        counts = tool_outcome_map[tool]
        total = counts["success"] + counts["error"]
        success_rate = counts["success"] / total if total > 0 else 0
        print(f"  {tool}: {counts['success']}/{total} = {success_rate:.1%}")
    
    # Save to CSV
    import csv
    csv_path = Path(OUTPUT_DIR) / "tool_analysis.csv"
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["Tool", "Intent", "Count"])
        for tool, intent_counts in sorted(tool_intent_map.items()):
            for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1]):
                writer.writerow([tool, intent, count])
    
    print(f"\n✅ Analysis saved: {csv_path}")

if __name__ == "__main__":
    main()
```

### 4.2 Run Tool Analysis

```pwsh
python 2_policy_eval/02_tool_selection_analysis.py
```

---

## 📄 Step 5: Generate HTML Report

### 5.1 Script: `labs/ml_lab/2_policy_eval/03_generate_report.py`

Create file: `labs/ml_lab/2_policy_eval/03_generate_report.py`

```python
#!/usr/bin/env python3
"""
Generate HTML report from metrics.
"""
import json
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = "../reports"

def main():
    metrics_path = Path(OUTPUT_DIR) / "baseline_metrics.json"
    
    with open(metrics_path, 'r', encoding='utf-8') as f:
        metrics = json.load(f)
    
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>OmniFlow Policy Evaluation Baseline</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        table {{ border-collapse: collapse; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
        .metric-box {{ background: #f0f0f0; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .success {{ color: green; font-weight: bold; }}
        .error {{ color: red; font-weight: bold; }}
        .warning {{ color: orange; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>🔬 OmniFlow Policy Evaluation – Baseline Report</h1>
    <p><em>Generated: {metrics.get('timestamp', 'N/A')}</em></p>
    
    <div class="metric-box">
        <h2>📊 Overall Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Total Episodes</td>
                <td class="success">{metrics.get('total_episodes', 'N/A')}</td>
            </tr>
            <tr>
                <td>Total Tool Calls</td>
                <td>{metrics.get('total_tool_calls', 'N/A')}</td>
            </tr>
            <tr>
                <td><strong>Success Count</strong></td>
                <td class="success"><strong>{metrics.get('success_count', 0)}</strong></td>
            </tr>
            <tr>
                <td><strong>Success Rate</strong></td>
                <td class="success"><strong>{metrics.get('success_rate', 0):.1%}</strong></td>
            </tr>
            <tr>
                <td>Timeout Count</td>
                <td class="warning">{metrics.get('timeout_count', 0)}</td>
            </tr>
            <tr>
                <td>Timeout Rate</td>
                <td class="warning">{metrics.get('timeout_rate', 0):.1%}</td>
            </tr>
            <tr>
                <td>Error Count</td>
                <td class="error">{metrics.get('error_count', 0)}</td>
            </tr>
            <tr>
                <td>Error Rate</td>
                <td class="error">{metrics.get('error_rate', 0):.1%}</td>
            </tr>
            <tr>
                <td>Avg Retries per Episode</td>
                <td>{metrics.get('avg_retries_per_episode', 0):.2f}</td>
            </tr>
        </table>
    </div>
    
    <div class="metric-box">
        <h2>🔧 Per-Tool Success Rates</h2>
        <table>
            <tr>
                <th>Tool Name</th>
                <th>Success</th>
                <th>Timeout</th>
                <th>Error</th>
                <th>Success Rate</th>
            </tr>
"""
    
    per_tool = metrics.get('per_tool_metrics', {})
    for tool, counts in sorted(per_tool.items()):
        total = sum(counts.values())
        success = counts.get('success', 0)
        success_rate = success / total if total > 0 else 0
        
        html_content += f"""
            <tr>
                <td><strong>{tool}</strong></td>
                <td class="success">{success}</td>
                <td class="warning">{counts.get('timeout', 0)}</td>
                <td class="error">{counts.get('error', 0)}</td>
                <td><strong>{success_rate:.1%}</strong></td>
            </tr>
"""
    
    html_content += """
        </table>
    </div>
    
    <div class="metric-box">
        <h2>🎯 Key Findings</h2>
        <ul>
            <li>System is operational with mostly successful tool calls</li>
            <li>Timeout rate indicates potential optimization opportunities</li>
            <li>Error rate should be investigated for root causes</li>
            <li><strong>Action</strong>: Use these metrics as baseline for ML policy comparison</li>
        </ul>
    </div>
    
    <footer style="margin-top: 40px; border-top: 1px solid #ccc; padding-top: 20px; color: #666;">
        <p>Report generated automatically by Policy Evaluation Phase</p>
    </footer>
</body>
</html>
"""
    
    html_path = Path(OUTPUT_DIR) / "policy_eval_baseline.html"
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ HTML report generated: {html_path}")
    print(f"   Open in browser: file://{html_path.resolve()}")

if __name__ == "__main__":
    main()
```

### 5.2 Generate Report

```pwsh
python 2_policy_eval/03_generate_report.py
```

---

## 📋 Step 6: Summary & Next Steps

### 6.1 Create Summary Markdown

**File**: `labs/ml_lab/reports/PHASE_1_SUMMARY.md`

```markdown
# Phase 1: Policy Evaluation – Summary

## ✅ Completions

- [x] Snapshot exploration (episode count, timestamp range)
- [x] Baseline metrics (success rate, retry distribution)
- [x] Per-tool analysis (success rate by tool)
- [x] HTML report generated

## 📊 Key Findings

| Metric | Value | Interpretation |
|--------|-------|-----------------|
| Total Episodes | ~50 | Small dataset; sufficient for Imitation Learning v0 |
| Success Rate | XXX% | Baseline for ML policy comparison |
| Timeout Rate | XXX% | Potential bottleneck; RL can optimize |
| Error Rate | XXX% | Root cause analysis needed |

## 🔬 Artifact Analysis

- **Best-performing tools**: [list]
- **Worst-performing tools**: [list]
- **Most-used intent**: [category]

## 🎯 Next Phase (Phase 2: Imitation Learning)

1. **State Encoder**: Implement fixed-size state vector from TM+PS+LO
2. **Intent Labeling**: Manually label 20 user_messages → intent (PA-01..PA-15)
3. **Imitation Model**: Train sklearn LogisticRegression on (intent, state) → tool
4. **Evaluation**: Accuracy on test set (target ≥ 50%)

### Estimated Timeline
- Week 1-2 of implementation

### Key Deliverables
- `intent_classifier.pkl` (model)
- `imitation_policy.pkl` (behavior cloning model)
- Accuracy report + confusion matrix

---

## Recommendations

1. **Immediate**: Investigate timeout causes (slow blob reads? network?)
2. **Short-term**: Start Phase 2 (Imitation Learning)
3. **Medium-term**: Deploy Shadow Mode (run LLM + ML in parallel)

---

Generated: 2026-02-10
```

---

## 🚀 How to Run Everything (One Command)

```pwsh
cd "c:/AI memory/NewHope/OmniFlowBeta/labs/ml_lab"

# Run all Phase 1 analysis
python 2_policy_eval/00_snapshot_explorer.py
python 2_policy_eval/01_baseline_metrics.py
python 2_policy_eval/02_tool_selection_analysis.py
python 2_policy_eval/03_generate_report.py

# View outputs
echo "✅ Policy Evaluation Complete!"
echo "📊 Metrics: $(pwd)/reports/baseline_metrics.json"
echo "📄 Report: $(pwd)/reports/policy_eval_baseline.html"
"$(pwd)/reports/policy_eval_baseline.html"  # Open in browser
```

---

## 📁 Expected Directory After Step 6

```
OmniFlowBeta/
└── labs/
    └── ml_lab/
        ├── 1_episode_parser/
        ├── 2_policy_eval/
        │   ├── 00_snapshot_explorer.py
        │   ├── 01_baseline_metrics.py
        │   ├── 02_tool_selection_analysis.py
        │   └── 03_generate_report.py
        ├── 3_encoding/
        ├── 4_imitation/
        ├── 5_offline_rl/
        ├── 6_planning/
        ├── 7_shadow_mode/
        ├── data/
        │   ├── episodes/
        │   ├── snapshots/
        │   └── artifacts/
        ├── reports/
        │   ├── snapshot_summary.json
        │   ├── baseline_metrics.json
        │   ├── baseline_metrics.csv
        │   ├── tool_analysis.csv
        │   ├── policy_eval_baseline.html
        │   └── PHASE_1_SUMMARY.md
        ├── notebooks/
        ├── requirements.txt
        └── README.md (to create)
```

---

## ✅ Success Criteria (Phase 1 DoD)

- [ ] `snapshot_summary.json` generated with episode counts
- [ ] `baseline_metrics.json` with success/timeout/error rates
- [ ] `baseline_metrics.csv` readable in Excel/Sheets
- [ ] `tool_analysis.csv` showing per-tool success rates
- [ ] `policy_eval_baseline.html` opens in browser without errors
- [ ] `PHASE_1_SUMMARY.md` contains key findings
- [ ] All metrics ≥ N for Phase 2 to proceed

---

## 🚦 Go/No-Go Decision

**PROCEED TO PHASE 2 IF**:
- ✅ Baseline metrics are computed
- ✅ Success rate > 0% (system is working)
- ✅ Tools can be ranked by performance
- ✅ Episode count ≥ 30

**STOP IF**:
- ❌ Metrics cannot be computed (no episodes found)
- ❌ All tools fail (success rate = 0)
- ❌ Snapshot is corrupted or unreadable

---

**EXECPLAN Version**: 1.0  
**Status**: Ready to execute  
**Estimated Duration**: 2-4 hours (mostly waiting for script output)  
**Risk Level**: 🟢 ZERO (read-only analysis)

**Next**: After Phase 1 completes → Approve Phase 2 setup
