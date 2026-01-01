"""
Unified bridge function for Gmail + GPT integration.
"""
from __future__ import annotations

import base64
import json
import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict, Tuple

import azure.functions as func
import requests
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig
from shared.gmail_client import GmailClient
from shared.gmail_oauth import GmailOAuthConfig, GmailTokenStore


def _parse_json(req: func.HttpRequest) -> Dict[str, Any]:
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
    logging.warning("custom_bridge error: %s", message)
    return _response({"status": "error", "message": message}, status_code=status_code)


def _resolve_user_id(body: Dict[str, Any]) -> str:
    user_id = (
        body.get("user_id")
        or body.get("payload", {}).get("user_id")
        or "default"
    )
    return user_id.strip() if isinstance(user_id, str) and user_id.strip() else "default"

def _bearer_token(req: func.HttpRequest) -> str | None:
    auth = req.headers.get("Authorization") or req.headers.get("authorization")
    if not auth or not isinstance(auth, str):
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts[0].lower(), parts[1].strip()
    if scheme != "bearer" or not token:
        return None
    return token


def _read_blob(blob_name: str) -> bytes:
    if not blob_name:
        raise ValueError("blob_name is required")
    if not AzureConfig.CONNECTION_STRING:
        raise ValueError("Azure storage connection string is missing")
    blob_service_client = BlobServiceClient.from_connection_string(AzureConfig.CONNECTION_STRING)
    container_client = blob_service_client.get_container_client(AzureConfig.CONTAINER_NAME)
    blob_client = container_client.get_blob_client(blob_name)
    try:
        return blob_client.download_blob().readall()
    except ResourceNotFoundError as exc:
        raise ValueError("Referenced blob not found") from exc


def _guess_mime(file_name: str) -> Tuple[str, str]:
    guess, _ = mimetypes.guess_type(file_name)
    if not guess:
        return "application", "octet-stream"
    maintype, subtype = guess.split("/", 1)
    return maintype, subtype


def _build_email(payload: Dict[str, Any]) -> EmailMessage:
    to = payload.get("to")
    if not to:
        raise ValueError("Recipient 'to' is required")
    subject = payload.get("subject") or "No Subject"
    body = payload.get("body") or ""
    from_address = payload.get("from_address") or "me"

    email = EmailMessage()
    email["Subject"] = subject
    if isinstance(to, str):
        email["To"] = to
    else:
        email["To"] = ", ".join(to)
    email["From"] = from_address
    email.set_content(body)

    for attachment in payload.get("attachments") or []:
        file_name = attachment.get("fileName")
        if not file_name:
            logging.warning("Skipping attachment without fileName")
            continue
        content = None
        if encoded := attachment.get("contentBase64"):
            content = base64.b64decode(encoded)
        elif blob_name := attachment.get("blob_name"):
            content = _read_blob(blob_name)
        if not content:
            continue
        maintype, subtype = _guess_mime(file_name)
        email.add_attachment(content, maintype=maintype, subtype=subtype, filename=file_name)

    return email


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
    except requests.HTTPError as exc:  # surface Google error details for diagnostics
        status = exc.response.status_code if exc.response else "n/a"
        body = exc.response.text if exc.response else ""
        logging.error("Token exchange failed (status=%s): %s", status, body)
        # bubble a trimmed message so callback returns 400 instead of 500
        raise ValueError(f"Token exchange failed (status={status})") from exc


def handle_oauth_authorize(user_id: str, payload: Dict[str, Any], __: str | None = None) -> Dict[str, Any]:
    if not GmailOAuthConfig.has_credentials():
        raise ValueError("Gmail OAuth configuration is incomplete")
    state = str(uuid.uuid4())
    login_hint = payload.get("login_hint")
    GmailTokenStore.save_state(state, user_id)
    authorize_url = GmailOAuthConfig.authorize_url(state, login_hint=login_hint)
    return {
        "action": "oauth_authorize",
        "authorize_url": authorize_url,
        "state": state,
        "scope": GmailOAuthConfig.SCOPES,
        "redirect_uri": GmailOAuthConfig.REDIRECT_URI,
    }


def handle_oauth_exchange(user_id: str, payload: Dict[str, Any], __: str | None = None) -> Dict[str, Any]:
    code = payload.get("code")
    if not code:
        raise ValueError("code is required for oauth_exchange")
    token_payload = _exchange_code(code)
    GmailTokenStore.save_tokens(user_id, token_payload)
    return {
        "action": "oauth_exchange",
        "status": "authorized",
        "user_id": user_id,
        "scope": token_payload.get("scope"),
        "expires_at": token_payload.get("expires_at"),
        "token_type": token_payload.get("token_type"),
    }


