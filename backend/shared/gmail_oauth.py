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


class GmailOAuthConfig:
    CLIENT_ID = os.environ.get("GMAIL_OAUTH_CLIENT_ID", "").strip()
    CLIENT_SECRET = os.environ.get("GMAIL_OAUTH_CLIENT_SECRET", "").strip()
    REDIRECT_URI = os.environ.get("GMAIL_OAUTH_REDIRECT_URI", "").strip()
    SCOPES = os.environ.get("GMAIL_OAUTH_SCOPES", "https://mail.google.com/").strip()
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
    """Persist Gmail OAuth payloads in blob storage for each user."""

    BLOB_PREFIX = "gmail/oauth"
    STATE_PREFIX = "gmail/state"

    @staticmethod
    def _normalize_user_id(user_id: Optional[str]) -> str:
        if not user_id or not isinstance(user_id, str):
            return "default"
        normalized = user_id.strip().replace("/", "_").replace("\\", "_") or "default"
        return normalized

    @classmethod
    def _blob_client(cls, user_id: Optional[str]):
        normalized_id = cls._normalize_user_id(user_id)
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
        blob_path = f"{cls.BLOB_PREFIX}/{normalized_id}.json"
        return container_client.get_blob_client(blob_path)

    @classmethod
    def _state_blob_client(cls, state: str):
        if not state or not isinstance(state, str) or not state.strip():
            raise ValueError("state is required")
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
        safe_state = state.strip().replace("/", "_").replace("\\", "_")
        blob_path = f"{cls.STATE_PREFIX}/{safe_state}.json"
        return container_client.get_blob_client(blob_path)

    @classmethod
    def save_state(cls, state: str, user_id: Optional[str]) -> None:
        blob_client = cls._state_blob_client(state)
        record = {
            "state": state,
            "user_id": cls._normalize_user_id(user_id),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
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
    def save_tokens(cls, user_id: Optional[str], token_payload: Dict[str, object]) -> None:
        blob_client = cls._blob_client(user_id)
        record = dict(token_payload)
        now = datetime.now(timezone.utc)
        record["saved_at"] = now.isoformat()
        if expires_in := record.get("expires_in"):
            try:
                expiration = now + timedelta(seconds=int(expires_in))
                record["expires_at"] = expiration.isoformat()
            except (TypeError, ValueError):
                pass
        blob_client.upload_blob(json.dumps(record, ensure_ascii=False).encode("utf-8"), overwrite=True)

    @classmethod
    def load_tokens(cls, user_id: Optional[str]) -> Optional[Dict[str, object]]:
        blob_client = cls._blob_client(user_id)
        try:
            raw = blob_client.download_blob().readall().decode("utf-8")
            return json.loads(raw)
        except ResourceNotFoundError:
            return None
        except AzureError as exc:
            logging.error("Failed to load tokens for %s: %s", user_id, exc)
            raise
