import os
import sys
import importlib
import uuid
from types import SimpleNamespace

import pytest
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

bridge = importlib.import_module("custom_bridge")


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeGmailClient:
    calls = []
    profile_response = {"emailAddress": "person@example.com"}
    message_headers = [
        {"name": "From", "value": "sender@example.com"},
        {"name": "Reply-To", "value": "reply@example.com"},
        {"name": "Subject", "value": "Original Subject"},
        {"name": "Message-ID", "value": "<msg-42@example.com>"},
        {"name": "References", "value": "<older@example.com>"},
    ]

    def __init__(self, user_id, *, access_token=None, account_slot=None):
        self.user_id = user_id
        self.access_token = access_token
        self.account_slot = account_slot

    def request(self, method, path, *, params=None, json=None):
        _FakeGmailClient.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json": json,
                "user_id": self.user_id,
                "access_token": self.access_token,
                "account_slot": self.account_slot,
            }
        )
        if path.startswith("messages/") and method == "get":
            return _FakeResponse(
                {
                    "threadId": "thr-42",
                    "payload": {
                        "headers": list(_FakeGmailClient.message_headers)
                    }
                }
            )
        if path == "profile" and method == "get":
            return _FakeResponse(dict(_FakeGmailClient.profile_response))
        if path == "messages/send":
            return _FakeResponse({"id": "msg-sent", "threadId": "thr-42"})
        if path.endswith("/trash"):
            return _FakeResponse({"id": "msg-1", "threadId": "thr-1"})
        return _FakeResponse({})

    def calendar_request(self, method, path, *, params=None, json=None):
        _FakeGmailClient.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json": json,
                "user_id": self.user_id,
                "access_token": self.access_token,
                "account_slot": self.account_slot,
            }
        )
        if method == "get" and path == "users/me/calendarList":
            return _FakeResponse(
                {
                    "items": [
                        {"id": "primary", "summary": "Primary"},
                        {"id": "secondary-birthdays", "summary": "Birthdays"},
                        {"id": "pl.polish#holiday@group.v.calendar.google.com", "summary": "Polish Holidays"},
                    ]
                }
            )
        if method == "get" and path == "calendars/primary/events":
            return _FakeResponse(
                {
                    "items": [
                        {
                            "id": "evt-primary-1",
                            "summary": "Team Sync",
                            "start": {"dateTime": "2026-05-08T09:00:00"},
                            "end": {"dateTime": "2026-05-08T09:30:00"},
                        }
                    ]
                }
            )
        if method == "get" and path == "calendars/secondary-birthdays/events":
            return _FakeResponse(
                {
                    "items": [
                        {
                            "id": "evt-bday-1",
                            "summary": "Mama ma urodziny",
                            "eventType": "birthday",
                            "start": {"date": "2026-05-07"},
                            "end": {"date": "2026-05-08"},
                        }
                    ]
                }
            )
        if method == "get" and path == "calendars/pl.polish%23holiday%40group.v.calendar.google.com/events":
            return _FakeResponse(
                {
                    "items": [
                        {
                            "id": "evt-holiday-1",
                            "summary": "Swieto",
                            "start": {"date": "2026-05-03"},
                            "end": {"date": "2026-05-04"},
                        }
                    ]
                }
            )
        if method in {"post", "patch"}:
            payload = {"id": "evt-1"}
            if isinstance(json, dict):
                payload.update(json)
            return _FakeResponse(payload)
        return _FakeResponse({})


@pytest.fixture(autouse=True)
def _patch_gmail_client(monkeypatch):
    _FakeGmailClient.calls = []
    _FakeGmailClient.profile_response = {"emailAddress": "person@example.com"}
    _FakeGmailClient.message_headers = [
        {"name": "From", "value": "sender@example.com"},
        {"name": "Reply-To", "value": "reply@example.com"},
        {"name": "Subject", "value": "Original Subject"},
        {"name": "Message-ID", "value": "<msg-42@example.com>"},
        {"name": "References", "value": "<older@example.com>"},
    ]
    monkeypatch.setattr(bridge, "GmailClient", _FakeGmailClient)
    monkeypatch.setattr(bridge, "load_user_profile", lambda user_id: {"display_name": "MarioBros", "primary_email": "person@example.com"})
    monkeypatch.setattr(bridge, "upsert_gmail_identity", lambda *args, **kwargs: {})
    monkeypatch.setattr(bridge.GmailTokenStore, "save_tokens", lambda *args, **kwargs: None)


