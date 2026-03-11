"""Helper wrapper for Gmail REST calls."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import requests

from .gmail_oauth import GmailOAuthConfig, GmailTokenStore, VALID_SLOTS


class GmailClient:
    BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"
    CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3"

    def __init__(self, user_id: str, *, access_token: Optional[str] = None, account_slot: Optional[str] = None):
        self.user_id = user_id
        self.account_slot = (account_slot or "primary").strip().lower()
        if self.account_slot not in VALID_SLOTS:
            self.account_slot = "primary"
        self._external_access_token = access_token.strip() if isinstance(access_token, str) and access_token.strip() else None
        self.tokens = GmailTokenStore.load_tokens(user_id, self.account_slot) if not self._external_access_token else None
        if not self._external_access_token and not self.tokens:
            raise ValueError("Gmail tokens not found for user")

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _expires_soon(self) -> bool:
        expires_at = self.tokens.get("expires_at")
        if not expires_at:
            return True
        try:
            expires = datetime.fromisoformat(expires_at)
        except ValueError:
            return True
        return expires - self._now() < timedelta(seconds=60)

    def _ensure_access_token(self) -> str:
        if self._external_access_token:
            return self._external_access_token
        if self._expires_soon():
            self._refresh_tokens()
        token = self.tokens.get("access_token")
        if not token:
            raise ValueError("Access token missing from Gmail token store")
        return token

    def _refresh_tokens(self) -> None:
        refresh_token = self.tokens.get("refresh_token")
        if not refresh_token:
            raise ValueError("Refresh token missing")
        payload = {
            "client_id": GmailOAuthConfig.CLIENT_ID,
            "client_secret": GmailOAuthConfig.CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        response = requests.post(GmailOAuthConfig.token_url(), data=payload, timeout=20)
        response.raise_for_status()
        refreshed = response.json()
        refreshed.setdefault("refresh_token", refresh_token)
        GmailTokenStore.save_tokens(self.user_id, refreshed, self.account_slot)
        self.tokens = GmailTokenStore.load_tokens(self.user_id, self.account_slot)

    def _headers(self) -> Dict[str, str]:
        token = self._ensure_access_token()
        return {"Authorization": f"Bearer {token}"}

    def request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None) -> requests.Response:
        url = f"{self.BASE_URL}/{path.lstrip('/')}"
        response = requests.request(method, url, params=params, json=json, headers=self._headers(), timeout=20)
        response.raise_for_status()
        return response

    def calendar_request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None) -> requests.Response:
        """Make a Google Calendar API v3 request using the same token as Gmail."""
        url = f"{self.CALENDAR_BASE_URL}/{path.lstrip('/')}"
        response = requests.request(method, url, params=params, json=json, headers=self._headers(), timeout=20)
        response.raise_for_status()
        return response
