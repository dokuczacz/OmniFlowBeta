import os
import sys
import importlib
import types


BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)


if "azure.functions" not in sys.modules:
    azure_pkg = types.ModuleType("azure")
    azure_pkg.__path__ = []
    azure_functions = types.ModuleType("azure.functions")

    class _HttpResponse:
        def __init__(self, body, status_code=200, mimetype="application/json"):
            self.body = body.encode("utf-8") if isinstance(body, str) else body
            self.status_code = status_code
            self.mimetype = mimetype

    azure_functions.HttpResponse = _HttpResponse
    azure_functions.HttpRequest = object
    sys.modules["azure"] = azure_pkg
    sys.modules["azure.functions"] = azure_functions


callback = importlib.import_module("gmail_oauth_callback")


class _FakeRequest:
    def __init__(self, params):
        self.params = params


def test_gmail_oauth_callback_saves_tokens_for_slot_from_state(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        callback.GmailTokenStore,
        "load_state",
        lambda state: {"user_id": "user-slot", "slot": "secondary"},
    )
    monkeypatch.setattr(
        callback,
        "_exchange_code",
        lambda code: {"access_token": "tok", "refresh_token": "ref", "scope": "https://mail.google.com/"},
    )
    monkeypatch.setattr(
        callback.GmailTokenStore,
        "save_tokens",
        lambda user_id, token_payload, slot=None: captured.update(
            {"user_id": user_id, "token_payload": token_payload, "slot": slot}
        ),
    )
    monkeypatch.setattr(callback.GmailTokenStore, "delete_state", lambda state: None)
    monkeypatch.setattr(callback, "_try_prefetch_inbox", lambda user_id, account_slot: None)

    resp = callback.main(_FakeRequest({"state": "abc", "code": "oauth-code"}))

    assert resp.status_code == 200
    assert captured["user_id"] == "user-slot"
    assert captured["slot"] == "secondary"
    assert captured["token_payload"]["access_token"] == "tok"
