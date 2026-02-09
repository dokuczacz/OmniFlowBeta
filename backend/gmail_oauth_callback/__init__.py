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


def _response(payload: Dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


def _html(message: str, status_code: int = 200, *, success: bool = False) -> func.HttpResponse:
    # On success, notify the opener window and auto-close the popup.
    if success:
        body = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Gmail OAuth</title></head>
<body>
<h2>OAuth completed successfully</h2>
<p>This window will close automatically.</p>
<script>
try { window.opener && window.opener.postMessage({type:"gmail_oauth_complete"}, "*"); } catch(e) {}
setTimeout(function(){ window.close(); }, 600);
</script>
</body>
</html>"""
    else:
        body = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Gmail OAuth</title></head>
<body>
<h2>{message}</h2>
<p>You may close this window and try again.</p>
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

    try:
        token_payload = _exchange_code(code)
        GmailTokenStore.save_tokens(user_id, token_payload)
        GmailTokenStore.delete_state(state)
    except ValueError as exc:
        return _html(str(exc), status_code=400)
    except Exception as exc:
        logging.error("gmail_oauth_callback failed: %s", exc, exc_info=True)
        return _html("Internal error", status_code=500)

    return _html("OAuth completed successfully", status_code=200, success=True)
