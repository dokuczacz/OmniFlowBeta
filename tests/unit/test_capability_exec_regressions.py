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


def test_custom_bridge_mail_list_merges_category_into_query(monkeypatch):
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
            "max_results": 10,
            "q": "in:inbox newer_than:30d",
            "category": "primary",
            "account_slot": "primary",
        },
    )

    assert result["status"] == "ok"
    assert captured["method"] == "get"
    assert captured["path"] == "messages"
    assert captured["params"]["q"] == "in:inbox newer_than:30d category:primary"


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


def test_mail_authorize_forwards_identity_hints(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"authorized": False, "requires_reauth": True}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.authorize",
            "confirm": False,
            "arguments": {
                "account_slot": "secondary",
                "login_hint": "horodecki.mariusz@gmail.com",
                "display_name": "MarioBros",
                "force": True,
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "ensure_authorized"
    assert captured["payload"]["account_slot"] == "secondary"
    assert captured["payload"]["login_hint"] == "horodecki.mariusz@gmail.com"
    assert captured["payload"]["display_name"] == "MarioBros"
    assert captured["payload"]["force"] is True


def test_mail_status_forwards_identity_hints(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"authorized": False, "requires_reauth": True}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.status",
            "confirm": False,
            "arguments": {
                "account_slot": "secondary",
                "login_hint": "horodecki.mariusz@gmail.com",
                "profile_name": "MarioBros",
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "oauth_status"
    assert captured["payload"]["account_slot"] == "secondary"
    assert captured["payload"]["login_hint"] == "horodecki.mariusz@gmail.com"
    assert captured["payload"]["display_name"] == "MarioBros"


def test_mail_find_builds_query_and_selects_latest(monkeypatch):
    def fake_bridge_action(action, _user_id, payload):
        if action == "gmail_search":
            assert payload["q"] == 'from:(dasteam) subject:(Lohnabrechnung) newer_than:60d'
            return {
                "messages": [
                    {"id": "msg-new", "threadId": "thr-new"},
                    {"id": "msg-old", "threadId": "thr-old"},
                ]
            }
        if action == "gmail_get":
            message_id = payload["message_id"]
            if message_id == "msg-new":
                return {
                    "message": {
                        "snippet": "Latest payroll message",
                        "labelIds": ["INBOX"],
                        "payload": {
                            "headers": [
                                {"name": "From", "value": "dasteam payroll"},
                                {"name": "Subject", "value": "Lohnabrechnung Mai"},
                                {"name": "Date", "value": "Fri, 08 May 2026 12:00:00 +0000"},
                            ]
                        },
                    }
                }
            return {
                "message": {
                    "snippet": "Older payroll message",
                    "labelIds": ["INBOX"],
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "dasteam payroll"},
                            {"name": "Subject", "value": "Lohnabrechnung April"},
                            {"name": "Date", "value": "Fri, 01 May 2026 12:00:00 +0000"},
                        ]
                    },
                }
            }
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.find",
            "confirm": False,
            "arguments": {
                "account_slot": "primary",
                "sender": "dasteam",
                "subject": "Lohnabrechnung",
                "newer_than_days": 60,
                "latest": True,
                "limit": 5,
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    result = body["result"]
    assert result["resolution"] == "single_match"
    assert result["selected_message_id"] == "msg-new"
    assert result["selected"]["subject"] == "Lohnabrechnung Mai"
    assert result["selection_reason"] == "latest"
    assert result["candidate_count"] == 2


def test_mail_find_returns_multiple_matches_without_latest(monkeypatch):
    def fake_bridge_action(action, _user_id, payload):
        if action == "gmail_search":
            return {"messages": [{"id": "m1", "threadId": "t1"}, {"id": "m2", "threadId": "t2"}]}
        if action == "gmail_get":
            return {
                "message": {
                    "snippet": "candidate",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "jobs@example.com"},
                            {"name": "Subject", "value": "Lohnabrechnung"},
                        ]
                    },
                }
            }
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.find",
            "confirm": False,
            "arguments": {"query": 'subject:"Lohnabrechnung"', "limit": 5},
        },
    )

    assert status == 200
    assert body["result"]["resolution"] == "multiple_matches"
    assert body["result"]["candidate_count"] == 2
    assert "selected_message_id" not in body["result"]


def test_calendar_calendars_list_forwards_account_slot(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"calendars": [], "count": 0, "account_slot": payload["account_slot"]}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "calendar.calendars.list",
            "confirm": False,
            "arguments": {"account_slot": "secondary", "min_access_role": "reader"},
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "calendar_list_calendars"
    assert captured["payload"]["account_slot"] == "secondary"


def test_mail_thread_get_forwards_thread_id(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"thread_id": payload["thread_id"], "messages": [], "message_count": 0}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.thread.get",
            "confirm": False,
            "arguments": {"thread_id": "thr-42", "account_slot": "secondary"},
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "gmail_thread_get"
    assert captured["payload"]["thread_id"] == "thr-42"
    assert captured["payload"]["account_slot"] == "secondary"


