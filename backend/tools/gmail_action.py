"""
Gmail tool operations (in-process) backed by OAuth tokens stored in blob storage.

This intentionally mirrors the `custom_bridge` capabilities but is callable via
the tool registry + Responses tool loop.
"""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any, Dict

from shared.gmail_client import GmailClient
from shared.gmail_oauth import GmailTokenStore


def _status(user_id: str) -> Dict[str, Any]:
    tokens = GmailTokenStore.load_tokens(user_id)
    if not tokens:
        return {"authorized": False, "user_id": user_id}
    return {
        "authorized": True,
        "user_id": user_id,
        "scope": tokens.get("scope"),
        "expires_at": tokens.get("expires_at"),
        "saved_at": tokens.get("saved_at"),
    }


def _send(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    to = payload.get("to")
    if not to:
        raise ValueError("payload.to is required")
    subject = payload.get("subject") or "No Subject"
    body = payload.get("body") or ""

    msg = EmailMessage()
    msg["To"] = str(to)
    msg["From"] = payload.get("from_address") or "me"
    msg["Subject"] = str(subject)
    msg.set_content(str(body))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    gmail = GmailClient(user_id)
    resp = gmail.request("post", "messages/send", json={"raw": raw}).json()
    return {"status": "sent", "message_id": resp.get("id"), "thread_id": resp.get("threadId")}


def _list(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    params: Dict[str, Any] = {}
    if payload.get("max_results") is not None:
        params["maxResults"] = int(payload.get("max_results"))
    if payload.get("label"):
        params["labelIds"] = str(payload.get("label")).split(",")
    if payload.get("q"):
        params["q"] = str(payload.get("q"))
    if payload.get("page_token"):
        params["pageToken"] = str(payload.get("page_token"))

    gmail = GmailClient(user_id)
    resp = gmail.request("get", "messages", params=params).json()
    return {
        "status": "ok",
        "messages": resp.get("messages", []),
        "next_page_token": resp.get("nextPageToken"),
        "result_size_estimate": resp.get("resultSizeEstimate"),
    }


def _get(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    mid = payload.get("message_id")
    if not mid:
        raise ValueError("payload.message_id is required")
    fmt = payload.get("format") or "metadata"
    gmail = GmailClient(user_id)
    msg = gmail.request("get", f"messages/{mid}", params={"format": fmt}).json()
    return {"status": "ok", "message": msg}


def _trash(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    mid = payload.get("message_id")
    if not mid:
        raise ValueError("payload.message_id is required")
    gmail = GmailClient(user_id)
    msg = gmail.request("post", f"messages/{mid}/trash").json()
    return {"status": "trashed", "message_id": msg.get("id") or mid}


def _delete(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    mid = payload.get("message_id")
    if not mid:
        raise ValueError("payload.message_id is required")
    gmail = GmailClient(user_id)
    gmail.request("delete", f"messages/{mid}")
    return {"status": "deleted", "message_id": mid}


def gmail_action(args: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    action = str((args or {}).get("action") or "").strip().lower()
    payload = (args or {}).get("payload") or {}
    if not action:
        raise ValueError("action is required")
    if not isinstance(payload, dict):
        payload = {}

    if action == "oauth_status":
        return _status(user_id)
    if action == "gmail_send":
        return _send(user_id, payload)
    if action == "gmail_list":
        return _list(user_id, payload)
    if action == "gmail_get":
        return _get(user_id, payload)
    if action == "gmail_trash":
        return _trash(user_id, payload)
    if action == "gmail_delete":
        return _delete(user_id, payload)

    raise ValueError(f"Unknown action: {action}")

