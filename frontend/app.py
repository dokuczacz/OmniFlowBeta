import html
import json
import os
import time

import requests
import streamlit as st
import streamlit.components.v1 as components


def get_backend_url() -> str:
    return (
        st.secrets.get("BACKEND_URL")
        if hasattr(st, "secrets") and "BACKEND_URL" in st.secrets
        else os.environ.get("BACKEND_URL", "http://localhost:7071/api/tool_call_handler")
    )


def build_endpoint_url(base_url: str, function_name: str) -> str:
    if "/api/" in base_url:
        base = base_url.split("/api/")[0].rstrip("/")
        return f"{base}/api/{function_name}"
    return base_url.rstrip("/") + f"/api/{function_name}"


def normalize_user_id(value: str) -> str:
    if not value:
        return ""
    cleaned = str(value).strip()
    if not cleaned or "/" in cleaned or "\\" in cleaned or ".." in cleaned:
        return ""
    return cleaned


def request_headers(user_id: str) -> dict:
    return {"Content-Type": "application/json", "X-User-Id": user_id}


def bootstrap_user_storage(user_id: str) -> tuple[bool, str]:
    headers = request_headers(user_id)
    list_url = build_endpoint_url(backend_url, "list_blobs")
    upload_url = build_endpoint_url(backend_url, "upload_data_or_file")
    try:
        resp = requests.get(list_url, headers=headers, params={"prefix": ""}, timeout=15)
        data = resp.json() if resp.ok else {}
        count = data.get("count", 0) if isinstance(data, dict) else 0
    except Exception as exc:
        return False, f"list_blobs failed: {exc}"
    if count > 0:
        return True, "User namespace already initialized."
    placeholders = {"current_thread.json": {}, "interaction_logs.json": []}
    for file_name, content in placeholders.items():
        payload = {"target_blob_name": file_name, "file_content": content, "user_id": user_id}
        try:
            upload = requests.post(upload_url, json=payload, headers=headers, timeout=15)
        except Exception as exc:
            return False, f"upload_data_or_file failed: {exc}"
        if not upload.ok:
            return False, f"upload_data_or_file failed: {upload.text}"
    return True, "User namespace initialized."


def current_user_id() -> str:
    return st.session_state.get("user_id", "default")


def get_active_user_id() -> str:
    user_id = current_user_id()
    st.session_state["user_id"] = user_id
    return user_id


def set_active_user(user_id: str) -> None:
    history_by_user = st.session_state.setdefault("history_by_user", {})
    current_user = st.session_state.get("user_id", "default")
    history_by_user[current_user] = st.session_state.get("history", [])
    st.session_state["user_id"] = user_id
    st.session_state["history"] = history_by_user.get(user_id, [])
    st.session_state["thread_id"] = None
    st.session_state.pop("last_backend_data", None)
    st.session_state.pop("last_backend_error", None)
    st.session_state.pop("last_latency", None)
    st.session_state.pop("pending_user_message", None)
    st.session_state["user_logged_once"] = user_id != "default"


def add_to_history(role: str, content: str) -> None:
    st.session_state.setdefault("history", [])
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    st.session_state["history"].append({"role": role, "content": content, "timestamp": timestamp})


def extract_assistant_text(payload: dict) -> str:
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
    elif isinstance(payload, str):
        return payload
    return "(No response)"


def render_chat(history: list) -> None:
    chat_html = "<div class='scrollable-history'>"
    for msg in history:
        content = html.escape(str(msg.get("content", ""))).replace("\n", "<br>")
        role = msg.get("role", "assistant")
        if role == "user":
            bubble = "bubble-user"
            label = "You:"
        else:
            bubble = "bubble-assistant"
            label = "Assistant:"
        chat_html += f"<div class='{bubble}' style='white-space:pre-wrap; word-break:break-word;'><b>{label}</b> {content}</div>"
    chat_html += "</div>"
    st.markdown(chat_html, unsafe_allow_html=True)
    components.html(
        """
        <script>
        const container = window.parent.document.querySelector('.scrollable-history');
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
        </script>
        """,
        height=0,
    )


backend_url = get_backend_url()
get_active_user_id()
thread_id = st.session_state.get("thread_id")
last_latency = st.session_state.get("last_latency")
st.session_state.setdefault("known_users", ["default"])
st.session_state.setdefault("show_add_user_input", False)
st.session_state.setdefault("history", [])
st.session_state.setdefault("continuous_logging", True)
if st.session_state.pop("clear_new_user_id", False):
    st.session_state["new_user_id"] = ""

