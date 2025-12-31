"""
Azure Function that exposes Microsoft OAuth for the GPT email tool.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict
from datetime import datetime, timezone, timedelta

import azure.functions as func
import requests
from requests import RequestException

from shared.oauth_email import OAuthConfig, OAuthTokenStore


def _json_body(req: func.HttpRequest) -> Dict[str, Any]:
    try:
        return req.get_json()
    except ValueError:
        return {}


def _response(payload: Dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json"
    )


def _error(message: str, status_code: int = 400) -> func.HttpResponse:
    logging.warning("OAuth email error: %s (status=%s)", message, status_code)
    return _response({"error": message}, status_code=status_code)


def _user_id(req: func.HttpRequest, body: Dict[str, Any]) -> str:
    user_id = (
        req.headers.get("x-user-id")
        or req.params.get("user_id")
        or body.get("user_id")
    )
    return user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"


def _exchange_code(code: str) -> Dict[str, Any]:
    if not OAuthConfig.has_credentials():
        raise ValueError("Missing OAuth configuration to request tokens")
    data = {
        "client_id": OAuthConfig.CLIENT_ID,
        "client_secret": OAuthConfig.CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": OAuthConfig.REDIRECT_URI,
        "scope": OAuthConfig.SCOPES,
    }
    headers = {"Accept": "application/json"}
    response = requests.post(OAuthConfig.token_url(), data=data, headers=headers, timeout=20)
    response.raise_for_status()
    payload = response.json()
    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
    if expires := payload.get("expires_in"):
        try:
            expires_int = int(expires)
            payload["expires_at"] = (datetime.now(timezone.utc) + timedelta(seconds=expires_int)).isoformat()
        except (ValueError, TypeError):
            pass
    return payload


def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    action=authorize -> returns URL for user consent
    action=exchange -> trades code for tokens + stores them
    action=status   -> returns whether tokens exist for the user
    """
    body = _json_body(req)
    action = (
        req.params.get("action")
        or body.get("action")
        or ""
    ).strip().lower()
    if not action:
        return _error("Missing 'action' parameter")

    user_id = _user_id(req, body)

    if action == "authorize":
        if not OAuthConfig.has_credentials():
            return _error("OAuth tenant/client configuration is incomplete", status_code=500)
        state = str(uuid.uuid4())
        login_hint = req.params.get("login_hint") or body.get("login_hint")
        try:
            authorize_url = OAuthConfig.authorize_url(state, login_hint=login_hint)
        except ValueError as exc:
            return _error(str(exc), status_code=500)
        return _response({
            "authorize_url": authorize_url,
            "state": state,
            "scope": OAuthConfig.SCOPES,
            "redirect_uri": OAuthConfig.REDIRECT_URI
        })

    if action == "exchange":
        code = req.params.get("code") or body.get("code")
        if not code:
            return _error("Missing 'code' for OAuth exchange")
        try:
            token_payload = _exchange_code(code)
            OAuthTokenStore.save_tokens(user_id, token_payload)
        except RequestException as exc:
            logging.error("Token exchange failed: %s", exc)
            return _error("Failed to exchange authorization code", status_code=502)
        except Exception as exc:
            logging.error("Unable to persist OAuth token: %s", exc)
            return _error(str(exc), status_code=500)
        return _response({
            "status": "authorized",
            "user_id": user_id,
            "scope": token_payload.get("scope"),
            "expires_at": token_payload.get("expires_at"),
            "token_type": token_payload.get("token_type"),
        })

    if action == "status":
        try:
            stored = OAuthTokenStore.load_tokens(user_id)
        except Exception as exc:
            logging.error("Token store access failed for %s: %s", user_id, exc)
            return _error("Unable to read stored tokens", status_code=500)
        if not stored:
            return _response({"authorized": False, "user_id": user_id})
        return _response({
            "authorized": True,
            "user_id": user_id,
            "scope": stored.get("scope"),
            "expires_at": stored.get("expires_at"),
            "saved_at": stored.get("saved_at"),
        })

    return _error(f"Unknown action '{action}'")
