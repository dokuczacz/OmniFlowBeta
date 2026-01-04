from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from shiny import App, reactive, render, ui


DEFAULT_BACKEND_URL = "http://localhost:7071/api/tool_call_handler"
USERS_ENV = "UI_USERS_JSON"
ENV_DEV_URL = "BACKEND_URL_DEV"
ENV_PROD_URL = "BACKEND_URL_PROD"
ENV_UI_ENV = "UI_ENV"


def normalize_user_id(value: str) -> str:
    if not value:
        return ""
    cleaned = str(value).strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        return ""
    return cleaned


def load_users_map() -> Dict[str, str]:
    raw = (os.environ.get(USERS_ENV) or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: Dict[str, str] = {}
    for k, v in parsed.items():
        if isinstance(k, str) and isinstance(v, str):
            out[k.strip()] = v.strip()
    return out


def _b64decode(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


def verify_password(password: str, stored: str) -> bool:
    # Format: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
    try:
        algo, iters_s, salt_b64, hash_b64 = stored.split("$", 3)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    try:
        iterations = int(iters_s)
        if iterations < 10_000 or iterations > 2_000_000:
            return False
        salt = _b64decode(salt_b64)
        expected = _b64decode(hash_b64)
    except Exception:
        return False
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(derived, expected)


def extract_assistant_text(payload: Any) -> str:
    if isinstance(payload, dict):
        if payload.get("message"):
            return str(payload["message"])
        response = payload.get("response")
        if isinstance(response, str):
            try:
                parsed = json.loads(response)
                if isinstance(parsed, dict) and parsed.get("message"):
                    return str(parsed["message"])
            except Exception:
                return response
            return response
        if isinstance(response, dict) and response.get("message"):
            return str(response["message"])
    if isinstance(payload, str):
        return payload
    return "(No response)"


def tool_call_handler_request(
    *,
    backend_url: str,
    user_id: str,
    message: str,
    thread_id: Optional[str],
) -> Tuple[Dict[str, Any], float]:
    headers = {"Content-Type": "application/json", "X-User-Id": user_id}
    payload: Dict[str, Any] = {"message": message, "runtime": "responses"}
    if thread_id:
        payload["thread_id"] = thread_id
    start = time.time()
    resp = requests.post(backend_url, json=payload, headers=headers, timeout=60)
    elapsed_ms = (time.time() - start) * 1000.0
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("Backend response is not a JSON object.")
    return data, elapsed_ms


app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.h3("OmniFlow PA"),
        ui.input_select(
            "env",
            "Environment",
            choices=["prod", "dev"],
            selected=str(os.environ.get(ENV_UI_ENV) or "prod").strip().lower() or "prod",
        ),
        ui.input_text(
            "backend_url",
            "Backend URL override (optional)",
            value=str(os.environ.get("BACKEND_URL") or "").strip(),
            placeholder=DEFAULT_BACKEND_URL,
        ),
        ui.output_text("effective_backend_label"),
        ui.hr(),
        ui.h4("Login"),
        ui.input_text("login_user_id", "User ID", placeholder="MarioBros"),
        ui.input_password("login_password", "Password"),
        ui.input_action_button("login_btn", "Login", class_="btn-primary"),
        ui.input_action_button("logout_btn", "Logout"),
        ui.output_text("login_status"),
        ui.hr(),
        ui.h4("Session"),
        ui.output_text("active_user_label"),
        ui.output_text("active_thread_label"),
        ui.output_text("last_latency_label"),
    ),
    ui.tags.style(
        """
        body { background: #0d1117; color: #e6edf3; }
        .sidebar { background: #0d1117; }
        .chat-history {
            max-height: 55vh;
            overflow-y: auto;
            padding: 10px;
            border: 1px solid #30363d;
            border-radius: 10px;
            background: #0d1117;
            margin-bottom: 12px;
        }
        .bubble {
            padding: 10px 12px;
            border-radius: 10px;
            margin-bottom: 8px;
            border: 1px solid #30363d;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .bubble-user { background: #1f6feb; color: #ffffff; border-color: #1f6feb; }
        .bubble-assistant { background: #161b22; color: #e6edf3; }
        .muted { color: #8b949e; font-size: 0.9em; }
        """
    ),
    ui.navset_tab(
        ui.nav(
            "Chat",
            ui.output_ui("chat_history"),
            ui.div(
                ui.input_text_area("chat_input", "Message", placeholder="Type a message..."),
                ui.input_action_button("send_btn", "Send"),
            ),
            ui.output_text("chat_error"),
        ),
        ui.nav(
            "Runs / Reports",
            ui.h4("Last response"),
            ui.output_text_verbatim("last_backend_json"),
        ),
        ui.nav(
            "Agent Control",
            ui.p("Placeholder - will map UI presets to backend runtime later (WP6/WP2 Phase 2)."),
        ),
        id="main_tabs",
    ),
    title="OmniFlow PA (Shiny)",
)


