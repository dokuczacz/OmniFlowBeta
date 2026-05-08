"""User profile storage for lightweight identity hints."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from azure.core.exceptions import ResourceNotFoundError

from .azure_client import AzureBlobClient


PROFILE_BLOB_NAME = "profile.json"
PROFILE_SCHEMA_VERSION = "omniflow.user_profile.v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sanitize_display_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:120]


def _default_display_name(user_id: str, email_address: str) -> str:
    local_part = str(email_address or "").split("@", 1)[0].strip()
    if local_part:
        return local_part[:120]
    fallback = str(user_id or "default").strip() or "default"
    return fallback[:120]


def default_profile(user_id: str) -> Dict[str, Any]:
    uid = str(user_id or "default").strip() or "default"
    now = _utc_now()
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "user_id": uid,
        "display_name": uid,
        "primary_email": "",
        "gmail": {"connected_accounts": {}},
        "created_utc": now,
        "updated_utc": now,
    }


def load_user_profile(user_id: str) -> Dict[str, Any]:
    uid = str(user_id or "default").strip() or "default"
    try:
        blob_client = AzureBlobClient.get_blob_client(PROFILE_BLOB_NAME, uid)
        raw = blob_client.download_blob().readall().decode("utf-8")
        profile = json.loads(raw)
    except ResourceNotFoundError:
        return default_profile(uid)
    except Exception:
        return default_profile(uid)
    if not isinstance(profile, dict):
        return default_profile(uid)
    profile.setdefault("schema_version", PROFILE_SCHEMA_VERSION)
    profile.setdefault("user_id", uid)
    profile.setdefault("display_name", uid)
    profile.setdefault("primary_email", "")
    gmail = profile.get("gmail")
    if not isinstance(gmail, dict):
        gmail = {}
        profile["gmail"] = gmail
    connected_accounts = gmail.get("connected_accounts")
    if not isinstance(connected_accounts, dict):
        gmail["connected_accounts"] = {}
    profile.setdefault("created_utc", _utc_now())
    profile["updated_utc"] = str(profile.get("updated_utc") or profile["created_utc"])
    return profile


def save_user_profile(user_id: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    uid = str(user_id or "default").strip() or "default"
    payload = dict(profile or {})
    payload["schema_version"] = PROFILE_SCHEMA_VERSION
    payload["user_id"] = uid
    if not payload.get("created_utc"):
        payload["created_utc"] = _utc_now()
    payload["updated_utc"] = _utc_now()
    try:
        blob_client = AzureBlobClient.get_blob_client(PROFILE_BLOB_NAME, uid)
        blob_client.upload_blob(json.dumps(payload, ensure_ascii=False).encode("utf-8"), overwrite=True)
    except Exception:
        return payload
    return payload


def upsert_gmail_identity(
    user_id: str,
    account_slot: str,
    email_address: str,
    *,
    display_name: Optional[str] = None,
    has_calendar_scope: Optional[bool] = None,
) -> Dict[str, Any]:
    uid = str(user_id or "default").strip() or "default"
    slot = str(account_slot or "primary").strip().lower() or "primary"
    email_value = str(email_address or "").strip().lower()
    profile = load_user_profile(uid)
    gmail = profile.setdefault("gmail", {})
    connected_accounts = gmail.setdefault("connected_accounts", {})
    existing_display_name = _sanitize_display_name(profile.get("display_name"))
    preferred_display_name = (
        _sanitize_display_name(display_name)
        or existing_display_name
        or _default_display_name(uid, email_value)
    )
    profile["display_name"] = preferred_display_name
    if slot == "primary" and email_value:
        profile["primary_email"] = email_value
    elif not str(profile.get("primary_email") or "").strip() and email_value:
        profile["primary_email"] = email_value

    account_entry: Dict[str, Any] = {
        "email_address": email_value,
        "linked_utc": _utc_now(),
    }
    if has_calendar_scope is not None:
        account_entry["has_calendar_scope"] = bool(has_calendar_scope)
    connected_accounts[slot] = account_entry
    return save_user_profile(uid, profile)
