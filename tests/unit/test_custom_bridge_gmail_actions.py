import os
import sys
import importlib
import uuid

import pytest

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
                        "headers": [
                            {"name": "From", "value": "sender@example.com"},
                            {"name": "Reply-To", "value": "reply@example.com"},
                            {"name": "Subject", "value": "Original Subject"},
                            {"name": "Message-ID", "value": "<msg-42@example.com>"},
                            {"name": "References", "value": "<older@example.com>"},
                        ]
                    },
                }
            )
        if path == "messages/send":
            return _FakeResponse({"id": "msg-sent", "threadId": "thr-42"})
        if path.endswith("/trash"):
            return _FakeResponse({"id": "msg-1", "threadId": "thr-1"})
        return _FakeResponse({})


@pytest.fixture(autouse=True)
def _patch_gmail_client(monkeypatch):
    _FakeGmailClient.calls = []
    monkeypatch.setattr(bridge, "GmailClient", _FakeGmailClient)


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
