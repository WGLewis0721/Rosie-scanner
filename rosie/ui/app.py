import streamlit as st
import os
import httpx

API_BASE = os.getenv("ROSIE_API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Rosie - AWS Intelligence", page_icon="🔍", layout="wide")
st.title("🔍 Rosie — AWS Environment Intelligence")
st.caption("Ask plain-English questions about your AWS environment.")

if "messages" not in st.session_state:
    st.session_state.messages = []

with st.sidebar:
    st.header("⚙️ Controls")
    if st.button("🔄 Refresh Inventory", type="primary"):
        region = st.text_input("Region", value="us-east-1")
        account_id = st.text_input("Account ID", value="000000000000")
        with st.spinner("Collecting AWS inventory..."):
            try:
                resp = httpx.post(f"{API_BASE}/collect", json={"region": region, "account_id": account_id}, timeout=120)
                data = resp.json()
                st.success(f"Collected {data.get('collected', 0)} resources")
            except Exception as e:
                st.error(f"Collection failed: {e}")
    st.divider()
    if st.button("Clear Chat"):
        st.session_state.messages = []
    st.markdown("**Supported question types:**")
    st.markdown("- What EC2 instances are running?\n- Which Lambda functions are on deprecated runtimes?\n- Which EC2 instances haven't been patched in 90 days?\n- Show me publicly accessible RDS databases\n- How many resources do we have by type?")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ask about your AWS environment..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                resp = httpx.post(
                    f"{API_BASE}/v1/chat/completions",
                    json={"model": "rosie", "messages": [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]},
                    timeout=120,
                )
                answer = resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                answer = f"Error communicating with API: {e}"
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})