st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], .stApp { background-color: #0d1117 !important; color: #e6edf3; }
    header, div[data-testid="stHeader"] { background-color: #0d1117 !important; border-bottom: 0 !important; }
    div[data-testid="stToolbar"] { background-color: #0d1117 !important; }
    div[data-testid="stDecoration"] { background: #0d1117 !important; }
    [data-testid="stHeaderActionButtons"] button { background-color: #161b22 !important; color: #e6edf3 !important; border: 1px solid #30363d !important; }
    .main .block-container {
        max-width: 1100px;
        padding-top: 0.5rem;
        display: flex;
        flex-direction: column;
        height: 100vh;
    }
    .stMarkdown, .stTextInput, .stButton, .stSubheader, .stHeader, label { color: #e6edf3 !important; }
    .stTextInput input, .stTextArea textarea {
        background-color: #161b22 !important;
        color: #e6edf3 !important;
        border: 1px solid #30363d !important;
    }
    .stButton button {
        background-color: #238636 !important;
        color: #ffffff !important;
        border: 1px solid #2ea043 !important;
        box-shadow: none !important;
    }
    .stButton button:disabled, .stButton button[disabled] {
        background-color: #30363d !important;
        border: 1px solid #30363d !important;
        color: #8b949e !important;
    }
    form[data-testid="stForm"] {
        margin-top: auto;
        padding: 12px 16px;
        background: #0d1117;
        border-top: 1px solid #30363d;
    }
    form[data-testid="stForm"] .stTextInput, form[data-testid="stForm"] .stTextInput input {
        width: 100% !important;
    }
    form[data-testid="stForm"] .stButton { margin-top: 8px; }
    .scrollable-history {
        height: 400px;
        overflow-y: auto;
        padding-right: 6px;
        margin-bottom: 1rem;
        background: #0d1117;
        border-radius: 10px;
        border: 1px solid #30363d;
    }
    .bubble-user { background: #1f6feb; color: #ffffff; padding: 10px; border-radius: 10px; margin-bottom: 8px; }
    .bubble-assistant { background: #30363d; color: #e6edf3; padding: 10px; border-radius: 10px; margin-bottom: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)


with st.sidebar:
    known_users = st.session_state["known_users"]
    active_user = current_user_id()
    if active_user not in known_users:
        known_users.append(active_user)

    st.markdown(f"**Active user:** `{active_user}`")
    if active_user == "default" and not st.session_state.get("user_logged_once", False):
        st.caption("No user logged! Default (demo) user is connected.")

    selected_user = st.selectbox(
        "Available users",
        known_users,
        index=known_users.index(active_user),
        key="switch_user_select",
    )
    if st.button("Switch to selected user"):
        if selected_user != active_user:
            set_active_user(selected_user)
        st.rerun()

    if st.button("Add new user"):
        st.session_state["show_add_user_input"] = not st.session_state["show_add_user_input"]

    if st.session_state["show_add_user_input"]:
        new_user = st.text_input("New user id", key="new_user_id")
        if st.button("Create user"):
            normalized = normalize_user_id(new_user)
            if not normalized:
                st.error("Invalid user id.")
            else:
                if normalized not in known_users:
                    known_users.append(normalized)
                set_active_user(normalized)
                ok, msg = bootstrap_user_storage(normalized)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                st.session_state["clear_new_user_id"] = True
                st.session_state["show_add_user_input"] = False
                st.rerun()

    st.divider()
    st.markdown("**Session Info**")
    st.markdown(f"**Thread:** `{thread_id if thread_id else '-'} `")
    st.markdown(f"**Last Latency:** `{last_latency if last_latency is not None else '-'} ms`")
    continuous_logging = st.checkbox(
        "Continuous logging",
        value=st.session_state["continuous_logging"],
    )
    st.session_state["continuous_logging"] = continuous_logging
    debug_mode = st.checkbox("Debug responses", value=False)


render_chat(st.session_state["history"])

with st.form("chat_form", clear_on_submit=True):
    user_message = st.text_area(
        "Your message:",
        "",
        height=125,
        key="user_message_input",
        disabled=st.session_state.get("pending_user_message") is not None,
    )
    submitted = st.form_submit_button("Send", disabled=st.session_state.get("pending_user_message") is not None)

if submitted and user_message.strip():
    add_to_history("user", user_message.strip())
    st.session_state["pending_user_message"] = user_message.strip()
    st.rerun()

components.html(
    """
    <script>
    const LABEL = "Your message:";
    function attachCtrlEnter() {
        const textarea = window.parent.document.querySelector(`textarea[aria-label="${LABEL}"]`);
        if (!textarea || textarea.__ctrlEnter) {
            return;
        }
        textarea.__ctrlEnter = true;
        textarea.addEventListener("keydown", function (event) {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                const form = textarea.closest("form");
                if (!form) {
                    return;
                }
                const submit = form.querySelector('button[type="submit"]');
                if (submit) {
                    submit.click();
                    event.preventDefault();
                }
            }
        });
    }
    const observer = new MutationObserver(attachCtrlEnter);
    observer.observe(window.parent.document.body, {childList: true, subtree: true});
    setTimeout(attachCtrlEnter, 500);
    </script>
    """,
    height=0,
)

pending_user_message = st.session_state.pop("pending_user_message", None)
if pending_user_message:
    current_user = current_user_id()
    payload = {
        "message": pending_user_message,
        "user_id": current_user,
        "log_interaction": st.session_state["continuous_logging"],
    }
    if thread_id:
        payload["thread_id"] = thread_id
    headers = request_headers(current_user)
    with st.spinner("Przetwarzam..."):
        try:
            start = time.perf_counter()
            resp = requests.post(backend_url, json=payload, headers=headers, timeout=30)
            st.session_state["last_latency"] = int((time.perf_counter() - start) * 1000)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            st.session_state["last_backend_data"] = data
            if resp.ok and data.get("status") == "success":
                assistant_msg = extract_assistant_text(data)
                add_to_history("assistant", assistant_msg)
                if data.get("thread_id"):
                    st.session_state["thread_id"] = data["thread_id"]
                st.session_state.pop("last_backend_error", None)
                st.rerun()
            else:
                error_msg = data.get("error", resp.text if hasattr(resp, "text") else "Unknown error")
                st.session_state["last_backend_error"] = f"Backend error: {error_msg}"
                st.error(st.session_state["last_backend_error"])
        except Exception as exc:
            st.session_state["last_latency"] = None
            st.session_state["last_backend_error"] = f"Request failed: {exc}"
            st.error(st.session_state["last_backend_error"])
            add_to_history("assistant", f"[timeout] {exc}")

if st.session_state.get("last_backend_error"):
    st.error(st.session_state["last_backend_error"])

if debug_mode:
    with st.expander("Raw backend response"):
        st.write(st.session_state.get("last_backend_data"))
