"""
Unit tests for gmail multi-slot token storage, calendar scope detection,
and GmailClient slot-awareness.
"""
import importlib
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

BACKEND = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# ---------------------------------------------------------------------------
# Helpers to stub azure-storage before importing gmail_oauth
# ---------------------------------------------------------------------------

def _make_azure_stubs():
    """Return minimal stubs for azure.storage.blob + azure.core.exceptions."""
    # azure
    azure_pkg = types.ModuleType("azure")
    azure_pkg.__path__ = []
    # azure.core
    azure_core = types.ModuleType("azure.core")
    azure_core.__path__ = []
    azure_core_exc = types.ModuleType("azure.core.exceptions")
    setattr(azure_core_exc, "ResourceNotFoundError", Exception)
    setattr(azure_core_exc, "AzureError", Exception)
    # azure.storage
    azure_storage = types.ModuleType("azure.storage")
    azure_storage.__path__ = []
    azure_storage_blob = types.ModuleType("azure.storage.blob")
    setattr(azure_storage_blob, "BlobServiceClient", MagicMock())
    setattr(azure_storage_blob, "ContentSettings", MagicMock())

    stubs = {
        "azure": azure_pkg,
        "azure.core": azure_core,
        "azure.core.exceptions": azure_core_exc,
        "azure.storage": azure_storage,
        "azure.storage.blob": azure_storage_blob,
    }
    return stubs


@pytest.fixture(scope="module")
def gmail_oauth_module():
    stubs = _make_azure_stubs()
    with patch.dict("sys.modules", stubs):
        mod = importlib.import_module("shared.gmail_oauth")
    return mod


# ---------------------------------------------------------------------------
# GmailTokenStore._normalize_slot
# ---------------------------------------------------------------------------

class TestNormalizeSlot:
    def test_none_returns_primary(self, gmail_oauth_module):
        assert gmail_oauth_module.GmailTokenStore._normalize_slot(None) == "primary"

    def test_empty_returns_primary(self, gmail_oauth_module):
        assert gmail_oauth_module.GmailTokenStore._normalize_slot("") == "primary"

    def test_primary_passthrough(self, gmail_oauth_module):
        assert gmail_oauth_module.GmailTokenStore._normalize_slot("primary") == "primary"

    def test_secondary_passthrough(self, gmail_oauth_module):
        assert gmail_oauth_module.GmailTokenStore._normalize_slot("secondary") == "secondary"

    def test_invalid_returns_primary(self, gmail_oauth_module):
        assert gmail_oauth_module.GmailTokenStore._normalize_slot("tertiary") == "primary"

    def test_uppercase_secondary(self, gmail_oauth_module):
        assert gmail_oauth_module.GmailTokenStore._normalize_slot("SECONDARY") == "secondary"


# ---------------------------------------------------------------------------
# GmailTokenStore._blob_client path construction
# ---------------------------------------------------------------------------

