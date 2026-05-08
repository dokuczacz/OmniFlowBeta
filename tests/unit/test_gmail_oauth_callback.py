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

if "azure.core" not in sys.modules:
    azure_core = types.ModuleType("azure.core")
    azure_core.__path__ = []
    azure_core_exc = types.ModuleType("azure.core.exceptions")
    setattr(azure_core_exc, "ResourceNotFoundError", Exception)
    setattr(azure_core_exc, "AzureError", Exception)
    setattr(azure_core_exc, "ResourceExistsError", Exception)
    azure_storage = types.ModuleType("azure.storage")
    azure_storage.__path__ = []
    azure_storage_blob = types.ModuleType("azure.storage.blob")
    setattr(azure_storage_blob, "BlobServiceClient", object)
    setattr(azure_storage_blob, "BlobClient", object)
    setattr(azure_storage_blob, "ContainerClient", object)
    sys.modules["azure.core"] = azure_core
    sys.modules["azure.core.exceptions"] = azure_core_exc
    sys.modules["azure.storage"] = azure_storage
    sys.modules["azure.storage.blob"] = azure_storage_blob


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


def test_gmail_oauth_callback_syncs_email_into_profile(monkeypatch):
    saved_profiles = []
    saved_tokens = []

    monkeypatch.setattr(
        callback.GmailTokenStore,
        "load_state",
        lambda state: {"user_id": "user-slot", "slot": "primary", "display_name": "MarioBros"},
    )
    monkeypatch.setattr(
        callback,
        "_exchange_code",
        lambda code: {"access_token": "tok", "refresh_token": "ref", "scope": "https://mail.google.com/ https://www.googleapis.com/auth/calendar"},
    )
    monkeypatch.setattr(
        callback.GmailTokenStore,
        "save_tokens",
        lambda user_id, token_payload, slot=None: saved_tokens.append((user_id, slot, dict(token_payload))),
    )
    monkeypatch.setattr(
        callback.GmailTokenStore,
        "load_tokens",
        lambda user_id, slot=None: {
            "access_token": "tok",
            "refresh_token": "ref",
            "scope": "https://mail.google.com/ https://www.googleapis.com/auth/calendar",
        },
    )
    monkeypatch.setattr(callback.GmailTokenStore, "delete_state", lambda state: None)
    monkeypatch.setattr(callback, "_try_prefetch_inbox", lambda user_id, account_slot: None)
    monkeypatch.setattr(
        callback,
        "GmailClient",
        lambda user_id, account_slot=None: type(
            "FakeGmailClient",
            (),
            {"request": lambda self, method, path: type("Resp", (), {"json": lambda self: {"emailAddress": "mario@example.com"}})()},
        )(),
    )
    monkeypatch.setattr(
        callback,
        "upsert_gmail_identity",
        lambda user_id, account_slot, email_address, display_name=None, has_calendar_scope=None: saved_profiles.append(
            {
                "user_id": user_id,
                "account_slot": account_slot,
                "email_address": email_address,
                "display_name": display_name,
                "has_calendar_scope": has_calendar_scope,
            }
        ),
    )

    resp = callback.main(_FakeRequest({"state": "abc", "code": "oauth-code"}))

    assert resp.status_code == 200
    assert saved_profiles[0]["display_name"] == "MarioBros"
    assert saved_profiles[0]["email_address"] == "mario@example.com"
    assert saved_profiles[0]["has_calendar_scope"] is True
    assert saved_tokens[-1][2]["email_address"] == "mario@example.com"