def test_handle_gmail_trash_success():
    result = bridge.handle_gmail_trash("user-1", {"message_id": "abc"}, "token-1")

    assert result["action"] == "gmail_trash"
    assert result["status"] == "ok"
    assert result["user_id"] == "user-1"
    assert result["message_id"] == "msg-1"
    assert result["thread_id"] == "thr-1"
    assert uuid.UUID(result["audit_id"])
    assert _FakeGmailClient.calls[0]["method"] == "post"
    assert _FakeGmailClient.calls[0]["path"] == "messages/abc/trash"


def test_handle_gmail_delete_success():
    result = bridge.handle_gmail_delete("user-1", {"message_id": "xyz"}, "token-2")

    assert result["action"] == "gmail_delete"
    assert result["status"] == "ok"
    assert result["user_id"] == "user-1"
    assert result["message_id"] == "xyz"
    assert uuid.UUID(result["audit_id"])
    assert _FakeGmailClient.calls[0]["method"] == "delete"
    assert _FakeGmailClient.calls[0]["path"] == "messages/xyz"


def test_handle_gmail_trash_requires_message_id():
    with pytest.raises(ValueError, match="message_id is required for gmail_trash"):
        bridge.handle_gmail_trash("user-1", {}, None)


def test_handle_gmail_delete_requires_message_id():
    with pytest.raises(ValueError, match="message_id is required for gmail_delete"):
        bridge.handle_gmail_delete("user-1", {}, None)


def test_handle_gmail_reply_success_uses_original_message_metadata():
    result = bridge.handle_gmail_reply(
        "user-1",
        {
            "message_id": "orig-1",
            "body": "Reply body",
            "attachments": [{"fileName": "reply.txt", "contentBase64": "SGVsbG8="}],
        },
        "token-3",
    )

    assert result["action"] == "gmail_reply"
    assert result["status"] == "sent"
    assert result["message_id"] == "msg-sent"
    assert result["thread_id"] == "thr-42"
    assert result["reply_to_message_id"] == "orig-1"
    assert uuid.UUID(result["audit_id"])
    assert _FakeGmailClient.calls[0]["method"] == "get"
    assert _FakeGmailClient.calls[0]["path"] == "messages/orig-1"
    assert _FakeGmailClient.calls[1]["method"] == "post"
    assert _FakeGmailClient.calls[1]["path"] == "messages/send"
    assert _FakeGmailClient.calls[1]["json"]["threadId"] == "thr-42"


def test_handle_gmail_reply_requires_message_id():
    with pytest.raises(ValueError, match="message_id is required for gmail_reply"):
        bridge.handle_gmail_reply("user-1", {"body": "Reply body"}, None)


def test_handle_gmail_reply_requires_body():
    with pytest.raises(ValueError, match="body is required for gmail_reply"):
        bridge.handle_gmail_reply("user-1", {"message_id": "orig-1"}, None)


def test_handle_gmail_reply_falls_back_to_to_header_when_sender_headers_missing():
    _FakeGmailClient.message_headers = [
        {"name": "To", "value": "target@example.com"},
        {"name": "Subject", "value": "Original Subject"},
        {"name": "Message-ID", "value": "<msg-42@example.com>"},
    ]

    result = bridge.handle_gmail_reply(
        "user-1",
        {"message_id": "orig-2", "body": "Reply body"},
        "token-33",
    )

    assert result["status"] == "sent"
    send_call = _FakeGmailClient.calls[1]
    raw_bytes = bridge.base64.urlsafe_b64decode(send_call["json"]["raw"] + "===")
    assert b"To: target@example.com" in raw_bytes


