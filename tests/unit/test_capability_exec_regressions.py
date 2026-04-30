import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")
    openai_stub.OpenAI = object
    sys.modules["openai"] = openai_stub

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


def test_mail_inbox_list_forwards_label_filters_and_limit_alias(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"messages": [], "next_page_token": None, "result_size_estimate": 0}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.inbox.list",
            "confirm": False,
            "arguments": {
                "account_slot": "primary",
                "limit": 20,
                "q": "newer_than:30d",
                "label_ids": ["INBOX"],
                "exclude_label_ids": "TRASH, SPAM",
                "include_spam_trash": False,
                "page_token": "cursor-123",
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "gmail_list"
    assert captured["payload"]["account_slot"] == "primary"
    assert captured["payload"]["max_results"] == 20
    assert captured["payload"]["q"] == "newer_than:30d"
    assert captured["payload"]["label_ids"] == ["INBOX"]
    assert captured["payload"]["exclude_label_ids"] == ["TRASH", "SPAM"]
    assert captured["payload"]["include_spam_trash"] is False
    assert captured["payload"]["page_token"] == "cursor-123"


def test_custom_bridge_mail_list_merges_exclusions_into_query(monkeypatch):
    import custom_bridge.__init__ as bridge

    captured = {}

    class FakeGmail:
        def __init__(self, user_id, access_token=None, account_slot="primary"):
            captured["user_id"] = user_id
            captured["account_slot"] = account_slot

        def request(self, method, path, params=None):
            captured["method"] = method
            captured["path"] = path
            captured["params"] = params or {}
            return type("Resp", (), {"json": lambda self: {"messages": [], "nextPageToken": None, "resultSizeEstimate": 0}})()

    monkeypatch.setattr(bridge, "GmailClient", FakeGmail)

    result = bridge.handle_gmail_list(
        "u1",
        {
            "max_results": 20,
            "q": "newer_than:30d",
            "label_ids": ["INBOX"],
            "exclude_label_ids": ["TRASH", "SPAM"],
            "include_spam_trash": False,
            "page_token": "cursor-123",
            "account_slot": "primary",
        },
    )

    assert result["status"] == "ok"
    assert captured["method"] == "get"
    assert captured["path"] == "messages"
    assert captured["params"]["maxResults"] == 20
    assert captured["params"]["labelIds"] == ["INBOX"]
    assert captured["params"]["q"] == "newer_than:30d -in:trash -in:spam"
    assert captured["params"]["includeSpamTrash"] is False
    assert captured["params"]["pageToken"] == "cursor-123"


def test_mail_search_uses_query_and_forwards_to_gmail_search(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"messages": [], "next_page_token": None, "result_size_estimate": 0}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.search",
            "confirm": False,
            "arguments": {
                "account_slot": "primary",
                "query": "in:inbox category:primary -in:spam -in:trash newer_than:7d",
                "limit": 15,
                "label_ids": ["INBOX"],
                "exclude_label_ids": ["PROMOTIONS"],
                "include_spam_trash": False,
                "page_token": "cursor-456",
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "gmail_search"
    assert captured["payload"]["account_slot"] == "primary"
    assert captured["payload"]["max_results"] == 15
    assert captured["payload"]["q"] == "in:inbox category:primary -in:spam -in:trash newer_than:7d"
    assert captured["payload"]["label_ids"] == ["INBOX"]
    assert captured["payload"]["exclude_label_ids"] == ["PROMOTIONS"]
    assert captured["payload"]["include_spam_trash"] is False
    assert captured["payload"]["page_token"] == "cursor-456"


def test_calendar_events_list_defaults_to_all_calendars(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"events": [], "count": 0}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "calendar.events.list",
            "confirm": False,
            "arguments": {
                "account_slot": "secondary",
                "time_min": "2026-05-01",
                "time_max": "2026-05-31",
                "max_results": 10,
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "calendar_list_events"
    assert captured["payload"]["account_slot"] == "secondary"
    assert captured["payload"]["include_all_calendars"] is True
    assert captured["payload"]["calendar_ids"] is None
