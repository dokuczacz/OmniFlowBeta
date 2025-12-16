import os

import requests


def _build_add_new_data_url() -> str:
    base = os.getenv("BACKEND_BASE_URL", "http://localhost:7071").rstrip("/")
    code = os.getenv("FUNCTION_CODE_ADD_NEW_DATA", "").strip()
    url = f"{base}/api/add_new_data"
    if code:
        url = f"{url}?code={code}"
    return url


ADD_NEW_DATA_URL = _build_add_new_data_url()
USER_ID = os.getenv("DEFAULT_USER_ID", "default")

CATEGORIES = [
    "PE",   # Prompt Engineering
    "UI",   # User Interaction
    "ML",   # Memory & Logs
    "LO",   # Life Optimizer
    "PS",   # Planning Strategy
    "TM",   # Task Management
    "SYS",  # System Design
    "GEN",  # General/Unclassified
]


# Category-specific starter data
category_starters = {
    "PE": {
        "prompt": "You are an expert assistant.",
        "tags": ["SYS", "instruction"],
        "created": "2025-12-16T00:00:00Z"
    },
    "UI": {
        "event": "user clicked button",
        "input": "Hello, assistant!",
        "feedback": "positive",
        "timestamp": "2025-12-16T00:00:00Z"
    },
    "ML": {
        "memory_id": 1,
        "event": "session_start",
        "timestamp": "2025-12-16T00:00:00Z",
        "recall_chain": []
    },
    "LO": {
        "plan": "Morning routine",
        "tasks": ["meditate", "exercise", "review goals"],
        "energy": "high",
        "date": "2025-12-16"
    },
    "PS": {
        "objective": "Complete MVP",
        "milestone": "Backend integration",
        "phase": "Sprint 1",
        "okrs": ["Deploy API", "Test user flows"]
    },
    "TM": {
        "tasks": [
            {"id": 1, "title": "Setup project repo", "status": "done"},
            {"id": 2, "title": "Implement API", "status": "in progress"},
            {"id": 3, "title": "Write tests", "status": "todo"}
        ],
        "last_updated": "2025-12-16T00:00:00Z"
    },
    "SYS": {
        "infra": "Azure Functions",
        "status": "deployed",
        "log": "System initialized.",
        "timestamp": "2025-12-16T00:00:00Z"
    },
    "GEN": {
        "note": "Initial general entry.",
        "meta": "setup",
        "timestamp": "2025-12-16T00:00:00Z"
    }
}

for category in CATEGORIES:
    blob_name = f"{category}.json"
    starter = category_starters.get(category, {"init": True})
    payload = {
        "target_blob_name": blob_name,
        "new_entry": starter,
        "user_id": USER_ID
    }
    headers = {"Content-Type": "application/json"}
    response = requests.post(ADD_NEW_DATA_URL, json=payload, headers=headers)
    print(f"Created {blob_name}: {response.status_code} {response.text}")