def test_handle_calendar_create_event_normalizes_nested_start_end():
    result = bridge.handle_calendar_create_event(
        "user-1",
        {
            "summary": "TEST OmniFlow Calendar",
            "description": "Test event",
            "start": {
                "dateTime": "2026-05-01T10:00:00",
                "timeZone": "Europe/Zurich",
            },
            "end": {
                "dateTime": "2026-05-01T10:30:00",
                "timeZone": "Europe/Zurich",
            },
        },
        "token-4",
    )

    assert result["action"] == "calendar_create_event"
    assert result["status"] == "ok"
    assert result["event_id"] == "evt-1"
    assert _FakeGmailClient.calls[0]["method"] == "post"
    assert _FakeGmailClient.calls[0]["path"] == "calendars/primary/events"
    assert _FakeGmailClient.calls[0]["json"]["start"] == {
        "dateTime": "2026-05-01T10:00:00",
        "timeZone": "Europe/Zurich",
    }
    assert _FakeGmailClient.calls[0]["json"]["end"] == {
        "dateTime": "2026-05-01T10:30:00",
        "timeZone": "Europe/Zurich",
    }


def test_handle_calendar_update_event_normalizes_flat_aliases():
    result = bridge.handle_calendar_update_event(
        "user-1",
        {
            "event_id": "evt-9",
            "summary": "Updated Calendar Event",
            "start_dateTime": "2026-05-01T11:00:00",
            "start_timeZone": "Europe/Zurich",
            "end_dateTime": "2026-05-01T11:30:00",
            "end_timeZone": "Europe/Zurich",
        },
        "token-5",
    )

    assert result["action"] == "calendar_update_event"
    assert result["status"] == "ok"
    assert _FakeGmailClient.calls[0]["method"] == "patch"
    assert _FakeGmailClient.calls[0]["path"] == "calendars/primary/events/evt-9"
    assert _FakeGmailClient.calls[0]["json"]["start"] == {
        "dateTime": "2026-05-01T11:00:00",
        "timeZone": "Europe/Zurich",
    }
    assert _FakeGmailClient.calls[0]["json"]["end"] == {
        "dateTime": "2026-05-01T11:30:00",
        "timeZone": "Europe/Zurich",
    }


def test_handle_calendar_list_events_aggregates_all_calendars():
    result = bridge.handle_calendar_list_events(
        "user-1",
        {
            "time_min": "2026-05-01T00:00:00Z",
            "time_max": "2026-05-31T23:59:59Z",
            "max_results": 20,
            "include_all_calendars": True,
        },
        "token-6",
    )

    assert result["action"] == "calendar_list_events"
    assert result["status"] == "ok"
    assert result["include_all_calendars"] is True
    assert result["calendar_ids"] == ["primary", "secondary-birthdays", "pl.polish#holiday@group.v.calendar.google.com"]
    assert result["count"] == 3
    assert [event["calendarId"] for event in result["events"]] == [
        "pl.polish#holiday@group.v.calendar.google.com",
        "secondary-birthdays",
        "primary",
    ]
    assert result["events"][0]["summary"] == "Swieto"
    assert result["events"][0]["calendarId"] == "pl.polish#holiday@group.v.calendar.google.com"
    assert result["events"][1]["summary"] == "Mama ma urodziny"
    assert result["events"][2]["summary"] == "Team Sync"


def test_handle_calendar_list_calendars_returns_accessible_calendar_metadata():
    result = bridge.handle_calendar_list_calendars(
        "user-1",
        {"account_slot": "primary", "min_access_role": "reader"},
        "token-7",
    )

    assert result["action"] == "calendar_list_calendars"
    assert result["status"] == "ok"
    assert result["account_slot"] == "primary"
    assert result["count"] == 3
    assert result["calendars"][0]["id"] == "primary"
    assert result["calendars"][1]["id"] == "secondary-birthdays"


def test_handle_oauth_status_reports_reauth_when_slot_missing(monkeypatch):
    monkeypatch.setattr(bridge.GmailTokenStore, "load_tokens", lambda user_id, slot=None: None)
    saved_states = []
    monkeypatch.setattr(
        bridge.GmailTokenStore,
        "save_state",
        lambda state, user_id, slot=None, metadata=None: saved_states.append((user_id, slot, state, metadata)),
    )
    monkeypatch.setattr(bridge.GmailOAuthConfig, "has_credentials", classmethod(lambda cls: True))
    monkeypatch.setattr(bridge.GmailOAuthConfig, "authorize_url", classmethod(lambda cls, state, login_hint=None: f"https://auth.example/{state}"))
    monkeypatch.setattr(bridge.GmailOAuthConfig, "SCOPES", "scope-a scope-b")
    monkeypatch.setattr(bridge.GmailOAuthConfig, "REDIRECT_URI", "https://app.example/callback")

    result = bridge.handle_oauth_status("user-1", {"account_slot": "secondary"})

    assert result["authorized"] is False
    assert result["requires_reauth"] is True
    assert result["reauth_reason"] == "no_token"
    assert result["account_slot"] == "secondary"
    assert result["authorize_url"].startswith("https://auth.example/")
    assert result["authorization_url"] == result["authorize_url"]
    assert all(slot == "secondary" for _, slot, _, _ in saved_states)


