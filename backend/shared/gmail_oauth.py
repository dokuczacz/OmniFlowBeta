"""
Gmail OAuth helpers for Azure Function integration.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from urllib.parse import quote

from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.storage.blob import BlobServiceClient

from .config import AzureConfig


GMAIL_SCOPE = "https://mail.google.com/"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
COMBINED_SCOPES = f"{GMAIL_SCOPE} {CALENDAR_SCOPE}"
VALID_SLOTS = ("primary", "secondary")


class GmailOAuthConfig:
    CLIENT_ID = os.environ.get("GMAIL_OAUTH_CLIENT_ID", "").strip()
    CLIENT_SECRET = os.environ.get("GMAIL_OAUTH_CLIENT_SECRET", "").strip()
    REDIRECT_URI = os.environ.get("GMAIL_OAUTH_REDIRECT_URI", "").strip()
    # Default: Gmail + Calendar combined scopes. Override with GMAIL_OAUTH_SCOPES env var.
    SCOPES = os.environ.get("GMAIL_OAUTH_SCOPES", COMBINED_SCOPES).strip()
    PROMPT = os.environ.get("GMAIL_OAUTH_PROMPT", "consent").strip()
    RESPONSE_TYPE = "code"
    RESPONSE_MODE = "query"

    @classmethod
    def has_credentials(cls) -> bool:
        return bool(cls.CLIENT_ID and cls.CLIENT_SECRET and cls.REDIRECT_URI)

    @classmethod
    def authorize_url(cls, state: str, login_hint: Optional[str] = None) -> str:
        if not cls.has_credentials():
            raise ValueError("Missing Gmail OAuth client configuration")
        params = {
            "client_id": cls.CLIENT_ID,
            "redirect_uri": cls.REDIRECT_URI,
            "response_type": cls.RESPONSE_TYPE,
            "scope": cls.SCOPES,
            "access_type": "offline",
            "prompt": cls.PROMPT,
            "state": state,
        }
        if login_hint:
            params["login_hint"] = login_hint
        query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items() if v)
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query}"

    @classmethod
    def token_url(cls) -> str:
        return "https://oauth2.googleapis.com/token"


class GmailTokenStore:
    """Persist Gmail OAuth payloads in blob storage for each user.

    Token paths:
      Slot-based (new):  gmail/oauth/{user_id}/{slot}.json  (slot: 'primary' | 'secondary')
      Legacy (backcompat): gmail/oauth/{user_id}.json  (migrated to 'primary' on next save)
    """

    BLOB_PREFIX = "gmail/oauth"
    STATE_PREFIX = "gmail/state"

    @staticmethod
    def _normalize_user_id(user_id: Optional[str]) -> str:
        if not user_id or not isinstance(user_id, str):
            return "default"
        normalized = user_id.strip().replace("/", "_").replace("\\", "_").replace("..", "__") or "default"
        return normalized

    @staticmethod
    def _normalize_slot(slot: Optional[str]) -> str:
        s = (slot or "primary").strip().lower()
        return s if s in VALID_SLOTS else "primary"

    @classmethod
    def _get_container_client(cls):
        if not AzureConfig.CONNECTION_STRING:
            raise ValueError("Azure storage connection string is missing")
        blob_service_client = BlobServiceClient.from_connection_string(AzureConfig.CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AzureConfig.CONTAINER_NAME)
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            try:
                blob_service_client.create_container(AzureConfig.CONTAINER_NAME)
            except AzureError as exc:
                logging.error("Could not create container %s: %s", AzureConfig.CONTAINER_NAME, exc)
                raise
            container_client = blob_service_client.get_container_client(AzureConfig.CONTAINER_NAME)
        return container_client

    @classmethod
    def _blob_client(cls, user_id: Optional[str], slot: Optional[str] = None):
        container_client = cls._get_container_client()
        normalized_id = cls._normalize_user_id(user_id)
        norm_slot = cls._normalize_slot(slot)
        blob_path = f"{cls.BLOB_PREFIX}/{normalized_id}/{norm_slot}.json"
        return container_client.get_blob_client(blob_path)

    @classmethod
    def _legacy_blob_client(cls, user_id: Optional[str]):
        """Blob client for the pre-slot legacy path: gmail/oauth/{user_id}.json."""
        container_client = cls._get_container_client()
        normalized_id = cls._normalize_user_id(user_id)
        blob_path = f"{cls.BLOB_PREFIX}/{normalized_id}.json"
        return container_client.get_blob_client(blob_path)

    @classmethod
    def _state_blob_client(cls, state: str):
        if not state or not isinstance(state, str) or not state.strip():
            raise ValueError("state is required")
        container_client = cls._get_container_client()
        safe_state = state.strip().replace("/", "_").replace("\\", "_")
        blob_path = f"{cls.STATE_PREFIX}/{safe_state}.json"
        return container_client.get_blob_client(blob_path)

    @classmethod
    def save_state(
        cls,
        state: str,
        user_id: Optional[str],
        slot: Optional[str] = None,
        metadata: Optional[Dict[str, object]] = None,
    ) -> None:
        blob_client = cls._state_blob_client(state)
        record = {
            "state": state,
            "user_id": cls._normalize_user_id(user_id),
            "slot": cls._normalize_slot(slot),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if value is None:
                    continue
                record[str(key)] = value
        blob_client.upload_blob(json.dumps(record, ensure_ascii=False).encode("utf-8"), overwrite=True)

    @classmethod
    def load_state(cls, state: str) -> Optional[Dict[str, object]]:
        blob_client = cls._state_blob_client(state)
        try:
            raw = blob_client.download_blob().readall().decode("utf-8")
            return json.loads(raw)
        except ResourceNotFoundError:
            return None
        except AzureError as exc:
            logging.error("Failed to load state %s: %s", state, exc)
            raise

    @classmethod
    def delete_state(cls, state: str) -> None:
        blob_client = cls._state_blob_client(state)
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            return
        except AzureError as exc:
            logging.error("Failed to delete state %s: %s", state, exc)
            raise

    @classmethod
    def save_tokens(cls, user_id: Optional[str], token_payload: Dict[str, object], slot: Optional[str] = None) -> None:
        blob_client = cls._blob_client(user_id, slot)
        record = dict(token_payload)
        now = datetime.now(timezone.utc)
        record["saved_at"] = now.isoformat()
        record["account_slot"] = cls._normalize_slot(slot)
        if expires_in := record.get("expires_in"):
            try:
                expiration = now + timedelta(seconds=int(expires_in))
                record["expires_at"] = expiration.isoformat()
            except (TypeError, ValueError):
                pass
        blob_client.upload_blob(json.dumps(record, ensure_ascii=False).encode("utf-8"), overwrite=True)

    @classmethod
    def load_tokens(cls, user_id: Optional[str], slot: Optional[str] = None) -> Optional[Dict[str, object]]:
        """Load tokens for the given slot. For 'primary', falls back to legacy path if slot path not found."""
        blob_client = cls._blob_client(user_id, slot)
        try:
            raw = blob_client.download_blob().readall().decode("utf-8")
            return json.loads(raw)
        except ResourceNotFoundError:
            # Legacy fallback for primary slot
            if cls._normalize_slot(slot) == "primary":
                try:
                    legacy_client = cls._legacy_blob_client(user_id)
                    raw = legacy_client.download_blob().readall().decode("utf-8")
                    return json.loads(raw)
                except ResourceNotFoundError:
                    return None
            return None
        except AzureError as exc:
            logging.error("Failed to load tokens for %s slot=%s: %s", user_id, slot, exc)
            raise

    @classmethod
    def delete_tokens(cls, user_id: Optional[str], slot: Optional[str] = None) -> None:
        blob_client = cls._blob_client(user_id, slot)
        try:
            blob_client.delete_blob()
        except ResourceNotFoundError:
            pass

    @classmethod
    def list_connected_accounts(cls, user_id: Optional[str]) -> list:
        """Return a list of connected account info dicts for all non-empty slots."""
        accounts = []
        for slot in VALID_SLOTS:
            tokens = cls.load_tokens(user_id, slot)
            if tokens:
                accounts.append({
                    "slot": slot,
                    "email_address": tokens.get("email_address"),
                    "saved_at": tokens.get("saved_at"),
                    "expires_at": tokens.get("expires_at"),
                    "has_calendar_scope": has_calendar_scope(tokens),
                })
        return accounts


def has_calendar_scope(token: "Optional[Dict]") -> bool:
    """Return True if the stored token includes the Google Calendar scope."""
    if not token:
        return False
    scope = str(token.get("scope") or "")
    return CALENDAR_SCOPE in scope
