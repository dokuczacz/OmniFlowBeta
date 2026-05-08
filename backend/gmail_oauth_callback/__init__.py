"""
OAuth redirect endpoint for Gmail (used by custom_bridge via Google consent).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import azure.functions as func
import requests

from shared.gmail_oauth import GmailOAuthConfig, GmailTokenStore
from shared.gmail_client import GmailClient
from shared.azure_client import AzureBlobClient
from shared.gmail_oauth import has_calendar_scope
from shared.user_profile import upsert_gmail_identity


def _response(payload: Dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _html(message: str, status_code: int = 200) -> func.HttpResponse:
    body = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Gmail OAuth</title></head>
<body>
<h2>{message}</h2>
<p>You may now return to ChatGPT and proceed.</p>
</body>
</html>"""
    return func.HttpResponse(body, status_code=status_code, mimetype="text/html")


def _exchange_code(code: str) -> Dict[str, Any]:
    payload = {
        "client_id": GmailOAuthConfig.CLIENT_ID,
        "client_secret": GmailOAuthConfig.CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": GmailOAuthConfig.REDIRECT_URI,
    }
    headers = {"Accept": "application/json"}
    try:
        response = requests.post(GmailOAuthConfig.token_url(), data=payload, headers=headers, timeout=20)
        response.raise_for_status()
        data = response.json()
        data["fetched_at"] = datetime.now(timezone.utc).isoformat()
        return data
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response else "n/a"
        body = exc.response.text if exc.response else ""
        logging.error("Token exchange failed (status=%s): %s", status, body)
        raise ValueError(f"Token exchange failed (status={status})") from exc


def main(req: func.HttpRequest) -> func.HttpResponse:
    error = req.params.get("error")
    if error:
        return _html(f"OAuth failed: {error}", status_code=400)

    state = req.params.get("state")
    code = req.params.get("code")
    if not state or not code:
        return _html("Missing 'state' or 'code' query parameter", status_code=400)

    state_record = GmailTokenStore.load_state(state)
    if not state_record:
        return _html("Unknown or expired 'state'", status_code=400)
    user_id = str(state_record.get("user_id") or "default").strip() or "default"
    account_slot = str(state_record.get("slot") or "primary").strip() or "primary"

    try:
        token_payload = _exchange_code(code)
        GmailTokenStore.save_tokens(user_id, token_payload, slot=account_slot)
        GmailTokenStore.delete_state(state)
    except ValueError as exc:
        return _html(str(exc), status_code=400)
    except Exception as exc:
        logging.error("gmail_oauth_callback failed: %s", exc, exc_info=True)
        return _html("Internal error", status_code=500)

    _try_attach_gmail_identity(user_id, account_slot, state_record)
    _try_prefetch_inbox(user_id, account_slot)
    return _html("OAuth completed successfully", status_code=200)


def _try_attach_gmail_identity(user_id: str, account_slot: str, state_record: Dict[str, Any]) -> None:
    try:
        gmail = GmailClient(user_id, account_slot=account_slot)
        profile = gmail.request("get", "profile").json()
        email_address = str(profile.get("emailAddress") or "").strip().lower()
        if not email_address:
            return
        stored = GmailTokenStore.load_tokens(user_id, slot=account_slot) or {}
        if str(stored.get("email_address") or "").strip().lower() != email_address:
            updated = dict(stored)
            updated["email_address"] = email_address
            GmailTokenStore.save_tokens(user_id, updated, slot=account_slot)
            stored = GmailTokenStore.load_tokens(user_id, slot=account_slot) or updated
        upsert_gmail_identity(
            user_id,
            account_slot,
            email_address,
            display_name=state_record.get("display_name"),
            has_calendar_scope=has_calendar_scope(stored),
        )
    except Exception as exc:
        logging.warning("gmail_oauth_callback: profile sync failed (non-blocking): %s", exc)


def _try_prefetch_inbox(user_id: str, account_slot: str) -> None:
    """Non-blocking: fetch 20 inbox messages and cache to users/{user_id}/mail/inbox_cache.json."""
    try:
        gmail = GmailClient(user_id, account_slot=account_slot)
        result = gmail.request("get", "messages", params={"maxResults": 20, "labelIds": ["INBOX"]})
        messages = result.json().get("messages", [])
        cache = {
            "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat() + "Z",
            "account_slot": account_slot,
            "messages": messages,
            "count": len(messages),
        }
        blob_client = AzureBlobClient.get_blob_client("mail/inbox_cache.json", user_id)
        blob_client.upload_blob(
            json.dumps(cache, ensure_ascii=False).encode("utf-8"),
            overwrite=True,
        )
        logging.info("gmail_oauth_callback: inbox prefetch saved %d messages for %s/%s", len(messages), user_id, account_slot)
    except Exception as exc:
        logging.warning("gmail_oauth_callback: inbox prefetch failed (non-blocking): %s", exc)
