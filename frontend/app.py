import streamlit as st
import time
import requests
import os


# --- Function Definitions ---
def get_backend_url():
    return (
        st.secrets.get("BACKEND_URL")
        if hasattr(st, "secrets") and "BACKEND_URL" in st.secrets
        else os.environ.get("BACKEND_URL", "http://localhost:7071/api/tool_call_handler")
    )

def get_user_id():
    user_id = st.session_state.get("user_id", "default")
    st.session_state.user_id = user_id
    return user_id

def get_thread_id():
    return st.session_state.get("thread_id")

def add_to_history(role, message):
    import datetime
    if "history" not in st.session_state:
        st.session_state["history"] = []
    user_name = st.session_state.get("user_id", "default")
    tool_name = None
    if role == "assistant":
        last_backend_data = st.session_state.get("last_backend_data")
        if last_backend_data:
            tool_calls = last_backend_data.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                tool_name = tool_calls[0].get("tool_name")
    else:
        tool_name = st.session_state.get("last_tool_name", None)
    timestamp = datetime.datetime.utcnow().isoformat()
    st.session_state["history"].append({
        "role": role,
        "content": message,
        "timestamp": timestamp,
        "user_name": user_name,
        "tool_name": tool_name
    })

# --- Initialize session state and debug info after all functions are defined ---
backend_url = get_backend_url()
user_id = get_user_id()
thread_id = st.session_state.get("thread_id", None)
last_latency = st.session_state.get("last_latency", None)


# --- Debug/Info Table in Sidebar ---
with st.sidebar:
    st.markdown("**Session Info**", unsafe_allow_html=True)
    st.markdown(f"**User ID:** `{user_id}`")
    st.markdown(f"**Thread:** `{thread_id if thread_id else '-'} `")
    st.markdown(f"**Last Latency:** `{last_latency if last_latency is not None else '-'} ms`")

    # Save to cloud button
    if st.button("Save History to Cloud", key="save_cloud_btn"):
        def save_history_to_cloud(user_id, history):
            """
            Send full chat history to backend save_interaction endpoint for batch backup.
            """
            import requests
            backend_url = os.environ.get("BACKEND_URL", "http://localhost:7071/api/save_interaction")
            url = f"{backend_url}"
            headers = {"Content-Type": "application/json", "X-User-Id": user_id}
            payload = {"history": history}
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                if response.status_code == 200:
                    return True, "History saved to cloud."
                else:
                    return False, f"Failed to save: {response.text}"
            except Exception as e:
                return False, f"Error: {e}"

        history = st.session_state.get("history", [])
        success, msg = save_history_to_cloud(user_id, history)
        if success:
            st.success(msg)
        else:
            st.error(msg)

