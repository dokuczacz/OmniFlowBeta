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

    def __init__(self, user_id, *, access_token=None):
        self.user_id = user_id
        self.access_token = access_token

    def request(self, method, path, *, params=None, json=None):
        _FakeGmailClient.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "json": json,
                "user_id": self.user_id,
                "access_token": self.access_token,
            }
        )
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
