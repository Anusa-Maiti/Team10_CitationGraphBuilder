"""
DS3294 – Citation Graph Builder  
A Streamlit dashboard for building, exploring, and analysing citation graphs
from scientific literature.
"""

import streamlit as st
import networkx as nx
import pandas as pd
import numpy as np
import json
import re
import io
from collections import Counter
from datetime import datetime

# ── Optional heavy imports (graceful degradation) ──────────────────────────
try:
    import plotly.graph_objects as go
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import PyPDF2
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from fuzzywuzzy import fuzz
    HAS_FUZZY = True
except ImportError:
    HAS_FUZZY = False

try:
    from pyvis.network import Network
    import streamlit.components.v1 as components
    HAS_PYVIS = True
except ImportError:
    HAS_PYVIS = False

# ═══════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Citation Graph Builder",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS (Light Theme for better Gestalt Figure-Ground contrast) ──────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    color: #1a1a1a;
}

.main-header {
    background: linear-gradient(135deg, #f0f4f8 0%, #d9e2ec 50%, #bcccdc 100%);
    padding: 2.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    border: 1px solid #9fb3c8;
    position: relative;
    overflow: hidden;
}
.main-header h1 {
    font-family: 'DM Serif Display', serif;
    color: #102a43;
    font-size: 2.2rem;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
}
.main-header p {
    color: #334e68;
    margin: 0;
    font-size: 0.95rem;
    font-weight: 400;
}
.badge {
    display: inline-block;
    background: #0277bd;
    color: #ffffff;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-family: 'IBM Plex Mono', monospace;
    margin-bottom: 0.8rem;
}

.metric-card {
    background: #ffffff;
    border: 1px solid #d9e2ec;
    border-radius: 10px;
    padding: 1.2rem 1rem;
    text-align: center;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05);
}
.metric-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2.2rem;
    font-weight: 600;
    color: #0277bd;
    line-height: 1;
}
.metric-label {
    color: #627d98;
    font-size: 0.78rem;
    margin-top: 0.3rem;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.section-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1.3rem;
    color: #102a43;
    margin: 1.5rem 0 0.8rem 0;
    border-left: 4px solid #0277bd;
    padding-left: 0.6rem;
}

