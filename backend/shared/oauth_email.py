"""
Microsoft Graph OAuth helpers for GPT email integration.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from urllib.parse import urlencode

from azure.core.exceptions import ResourceNotFoundError, AzureError
from azure.storage.blob import BlobServiceClient

from .config import AzureConfig


class OAuthConfig:
    """Settings needed to perform the Microsoft identity OAuth flow."""

    TENANT_ID = os.environ.get("OAUTH_TENANT_ID", "").strip()
    CLIENT_ID = os.environ.get("OAUTH_CLIENT_ID", "").strip()
    CLIENT_SECRET = os.environ.get("OAUTH_CLIENT_SECRET", "").strip()
    REDIRECT_URI = os.environ.get(
        "OAUTH_REDIRECT_URI",
        "https://login.microsoftonline.com/common/oauth2/nativeclient"
    ).strip()
    SCOPES = os.environ.get(
        "OAUTH_SCOPES",
        "https://graph.microsoft.com/Mail.ReadWrite offline_access openid profile"
    ).strip()
    RESPONSE_MODE = os.environ.get("OAUTH_RESPONSE_MODE", "query").strip()
    PROMPT = os.environ.get("OAUTH_PROMPT", "consent").strip()

    @classmethod
    def has_credentials(cls) -> bool:
        return all([cls.TENANT_ID, cls.CLIENT_ID, cls.CLIENT_SECRET])

    @classmethod
    def authorize_url(cls, state: str, *, login_hint: Optional[str] = None) -> str:
        if not cls.has_credentials():
            raise ValueError("Missing OAuth tenant/client configuration")
        params = {
            "client_id": cls.CLIENT_ID,
            "response_type": "code",
            "response_mode": cls.RESPONSE_MODE,
            "redirect_uri": cls.REDIRECT_URI,
            "scope": cls.SCOPES,
            "prompt": cls.PROMPT,
            "state": state,
        }
        if login_hint:
            params["login_hint"] = login_hint
        query = urlencode({k: v for k, v in params.items() if v is not None})
        return f"https://login.microsoftonline.com/{cls.TENANT_ID}/oauth2/v2.0/authorize?{query}"

    @classmethod
    def token_url(cls) -> str:
        if not cls.TENANT_ID:
            raise ValueError("Missing OAUTH_TENANT_ID")
        return f"https://login.microsoftonline.com/{cls.TENANT_ID}/oauth2/v2.0/token"


class OAuthTokenStore:
    """Simple blob-backed token persistence for the GPT email helper."""

    BLOB_PREFIX = "gpt-email/oauth_tokens"

    @staticmethod
    def _normalize_user_id(user_id: str | None) -> str:
        if not user_id or not isinstance(user_id, str):
            return "default"
        return user_id.replace("/", "_").replace("\\", "_").strip() or "default"

    @classmethod
    def _blob_client(cls, user_id: str):
        if not AzureConfig.CONNECTION_STRING:
            raise ValueError("Missing Azure storage connection string")
        blob_service_client = BlobServiceClient.from_connection_string(AzureConfig.CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AzureConfig.CONTAINER_NAME)
        try:
            container_client.get_container_properties()
        except ResourceNotFoundError:
            try:
                container_client = blob_service_client.create_container(AzureConfig.CONTAINER_NAME)
            except AzureError as exc:
                logging.error("Unable to create container for OAuth tokens: %s", exc)
                raise
        normalized_id = cls._normalize_user_id(user_id)
        blob_path = f"{cls.BLOB_PREFIX}/{normalized_id}.json"
        return container_client.get_blob_client(blob_path)

    @classmethod
    def save_tokens(cls, user_id: str, token_payload: Dict[str, object]) -> None:
        client = cls._blob_client(user_id)
        record = dict(token_payload)
        now = datetime.now(timezone.utc).isoformat()
        record["saved_at"] = now
        if expires := record.get("expires_in"):
            try:
                expires_ts = datetime.now(timezone.utc) + timedelta(seconds=int(expires))
                record["expires_at"] = expires_ts.isoformat()
            except (TypeError, ValueError):
                pass
        client.upload_blob(json.dumps(record, ensure_ascii=False), overwrite=True)

    @classmethod
    def load_tokens(cls, user_id: str) -> Optional[Dict[str, object]]:
        client = cls._blob_client(user_id)
        try:
            data = client.download_blob().readall().decode("utf-8")
            return json.loads(data)
        except ResourceNotFoundError:
            return None
        except AzureError as exc:
            logging.error("Failed to read OAuth tokens for %s: %s", user_id, exc)
            raise
