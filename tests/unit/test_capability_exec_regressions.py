import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tool_call_handler as handler  # noqa: E402


def test_task_create_returns_flattened_index_and_update_accepts_it(monkeypatch):
    # This shape used to break create->update because len(tm_data) != flattened task index.
    state = {"tm": [{"tasks": []}]}

    def fake_read(_user_id, file_name):
        assert file_name == "TM.json"
        return {"status": "success", "data": state["tm"]}

    def fake_upload(_user_id, target_blob_name, file_content):
        assert target_blob_name == "TM.json"
        state["tm"] = file_content
        return {"status": "success"}

    monkeypatch.setattr(handler, "_inprocess_read_blob_file", fake_read)
    monkeypatch.setattr(handler, "_inprocess_upload_data_or_file", fake_upload)

    create_payload = {
        "capability": "task.create",
        "confirm": False,
        "arguments": {"title": "Regression task"},
    }
    create_body, create_status = handler._handle_capability_exec("u1", create_payload)
    assert create_status == 200
    assert create_body["status"] == "success"
    assert create_body["result"]["created"]["title"] == "Regression task"
    assert create_body["result"]["task_index"] == 1

    update_payload = {
        "capability": "task.update",
        "confirm": False,
        "arguments": {
            "task_index": create_body["result"]["task_index"],
            "title": "Updated regression task",
        },
    }
    update_body, update_status = handler._handle_capability_exec("u1", update_payload)
    assert update_status == 200
    assert update_body["status"] == "success"
    assert update_body["result"]["updated"]["title"] == "Updated regression task"


def test_calendar_token_exchange_failure_maps_to_mail_auth_required(monkeypatch):
    def fake_bridge_action(_action, _user_id, _payload):
        raise ValueError("Token exchange failed (status=400)")

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "calendar.events.list",
            "confirm": False,
            "arguments": {
                "time_min": "2026-03-31",
                "time_max": "2026-04-07",
                "max_results": 10,
            },
        },
    )

    assert status == 409
    assert body["status"] == "error"
    assert body["error"]["code"] == "MAIL_AUTH_REQUIRED"
