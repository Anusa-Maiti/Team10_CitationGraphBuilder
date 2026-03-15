import streamlit as st
import networkx as nx
import pandas as pd

# Import logic from our separate modules
from styles import apply_custom_css
from data_handler import init_state, load_sample, get_stats
from visualizer import render_interactive_graph

# ═══════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG & SETUP
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Citation Graph Builder",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_custom_css()
init_state()

# ═══════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🔬 Citation Graph Builder")
    st.markdown("---")
    page = st.radio("Navigation", [
        "📊 Dashboard",
        "🔍 Explore Graph",
        "📈 Analytics",
    ])
    st.markdown("---")
    
    stats = get_stats()
    st.markdown(f"**Corpus:** `{stats['nodes']}` papers")
    st.markdown(f"**Citations:** `{stats['edges']}` edges")
    
    if st.button("🗑️ Reset Graph", use_container_width=True):
        st.session_state["graph"] = nx.DiGraph()
        st.session_state["articles"] = {}
        st.success("Graph reset.")
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
#  PAGE ROUTING
# ═══════════════════════════════════════════════════════════════════════════
G = st.session_state["graph"]

if page == "📊 Dashboard":
    st.markdown("<div class='main-header'><div class='badge'>Interactive Graph Application</div><h1>🔬 Citation Graph Builder</h1><p>Extract · Connect · Analyse</p></div>", unsafe_allow_html=True)
    
    st.info("Click the button below to load the specialized 30-paper niche corpus focusing on Transformer & LLM history.")
    if st.button("🚀 Load Demo Corpus (30 papers)", use_container_width=True, type="primary"):
        load_sample()
        st.rerun()

    stats = get_stats()
    c1, c2, c3 = st.columns(3)
    c1.markdown(f"<div class='metric-card'><div class='metric-val'>{stats['nodes']}</div><div class='metric-label'>Papers</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='metric-card'><div class='metric-val'>{stats['edges']}</div><div class='metric-label'>Citations</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='metric-card'><div class='metric-val'>{stats['max_indegree']}</div><div class='metric-label'>Max In-Degree</div></div>", unsafe_allow_html=True)

elif page == "📈 Analytics":
    st.markdown("<div class='section-title'>📈 Graph Analytics</div>", unsafe_allow_html=True)
    if G.number_of_nodes() > 0:
        pr = nx.pagerank(G, alpha=0.85)
        pr_df = pd.DataFrame([{"ID": k, "Title": st.session_state["articles"].get(k, {}).get("title", ""), "PageRank": round(v,4)} for k, v in sorted(pr.items(), key=lambda x:-x[1])])
        st.dataframe(pr_df, use_container_width=True)
    else:
        st.warning("Load data on the Dashboard first.")

elif page == "🔍 Explore Graph":
    st.markdown("<div class='section-title'>🕸️ Interactive Citation Graph</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.warning("No papers in corpus. Go to Dashboard and load the demo corpus.")
        st.stop()

    col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
    with col_cfg1:
        physics_on = st.checkbox("Enable Physics (Proximity Principle)", value=True)
    with col_cfg2:
        show_labels = st.checkbox("Show Labels", value=True)
    with col_cfg3:
        max_nodes = st.slider("Max nodes", 5, max(G.number_of_nodes(), 5), max(G.number_of_nodes(), 5))

    if st.button("🔄 Render Graph", type="primary"):
        # We pass the graph, the articles dictionary, and our UI settings into our visualizer module
        render_interactive_graph(G, st.session_state["articles"], max_nodes, physics_on, show_labels)