# --- Dark theme + chat layout CSS ---
st.markdown(
    """
    <style>
    html, body, [data-testid="stAppViewContainer"], .stApp { background-color: #0d1117 !important; color: #e6edf3; }
    header, div[data-testid="stHeader"] { background-color: #0d1117 !important; border-bottom: 0 !important; }
    div[data-testid="stToolbar"] { background-color: #0d1117 !important; }
    div[data-testid="stDecoration"] { background: #0d1117 !important; }
    [data-testid="stHeaderActionButtons"] button { background-color: #161b22 !important; color: #e6edf3 !important; border: 1px solid #30363d !important; }
    /* main layout: column with chat taking available height */
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
    /* chat history area fills space above input */
    .chat-history {
        flex: 1 1 auto;
        overflow-y: auto;
        padding-right: 6px;
        margin-bottom: 1rem;
    }
    /* input form sits at the bottom of column */
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
    /* chat bubbles */
    .bubble-user { background: #1f6feb; color: #ffffff; padding: 10px; border-radius: 10px; margin-bottom: 8px; }
    .bubble-assistant { background: #30363d; color: #e6edf3; padding: 10px; border-radius: 10px; margin-bottom: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Load backend URL from environment or Streamlit secrets
def get_backend_url():
    return (
        st.secrets.get("BACKEND_URL")
        if hasattr(st, "secrets") and "BACKEND_URL" in st.secrets
        else os.environ.get("BACKEND_URL", "http://localhost:7071/api/tool_call_handler")
    )




# User ID management (robust default)
def get_user_id():
    user_id = st.session_state.get("user_id", "default")
    # Optionally allow user to change, or just always use default
    st.session_state.user_id = user_id
    return user_id


# --- Ensure these are defined before any logic uses them ---
backend_url = get_backend_url()
user_id = get_user_id()
thread_id = st.session_state.get("thread_id", None)
# thread_id = get_thread_id()  # <- Wywołanie przeniesione poniżej definicji lub usuń jeśli niepotrzebne


# Thread ID management
def get_thread_id():
    return st.session_state.get("thread_id")

# Jeśli potrzebujesz thread_id, wywołaj po definicji funkcji:
# thread_id = get_thread_id()




# --- Chat Layout: Fixed-height, scrollable chat history + input always at bottom ---
st.markdown(
    """
    <style>
    .scrollable-history {
        height: 400px;
        overflow-y: auto;
        padding-right: 6px;
        margin-bottom: 1rem;
        background: #0d1117;
        border-radius: 10px;
        border: 1px solid #30363d;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


chat_html = "<div class='scrollable-history'>"
if "history" in st.session_state:
    for msg in st.session_state["history"]:
        if msg["role"] == "user":
            chat_html += f"<div class='bubble-user'><b>Ty:</b> {msg['content']}</div>"
        else:
            chat_html += f"<div class='bubble-assistant'><b>Asystent:</b> {msg['content']}</div>"
chat_html += "</div>"
st.markdown(chat_html, unsafe_allow_html=True)

with st.form("chat_form", clear_on_submit=True):
    user_message = st.text_input("Your message:", "", key="user_message_input", disabled=st.session_state.get("pending_user_message") is not None)
    submitted = st.form_submit_button("Send", disabled=st.session_state.get("pending_user_message") is not None)


# User input is always added to history immediately, and input is never disabled
if 'submitted' in locals() and submitted and user_message.strip():
    add_to_history("user", user_message)
    st.session_state["pending_user_message"] = user_message
    st.rerun()

pending_user_message = st.session_state.pop("pending_user_message", None)
if pending_user_message:
    payload = {"message": pending_user_message, "user_id": user_id}
    if thread_id is not None:
        payload["thread_id"] = thread_id
    st.write("[DEBUG] Sending payload to backend:", payload)
    try:
        t0 = time.perf_counter()
        resp = requests.post(backend_url, json=payload, timeout=30)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        st.session_state["last_latency"] = latency_ms
        st.write(f"[DEBUG] Backend response status: {resp.status_code}")
        st.write("[DEBUG] Backend response text:", resp.text)
        try:
            data = resp.json()
        except Exception:
            data = None
        st.write("[DEBUG] Parsed backend response:", data)
        if resp.status_code == 200 and data and data.get("status") == "success":
            assistant_msg = data.get("response", "(No response)")
            add_to_history("assistant", assistant_msg)
            if data.get("thread_id"):
                st.session_state["thread_id"] = data["thread_id"]
            st.session_state.pop("last_backend_error", None)
            st.rerun()
        else:
            error_msg = data.get("error", "Unknown error") if data else resp.text
            st.session_state["last_backend_error"] = f"Backend error: {error_msg}"
            st.error(f"Backend error: {error_msg}")
            # Always re-enable input after error
            st.session_state.pop("pending_user_message", None)

    except Exception as e:
        st.session_state["last_latency"] = None
        st.session_state["last_backend_error"] = f"Request failed: {e}"
        st.error(f"Request failed: {e}")
        # Add timeout/error as assistant message in chat
        add_to_history("assistant", f"[timeout or error] {e}")
        st.session_state.pop("pending_user_message", None)




# --- Chat history below input ---
import streamlit.components.v1 as components
chat_html = """
<div id='chat-history' style='max-height: 400px; overflow-y: auto; border: 1px solid #eee; padding: 0.5em; background: #fafafa;'>
"""
for msg in st.session_state.get("history", []):
    chat_html += f"<div><b>{msg['role']}:</b> {msg['content']}</div>"
chat_html += "</div>"
chat_html += """
<script>
var chatDiv = window.parent.document.getElementById('chat-history');
if (chatDiv) { chatDiv.scrollTop = chatDiv.scrollHeight; }
</script>
"""
components.html(chat_html, height=420)
