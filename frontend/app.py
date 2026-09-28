"""
Agentic Data Assistant — Streamlit Frontend

Premium dark-themed dashboard with:
  • CSV drag-and-drop upload
  • Chat-style query interface
  • Real-time agent thought stream
  • Generated-code viewer
  • Result display with markdown rendering
"""

from __future__ import annotations

import json
import time

import requests
import streamlit as st

# ── Configuration ──
API_URL = "http://localhost:8000/api"

st.set_page_config(
    page_title="Agentic Data Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Premium Dark Theme ──
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Global ─────────────────────────────── */
.stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ── Header ─────────────────────────────── */
.hero {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    padding: 2.5rem 2rem;
    border-radius: 18px;
    border: 1px solid rgba(255,255,255,0.06);
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at 30% 50%, rgba(102,126,234,0.15) 0%, transparent 60%);
    pointer-events: none;
}
.hero h1 {
    font-size: 2.2rem;
    font-weight: 700;
    background: linear-gradient(90deg, #667eea, #764ba2, #f093fb);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin: 0 0 0.4rem 0;
}
.hero p {
    color: rgba(255,255,255,0.55);
    font-size: 1.05rem;
    margin: 0;
}

/* ── Thought Steps ──────────────────────── */
.thought-card {
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    padding: 0.9rem 1.2rem;
    margin-bottom: 0.6rem;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82rem;
    line-height: 1.65;
    transition: border-color 0.2s;
}
.thought-card:hover {
    border-color: rgba(255,255,255,0.15);
}
.thought-card.reason  { border-left: 3px solid #667eea; }
.thought-card.act     { border-left: 3px solid #f093fb; }
.thought-card.observe { border-left: 3px solid #4fd1c5; }
.thought-card.respond { border-left: 3px solid #ffd93d; }

/* ── Status Badges ──────────────────────── */
.badge {
    display: inline-block;
    padding: 0.2rem 0.65rem;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.6px;
}
.badge-running   { background: rgba(102,126,234,0.18); color: #667eea; }
.badge-completed { background: rgba(79,209,197,0.18); color: #4fd1c5; }
.badge-failed    { background: rgba(252,129,129,0.18); color: #fc8181; }

/* ── Dataset Info Card ──────────────────── */
.ds-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 1.2rem;
    margin-top: 0.8rem;
}
.ds-card h4 { margin: 0 0 0.6rem 0; color: rgba(255,255,255,0.85); }
.ds-stat {
    display: flex; justify-content: space-between;
    padding: 0.25rem 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 0.85rem;
}
.ds-stat span:first-child { color: rgba(255,255,255,0.5); }
.ds-stat span:last-child  { color: rgba(255,255,255,0.9); font-weight: 500; }

/* ── Hide Streamlit chrome ──────────────── */
#MainMenu, footer, header { visibility: hidden; }
</style>
""",
    unsafe_allow_html=True,
)


# ────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────

st.markdown(
    """
<div class="hero">
    <h1>🧠 Agentic Data Assistant</h1>
    <p>Upload a dataset · Ask questions in plain English · Get validated insights</p>
</div>
""",
    unsafe_allow_html=True,
)


# ────────────────────────────────────────────────────────────────
# Sidebar: Upload & Dataset Info
# ────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📂 Dataset")

    uploaded_file = st.file_uploader(
        "Drag & drop a CSV",
        type=["csv"],
        help="The dataset will be indexed into a FAISS vector store for efficient retrieval.",
    )

    if uploaded_file is not None:
        if st.button("🚀  Upload & Index", use_container_width=True, type="primary"):
            with st.spinner("Uploading and building FAISS index…"):
                try:
                    resp = requests.post(
                        f"{API_URL}/upload",
                        files={"file": (uploaded_file.name, uploaded_file.getvalue(), "text/csv")},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state["dataset"] = data
                        st.success(
                            f"✅ Indexed **{data['row_count']:,}** rows × "
                            f"**{len(data['columns'])}** columns"
                        )
                    else:
                        st.error(f"Upload failed: {resp.text}")
                except requests.ConnectionError:
                    st.error(
                        "Cannot connect to backend. "
                        "Run: `uvicorn backend.main:app --reload --port 8000`"
                    )

    # Dataset info card
    if "dataset" in st.session_state:
        ds = st.session_state["dataset"]
        st.markdown(
            f"""
<div class="ds-card">
    <h4>📊 {ds['filename']}</h4>
    <div class="ds-stat"><span>Rows</span><span>{ds['row_count']:,}</span></div>
    <div class="ds-stat"><span>Columns</span><span>{len(ds['columns'])}</span></div>
    <div class="ds-stat"><span>Dataset ID</span><span><code>{ds['dataset_id']}</code></span></div>
</div>
""",
            unsafe_allow_html=True,
        )
        with st.expander("📋 Column List"):
            for col in ds["columns"]:
                st.markdown(f"- `{col}`")

    st.markdown("---")
    st.caption("Powered by LangGraph · FAISS · Docker · OpenAI")


# ────────────────────────────────────────────────────────────────
# Main: Chat Interface
# ────────────────────────────────────────────────────────────────

if "dataset" not in st.session_state:
    st.info("👈 Upload a CSV dataset in the sidebar to get started.")
    st.stop()

st.markdown("### 💬 Ask Your Data")

# Chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Render past messages
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("code"):
            with st.expander("💻 Generated Code"):
                st.code(msg["code"], language="python")
        if msg.get("thoughts"):
            with st.expander("🧠 Thought Process"):
                for t in msg["thoughts"]:
                    t_type = t.get("type", "reason")
                    st.markdown(
                        f'<div class="thought-card {t_type}">{t.get("content", "")}</div>',
                        unsafe_allow_html=True,
                    )

# Chat input
if query := st.chat_input("e.g. What is the correlation between marketing spend and Q3 revenue?"):
    # User message
    st.session_state["messages"].append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Assistant response
    with st.chat_message("assistant"):
        with st.status("🧠 Reasoning…", expanded=True) as status_ui:
            try:
                # Start analysis
                resp = requests.post(
                    f"{API_URL}/analyze",
                    json={
                        "dataset_id": st.session_state["dataset"]["dataset_id"],
                        "query": query,
                    },
                    timeout=10,
                )
                if resp.status_code != 200:
                    st.error(f"Failed to start analysis: {resp.text}")
                    st.stop()

                thread_id = resp.json()["thread_id"]
                thoughts_seen = 0

                # Poll for updates
                while True:
                    thread = requests.get(
                        f"{API_URL}/threads/{thread_id}", timeout=10
                    ).json()

                    # Show new thought steps
                    thoughts = thread.get("thoughts", [])
                    for thought in thoughts[thoughts_seen:]:
                        step_label = {
                            "reason": "🔍 Reasoning",
                            "act": "💻 Generating Code",
                            "observe": "⚙️ Executing",
                            "respond": "📊 Formatting",
                        }.get(thought.get("type", ""), "🔄 Processing")

                        st.write(f"**{step_label}**")
                        st.markdown(thought.get("content", ""))
                        thoughts_seen += 1

                    if thread["status"] in ("completed", "failed"):
                        break

                    time.sleep(1)

                # Final result
                if thread["status"] == "completed":
                    status_ui.update(label="✅ Analysis Complete", state="complete")
                    result = thread.get("result") or "No result."
                    code = thread.get("generated_code") or ""

                    st.markdown("---")
                    st.markdown(result)

                    if code:
                        with st.expander("💻 Generated Code"):
                            st.code(code, language="python")

                    st.session_state["messages"].append(
                        {
                            "role": "assistant",
                            "content": result,
                            "code": code,
                            "thoughts": thoughts,
                        }
                    )
                else:
                    status_ui.update(label="❌ Analysis Failed", state="error")
                    error_msg = thread.get("error") or "Unknown error"
                    st.error(f"Analysis failed: {error_msg}")
                    st.session_state["messages"].append(
                        {
                            "role": "assistant",
                            "content": f"❌ Analysis failed: {error_msg}",
                            "thoughts": thoughts,
                        }
                    )

            except requests.ConnectionError:
                st.error(
                    "Cannot connect to the backend API. "
                    "Make sure it's running on port 8000."
                )
