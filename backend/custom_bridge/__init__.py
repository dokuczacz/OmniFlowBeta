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
from email.utils import getaddresses
from typing import Any, Dict, Tuple
from urllib.parse import quote

import azure.functions as func
import requests
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobServiceClient

from shared.config import AzureConfig
from shared.gmail_client import GmailClient
from shared.gmail_oauth import GmailOAuthConfig, GmailTokenStore
from shared.gmail_oauth import has_calendar_scope
from shared.user_profile import load_user_profile, upsert_gmail_identity


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


def _mail_extract_addresses(message_obj: Dict[str, Any], header_name: str) -> list[str]:
    header_value = _mail_extract_header(message_obj, header_name)
    if not header_value:
        return []
    parsed = getaddresses([header_value])
    out: list[str] = []
    for _, address in parsed:
        normalized = str(address or "").strip()
        if normalized:
            out.append(normalized)
    return out


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
    cc = payload.get("cc")
    if isinstance(cc, str) and cc.strip():
        email["Cc"] = cc.strip()
    elif isinstance(cc, list):
        cc_items = [str(item).strip() for item in cc if str(item).strip()]
        if cc_items:
            email["Cc"] = ", ".join(cc_items)
    bcc = payload.get("bcc")
    if isinstance(bcc, str) and bcc.strip():
        email["Bcc"] = bcc.strip()
    elif isinstance(bcc, list):
        bcc_items = [str(item).strip() for item in bcc if str(item).strip()]
        if bcc_items:
            email["Bcc"] = ", ".join(bcc_items)

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
    profile_name = str(payload.get("display_name") or payload.get("profile_name") or "").strip()
    GmailTokenStore.save_state(
        state,
        user_id,
        slot=account_slot,
        metadata={"display_name": profile_name} if profile_name else None,
    )
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


def handle_oauth_status(user_id: str, payload: Dict[str, Any], __: str | None = None) -> Dict[str, Any]:
    return _build_oauth_status(user_id, payload or {})


def _is_token_expired(stored: Dict[str, Any]) -> bool:
    """Return True if the stored token's expires_at is in the past."""
    expires_at = stored.get("expires_at")
    if not expires_at:
        return True
    try:
        from datetime import datetime, timezone
        exp = datetime.fromisoformat(str(expires_at))
        return exp <= datetime.now(timezone.utc)
    except (ValueError, TypeError):
        return True


def _build_reauth_response(
    user_id: str,
    account_slot: str,
    payload: Dict[str, Any],
    reason: str,
    *,
    include_reauth_link: bool = True,
) -> Dict[str, Any]:
    """Build a reauth-required response with a fresh authorize_url."""
    if include_reauth_link and not GmailOAuthConfig.has_credentials():
        raise ValueError("Gmail OAuth configuration is incomplete")
    result = {
        "action": "ensure_authorized",
        "authorized": False,
        "requires_reauth": True,
        "user_id": user_id,
        "account_slot": account_slot,
        "scope": GmailOAuthConfig.SCOPES,
        "reauth_reason": reason,
    }
    if include_reauth_link:
        reauth_state = str(uuid.uuid4())
        login_hint = payload.get("login_hint")
        profile_name = str(payload.get("display_name") or payload.get("profile_name") or "").strip()
        GmailTokenStore.save_state(
            reauth_state,
            user_id,
            slot=account_slot,
            metadata={"display_name": profile_name} if profile_name else None,
        )
        authorize_url = GmailOAuthConfig.authorize_url(reauth_state, login_hint=login_hint)
        result["state"] = reauth_state
        result["authorize_url"] = authorize_url
        result["authorization_url"] = authorize_url
        result["redirect_uri"] = GmailOAuthConfig.REDIRECT_URI
    return result


