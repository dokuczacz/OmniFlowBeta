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
from shared.gmail_oauth import has_calendar_scope


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


def _mail_extract_header(message_obj: Dict[str, Any], header_name: str) -> str:
    payload = message_obj.get("payload") if isinstance(message_obj, dict) else None
    headers = payload.get("headers") if isinstance(payload, dict) else None
    if not isinstance(headers, list):
        return ""
    target = str(header_name or "").strip().lower()
    for item in headers:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip().lower()
        if name == target:
            return str(item.get("value") or "").strip()
    return ""


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

    for header_name, header_value in (payload.get("extra_headers") or {}).items():
        if header_name and header_value:
            email[str(header_name)] = str(header_value)

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
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    GmailTokenStore.save_state(state, user_id, slot=account_slot)
    authorize_url = GmailOAuthConfig.authorize_url(state, login_hint=login_hint)
    return {
        "action": "oauth_authorize",
        "authorize_url": authorize_url,
        "state": state,
        "account_slot": account_slot,
        "scope": GmailOAuthConfig.SCOPES,
        "redirect_uri": GmailOAuthConfig.REDIRECT_URI,
    }


def handle_oauth_exchange(user_id: str, payload: Dict[str, Any], __: str | None = None) -> Dict[str, Any]:
    code = payload.get("code")
    if not code:
        raise ValueError("code is required for oauth_exchange")
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    token_payload = _exchange_code(code)
    GmailTokenStore.save_tokens(user_id, token_payload, slot=account_slot)
    return {
        "action": "oauth_exchange",
        "status": "authorized",
        "user_id": user_id,
        "account_slot": account_slot,
        "scope": token_payload.get("scope"),
        "expires_at": token_payload.get("expires_at"),
        "token_type": token_payload.get("token_type"),
    }


def handle_oauth_status(user_id: str, _: Dict[str, Any], __: str | None = None) -> Dict[str, Any]:
    accounts = GmailTokenStore.list_connected_accounts(user_id)
    if not accounts:
        return {"action": "oauth_status", "authorized": False, "user_id": user_id, "accounts": []}
    # Enrich with live profile if possible
    enriched = []
    for acc in accounts:
        slot = acc["slot"]
        email_address = acc.get("email_address")
        if not email_address:
            try:
                gmail = GmailClient(user_id, account_slot=slot)
                profile = gmail.request("get", "profile").json()
                email_address = profile.get("emailAddress")
            except Exception:
                pass
        enriched.append({**acc, "email_address": email_address})
    try:
        primary = next((a for a in enriched if a["slot"] == "primary"), enriched[0])
    except Exception:
        primary = {}
    return {
        "action": "oauth_status",
        "authorized": True,
        "user_id": user_id,
        "email_address": primary.get("email_address"),
        "accounts": enriched,
    }


def _is_token_expired(stored: Dict[str, Any]) -> bool:
    """Return True if the stored token's expires_at is in the past."""
    expires_at = stored.get("expires_at")
    if not expires_at:
        return False
    try:
        from datetime import datetime, timezone
        exp = datetime.fromisoformat(str(expires_at))
        return exp <= datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return False


def _build_reauth_response(user_id: str, account_slot: str, payload: Dict[str, Any], reason: str) -> Dict[str, Any]:
    """Build a reauth-required response with a fresh authorize_url."""
    if not GmailOAuthConfig.has_credentials():
        raise ValueError("Gmail OAuth configuration is incomplete")
    reauth_state = str(uuid.uuid4())
    login_hint = payload.get("login_hint")
    GmailTokenStore.save_state(reauth_state, user_id, slot=account_slot)
    return {
        "action": "ensure_authorized",
        "authorized": False,
        "user_id": user_id,
        "account_slot": account_slot,
        "scope": GmailOAuthConfig.SCOPES,
        "state": reauth_state,
        "authorize_url": GmailOAuthConfig.authorize_url(reauth_state, login_hint=login_hint),
        "redirect_uri": GmailOAuthConfig.REDIRECT_URI,
        "reauth_reason": reason,
    }