class TestBlobClientPath:
    def _get_blob_path(self, token_store, user_id, slot):
        """Extract the blob name from the BlobClient mock."""
        container_mock = MagicMock()
        with patch.object(token_store, "_get_container_client", return_value=container_mock):
            token_store._blob_client(user_id, slot)
            args = container_mock.get_blob_client.call_args
            return args[0][0] if args and args[0] else args[1].get("blob")

    def test_slot_path_primary(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        container_mock = MagicMock()
        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            GTS._blob_client("user1", "primary")
        path = container_mock.get_blob_client.call_args[0][0]
        assert path == "gmail/oauth/user1/primary.json"

    def test_slot_path_secondary(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        container_mock = MagicMock()
        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            GTS._blob_client("user2", "secondary")
        path = container_mock.get_blob_client.call_args[0][0]
        assert path == "gmail/oauth/user2/secondary.json"

    def test_legacy_path(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        container_mock = MagicMock()
        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            GTS._legacy_blob_client("user3")
        path = container_mock.get_blob_client.call_args[0][0]
        assert path == "gmail/oauth/user3.json"


# ---------------------------------------------------------------------------
# has_calendar_scope
# ---------------------------------------------------------------------------

class TestHasCalendarScope:
    CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
    GMAIL_SCOPE = "https://mail.google.com/"

    def test_detects_calendar_scope(self, gmail_oauth_module):
        token = {"scope": f"{self.GMAIL_SCOPE} {self.CALENDAR_SCOPE}"}
        assert gmail_oauth_module.has_calendar_scope(token) is True

    def test_missing_calendar_scope(self, gmail_oauth_module):
        token = {"scope": self.GMAIL_SCOPE}
        assert gmail_oauth_module.has_calendar_scope(token) is False

    def test_none_token(self, gmail_oauth_module):
        assert gmail_oauth_module.has_calendar_scope(None) is False

    def test_no_scope_key(self, gmail_oauth_module):
        assert gmail_oauth_module.has_calendar_scope({}) is False


# ---------------------------------------------------------------------------
# save_tokens stamps account_slot
# ---------------------------------------------------------------------------

class TestSaveTokensSlot:
    def test_account_slot_stamped(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        blob_mock = MagicMock()
        container_mock = MagicMock()
        container_mock.get_blob_client.return_value = blob_mock

        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            GTS.save_tokens("user1", {"access_token": "tok", "scope": "gmail"}, slot="secondary")

        blob_mock.upload_blob.assert_called_once()
        uploaded_bytes = blob_mock.upload_blob.call_args[0][0]
        data = json.loads(uploaded_bytes)
        assert data["account_slot"] == "secondary"


# ---------------------------------------------------------------------------
# load_tokens: legacy fallback for primary slot only
# ---------------------------------------------------------------------------

class TestLoadTokensFallback:
    def _make_blob(self, data):
        blob = MagicMock()
        blob.download_blob.return_value.readall.return_value = json.dumps(data).encode()
        return blob

    def test_loads_slot_path_first_primary(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        slot_blob = self._make_blob({"access_token": "slot_tok"})
        container_mock = MagicMock()
        container_mock.get_blob_client.return_value = slot_blob

        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            result = GTS.load_tokens("user1", slot="primary")

        assert result["access_token"] == "slot_tok"

    def test_falls_back_to_legacy_for_primary(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        # slot blob doesn't exist
        slot_blob = MagicMock()
        slot_blob.download_blob.side_effect = gmail_oauth_module.ResourceNotFoundError
        legacy_blob = self._make_blob({"access_token": "legacy_tok"})
        container_mock = MagicMock()
        # First call → slot blob, second call → legacy blob
        container_mock.get_blob_client.side_effect = [slot_blob, legacy_blob]

        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            result = GTS.load_tokens("user1", slot="primary")

        assert result["access_token"] == "legacy_tok"

    def test_no_fallback_for_secondary(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        slot_blob = MagicMock()
        slot_blob.download_blob.side_effect = gmail_oauth_module.ResourceNotFoundError
        container_mock = MagicMock()
        container_mock.get_blob_client.return_value = slot_blob

        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            result = GTS.load_tokens("user1", slot="secondary")

        assert result is None


# ---------------------------------------------------------------------------
# list_connected_accounts
# ---------------------------------------------------------------------------

class TestListConnectedAccounts:
    def _make_blob_with(self, data):
        blob = MagicMock()
        blob.download_blob.return_value.readall.return_value = json.dumps(data).encode()
        return blob

    def _make_missing_blob(self, exc_class):
        blob = MagicMock()
        blob.download_blob.side_effect = exc_class
        return blob

    def test_returns_primary_only(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        primary_data = {
            "email_address": "a@example.com",
            "saved_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
            "scope": "https://mail.google.com/",
            "account_slot": "primary",
        }
        primary_blob = self._make_blob_with(primary_data)
        secondary_blob = self._make_missing_blob(gmail_oauth_module.ResourceNotFoundError)

        container_mock = MagicMock()
        container_mock.get_blob_client.side_effect = [primary_blob, secondary_blob]

        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            accounts = GTS.list_connected_accounts("user1")

        assert len(accounts) == 1
        assert accounts[0]["slot"] == "primary"
        assert accounts[0]["email_address"] == "a@example.com"
        assert accounts[0]["has_calendar_scope"] is False

    def test_returns_both_slots(self, gmail_oauth_module):
        GTS = gmail_oauth_module.GmailTokenStore
        CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
        primary_data = {
            "email_address": "a@example.com",
            "saved_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
            "scope": f"https://mail.google.com/ {CALENDAR_SCOPE}",
            "account_slot": "primary",
        }
        secondary_data = {
            "email_address": "b@example.com",
            "saved_at": "2024-01-01T00:00:00Z",
            "expires_at": "2024-01-02T00:00:00Z",
            "scope": "https://mail.google.com/",
            "account_slot": "secondary",
        }
        container_mock = MagicMock()
        container_mock.get_blob_client.side_effect = [
            self._make_blob_with(primary_data),
            self._make_blob_with(secondary_data),
        ]

        with patch.object(GTS, "_get_container_client", return_value=container_mock):
            accounts = GTS.list_connected_accounts("user1")

        assert len(accounts) == 2
        primary = next(a for a in accounts if a["slot"] == "primary")
        secondary = next(a for a in accounts if a["slot"] == "secondary")
        assert primary["has_calendar_scope"] is True
        assert secondary["has_calendar_scope"] is False