def _auth_success_response(
    user_id: str,
    account_slot: str,
    stored: Dict[str, Any],
    *,
    email_address: str | None = None,
    needs_reauth: bool = False,
    reauth_reason: str = "",
    payload: Dict[str, Any] | None = None,
    include_reauth_link: bool = True,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "action": "ensure_authorized",
        "authorized": True,
        "requires_reauth": bool(needs_reauth),
        "user_id": user_id,
        "account_slot": account_slot,
        "scope": stored.get("scope"),
        "expires_at": stored.get("expires_at"),
        "saved_at": stored.get("saved_at"),
        "has_calendar_scope": has_calendar_scope(stored),
    }
    if email_address:
        result["email_address"] = email_address
    profile = load_user_profile(user_id)
    display_name = str(profile.get("display_name") or "").strip()
    primary_email = str(profile.get("primary_email") or "").strip()
    if display_name:
        result["display_name"] = display_name
    if primary_email:
        result["primary_email"] = primary_email
    if needs_reauth and reauth_reason:
        result["reauth_reason"] = reauth_reason
        if include_reauth_link and GmailOAuthConfig.has_credentials():
            reauth_state = str(uuid.uuid4())
            login_hint = (payload or {}).get("login_hint")
            profile_name = str((payload or {}).get("display_name") or (payload or {}).get("profile_name") or "").strip()
            GmailTokenStore.save_state(
                reauth_state,
                user_id,
                slot=account_slot,
                metadata={"display_name": profile_name} if profile_name else None,
            )
            authorize_url = GmailOAuthConfig.authorize_url(reauth_state, login_hint=login_hint)
            result["reauth_state"] = reauth_state
            result["authorize_url"] = authorize_url
            result["authorization_url"] = authorize_url
            result["redirect_uri"] = GmailOAuthConfig.REDIRECT_URI
    return result


def _evaluate_auth_state(
    user_id: str,
    account_slot: str,
    payload: Dict[str, Any],
    *,
    include_reauth_link: bool = True,
) -> Dict[str, Any]:
    stored = GmailTokenStore.load_tokens(user_id, slot=account_slot)
    if not stored:
        return _build_reauth_response(user_id, account_slot, payload, reason="no_token", include_reauth_link=include_reauth_link)

    has_refresh = bool(str(stored.get("refresh_token") or "").strip())
    if _is_token_expired(stored) and not has_refresh:
        return _build_reauth_response(
            user_id,
            account_slot,
            payload,
            reason="token_expired_no_refresh",
            include_reauth_link=include_reauth_link,
        )

    email_address = str(stored.get("email_address") or "").strip() or None
    try:
        gmail = GmailClient(user_id, account_slot=account_slot)
        profile = gmail.request("get", "profile").json()
        email_address = str(profile.get("emailAddress") or "").strip() or email_address
        refreshed = GmailTokenStore.load_tokens(user_id, slot=account_slot) or stored
        stored = refreshed
        if email_address and str(stored.get("email_address") or "").strip() != email_address:
            stored = dict(stored)
            stored["email_address"] = email_address
            GmailTokenStore.save_tokens(user_id, stored, slot=account_slot)
            stored = GmailTokenStore.load_tokens(user_id, slot=account_slot) or stored
        if email_address:
            upsert_gmail_identity(
                user_id,
                account_slot,
                email_address,
                display_name=payload.get("display_name") or payload.get("profile_name"),
                has_calendar_scope=has_calendar_scope(stored),
            )
    except requests.HTTPError as exc:
        response = exc.response
        status_code = getattr(response, "status_code", None)
        response_url = str(getattr(response, "url", "") or "")
        if "oauth2.googleapis.com/token" in response_url:
            return _build_reauth_response(
                user_id,
                account_slot,
                payload,
                reason=f"refresh_http_{status_code or 'unknown'}",
                include_reauth_link=include_reauth_link,
            )
        if status_code in (401, 403):
            return _build_reauth_response(
                user_id,
                account_slot,
                payload,
                reason=f"profile_http_{status_code}",
                include_reauth_link=include_reauth_link,
            )
    except ValueError as exc:
        message = str(exc or "").strip()
        if message in {"Refresh token missing", "Access token missing from Gmail token store"}:
            return _build_reauth_response(
                user_id,
                account_slot,
                payload,
                reason=message.lower().replace(" ", "_"),
                include_reauth_link=include_reauth_link,
            )
    except requests.RequestException:
        pass
    except Exception:
        pass

    needs_reauth = not has_calendar_scope(stored)
    return _auth_success_response(
        user_id,
        account_slot,
        stored,
        email_address=email_address,
        needs_reauth=needs_reauth,
        reauth_reason="calendar_scope_missing" if needs_reauth else "",
        payload=payload,
        include_reauth_link=include_reauth_link,
    )