def handle_ensure_authorized(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    if access_token:
        return {
            "action": "ensure_authorized",
            "authorized": True,
            "user_id": user_id,
            "scope": GmailOAuthConfig.SCOPES,
        }
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    force = bool(payload.get("force", False))

    stored = GmailTokenStore.load_tokens(user_id, slot=account_slot)

    # Force reauth: discard stored token and generate fresh authorize_url
    if force or not stored:
        return _build_reauth_response(user_id, account_slot, payload, reason="force" if force else "no_token")

    # Expired with no refresh_token: cannot self-heal, must reauth
    has_refresh = bool(str(stored.get("refresh_token") or "").strip())
    if _is_token_expired(stored) and not has_refresh:
        return _build_reauth_response(user_id, account_slot, payload, reason="token_expired_no_refresh")

    # Probe token liveness via profile API (triggers refresh if expired but refresh_token present)
    email_address = None
    auth_failure = False
    auth_failure_reason = ""
    try:
        gmail = GmailClient(user_id, account_slot=account_slot)
        profile = gmail.request("get", "profile").json()
        email_address = profile.get("emailAddress")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code in (401, 403):
            auth_failure = True
            auth_failure_reason = f"profile_http_{exc.response.status_code}"
        # else: transient network error – keep authorized, don't block
    except Exception:
        pass  # transient or network error; keep existing authorized state

    if auth_failure:
        return _build_reauth_response(user_id, account_slot, payload, reason=auth_failure_reason)

    needs_reauth = not has_calendar_scope(stored)
    result: Dict[str, Any] = {
        "action": "ensure_authorized",
        "authorized": True,
        "user_id": user_id,
        "account_slot": account_slot,
        **({"email_address": email_address} if email_address else {}),
        "scope": stored.get("scope"),
        "expires_at": stored.get("expires_at"),
        "saved_at": stored.get("saved_at"),
    }
    if needs_reauth:
        result["needs_reauth"] = True
        result["needs_reauth_reason"] = "calendar_scope_missing"
        if GmailOAuthConfig.has_credentials():
            reauth_state = str(uuid.uuid4())
            login_hint = payload.get("login_hint")
            GmailTokenStore.save_state(reauth_state, user_id, slot=account_slot)
            result["authorize_url"] = GmailOAuthConfig.authorize_url(reauth_state, login_hint=login_hint)
            result["reauth_state"] = reauth_state
    return result


def handle_gmail_send(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    email = _build_email(payload)
    raw = base64.urlsafe_b64encode(email.as_bytes()).decode("ascii")
    audit_id = str(uuid.uuid4())
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    response = gmail.request("post", "messages/send", json={"raw": raw})
    result = response.json()
    return {
        "action": "gmail_send",
        "status": "sent",
        "user_id": user_id,
        "account_slot": account_slot,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId"),
        "audit_id": audit_id,
    }


def handle_gmail_reply(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    message_id = str(payload.get("message_id") or "").strip()
    body = str(payload.get("body") or "")
    if not message_id:
        raise ValueError("message_id is required for gmail_reply")
    if not body:
        raise ValueError("body is required for gmail_reply")

    audit_id = str(uuid.uuid4())
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    original = gmail.request(
        "get",
        f"messages/{message_id}",
        params={
            "format": "metadata",
            "metadataHeaders": ["Reply-To", "From", "Subject", "Message-ID", "References"],
        },
    ).json()

    to_value = payload.get("to")
    if isinstance(to_value, str):
        to_list = [to_value]
    elif isinstance(to_value, list):
        to_list = [str(item).strip() for item in to_value if str(item).strip()]
    else:
        reply_target = _mail_extract_header(original, "Reply-To") or _mail_extract_header(original, "From")
        to_list = [reply_target] if reply_target else []
    if not to_list:
        raise ValueError("reply target could not be resolved for gmail_reply")

    original_subject = _mail_extract_header(original, "Subject")
    subject = str(payload.get("subject") or "").strip() or original_subject or "No Subject"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message_id_header = _mail_extract_header(original, "Message-ID")
    references = _mail_extract_header(original, "References")
    merged_references = " ".join(part for part in (references, message_id_header) if part).strip()

    email = _build_email(
        {
            "to": to_list,
            "subject": subject,
            "body": body,
            "cc": list(payload.get("cc") or []),
            "bcc": list(payload.get("bcc") or []),
            "attachments": list(payload.get("attachments") or []),
            "from_address": payload.get("from_address") or "me",
            "extra_headers": {
                "In-Reply-To": message_id_header,
                "References": merged_references,
            },
        }
    )
    raw = base64.urlsafe_b64encode(email.as_bytes()).decode("ascii")
    send_payload: Dict[str, Any] = {"raw": raw}
    if original.get("threadId"):
        send_payload["threadId"] = original.get("threadId")
    response = gmail.request("post", "messages/send", json=send_payload)
    result = response.json()
    return {
        "action": "gmail_reply",
        "status": "sent",
        "user_id": user_id,
        "account_slot": account_slot,
        "message_id": result.get("id"),
        "thread_id": result.get("threadId") or original.get("threadId"),
        "reply_to_message_id": message_id,
        "audit_id": audit_id,
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
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    response = gmail.request("get", "messages", params=params)
    result = response.json()
    return {
        "action": "gmail_list",
        "status": "ok",
        "user_id": user_id,
        "account_slot": account_slot,
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
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    response = gmail.request("get", f"messages/{message_id}", params={"format": format_type})
    payload_response = response.json()
    return {
        "action": "gmail_get",
        "status": "ok",
        "account_slot": account_slot,
        "user_id": user_id,
        "message": payload_response,
    }


def handle_gmail_trash(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    message_id = payload.get("message_id")
    if not message_id:
        raise ValueError("message_id is required for gmail_trash")
    audit_id = str(uuid.uuid4())
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    response = gmail.request("post", f"messages/{message_id}/trash")
    payload_response = response.json()
    return {
        "action": "gmail_trash",
        "status": "ok",
        "user_id": user_id,
        "account_slot": account_slot,
        "message_id": payload_response.get("id") or message_id,
        "thread_id": payload_response.get("threadId"),
        "audit_id": audit_id,
    }


def handle_gmail_delete(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    message_id = payload.get("message_id")
    if not message_id:
        raise ValueError("message_id is required for gmail_delete")
    audit_id = str(uuid.uuid4())
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    gmail.request("delete", f"messages/{message_id}")
    return {
        "action": "gmail_delete",
        "status": "ok",
        "user_id": user_id,
        "account_slot": account_slot,
        "message_id": message_id,
        "audit_id": audit_id,
    }


def handle_gmail_attachment(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    message_id = payload.get("message_id")
    attachment_id = payload.get("attachment_id")
    if not message_id or not attachment_id:
        raise ValueError("message_id and attachment_id are required for gmail_attachment")
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    response = gmail.request("get", f"messages/{message_id}/attachments/{attachment_id}")
    payload_response = response.json()
    return {
        "action": "gmail_attachment",
        "status": "ok",
        "user_id": user_id,
        "attachment_id": attachment_id,
        "data": payload_response.get("data"),
    }


def handle_calendar_list_events(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    params: Dict[str, Any] = {"singleEvents": True, "orderBy": "startTime"}
    params["maxResults"] = int(payload.get("max_results") or 20)
    if payload.get("time_min"):
        params["timeMin"] = payload["time_min"]
    if payload.get("time_max"):
        params["timeMax"] = payload["time_max"]
    resp = gmail.calendar_request("get", "calendars/primary/events", params=params)
    items = resp.json().get("items", [])
    return {"action": "calendar_list_events", "status": "ok", "account_slot": account_slot, "events": items, "count": len(items)}


def handle_calendar_get_event(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("event_id is required for calendar_get_event")
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    resp = gmail.calendar_request("get", f"calendars/primary/events/{event_id}")
    return {"action": "calendar_get_event", "status": "ok", "account_slot": account_slot, "event": resp.json()}


def handle_calendar_create_event(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    event_body = {k: payload[k] for k in ("summary", "description", "start", "end", "attendees", "location", "recurrence") if k in payload}
    resp = gmail.calendar_request("post", "calendars/primary/events", json=event_body)
    created = resp.json()
    return {"action": "calendar_create_event", "status": "ok", "account_slot": account_slot, "event_id": created.get("id"), "event": created}


def handle_calendar_update_event(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("event_id is required for calendar_update_event")
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    patch_body = {k: payload[k] for k in ("summary", "description", "start", "end", "attendees", "location", "recurrence") if k in payload}
    resp = gmail.calendar_request("patch", f"calendars/primary/events/{event_id}", json=patch_body)
    return {"action": "calendar_update_event", "status": "ok", "account_slot": account_slot, "event": resp.json()}


def handle_calendar_delete_event(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("event_id is required for calendar_delete_event")
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    gmail.calendar_request("delete", f"calendars/primary/events/{event_id}")
    return {"action": "calendar_delete_event", "status": "ok", "account_slot": account_slot, "event_id": event_id}


ACTION_HANDLERS = {
    "oauth_authorize": handle_oauth_authorize,
    "oauth_exchange": handle_oauth_exchange,
    "oauth_status": handle_oauth_status,
    "ensure_authorized": handle_ensure_authorized,
    "gmail_send": handle_gmail_send,
    "gmail_reply": handle_gmail_reply,
    "gmail_list": handle_gmail_list,
    "gmail_get": handle_gmail_get,
    "gmail_trash": handle_gmail_trash,
    "gmail_delete": handle_gmail_delete,
    "gmail_attachment": handle_gmail_attachment,
    "gmail_accounts_list": lambda uid, pl, _: {
        "action": "gmail_accounts_list",
        "user_id": uid,
        "accounts": GmailTokenStore.list_connected_accounts(uid),
    },
    "calendar_list_events": handle_calendar_list_events,
    "calendar_get_event": handle_calendar_get_event,
    "calendar_create_event": handle_calendar_create_event,
    "calendar_update_event": handle_calendar_update_event,
    "calendar_delete_event": handle_calendar_delete_event,
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