def server(input, output, session):
    users_map = load_users_map()

    active_user = reactive.Value("")  # user_id
    active_thread_id = reactive.Value("")  # thread_id (conversation handle)
    login_error = reactive.Value("")
    chat_error = reactive.Value("")
    last_backend_data = reactive.Value({})  # dict
    last_latency_ms = reactive.Value(None)  # float | None

    history: reactive.Value[List[Dict[str, str]]] = reactive.Value([])

    def _effective_backend_url() -> str:
        override = str(input.backend_url() or "").strip()
        if override:
            return override
        env_choice = str(input.env() or "prod").strip().lower()
        if env_choice == "dev":
            dev = str(os.environ.get(ENV_DEV_URL) or "").strip()
            if dev:
                return dev
        prod = str(os.environ.get(ENV_PROD_URL) or "").strip()
        if prod:
            return prod
        return DEFAULT_BACKEND_URL

    @output
    @render.text
    def effective_backend_label():
        url = _effective_backend_url()
        return f"Effective backend: {url}"

    @reactive.effect
    @reactive.event(input.logout_btn)
    def _logout():
        active_user.set("")
        active_thread_id.set("")
        history.set([])
        last_backend_data.set({})
        last_latency_ms.set(None)
        login_error.set("")
        chat_error.set("")

    @reactive.effect
    @reactive.event(input.login_btn)
    def _login():
        login_error.set("")
        raw_user = normalize_user_id(input.login_user_id())
        password = str(input.login_password() or "")

        if not users_map:
            login_error.set(f"Missing {USERS_ENV} env var or invalid JSON.")
            return
        if not raw_user:
            login_error.set("Invalid user_id.")
            return
        stored = users_map.get(raw_user)
        if not stored:
            login_error.set("Unknown user_id (not present in UI_USERS_JSON).")
            return
        if not verify_password(password, stored):
            login_error.set("Invalid password.")
            return

        active_user.set(raw_user)
        chat_error.set("")

    @output
    @render.text
    def login_status():
        if active_user.get():
            return "OK: logged in"
        if login_error.get():
            return f"ERROR: {login_error.get()}"
        return "Not logged in"

    @output
    @render.text
    def active_user_label():
        user = active_user.get() or "(none)"
        return f"Active user: {user}"

    @output
    @render.text
    def active_thread_label():
        tid = active_thread_id.get() or "(none)"
        return f"Thread: {tid}"

    @output
    @render.text
    def last_latency_label():
        v = last_latency_ms.get()
        if v is None:
            return "Last latency: (none)"
        return f"Last latency: {v:.0f} ms"

    def _append(role: str, content: str) -> None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        items = list(history.get())
        items.append({"role": role, "content": content, "timestamp": ts})
        history.set(items)

    @reactive.effect
    @reactive.event(input.send_btn)
    def _send():
        chat_error.set("")
        user = active_user.get()
        if not user:
            chat_error.set("Login required.")
            return
        msg = str(input.chat_input() or "").strip()
        if not msg:
            chat_error.set("Empty message.")
            return
        backend_url = _effective_backend_url()

        _append("user", msg)
        try:
            data, elapsed_ms = tool_call_handler_request(
                backend_url=backend_url,
                user_id=user,
                message=msg,
                thread_id=active_thread_id.get() or None,
            )
            last_backend_data.set(data)
            last_latency_ms.set(elapsed_ms)
            if isinstance(data.get("thread_id"), str) and data["thread_id"]:
                active_thread_id.set(data["thread_id"])
            _append("assistant", extract_assistant_text(data))
        except Exception as exc:
            chat_error.set(str(exc))
            _append("assistant", f"(Error) {exc}")

    @output
    @render.text
    def chat_error():
        return chat_error.get()

    @output
    @render.ui
    def chat_history():
        items = history.get()
        if not items:
            return ui.p("No messages yet.")
        blocks: List[Any] = []
        for msg in items:
            role = msg.get("role", "assistant")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            if role == "user":
                blocks.append(
                    ui.div(
                        ui.div(ui.strong("You"), ui.span(f"  {ts}", class_="muted")),
                        ui.div(content),
                        class_="bubble bubble-user",
                    )
                )
            else:
                blocks.append(
                    ui.div(
                        ui.div(ui.strong("Assistant"), ui.span(f"  {ts}", class_="muted")),
                        ui.div(content),
                        class_="bubble bubble-assistant",
                    )
                )
        return ui.div(*blocks, class_="chat-history")

    @output
    @render.text
    def last_backend_json():
        data = last_backend_data.get()
        if not data:
            return "(none)"
        return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


app = App(app_ui, server)
