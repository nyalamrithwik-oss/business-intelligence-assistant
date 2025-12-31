"""
Business Intelligence Assistant - Streamlit UI
Interactive web interface for the assistant
"""
import streamlit as st
from datetime import datetime
from business_assistant import BusinessAssistant

# Page configuration
st.set_page_config(
    page_title="Business Intelligence Assistant",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .stApp {
        max-width: 1200px;
        margin: 0 auto;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .source-box {
        background-color: #e8f4f8;
        padding: 0.5rem;
        border-left: 3px solid #1f77b4;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'assistant' not in st.session_state:
    st.session_state.assistant = BusinessAssistant()
    st.session_state.initialized = False
    st.session_state.messages = []

# Sidebar
with st.sidebar:
    st.header("Knowledge Base")
    if not st.session_state.initialized:
        if st.button("Load Knowledge Base"):
            st.session_state.assistant.load_knowledge_base("data")
            st.session_state.initialized = True
            st.success("Knowledge base loaded!")
    else:
        st.success("Knowledge base loaded!")
    st.markdown("---")
    st.header("Tool Status")
    st.write("(Tool status display placeholder)")

# Main area
st.title("🧠 Business Intelligence Assistant")
st.markdown("*Your AI-powered business research and automation assistant*")

# Check if knowledge base is loaded
if not st.session_state.initialized:
    st.warning("Knowledge base not loaded. Please load it from the sidebar.")
    st.stop()

# Display chat messages
for message in st.session_state.messages:
    if message["role"] == "user":
        st.markdown(f"**You:** {message['content']}")
    else:
        st.markdown(f"**Assistant:** {message['content']}")

# Chat input
user_input = st.text_input("Ask a question:", "")
if user_input:
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.spinner("Thinking..."):
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(st.session_state.assistant.process_query(user_input))
        st.session_state.messages.append({"role": "assistant", "content": result.get("response", "(No answer)")})
    st.rerun()
