import math
import streamlit as st
import os
import httpx
from collections import Counter

API_BASE = os.getenv("ROSIE_API_BASE", "http://localhost:8000")

st.set_page_config(
    page_title="Rosie — AWS Intelligence",
    page_icon="🌹",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Sidebar width */
    [data-testid="stSidebar"] { min-width: 260px; max-width: 280px; }

    /* Card-style metric boxes */
    div[data-testid="metric-container"] {
        background: #1e2130;
        border: 1px solid #2e3250;
        border-radius: 10px;
        padding: 12px 16px;
    }

    /* Resource cards */
    .resource-card {
        background: #1e2130;
        border: 1px solid #2e3250;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
    .resource-card code { font-size: 0.75rem; color: #a0aec0; }

    /* Example question pills */
    div[data-testid="stButton"] button[kind="secondary"] {
        border-radius: 20px;
        font-size: 0.82rem;
        padding: 4px 12px;
    }

    /* Health badge colours */
    .badge-ok   { color: #48bb78; font-weight: 700; }
    .badge-err  { color: #fc8181; font-weight: 700; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state defaults ────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = ""

# ── Helper: call API ──────────────────────────────────────────────────────────
def _api_health() -> bool:
    try:
        r = httpx.get(f"{API_BASE}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def _fetch_inventory() -> list[dict]:
    try:
        r = httpx.get(f"{API_BASE}/inventory", timeout=30)
        r.raise_for_status()
        return r.json().get("resources", [])
    except Exception:
        return []

def _ask(messages: list[dict]) -> str:
    try:
        resp = httpx.post(
            f"{API_BASE}/v1/chat/completions",
            json={"model": "rosie", "messages": messages},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        return f"⚠️ Error communicating with API: {exc}"

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌹 Rosie")
    st.caption("AI-powered AWS environment intelligence")
    st.divider()

    # Health indicator
    healthy = _api_health()
    status_label = "● Online" if healthy else "● Offline"
    status_class = "badge-ok" if healthy else "badge-err"
    st.markdown(
        f'<span class="{status_class}">API {status_label}</span>',
        unsafe_allow_html=True,
    )
    st.divider()

    st.subheader("⚙️ Collect Inventory")
    region = st.text_input("Region", value="us-east-1")
    account_id = st.text_input("Account ID", value="000000000000")
    if st.button("🔄 Refresh Inventory", type="primary", use_container_width=True):
        with st.spinner("Collecting AWS inventory…"):
            try:
                resp = httpx.post(
                    f"{API_BASE}/collect",
                    json={"region": region, "account_id": account_id},
                    timeout=120,
                )
                data = resp.json()
                st.success(f"✅ Collected {data.get('collected', 0)} resources")
            except Exception as exc:
                st.error(f"Collection failed: {exc}")
    st.divider()

    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ── Main content ──────────────────────────────────────────────────────────────
st.markdown("# 🌹 Rosie — AWS Environment Intelligence")

tab_chat, tab_dashboard, tab_resources = st.tabs(["💬 Chat", "📊 Dashboard", "🗂️ Resources"])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — Chat
# ════════════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown("### Ask about your AWS environment")

    EXAMPLE_QUESTIONS = [
        "What EC2 instances are running?",
        "Which Lambda functions use deprecated runtimes?",
        "Are there any public S3 buckets?",
        "Which security groups allow 0.0.0.0/0 inbound?",
        "Which EC2 instances haven't been patched in 90 days?",
        "Show me publicly accessible RDS databases",
        "How many resources do we have by type?",
        "What VPCs exist and what are their CIDR ranges?",
    ]
    EXAMPLE_COLS = 4

    # Example question pills
    st.caption("**Try an example:**")
    cols = st.columns(EXAMPLE_COLS)
    for idx, question in enumerate(EXAMPLE_QUESTIONS):
        if cols[idx % EXAMPLE_COLS].button(question, key=f"example_{idx}", use_container_width=True):
            st.session_state.pending_question = question

    st.divider()

    # Render conversation history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Pick up a pending question (from example pills) or the chat input widget
    prompt = st.chat_input("Ask about your AWS environment…") or st.session_state.pending_question
    if st.session_state.pending_question:
        st.session_state.pending_question = ""

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                answer = _ask(
                    [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                )
            st.markdown(answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()

# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — Dashboard
# ════════════════════════════════════════════════════════════════════════════════
with tab_dashboard:
    st.markdown("### Inventory Dashboard")

    if st.button("🔃 Refresh Dashboard", key="dash_refresh"):
        st.cache_data.clear()

    @st.cache_data(ttl=60)
    def _cached_inventory():
        return _fetch_inventory()

    resources = _cached_inventory()

    if not resources:
        st.info("No inventory data found. Use **Refresh Inventory** in the sidebar to collect resources.")
    else:
        type_counts = Counter(r.get("resource_type", "unknown") for r in resources)
        region_counts = Counter(r.get("region", "unknown") for r in resources)

        # KPI row
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Resources", len(resources))
        col2.metric("Resource Types", len(type_counts))
        col3.metric("Regions", len(region_counts))

        st.divider()

        chart_col, region_col = st.columns([3, 2])

        with chart_col:
            st.markdown("#### Resources by Type")
            type_data = dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True))
            st.bar_chart(type_data, use_container_width=True)

        with region_col:
            st.markdown("#### Resources by Region")
            for rgn, count in sorted(region_counts.items(), key=lambda x: x[1], reverse=True):
                pct = count / len(resources)
                st.markdown(f"**{rgn}** — {count}")
                st.progress(pct)

        st.divider()
        st.markdown("#### Resource Type Breakdown")
        rows = [{"Type": t, "Count": c} for t, c in sorted(type_counts.items())]
        st.dataframe(rows, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════════════════════
# TAB 3 — Resource Explorer
# ════════════════════════════════════════════════════════════════════════════════
with tab_resources:
    st.markdown("### Resource Explorer")

    all_resources = _cached_inventory()

    if not all_resources:
        st.info("No inventory data found. Use **Refresh Inventory** in the sidebar to collect resources.")
    else:
        resource_types = sorted({r.get("resource_type", "unknown") for r in all_resources})
        all_types_label = "— All Types —"

        filter_col, search_col = st.columns([2, 3])
        with filter_col:
            selected_type = st.selectbox("Filter by type", [all_types_label] + resource_types)
        with search_col:
            search_query = st.text_input("🔍 Search by name, ID, or keyword", placeholder="e.g. prod, sg-0abc123…")

        filtered = all_resources
        if selected_type != all_types_label:
            filtered = [r for r in filtered if r.get("resource_type") == selected_type]
        if search_query:
            q = search_query.lower()
            filtered = [
                r for r in filtered
                if q in r.get("name", "").lower()
                or q in r.get("resource_id", "").lower()
                or q in r.get("region", "").lower()
            ]

        st.caption(f"Showing **{len(filtered)}** of **{len(all_resources)}** resources")
        st.divider()

        PAGE_SIZE = 25
        total_pages = max(1, math.ceil(len(filtered) / PAGE_SIZE))
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1) if total_pages > 1 else 1
        page_resources = filtered[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]

        for res in page_resources:
            rtype = res.get("resource_type", "unknown")
            rname = res.get("name") or res.get("resource_id", "")
            rid = res.get("resource_id", "")
            rregion = res.get("region", "")

            with st.expander(f"**{rname}** · `{rtype}` · {rregion}"):
                meta_col, detail_col = st.columns([1, 2])
                with meta_col:
                    st.markdown(f"**ID:** `{rid}`")
                    st.markdown(f"**Type:** `{rtype}`")
                    st.markdown(f"**Region:** `{rregion}`")
                    account = res.get("account_id", "")
                    if account:
                        st.markdown(f"**Account:** `{account}`")
                    tags = res.get("tags", {})
                    if tags:
                        st.markdown("**Tags:**")
                        for k, v in list(tags.items())[:8]:
                            st.markdown(f"  `{k}` = `{v}`")
                with detail_col:
                    details = res.get("details", {})
                    if details:
                        st.json(details, expanded=False)
