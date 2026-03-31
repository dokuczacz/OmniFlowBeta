"""
Golden tests for Custom GPT Task Management capability.

Validates: task.create→task.list→task.update→task.complete→task.delete flow
with task_index reliability and response contract.
"""
import pytest
import requests
import json
from datetime import datetime, timedelta

# Config - substitute with actual endpoint and function key
BASE_URL = "http://localhost:7071"
FUNCTION_KEY = "dev-key-custom-gpt"
USER_ID = "test_golden_tasks"


@pytest.fixture(scope="module")
def api_headers():
    return {
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def function_params():
    return {"code": FUNCTION_KEY}


class TestTaskCreateReturnsTaskIndex:
    """Verify task.create response includes task_index (FIX #1)."""
    
    def test_task_create_returns_task_index(self, api_headers, function_params):
        """task.create should return created entry + task_index (1-based)."""
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.create",
                "confirm": False,
                "arguments": {
                    "title": "Golden Test Task 1",
                    "priority": "high",
                    "due_date": (datetime.now() + timedelta(days=1)).date().isoformat(),
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        
        # Validate response contract
        assert data["status"] == "success"
        assert data["action"] == "capability_exec"
        assert data["capability"] == "task.create"
        
        # FIX #1 validation
        result = data["result"]
        assert "created" in result, "Response must contain 'created' entry"
        assert "task_index" in result, "Response must contain 'task_index' (FIX #1)"
        assert isinstance(result["task_index"], int)
        assert result["task_index"] >= 1, "task_index must be 1-based"
        
        # Store for subsequent tests
        pytest.globals = pytest.globals or {}
        pytest.globals["task_id"] = result["created"].get("id")
        pytest.globals["task_index"] = result["task_index"]
        pytest.globals["created_task"] = result["created"]
    
    def test_task_create_with_optional_fields(self, api_headers, function_params):
        """Verify task.create accepts optional fields (tags, estimated_time, energy)."""
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.create",
                "confirm": False,
                "arguments": {
                    "title": "Golden Test Task 2 - Full",
                    "priority": "medium",
                    "status": "in_progress",
                    "tags": ["golden", "test", "custom-gpt"],
                    "estimated_time": "2hours",
                    "energy": "high",
                    "due_date": (datetime.now() + timedelta(days=2)).date().isoformat(),
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        result = data["result"]
        entry = result["created"]
        assert entry["tags"] == ["golden", "test", "custom-gpt"]
        assert entry["estimated_time"] == "2hours"
        assert entry["energy"] == "high"
        assert entry["status"] == "in_progress"


class TestTaskListAndUpdateWithIndex:
    """Verify task.list returns flattened tasks and task.update uses task_index."""
    
    def test_task_list_returns_flattened_tasks(self, api_headers, function_params):
        """task.list should return flat array of tasks with task_index."""
        payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.list",
                "confirm": False,
                "arguments": {}
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        result = data["result"]
        assert "tasks" in result
        assert isinstance(result["tasks"], list)
        assert result["count"] == len(result["tasks"])
        
        # Each task should have task_index
        for i, task in enumerate(result["tasks"], 1):
            assert "task_index" in task, f"Task {i} missing task_index"
            assert task["task_index"] == i, f"task_index mismatch: got {task['task_index']}, expected {i}"
    
    def test_task_update_using_task_index(self, api_headers, function_params):
        """task.update should work with task_index (FIX #1 enables this)."""
        # First create a task to get task_index
        create_payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.create",
                "confirm": False,
                "arguments": {"title": "Task to Update"}
            }
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=create_payload,
        )
        task_index = create_resp.json()["result"]["task_index"]
        
        # Now update using task_index (not ID)
        update_payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.update",
                "confirm": False,
                "arguments": {
                    "task_index": task_index,
                    "title": "Task Updated via Index",
                    "status": "in_progress",
                }
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=update_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        
        result = data["result"]
        assert result["updated"]["title"] == "Task Updated via Index"
        assert result["task_index"] == task_index


class TestTaskCompleteAndDelete:
    """Verify task.complete and task.delete operations."""
    
    def test_task_complete(self, api_headers, function_params):
        """task.complete marks task as done."""
        # Create task
        create_payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.create",
                "confirm": False,
                "arguments": {"title": "Task to Complete"}
            }
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=create_payload,
        )
        task_index = create_resp.json()["result"]["task_index"]
        
        # Complete it
        complete_payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.complete",
                "confirm": False,
                "arguments": {"task_index": task_index}
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=complete_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["result"]["completed"] is True
        assert data["result"]["task_index"] == task_index
    
    def test_task_delete_requires_confirm(self, api_headers, function_params):
        """task.delete requires confirm=true (destructive)."""
        # Create task
        create_payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.create",
                "confirm": False,
                "arguments": {"title": "Task to Delete"}
            }
        }
        create_resp = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=create_payload,
        )
        task_index = create_resp.json()["result"]["task_index"]
        
        # Try delete without confirm
        delete_payload = {
            "action": "capability_exec",
            "user_id": USER_ID,
            "params": {
                "capability": "task.delete",
                "confirm": False,
                "arguments": {"task_index": task_index}
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=delete_payload,
        )
        # Should be blocked with 409
        assert response.status_code == 409
        data = response.json()
        assert data["error"]["code"] == "CONFIRMATION_REQUIRED"
        
        # Now with confirm=true
        delete_payload["params"]["confirm"] = True
        response = requests.post(
            f"{BASE_URL}/api/tool_call_handler",
            params=function_params,
            headers=api_headers,
            json=delete_payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["result"]["deleted"] is not None