def _build_oauth_status(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    requested_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    account_results = []
    for slot in ("primary", "secondary"):
        status = _evaluate_auth_state(user_id, slot, payload, include_reauth_link=(slot == requested_slot))
        account_results.append(
            {
                "slot": slot,
                "authorized": bool(status.get("authorized")),
                "requires_reauth": bool(status.get("requires_reauth")),
                "reauth_reason": status.get("reauth_reason"),
                "email_address": status.get("email_address"),
                "saved_at": status.get("saved_at"),
                "expires_at": status.get("expires_at"),
                "has_calendar_scope": bool(status.get("has_calendar_scope")),
                **({"authorize_url": status.get("authorize_url")} if status.get("authorize_url") else {}),
                **({"authorization_url": status.get("authorization_url")} if status.get("authorization_url") else {}),
                **({"reauth_state": status.get("reauth_state")} if status.get("reauth_state") else {}),
                **({"redirect_uri": status.get("redirect_uri")} if status.get("redirect_uri") else {}),
            }
        )

    slot_status = next((item for item in account_results if item["slot"] == requested_slot), account_results[0] if account_results else {})
    profile = load_user_profile(user_id)
    display_name = str(profile.get("display_name") or "").strip()
    primary_email = str(profile.get("primary_email") or "").strip()
    return {
        "action": "oauth_status",
        "authorized": bool(slot_status.get("authorized")),
        "requires_reauth": bool(slot_status.get("requires_reauth")),
        "reauth_reason": slot_status.get("reauth_reason"),
        "user_id": user_id,
        "account_slot": requested_slot,
        "email_address": slot_status.get("email_address"),
        "saved_at": slot_status.get("saved_at"),
        "expires_at": slot_status.get("expires_at"),
        "has_calendar_scope": bool(slot_status.get("has_calendar_scope")),
        **({"authorize_url": slot_status.get("authorize_url")} if slot_status.get("authorize_url") else {}),
        **({"authorization_url": slot_status.get("authorization_url")} if slot_status.get("authorization_url") else {}),
        **({"reauth_state": slot_status.get("reauth_state")} if slot_status.get("reauth_state") else {}),
        **({"redirect_uri": slot_status.get("redirect_uri")} if slot_status.get("redirect_uri") else {}),
        **({"display_name": display_name} if display_name else {}),
        **({"primary_email": primary_email} if primary_email else {}),
        "accounts": account_results,
    }


def handle_ensure_authorized(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    if access_token:
        return {
            "action": "ensure_authorized",
            "authorized": True,
            "requires_reauth": False,
            "user_id": user_id,
            "scope": GmailOAuthConfig.SCOPES,
        }
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    force = bool(payload.get("force", False))
    if force:
        return _build_reauth_response(user_id, account_slot, payload, reason="force")
    return _evaluate_auth_state(user_id, account_slot, payload)


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
            "metadataHeaders": ["Reply-To", "From", "Sender", "To", "Subject", "Message-ID", "Message-Id", "In-Reply-To", "References"],
        },
    ).json()

    to_value = payload.get("to")
    if isinstance(to_value, str):
        to_list = [to_value]
    elif isinstance(to_value, list):
        to_list = [str(item).strip() for item in to_value if str(item).strip()]
    else:
        to_list = []
        for header_name in ("Reply-To", "From", "Sender", "To"):
            to_list = _mail_extract_addresses(original, header_name)
            if to_list:
                break
    if not to_list:
        raise ValueError("reply target could not be resolved for gmail_reply")

    original_subject = _mail_extract_header(original, "Subject")
    subject = str(payload.get("subject") or "").strip() or original_subject or "No Subject"
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    message_id_header = _mail_extract_header(original, "Message-ID") or _mail_extract_header(original, "In-Reply-To")
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


def handle_gmail_accounts_list(user_id: str, payload: Dict[str, Any], __: str | None = None) -> Dict[str, Any]:
    del payload
    profile = load_user_profile(user_id)
    result = {
        "action": "gmail_accounts_list",
        "user_id": user_id,
        "accounts": GmailTokenStore.list_connected_accounts(user_id),
    }
    display_name = str(profile.get("display_name") or "").strip()
    primary_email = str(profile.get("primary_email") or "").strip()
    if display_name:
        result["display_name"] = display_name
    if primary_email:
        result["primary_email"] = primary_email
    return result