.graph-container {
    background: #ffffff;
    border-radius: 12px;
    padding: 10px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.1);
    border: 1px solid #e0e0e0;
}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
#  SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════
def init_state():
    defaults = {
        "graph": nx.DiGraph(),
        "articles": {},          
        "uploaded_count": 0,
        "log": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()
G: nx.DiGraph = st.session_state["graph"]


# ═══════════════════════════════════════════════════════════════════════════
#  HELPER UTILITIES & DATA
# ═══════════════════════════════════════════════════════════════════════════

# Full 30-Paper Niche Corpus: Transformer Models & LLMs
SAMPLE_PAPERS = [
    {"id": "vaswani2017", "title": "Attention Is All You Need", "authors": "Vaswani et al.", "year": 2017, "venue": "NeurIPS", "category": "Core", "url": "https://arxiv.org/abs/1706.03762", "refs": []},
    {"id": "devlin2018", "title": "BERT: Pre-training of Deep Bidirectional Transformers", "authors": "Devlin et al.", "year": 2018, "venue": "NAACL", "category": "Core", "url": "https://arxiv.org/abs/1810.04805", "refs": ["vaswani2017"]},
    {"id": "radford2018", "title": "Improving Language Understanding by Generative Pre-Training", "authors": "Radford et al.", "year": 2018, "venue": "OpenAI", "category": "Core", "url": "https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf", "refs": ["vaswani2017"]},
    {"id": "radford2019", "title": "Language Models are Unsupervised Multitask Learners", "authors": "Radford et al.", "year": 2019, "venue": "OpenAI", "category": "LLM", "url": "https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf", "refs": ["radford2018", "vaswani2017"]},
    {"id": "brown2020", "title": "Language Models are Few-Shot Learners (GPT-3)", "authors": "Brown et al.", "year": 2020, "venue": "NeurIPS", "category": "LLM", "url": "https://arxiv.org/abs/2005.14165", "refs": ["radford2019", "vaswani2017"]},
    {"id": "liu2019", "title": "RoBERTa: A Robustly Optimized BERT Pretraining Approach", "authors": "Liu et al.", "year": 2019, "venue": "arXiv", "category": "Core", "url": "https://arxiv.org/abs/1907.11692", "refs": ["devlin2018"]},
    {"id": "raffel2019", "title": "Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer (T5)", "authors": "Raffel et al.", "year": 2019, "venue": "JMLR", "category": "Core", "url": "https://arxiv.org/abs/1910.10683", "refs": ["vaswani2017"]},
    {"id": "lan2019", "title": "ALBERT: A Lite BERT for Self-supervised Learning", "authors": "Lan et al.", "year": 2019, "venue": "ICLR", "category": "Efficient", "url": "https://arxiv.org/abs/1909.11942", "refs": ["devlin2018"]},
    {"id": "sanh2019", "title": "DistilBERT, a distilled version of BERT", "authors": "Sanh et al.", "year": 2019, "venue": "arXiv", "category": "Efficient", "url": "https://arxiv.org/abs/1910.01108", "refs": ["devlin2018"]},
    {"id": "dosovitskiy2020", "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale (ViT)", "authors": "Dosovitskiy et al.", "year": 2020, "venue": "ICLR", "category": "Vision", "url": "https://arxiv.org/abs/2010.11929", "refs": ["vaswani2017"]},
    {"id": "touvron2020", "title": "Training data-efficient image transformers & distillation through attention (DeiT)", "authors": "Touvron et al.", "year": 2020, "venue": "ICML", "category": "Vision", "url": "https://arxiv.org/abs/2012.12877", "refs": ["dosovitskiy2020"]},
    {"id": "liu2021", "title": "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows", "authors": "Liu et al.", "year": 2021, "venue": "ICCV", "category": "Vision", "url": "https://arxiv.org/abs/2103.14030", "refs": ["dosovitskiy2020"]},
    {"id": "radford2021", "title": "Learning Transferable Visual Models From Natural Language Supervision (CLIP)", "authors": "Radford et al.", "year": 2021, "venue": "ICML", "category": "Vision", "url": "https://arxiv.org/abs/2103.00020", "refs": ["dosovitskiy2020", "radford2019"]},
    {"id": "carion2020", "title": "End-to-End Object Detection with Transformers (DETR)", "authors": "Carion et al.", "year": 2020, "venue": "ECCV", "category": "Vision", "url": "https://arxiv.org/abs/2005.12872", "refs": ["vaswani2017"]},
    {"id": "kitaev2020", "title": "Reformer: The Efficient Transformer", "authors": "Kitaev et al.", "year": 2020, "venue": "ICLR", "category": "Efficient", "url": "https://arxiv.org/abs/2001.04451", "refs": ["vaswani2017"]},
    {"id": "wang2020", "title": "Linformer: Self-Attention with Linear Complexity", "authors": "Wang et al.", "year": 2020, "venue": "arXiv", "category": "Efficient", "url": "https://arxiv.org/abs/2006.04768", "refs": ["vaswani2017"]},
    {"id": "beltagy2020", "title": "Longformer: The Long-Document Transformer", "authors": "Beltagy et al.", "year": 2020, "venue": "arXiv", "category": "Efficient", "url": "https://arxiv.org/abs/2004.05150", "refs": ["vaswani2017"]},
    {"id": "zaheer2020", "title": "Big Bird: Transformers for Longer Sequences", "authors": "Zaheer et al.", "year": 2020, "venue": "NeurIPS", "category": "Efficient", "url": "https://arxiv.org/abs/2007.14062", "refs": ["vaswani2017"]},
    {"id": "choromanski2020", "title": "Rethinking Attention with Performers", "authors": "Choromanski et al.", "year": 2020, "venue": "ICLR", "category": "Efficient", "url": "https://arxiv.org/abs/2009.14794", "refs": ["vaswani2017"]},
    {"id": "ouyang2022", "title": "Training language models to follow instructions with human feedback (InstructGPT)", "authors": "Ouyang et al.", "year": 2022, "venue": "NeurIPS", "category": "LLM", "url": "https://arxiv.org/abs/2203.02155", "refs": ["brown2020"]},
    {"id": "touvron2023", "title": "LLaMA: Open and Efficient Foundation Language Models", "authors": "Touvron et al.", "year": 2023, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2302.13971", "refs": ["brown2020", "hoffmann2022", "chowdhery2022"]},
    {"id": "touvron2023b", "title": "Llama 2: Open Foundation and Fine-Tuned Chat Models", "authors": "Touvron et al.", "year": 2023, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2307.09288", "refs": ["touvron2023"]},
    {"id": "chowdhery2022", "title": "PaLM: Scaling Language Modeling with Pathways", "authors": "Chowdhery et al.", "year": 2022, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2204.02311", "refs": ["vaswani2017"]},
    {"id": "hoffmann2022", "title": "Training Compute-Optimal Large Language Models (Chinchilla)", "authors": "Hoffmann et al.", "year": 2022, "venue": "NeurIPS", "category": "LLM", "url": "https://arxiv.org/abs/2203.15556", "refs": ["rae2021"]},
    {"id": "rae2021", "title": "Scaling Language Models: Methods, Analysis & Insights from Training Gopher", "authors": "Rae et al.", "year": 2021, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2112.11446", "refs": ["vaswani2017"]},
    {"id": "zhang2022", "title": "OPT: Open Pre-trained Transformer Language Models", "authors": "Zhang et al.", "year": 2022, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2205.01068", "refs": ["brown2020"]},
    {"id": "scao2022", "title": "BLOOM: A 176B-Parameter Open-Access Multilingual Language Model", "authors": "Scao et al.", "year": 2022, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2211.05100", "refs": ["brown2020"]},
    {"id": "jiang2023", "title": "Mistral 7B", "authors": "Jiang et al.", "year": 2023, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2310.06825", "refs": ["touvron2023"]},
    {"id": "bubeck2023", "title": "Sparks of Artificial General Intelligence: Early experiments with GPT-4", "authors": "Bubeck et al.", "year": 2023, "venue": "arXiv", "category": "LLM", "url": "https://arxiv.org/abs/2303.12712", "refs": ["brown2020", "ouyang2022"]},
    {"id": "wei2022", "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models", "authors": "Wei et al.", "year": 2022, "venue": "NeurIPS", "category": "LLM", "url": "https://arxiv.org/abs/2201.11903", "refs": ["brown2020", "chowdhery2022"]}
]

def add_paper_to_graph(paper: dict):
    pid = paper["id"]
    st.session_state["articles"][pid] = paper
    G.add_node(pid, **{k: v for k, v in paper.items() if k != "refs"})
    for ref in paper.get("refs", []):
        if ref in st.session_state["articles"]:
            G.add_edge(pid, ref)

def load_sample():
    for p in SAMPLE_PAPERS:
        add_paper_to_graph(p)
    st.session_state["log"].append(f"✅ Loaded {len(SAMPLE_PAPERS)} sample papers on Transformers.")

def get_stats() -> dict:
    nodes = G.number_of_nodes()
    edges = G.number_of_edges()
    if nodes == 0:
        return {"nodes": 0, "edges": 0, "density": 0, "components": 0, "avg_degree": 0, "max_indegree": 0}
    return {"nodes": nodes, "edges": edges,
            "density": round(nx.density(G), 5),
            "components": nx.number_weakly_connected_components(G),
            "avg_degree": round(sum(dict(G.degree()).values()) / nodes, 2),
            "max_indegree": max((d for _, d in G.in_degree()), default=0)}


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
        G = st.session_state["graph"]
        st.success("Graph reset.")


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE ROUTING
# ═══════════════════════════════════════════════════════════════════════════
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
    st.markdown("<div class='section-title'>🕸️ Interactive Citation Graph (Gestalt Optimized)</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.warning("No papers in corpus. Go to Dashboard and load the demo corpus.")
        st.stop()

    if not HAS_PYVIS:
        st.error("pyvis not installed. Please install it using `pip install pyvis`.")
    else:
        col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
        with col_cfg1:
            physics_on = st.checkbox("Enable Physics (Proximity Principle)", value=True)
        with col_cfg2:
            show_labels = st.checkbox("Show Labels", value=True)
        with col_cfg3:
            max_nodes = st.slider("Max nodes", 5, max(G.number_of_nodes(), 5), max(G.number_of_nodes(), 5))

        if st.button("🔄 Render Graph", type="primary"):
            top_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:max_nodes]
            sub = G.subgraph(top_nodes)
            
            # 1. Figure-Ground: Light background ensures high contrast against vibrant nodes
            net = Network(height="650px", width="100%", directed=True,
                          bgcolor="#fcfcfc", font_color="#1a1a1a")
            
            # 2. Similarity: Distinct, high-contrast color palettes per category
            color_map = {
                "Core": {"background": "#29b6f6", "border": "#0277bd"},     # Light Blue / Dark Blue
                "Vision": {"background": "#ffa726", "border": "#ef6c00"},   # Orange / Deep Orange
                "Efficient": {"background": "#66bb6a", "border": "#2e7d32"},# Green / Dark Green
                "LLM": {"background": "#ab47bc", "border": "#6a1b9a"}       # Purple / Deep Purple
            }

            # 3. Proximity: Physics engine tuned to cluster heavily connected papers
            if physics_on:
                net.barnes_hut(
                    gravity=-4000, 
                    central_gravity=0.15, 
                    spring_length=120, 
                    spring_strength=0.08, 
                    damping=0.8,
                    overlap=0
                )
            
            pr = nx.pagerank(sub, alpha=0.85) if sub.number_of_nodes() > 1 else {n: 1 for n in sub.nodes()}
            pr_max = max(pr.values()) if pr else 1
            
            for node in sub.nodes():
                art = st.session_state["articles"].get(node, {})
                size = 15 + 35 * (pr.get(node, 0) / pr_max)
                label = node if show_labels else ""
                cat = art.get('category', 'Core')
                
                # Interactive HTML Tooltip with DOI link
                url = art.get('url', '#')
                tip_html = f"""
                <div style='font-family:sans-serif; padding:8px; min-width:200px;'>
                    <b style='color:#111; font-size:15px;'>{art.get('title','?')}</b><br>
                    <span style='color:#555;'>{art.get('authors','')}</span><br>
                    <div style='margin-top:6px; margin-bottom:10px;'>
                        <span style='color:#555; font-size:13px;'>{art.get('year','')}</span> &nbsp;
                        <span style='background-color:#eee; color:#333; padding:3px 6px; border-radius:4px; font-size:12px; font-weight:bold;'>{cat}</span>
                    </div>
                    <a href='{url}' target='_blank' style='display:inline-block; background:#0277bd; color:white; padding:6px 12px; border-radius:4px; text-decoration:none; font-size:13px; font-weight:bold;'>🔗 Open DOI / Paper</a>
                </div>
                """
                
                color_scheme = color_map.get(cat, color_map["Core"])
                
                # 4. Closure & Figure-Ground: Borders and shadows make nodes "pop" off the canvas
                net.add_node(
                    node, 
                    label=label, 
                    title=tip_html, 
                    size=size,
                    color=color_scheme, 
                    borderWidth=2,
                    borderWidthSelected=4,
                    shadow={"enabled": True, "color": "rgba(0,0,0,0.15)", "size": 6, "x": 2, "y": 3}
                )
            
            for src, tgt in sub.edges():
                # 5. Continuity: Smooth curved lines guiding the eye from source to target
                # Hover highlight changes the edge color drastically for immediate feedback
                net.add_edge(
                    src, tgt, 
                    color={"color": "rgba(100,110,120,0.25)", "highlight": "#ff5722"}, 
                    arrows="to", 
                    smooth={"type": "curvedCW", "roundness": 0.2}
                )
            
            # Focal Point (Interaction): Hovering dims unrelated nodes to 20% opacity
            net.set_options("""
            var options = {
              "interaction": {
                "hover": true,
                "tooltipDelay": 150,
                "hoverConnectedEdges": true
              }
            }
            """)

            import tempfile, os
            tmp_path = os.path.join(tempfile.gettempdir(), "citation_graph_pyvis.html")
            net.save_graph(tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                html_out = f.read()
            
            # Wrap in a white container to match the light background of the graph
            st.markdown("<div class='graph-container'>", unsafe_allow_html=True)
            components.html(html_out, height=660, scrolling=False)
            st.markdown("</div>", unsafe_allow_html=True)
            
            st.caption("✨ **Gestalt Design:** Hover over nodes to see the 'Figure-Ground' isolation. Colors map to sub-fields (Similarity). Click links in popups to view papers.")