def test_handle_oauth_status_reports_refresh_failure(monkeypatch):
    expired = {
        "access_token": "old-token",
        "refresh_token": "refresh-token",
        "expires_at": "2020-01-01T00:00:00+00:00",
        "scope": "https://mail.google.com/",
        "saved_at": "2020-01-01T00:00:00+00:00",
    }
    monkeypatch.setattr(bridge.GmailTokenStore, "load_tokens", lambda user_id, slot=None: expired)
    monkeypatch.setattr(bridge.GmailTokenStore, "save_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(bridge.GmailOAuthConfig, "has_credentials", classmethod(lambda cls: True))
    monkeypatch.setattr(bridge.GmailOAuthConfig, "authorize_url", classmethod(lambda cls, state, login_hint=None: f"https://auth.example/{state}"))
    monkeypatch.setattr(bridge.GmailOAuthConfig, "REDIRECT_URI", "https://app.example/callback")

    class FailingGmail:
        def __init__(self, user_id, *, access_token=None, account_slot=None):
            pass

        def request(self, method, path, *, params=None, json=None):
            response = SimpleNamespace(status_code=400, url="https://oauth2.googleapis.com/token")
            raise requests.HTTPError("refresh failed", response=response)

    monkeypatch.setattr(bridge, "GmailClient", FailingGmail)

    result = bridge.handle_oauth_status("user-1", {"account_slot": "primary"})

    assert result["authorized"] is False
    assert result["requires_reauth"] is True
    assert result["reauth_reason"] == "refresh_http_400"


def test_handle_ensure_authorized_and_status_share_same_verdict(monkeypatch):
    token = {
        "access_token": "live-token",
        "refresh_token": "refresh-token",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "scope": "https://mail.google.com/",
        "saved_at": "2026-05-07T08:00:00+00:00",
    }
    monkeypatch.setattr(bridge.GmailTokenStore, "load_tokens", lambda user_id, slot=None: token)
    saved_states = []
    monkeypatch.setattr(
        bridge.GmailTokenStore,
        "save_state",
        lambda state, user_id, slot=None, metadata=None: saved_states.append((user_id, slot, state, metadata)),
    )
    monkeypatch.setattr(bridge.GmailOAuthConfig, "has_credentials", classmethod(lambda cls: True))
    monkeypatch.setattr(bridge.GmailOAuthConfig, "authorize_url", classmethod(lambda cls, state, login_hint=None: f"https://auth.example/{state}"))
    monkeypatch.setattr(bridge.GmailOAuthConfig, "REDIRECT_URI", "https://app.example/callback")

    class HealthyGmail:
        def __init__(self, user_id, *, access_token=None, account_slot=None):
            self.account_slot = account_slot

        def request(self, method, path, *, params=None, json=None):
            return _FakeResponse({"emailAddress": f"{self.account_slot}@example.com"})

    monkeypatch.setattr(bridge, "GmailClient", HealthyGmail)

    status_result = bridge.handle_oauth_status("user-1", {"account_slot": "secondary"})
    authorize_result = bridge.handle_ensure_authorized("user-1", {"account_slot": "secondary"})

    assert status_result["authorized"] is True
    assert authorize_result["authorized"] is True
    assert status_result["requires_reauth"] is True
    assert authorize_result["requires_reauth"] is True
    assert status_result["reauth_reason"] == "calendar_scope_missing"
    assert authorize_result["reauth_reason"] == "calendar_scope_missing"
    assert any(slot == "secondary" for _, slot, _, _ in saved_states)