def handle_gmail_list(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if max_results := payload.get("max_results"):
        params["maxResults"] = int(max_results)
    base_query = str(payload.get("q") or "").strip()
    category_value = str(payload.get("category") or "").strip()
    if category_value:
        normalized_category = category_value.lower()
        if normalized_category.startswith("category:"):
            normalized_category = normalized_category.split(":", 1)[1].strip()
        if normalized_category in {"primary", "social", "promotions", "updates", "forums"}:
            base_query = " ".join(part for part in (base_query, f"category:{normalized_category}") if part).strip()
    label_ids = payload.get("label_ids") or payload.get("labelIds") or payload.get("label")
    if isinstance(label_ids, str):
        label_ids = [item.strip() for item in label_ids.split(",")]
    if isinstance(label_ids, list):
        normalized_label_ids = [str(item).strip() for item in label_ids if str(item).strip()]
        if normalized_label_ids:
            params["labelIds"] = normalized_label_ids
    exclude_label_ids = payload.get("exclude_label_ids") or payload.get("excludeLabelIds")
    if isinstance(exclude_label_ids, str):
        exclude_label_ids = [item.strip() for item in exclude_label_ids.split(",")]
    if isinstance(exclude_label_ids, list):
        excluded = [str(item).strip() for item in exclude_label_ids if str(item).strip()]
        if excluded:
            query_parts = [base_query] if base_query else []
            for label_id in excluded:
                upper = label_id.upper()
                if upper == "SPAM":
                    query_parts.append("-in:spam")
                elif upper == "TRASH":
                    query_parts.append("-in:trash")
                elif upper == "INBOX":
                    query_parts.append("-in:inbox")
                elif upper == "SENT":
                    query_parts.append("-in:sent")
                elif upper == "DRAFT":
                    query_parts.append("-in:drafts")
                elif upper.startswith("CATEGORY_"):
                    query_parts.append(f"-category:{upper.removeprefix('CATEGORY_').lower()}")
                elif upper in {"PRIMARY", "SOCIAL", "PROMOTIONS", "UPDATES", "FORUMS"}:
                    if upper == "PRIMARY":
                        query_parts.append("-category:primary")
                    else:
                        query_parts.append(f"-category:{upper.lower()}")
                else:
                    query_parts.append(f"-label:{label_id}")
            params["q"] = " ".join(part for part in query_parts if part).strip()
    elif base_query:
        params["q"] = base_query
    if page_token := payload.get("page_token"):
        params["pageToken"] = page_token
    if payload.get("include_spam_trash") is not None:
        params["includeSpamTrash"] = bool(payload.get("include_spam_trash"))
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


def handle_gmail_search(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    result = handle_gmail_list(user_id, payload, access_token=access_token)
    result["action"] = "gmail_search"
    result["query"] = str(payload.get("q") or "").strip()
    return result


def _calendar_time_object(payload: Dict[str, Any], field_name: str) -> Dict[str, Any]:
    value = payload.get(field_name)
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key in ("dateTime", "date", "timeZone"):
            item = value.get(key)
            if item is not None and str(item).strip():
                out[key] = str(item).strip()
        return out

    def _tz() -> str:
        return str(
            payload.get(f"{field_name}_timeZone")
            or payload.get(f"{field_name}TimeZone")
            or payload.get(f"{field_name}_timezone")
            or payload.get("timeZone")
            or payload.get("time_zone")
            or ""
        ).strip()

    if isinstance(value, str) and value.strip():
        out = {"dateTime": value.strip()}
        tz = _tz()
        if tz:
            out["timeZone"] = tz
        return out

    for alias in (
        f"{field_name}_dateTime",
        f"{field_name}DateTime",
        f"{field_name}_datetime",
    ):
        candidate = payload.get(alias)
        if isinstance(candidate, str) and candidate.strip():
            out = {"dateTime": candidate.strip()}
            tz = _tz()
            if tz:
                out["timeZone"] = tz
            return out

    for alias in (
        f"{field_name}_date",
        f"{field_name}Date",
    ):
        candidate = payload.get(alias)
        if isinstance(candidate, str) and candidate.strip():
            out = {"date": candidate.strip()}
            tz = _tz()
            if tz:
                out["timeZone"] = tz
            return out

    return {}


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
    include_all_calendars = bool(payload.get("include_all_calendars", False))
    calendar_ids = payload.get("calendar_ids")
    if isinstance(calendar_ids, str):
        calendar_ids = [item.strip() for item in calendar_ids.split(",")]
    if not isinstance(calendar_ids, list):
        calendar_ids = []
    calendar_ids = [str(item).strip() for item in calendar_ids if str(item).strip()]

    if include_all_calendars and not calendar_ids:
        list_resp = gmail.calendar_request("get", "users/me/calendarList", params={"minAccessRole": "reader", "showHidden": True})
        calendars = list_resp.json().get("items", [])
        calendar_ids = [
            str(item.get("id") or "").strip()
            for item in calendars
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]

    if not calendar_ids:
        calendar_ids = ["primary"]

    events: list[dict] = []
    for calendar_id in calendar_ids:
        encoded_calendar_id = quote(calendar_id, safe="")
        resp = gmail.calendar_request("get", f"calendars/{encoded_calendar_id}/events", params=params)
        items = resp.json().get("items", [])
        for item in items:
            if isinstance(item, dict):
                enriched = dict(item)
                enriched.setdefault("calendarId", calendar_id)
                events.append(enriched)

    events.sort(key=lambda item: str((item or {}).get("start", {}).get("dateTime") or (item or {}).get("start", {}).get("date") or ""))
    return {
        "action": "calendar_list_events",
        "status": "ok",
        "account_slot": account_slot,
        "calendar_ids": calendar_ids,
        "events": events,
        "count": len(events),
        "include_all_calendars": include_all_calendars,
    }


def handle_calendar_list_calendars(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    params: Dict[str, Any] = {"showHidden": True}
    if payload.get("min_access_role"):
        params["minAccessRole"] = str(payload.get("min_access_role")).strip()
    resp = gmail.calendar_request("get", "users/me/calendarList", params=params)
    items = resp.json().get("items", [])
    calendars: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        calendars.append(
            {
                "id": str(item.get("id") or "").strip(),
                "summary": str(item.get("summary") or "").strip(),
                "primary": bool(item.get("primary", False)),
                "selected": bool(item.get("selected", False)),
                "accessRole": str(item.get("accessRole") or "").strip(),
                "timeZone": str(item.get("timeZone") or "").strip(),
                "backgroundColor": str(item.get("backgroundColor") or "").strip(),
            }
        )
    return {
        "action": "calendar_list_calendars",
        "status": "ok",
        "account_slot": account_slot,
        "calendars": calendars,
        "count": len(calendars),
    }


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
    event_body = {k: payload[k] for k in ("summary", "description", "attendees", "location", "recurrence") if k in payload}
    start = _calendar_time_object(payload, "start")
    end = _calendar_time_object(payload, "end")
    if start:
        event_body["start"] = start
    if end:
        event_body["end"] = end
    resp = gmail.calendar_request("post", "calendars/primary/events", json=event_body)
    created = resp.json()
    return {"action": "calendar_create_event", "status": "ok", "account_slot": account_slot, "event_id": created.get("id"), "event": created}


def handle_calendar_update_event(user_id: str, payload: Dict[str, Any], access_token: str | None = None) -> Dict[str, Any]:
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("event_id is required for calendar_update_event")
    account_slot = str(payload.get("account_slot") or "primary").strip() or "primary"
    gmail = GmailClient(user_id, access_token=access_token, account_slot=account_slot)
    patch_body = {k: payload[k] for k in ("summary", "description", "attendees", "location", "recurrence") if k in payload}
    start = _calendar_time_object(payload, "start")
    end = _calendar_time_object(payload, "end")
    if start:
        patch_body["start"] = start
    if end:
        patch_body["end"] = end
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
    "gmail_search": handle_gmail_search,
    "gmail_get": handle_gmail_get,
    "gmail_trash": handle_gmail_trash,
    "gmail_delete": handle_gmail_delete,
    "gmail_attachment": handle_gmail_attachment,
    "gmail_accounts_list": handle_gmail_accounts_list,
    "calendar_list_events": handle_calendar_list_events,
    "calendar_list_calendars": handle_calendar_list_calendars,
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