def test_mail_modify_requires_confirm(monkeypatch):
    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.modify",
            "confirm": False,
            "arguments": {"message_id": "msg-1", "mark_read": True},
        },
    )

    assert status == 409
    assert body["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_mail_modify_forwards_state_flags_and_labels(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"message_id": payload["message_id"], "labelIds": []}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.modify",
            "confirm": True,
            "arguments": {
                "account_slot": "primary",
                "message_id": "msg-99",
                "mark_read": True,
                "archive": True,
                "star": True,
                "add_label_ids": ["IMPORTANT"],
                "remove_label_ids": ["CATEGORY_UPDATES"],
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "gmail_modify"
    assert captured["payload"]["message_id"] == "msg-99"
    assert captured["payload"]["mark_read"] is True
    assert captured["payload"]["archive"] is True
    assert captured["payload"]["star"] is True
    assert captured["payload"]["add_label_ids"] == ["IMPORTANT"]
    assert captured["payload"]["remove_label_ids"] == ["CATEGORY_UPDATES"]


def test_mail_attachment_get_forwards_ids(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"message_id": payload["message_id"], "attachment_id": payload["attachment_id"], "data": "SGVsbG8="}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.attachment.get",
            "confirm": False,
            "arguments": {"account_slot": "secondary", "message_id": "msg-1", "attachment_id": "att-9"},
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "gmail_attachment"
    assert captured["payload"]["account_slot"] == "secondary"


def test_calendar_freebusy_get_forwards_range(monkeypatch):
    captured = {}

    def fake_bridge_action(action, _user_id, payload):
        captured["action"] = action
        captured["payload"] = payload
        return {"calendar_ids": payload["calendar_ids"], "calendars": []}

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "calendar.freebusy.get",
            "confirm": False,
            "arguments": {
                "account_slot": "primary",
                "time_min": "2026-05-08T00:00:00Z",
                "time_max": "2026-05-08T23:59:59Z",
                "calendar_ids": ["primary", "team"],
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "calendar_freebusy"
    assert captured["payload"]["calendar_ids"] == ["primary", "team"]


def test_mail_inbox_list_forwards_category(monkeypatch):
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
                "limit": 10,
                "category": "primary",
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    assert captured["action"] == "gmail_list"
    assert captured["payload"]["category"] == "primary"


def test_mail_inbox_list_enriched_response_keeps_label_ids(monkeypatch):
    def fake_bridge_action(action, _user_id, payload):
        if action == "gmail_list":
            return {
                "messages": [
                    {
                        "id": "msg-1",
                        "threadId": "thr-1",
                        "labelIds": ["INBOX", "CATEGORY_UPDATES"],
                    }
                ],
                "next_page_token": None,
                "result_size_estimate": 1,
            }
        if action == "gmail_get":
            return {
                "message": {
                    "snippet": "Build completed",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "alerts@example.com"},
                            {"name": "Subject", "value": "CI status"},
                            {"name": "Date", "value": "Thu, 30 Apr 2026 08:00:00 +0000"},
                        ]
                    },
                }
            }
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.inbox.list",
            "confirm": False,
            "arguments": {
                "account_slot": "primary",
                "limit": 5,
            },
        },
    )

    assert status == 200
    assert body["status"] == "success"
    messages = body["result"]["messages"]
    assert messages[0]["labelIds"] == ["INBOX", "CATEGORY_UPDATES"]
    assert messages[0]["subject"] == "CI status"
    assert messages[0]["from"] == "alerts@example.com"


def test_mail_inbox_list_enriched_response_falls_back_to_message_label_ids(monkeypatch):
    def fake_bridge_action(action, _user_id, payload):
        if action == "gmail_list":
            return {
                "messages": [
                    {
                        "id": "msg-1",
                        "threadId": "thr-1",
                    }
                ],
                "next_page_token": None,
                "result_size_estimate": 1,
            }
        if action == "gmail_get":
            return {
                "message": {
                    "labelIds": ["UNREAD", "INBOX"],
                    "snippet": "Build completed",
                    "payload": {
                        "headers": [
                            {"name": "From", "value": "alerts@example.com"},
                            {"name": "Subject", "value": "CI status"},
                        ]
                    },
                }
            }
        raise AssertionError(f"Unexpected action: {action}")

    monkeypatch.setattr(handler, "_bridge_action", fake_bridge_action)

    body, status = handler._handle_capability_exec(
        "u1",
        {
            "capability": "mail.inbox.list",
            "confirm": False,
            "arguments": {"account_slot": "primary", "limit": 5},
        },
    )

    assert status == 200
    assert body["result"]["messages"][0]["labelIds"] == ["UNREAD", "INBOX"]


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