def handle_oauth_status(user_id: str, _: Dict[str, Any], __: str | None = None) -> Dict[str, Any]:
    stored = GmailTokenStore.load_tokens(user_id)
    if not stored:
        return {
            "action": "oauth_status",
            "authorized": False,
            "user_id": user_id,
        }
    return {
        "action": "oauth_status",
        "authorized": True,
        "user_id": user_id,
        "scope": stored.get("scope"),
        "expires_at": stored.get("expires_at"),
        "saved_at": stored.get("saved_at"),
    }


def handle_ensure_authorized(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    if access_token:
        return {
            "action": "ensure_authorized",
            "authorized": True,
            "user_id": user_id,
            "scope": GmailOAuthConfig.SCOPES,
        }
    stored = GmailTokenStore.load_tokens(user_id)
    if stored:
        return {
            "action": "ensure_authorized",
            "authorized": True,
            "user_id": user_id,
            "scope": stored.get("scope"),
            "expires_at": stored.get("expires_at"),
            "saved_at": stored.get("saved_at"),
        }
    if not GmailOAuthConfig.has_credentials():
        raise ValueError("Gmail OAuth configuration is incomplete")
    state = str(uuid.uuid4())
    login_hint = payload.get("login_hint")
    GmailTokenStore.save_state(state, user_id)
    authorize_url = GmailOAuthConfig.authorize_url(state, login_hint=login_hint)
    return {
        "action": "ensure_authorized",
        "authorized": False,
        "user_id": user_id,
        "scope": GmailOAuthConfig.SCOPES,
        "state": state,
        "authorize_url": authorize_url,
        "redirect_uri": GmailOAuthConfig.REDIRECT_URI,
    }


def handle_gmail_send(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    email = _build_email(payload)
    raw = base64.urlsafe_b64encode(email.as_bytes()).decode("ascii")
    gmail = GmailClient(user_id, access_token=access_token)
    response = gmail.request("post", "messages/send", json={"raw": raw})
    result = response.json()
    return {
        "action": "gmail_send",
        "status": "sent",
        "user_id": user_id,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
    }


def handle_gmail_list(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if max_results := payload.get("max_results"):
        params["maxResults"] = int(max_results)
    if label := payload.get("label"):
        params["labelIds"] = label.split(",")
    if query := payload.get("q"):
        params["q"] = query
    if page_token := payload.get("page_token"):
        params["pageToken"] = page_token
    gmail = GmailClient(user_id, access_token=access_token)
    response = gmail.request("get", "messages", params=params)
    result = response.json()
    return {
        "action": "gmail_list",
        "status": "ok",
        "user_id": user_id,
        "messages": result.get("messages", []),
        "next_page_token": result.get("nextPageToken"),
        "result_size_estimate": result.get("resultSizeEstimate"),
    }


def handle_gmail_get(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    message_id = payload.get("message_id")
    if not message_id:
        raise ValueError("message_id is required for gmail_get")
    format_type = payload.get("format") or "full"
    if format_type not in {"minimal", "full", "metadata", "raw"}:
        raise ValueError("format must be one of minimal|full|metadata|raw")
    gmail = GmailClient(user_id, access_token=access_token)
    response = gmail.request("get", f"messages/{message_id}", params={"format": format_type})
    payload_response = response.json()
    return {
        "action": "gmail_get",
        "status": "ok",
        "user_id": user_id,
        "message": payload_response,
    }


def handle_gmail_attachment(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    message_id = payload.get("message_id")
    attachment_id = payload.get("attachment_id")
    if not message_id or not attachment_id:
        raise ValueError("message_id and attachment_id are required for gmail_attachment")
    gmail = GmailClient(user_id, access_token=access_token)
    response = gmail.request("get", f"messages/{message_id}/attachments/{attachment_id}")
    payload_response = response.json()
    return {
        "action": "gmail_attachment",
        "status": "ok",
        "user_id": user_id,
        "attachment_id": attachment_id,
        "data": payload_response.get("data"),
    }


ACTION_HANDLERS = {
    "oauth_authorize": handle_oauth_authorize,
    "oauth_exchange": handle_oauth_exchange,
    "oauth_status": handle_oauth_status,
    "ensure_authorized": handle_ensure_authorized,
    "gmail_send": handle_gmail_send,
    "gmail_list": handle_gmail_list,
    "gmail_get": handle_gmail_get,
    "gmail_attachment": handle_gmail_attachment,
}


def main(req: func.HttpRequest) -> func.HttpResponse:
    body = _parse_json(req)
    action = (body.get("action") or "").strip().lower()
    if not action:
        return _error("Missing 'action' field")
    handler = ACTION_HANDLERS.get(action)
    if not handler:
        return _error(f"Unknown action '{action}'")
    user_id = _resolve_user_id(body)
    access_token = _bearer_token(req)
    payload = body.get("payload", {})
    try:
        result = handler(user_id, payload, access_token)
    except ValueError as exc:
        return _error(str(exc))
    except Exception as exc:
        logging.error("custom_bridge action %s failed: %s", action, exc, exc_info=True)
        return _error("Internal error", status_code=500)
    return _response({"status": "ok", "action": action, "result": result})
