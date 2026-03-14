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
import random
from collections import Counter, defaultdict
from datetime import datetime

# ── Optional heavy imports (graceful degradation) ──────────────────────────
try:
    import matplotlib.pyplot as plt
    import matplotlib.cm as cm
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

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

# ── Custom CSS ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

.main-header {
    background: linear-gradient(135deg, #0f1923 0%, #1a2f45 50%, #0d2137 100%);
    padding: 2.5rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    border: 1px solid #1e3a5f;
    position: relative;
    overflow: hidden;
}
.main-header::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -10%;
    width: 300px;
    height: 300px;
    background: radial-gradient(circle, rgba(0,180,255,0.08) 0%, transparent 70%);
    border-radius: 50%;
}
.main-header h1 {
    font-family: 'DM Serif Display', serif;
    color: #e8f4fd;
    font-size: 2.2rem;
    margin: 0 0 0.3rem 0;
    letter-spacing: -0.5px;
}
.main-header p {
    color: #7db8d8;
    margin: 0;
    font-size: 0.95rem;
    font-weight: 300;
}
.badge {
    display: inline-block;
    background: rgba(0,180,255,0.15);
    color: #4fc3f7;
    border: 1px solid rgba(0,180,255,0.3);
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-family: 'IBM Plex Mono', monospace;
    margin-bottom: 0.8rem;
}

.metric-card {
    background: #0f1923;
    border: 1px solid #1e3a5f;
    border-radius: 10px;
    padding: 1.2rem 1rem;
    text-align: center;
}
.metric-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 2.2rem;
    font-weight: 600;
    color: #4fc3f7;
    line-height: 1;
}
.metric-label {
    color: #7db8d8;
    font-size: 0.78rem;
    margin-top: 0.3rem;
    text-transform: uppercase;
    letter-spacing: 1px;
}

.section-title {
    font-family: 'DM Serif Display', serif;
    font-size: 1.3rem;
    color: #e8f4fd;
    margin: 1.5rem 0 0.8rem 0;
    border-left: 3px solid #4fc3f7;
    padding-left: 0.6rem;
}

.node-card {
    background: #0f1923;
    border: 1px solid #1e3a5f;
    border-radius: 8px;
    padding: 1rem;
    margin: 0.4rem 0;
}
.node-card h4 { color: #4fc3f7; margin: 0 0 0.3rem 0; font-size: 0.95rem; }
.node-card p  { color: #7db8d8; margin: 0; font-size: 0.82rem; }

.tip-box {
    background: rgba(79,195,247,0.06);
    border: 1px solid rgba(79,195,247,0.25);
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 0.8rem 0;
    color: #a8d8ea;
    font-size: 0.88rem;
}
.warn-box {
    background: rgba(255,167,38,0.07);
    border: 1px solid rgba(255,167,38,0.3);
    border-radius: 8px;
    padding: 1rem 1.2rem;
    margin: 0.8rem 0;
    color: #ffcc80;
    font-size: 0.88rem;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0a1520;
    border-right: 1px solid #1e3a5f;
}
[data-testid="stSidebar"] .stRadio > label { color: #7db8d8; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
#  SESSION STATE
# ═══════════════════════════════════════════════════════════════════════════
def init_state():
    defaults = {
        "graph": nx.DiGraph(),
        "articles": {},          # id -> metadata dict
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
    {"id": "radford2018", "title": "Improving Language Understanding by Generative Pre-Training (GPT)", "authors": "Radford et al.", "year": 2018, "venue": "OpenAI", "category": "Core", "url": "https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf", "refs": ["vaswani2017"]},
    {"id": "radford2019", "title": "Language Models are Unsupervised Multitask Learners (GPT-2)", "authors": "Radford et al.", "year": 2019, "venue": "OpenAI", "category": "LLM", "url": "https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf", "refs": ["radford2018", "vaswani2017"]},
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

def extract_metadata_from_text(text: str) -> dict:
    """Naive heuristic extraction from raw PDF text."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    title = lines[0] if lines else "Unknown Title"
    year_match = re.search(r'\b(19|20)\d{2}\b', text)
    year = int(year_match.group()) if year_match else 2000
    authors = "Unknown"
    for line in lines[1:6]:
        if re.search(r'[A-Z][a-z]+,\s[A-Z]', line) or re.search(r'[A-Z]\.\s[A-Z][a-z]+', line):
            authors = line; break
    refs = re.findall(r'\[(\d+)\]\s([A-Z][^,\n]{5,60}),', text)
    return {"title": title[:120], "authors": authors, "year": year, "venue": "Unknown", "refs": []}

def fuzzy_match(title_a: str, title_b: str) -> float:
    if HAS_FUZZY:
        return fuzz.token_set_ratio(title_a, title_b) / 100.0
    a = set(title_a.lower().split()); b = set(title_b.lower().split())
    return len(a & b) / max(len(a | b), 1)

def get_stats() -> dict:
    nodes = G.number_of_nodes()
    edges = G.number_of_edges()
    if nodes == 0:
        return {"nodes": 0, "edges": 0, "density": 0,
                "components": 0, "avg_degree": 0, "max_indegree": 0}
    density = nx.density(G)
    components = nx.number_weakly_connected_components(G)
    avg_deg = sum(dict(G.degree()).values()) / nodes
    max_ind = max((d for _, d in G.in_degree()), default=0)
    return {"nodes": nodes, "edges": edges,
            "density": round(density, 5),
            "components": components,
            "avg_degree": round(avg_deg, 2),
            "max_indegree": max_ind}


# ═══════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<div style='color:#4fc3f7;font-family:IBM Plex Mono,monospace;font-size:0.8rem;letter-spacing:2px;'>DS3294 PROJECT</div>", unsafe_allow_html=True)
    st.markdown("## 🔬 Citation Graph")
    st.markdown("---")
    page = st.radio("Navigation", [
        "📊 Dashboard",
        "📥 Ingest Papers",
        "🔍 Explore Graph",
        "📈 Analytics",
        "🗂️ Manage Corpus",
        "📖 Project Guide",
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
#  PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.markdown("""
    <div class='main-header'>
        <div class='badge'>DS3294 · Practice Project #13</div>
        <h1>🔬 Citation Graph Builder</h1>
        <p>Extract · Connect · Analyse scientific literature at scale</p>
    </div>
    """, unsafe_allow_html=True)

    stats = get_stats()
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, (label, val) in zip([c1,c2,c3,c4,c5], [
        ("Papers", stats["nodes"]),
        ("Citations", stats["edges"]),
        ("Components", stats["components"]),
        ("Avg Degree", stats["avg_degree"]),
        ("Max In-Degree", stats["max_indegree"]),
    ]):
        with col:
            st.markdown(f"""
            <div class='metric-card'>
                <div class='metric-val'>{val}</div>
                <div class='metric-label'>{label}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("---")
    col_l, col_r = st.columns([1.4, 1])

    with col_l:
        st.markdown("<div class='section-title'>Quick Start</div>", unsafe_allow_html=True)
        st.markdown("""
        <div class='tip-box'>
        <b>1.</b> Load the demo corpus below, or switch to <em>Ingest Papers</em> to upload your own PDFs.<br>
        <b>2.</b> Head to <em>Explore Graph</em> to browse citation neighbourhoods.<br>
        <b>3.</b> Use <em>Analytics</em> for degree distributions, PageRank, communities.
        </div>
        """, unsafe_allow_html=True)

        if st.button("🚀 Load Demo Corpus (30 papers)", use_container_width=True):
            load_sample()
            st.rerun()

        if st.session_state["log"]:
            st.markdown("<div class='section-title'>Activity Log</div>", unsafe_allow_html=True)
            for msg in reversed(st.session_state["log"][-8:]):
                st.markdown(f"<small style='color:#7db8d8'>{msg}</small>", unsafe_allow_html=True)

    with col_r:
        st.markdown("<div class='section-title'>Pipeline Overview</div>", unsafe_allow_html=True)
        st.markdown("""
        <div class='node-card'>
        <h4>① PDF Ingest</h4>
        <p>Upload PDFs → extract text → parse metadata & references</p>
        </div>
        <div class='node-card'>
        <h4>② Reference Resolution</h4>
        <p>Fuzzy matching · DOI lookup · disambiguation</p>
        </div>
        <div class='node-card'>
        <h4>③ Graph Construction</h4>
        <p>Directed graph: nodes = papers, edges = citations</p>
        </div>
        <div class='node-card'>
        <h4>④ Analysis & Visualisation</h4>
        <p>PageRank · communities · degree distribution</p>
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE: INGEST PAPERS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📥 Ingest Papers":
    st.markdown("<div class='section-title'>📥 Ingest Papers</div>", unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Upload PDFs", "Manual Entry", "Batch JSON"])

    with tab1:
        st.markdown("""<div class='tip-box'>
        Upload one or more open-access PDF articles. The system will attempt to extract the title,
        authors, year, and reference list automatically via text parsing.
        </div>""", unsafe_allow_html=True)
        
        if not HAS_PYPDF:
            st.markdown("""<div class='warn-box'>
            ⚠️ <b>PyPDF2 not installed.</b> Install it with <code>pip install PyPDF2</code> for real
            PDF parsing. You can still use Manual Entry or Batch JSON to add papers.
            </div>""", unsafe_allow_html=True)

        uploaded = st.file_uploader("Drop PDFs here", type=["pdf"], accept_multiple_files=True)
        if uploaded:
            for f in uploaded:
                pid = f.name.replace(".pdf", "").replace(" ", "_").lower()
                if pid in st.session_state["articles"]:
                    st.info(f"Already loaded: {f.name}")
                    continue
                if HAS_PYPDF:
                    reader = PyPDF2.PdfReader(io.BytesIO(f.read()))
                    text = "\n".join(p.extract_text() or "" for p in reader.pages)
                    meta = extract_metadata_from_text(text)
                else:
                    meta = {"title": f.name, "authors": "Unknown", "year": 2024,
                            "venue": "Unknown", "refs": []}
                meta["id"] = pid
                add_paper_to_graph(meta)
                st.session_state["uploaded_count"] += 1
                st.session_state["log"].append(f"📄 Uploaded: {meta['title'][:60]}")
            st.success(f"Added {len(uploaded)} paper(s) to graph.")
            st.rerun()

    with tab2:
        st.markdown("Add a paper manually:")
        with st.container():
            c1, c2 = st.columns(2)
            with c1:
                m_title   = st.text_input("Title")
                m_authors = st.text_input("Authors (semicolon-separated)")
            with c2:
                m_year  = st.number_input("Year", min_value=1900, max_value=2030, value=2023)
                m_venue = st.text_input("Venue / Journal")
            m_refs = st.text_area("Reference IDs (one per line, must match existing paper IDs)")
            m_id   = st.text_input("Paper ID (slug, e.g. smith2023nlp)", value="")
            if st.button("➕ Add Paper"):
                if not m_title or not m_id:
                    st.error("Title and ID are required.")
                else:
                    refs = [r.strip() for r in m_refs.split("\n") if r.strip()]
                    paper = {"id": m_id, "title": m_title, "authors": m_authors,
                             "year": int(m_year), "venue": m_venue, "refs": refs}
                    add_paper_to_graph(paper)
                    st.session_state["log"].append(f"➕ Added manually: {m_title[:60]}")
                    st.success(f"Paper '{m_id}' added!")
                    st.rerun()

    with tab3:
        st.markdown("""<div class='tip-box'>
        Paste a JSON array of paper objects. Each object should have:
        <code>id, title, authors, year, venue, refs</code> (refs is a list of IDs).
        </div>""", unsafe_allow_html=True)
        json_text = st.text_area("Paste JSON here", height=200,
            value=json.dumps([SAMPLE_PAPERS[0], SAMPLE_PAPERS[1]], indent=2))
        if st.button("📤 Import JSON"):
            try:
                papers = json.loads(json_text)
                for p in papers:
                    add_paper_to_graph(p)
                st.success(f"Imported {len(papers)} papers.")
                st.session_state["log"].append(f"📤 JSON import: {len(papers)} papers")
                st.rerun()
            except Exception as e:
                st.error(f"JSON parse error: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE: EXPLORE GRAPH
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🔍 Explore Graph":
    st.markdown("<div class='section-title'>🔍 Explore Citation Graph</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.warning("No papers in corpus. Load demo or ingest papers first.")
        st.stop()

    # ── Paper lookup ────────────────────────────────────────────────────────
    ids = list(st.session_state["articles"].keys())
    selected = st.selectbox("Select a paper to inspect", ids,
        format_func=lambda x: f"{x} — {st.session_state['articles'][x]['title'][:60]}")

    if selected:
        art = st.session_state["articles"][selected]
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown(f"""
            <div class='node-card'>
                <h4>📄 {art['title']}</h4>
                <p><b>Authors:</b> {art.get('authors','—')}</p>
                <p><b>Year:</b> {art.get('year','—')} &nbsp;|&nbsp; <b>Venue:</b> {art.get('venue','—')}</p>
                <p><b>ID:</b> <code style='color:#4fc3f7'>{selected}</code></p>
                <p><b>URL:</b> <a href='{art.get('url','#')}' target='_blank'>{art.get('url','—')}</a></p>
            </div>""", unsafe_allow_html=True)
        with c2:
            in_d  = G.in_degree(selected)
            out_d = G.out_degree(selected)
            st.markdown(f"""
            <div class='metric-card'><div class='metric-val'>{in_d}</div>
            <div class='metric-label'>Cited by</div></div>""", unsafe_allow_html=True)
            st.markdown("")
            st.markdown(f"""
            <div class='metric-card'><div class='metric-val'>{out_d}</div>
            <div class='metric-label'>References</div></div>""", unsafe_allow_html=True)

        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown("**📤 Papers this cites (out-edges)**")
            refs = list(G.successors(selected))
            if refs:
                for r in refs:
                    a = st.session_state["articles"].get(r, {})
                    st.markdown(f"- `{r}` — {a.get('title','?')[:55]}")
            else:
                st.markdown("_None in corpus_")
        with col_r:
            st.markdown("**📥 Papers that cite this (in-edges)**")
            citers = list(G.predecessors(selected))
            if citers:
                for c in citers:
                    a = st.session_state["articles"].get(c, {})
                    st.markdown(f"- `{c}` — {a.get('title','?')[:55]}")
            else:
                st.markdown("_None in corpus_")

    # ── Full papers table ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-title'>All Papers</div>", unsafe_allow_html=True)
    rows = []
    for pid, art in st.session_state["articles"].items():
        rows.append({
            "ID": pid,
            "Title": art.get("title","")[:70],
            "Category": art.get("category", "Core"),
            "Authors": art.get("authors","")[:40],
            "Year": art.get("year",""),
            "In-degree": G.in_degree(pid),
            "Out-degree": G.out_degree(pid),
        })
    if rows:
        df = pd.DataFrame(rows).sort_values("In-degree", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Interactive Graph Visualisation ────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-title'>🕸️ Interactive Citation Graph</div>", unsafe_allow_html=True)

    if not HAS_PYVIS:
        st.markdown("""<div class='warn-box'>
        ⚠️ <b>pyvis not installed.</b> Run <code>pip install pyvis</code> to enable the interactive graph.
        </div>""", unsafe_allow_html=True)
    else:
        col_cfg1, col_cfg2, col_cfg3 = st.columns(3)
        with col_cfg1:
            physics_on = st.checkbox("Enable physics simulation", value=True)
        with col_cfg2:
            show_labels = st.checkbox("Show paper IDs as labels", value=True)
        with col_cfg3:
            max_nodes = st.slider("Max nodes to display", 5,
                                  min(50, max(G.number_of_nodes(), 5)),
                                  min(30, max(G.number_of_nodes(), 5)))

        if st.button("🔄 Render Graph"):
            top_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:max_nodes]
            sub = G.subgraph(top_nodes)
            net = Network(height="600px", width="100%", directed=True,
                          bgcolor="#0a1520", font_color="#a8d8ea")
            
            # Gestalt: Grouping by color
            color_map = {
                "Core": "#4fc3f7", 
                "Vision": "#ff8a65", 
                "Efficient": "#81c784", 
                "LLM": "#ba68c8"
            }

            # Gestalt: Physics tuning for Proximity/Clustering
            if physics_on:
                net.barnes_hut(gravity=-8000, central_gravity=0.3, spring_length=150, spring_strength=0.05)
            
            pr = nx.pagerank(sub, alpha=0.85) if sub.number_of_nodes() > 1 else {n: 1 for n in sub.nodes()}
            pr_max = max(pr.values()) if pr else 1
            
            for node in sub.nodes():
                art = st.session_state["articles"].get(node, {})
                size = 15 + 35 * (pr.get(node, 0) / pr_max)
                label = node if show_labels else ""
                cat = art.get('category', 'Core')
                
                # HTML Rich Tooltip for Interaction
                url = art.get('url', '#')
                tip_html = f"""
                <div style='font-family:sans-serif; padding:5px;'>
                    <b style='color:#333; font-size:14px;'>{art.get('title','?')}</b><br>
                    <span style='color:#666;'>{art.get('authors','')}</span><br>
                    <span style='color:#666;'>{art.get('year','')} · <span style='background-color:#eee; padding:2px 4px; border-radius:3px;'>{cat}</span></span><br><br>
                    <a href='{url}' target='_blank' style='background:#4fc3f7; color:white; padding:4px 8px; border-radius:4px; text-decoration:none;'>View Paper / DOI</a>
                </div>
                """
                
                net.add_node(node, label=label, title=tip_html, size=size,
                             color=color_map.get(cat, "#4fc3f7"), borderWidth=2)
            
            for src, tgt in sub.edges():
                # Gestalt: Continuity (Smooth curved lines)
                net.add_edge(src, tgt, color="rgba(255,255,255,0.15)", arrows="to", smooth={"type": "curvedCW", "roundness": 0.2})
            
            # Allow HTML inside tooltips & Figure-Ground hover effects
            net.set_options("""
            var options = {
              "interaction": {
                "hover": true,
                "tooltipDelay": 200,
                "hoverConnectedEdges": true
              }
            }
            """)

            import tempfile, os
            tmp_path = os.path.join(tempfile.gettempdir(), "citation_graph_pyvis.html")
            net.save_graph(tmp_path)
            with open(tmp_path, "r", encoding="utf-8") as f:
                html_out = f.read()
            components.html(html_out, height=620, scrolling=False)
            st.caption(f"Showing top {max_nodes} nodes by degree. Node size ∝ PageRank. Colors: Core(Blue), LLM(Purple), Vision(Orange), Efficient(Green).")

    # ── Fuzzy search ────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-title'>🔎 Title Search (Fuzzy)</div>", unsafe_allow_html=True)
    query = st.text_input("Search by title keywords")
    if query:
        results = []
        for pid, art in st.session_state["articles"].items():
            score = fuzzy_match(query, art.get("title",""))
            if score > 0.25:
                results.append((score, pid, art))
        results.sort(reverse=True)
        if results:
            for score, pid, art in results[:8]:
                st.markdown(f"**{art['title'][:80]}** `{pid}` — match: `{score:.0%}`")
        else:
            st.info("No matches found.")


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE: ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📈 Analytics":
    st.markdown("<div class='section-title'>📈 Graph Analytics</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.warning("Load data first.")
        st.stop()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Degree Distribution", "PageRank", "Centrality", "Components", "Comparison"])

    # ── Degree distribution ─────────────────────────────────────────────────
    with tab1:
        in_degrees  = [G.in_degree(n)  for n in G.nodes()]
        out_degrees = [G.out_degree(n) for n in G.nodes()]

        if HAS_PLOTLY:
            fig = px.histogram(
                pd.DataFrame({"In-degree": in_degrees, "Out-degree": out_degrees}),
                barmode="overlay", opacity=0.75,
                color_discrete_map={"In-degree":"#4fc3f7","Out-degree":"#ff8a65"},
                template="plotly_dark",
                title="Degree Distribution",
            )
            fig.update_layout(paper_bgcolor="#0f1923", plot_bgcolor="#0a1520")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(pd.Series(Counter(in_degrees), name="In-degree"))

        c1, c2, c3 = st.columns(3)
        c1.metric("Max In-degree",  max(in_degrees))
        c2.metric("Max Out-degree", max(out_degrees))
        c3.metric("Mean Degree", f"{np.mean(in_degrees):.2f}")

    # ── PageRank ────────────────────────────────────────────────────────────
    with tab2:
        pr = nx.pagerank(G, alpha=0.85)
        pr_df = pd.DataFrame([
            {"Paper": st.session_state["articles"].get(k,{}).get("title","")[:60],
             "ID": k, "PageRank": round(v,6),
             "In-degree": G.in_degree(k)}
            for k, v in sorted(pr.items(), key=lambda x:-x[1])
        ])

        if HAS_PLOTLY:
            fig = px.bar(pr_df.head(10), x="PageRank", y="Paper",
                         orientation="h", template="plotly_dark",
                         color="PageRank", color_continuous_scale="Blues",
                         title="Top 10 Papers by PageRank")
            fig.update_layout(paper_bgcolor="#0f1923", plot_bgcolor="#0a1520",
                              yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(pr_df, use_container_width=True, hide_index=True)

    # ── Centrality ──────────────────────────────────────────────────────────
    with tab3:
        st.markdown("**Betweenness & Closeness Centrality** — which papers are most 'bridging'?")
        bc = nx.betweenness_centrality(G)
        try:
            cc = nx.closeness_centrality(G)
        except Exception:
            cc = {n: 0 for n in G.nodes()}
        cent_df = pd.DataFrame([
            {"Paper": st.session_state["articles"].get(k,{}).get("title","")[:60],
             "ID": k,
             "Betweenness": round(v, 6),
             "Closeness": round(cc.get(k, 0), 6),
             "In-degree": G.in_degree(k)}
            for k, v in sorted(bc.items(), key=lambda x: -x[1])
        ])
        if HAS_PLOTLY:
            fig = px.scatter(cent_df, x="Betweenness", y="Closeness",
                             size="In-degree", hover_name="Paper",
                             template="plotly_dark", title="Betweenness vs Closeness Centrality",
                             color="Betweenness", color_continuous_scale="Blues")
            fig.update_layout(paper_bgcolor="#0f1923", plot_bgcolor="#0a1520")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(cent_df, use_container_width=True, hide_index=True)

    # ── Connected components ────────────────────────────────────────────────
    with tab4:
        wcc = list(nx.weakly_connected_components(G))
        st.metric("Weakly Connected Components", len(wcc))
        comp_data = sorted([{"Component": i+1, "Size": len(c),
                              "Nodes": ", ".join(list(c)[:5]) + ("…" if len(c)>5 else "")}
                            for i, c in enumerate(wcc)], key=lambda x: -x["Size"])
        st.dataframe(pd.DataFrame(comp_data), use_container_width=True, hide_index=True)

        try:
            longest = nx.dag_longest_path_length(G)
            st.metric("Longest Citation Chain", longest)
        except Exception:
            st.info("Graph has cycles — longest path not applicable.")

    # ── Storage comparison ──────────────────────────────────────────────────
    with tab5:
        st.markdown("**In-memory vs Edge-list Storage Comparison**")
        n = G.number_of_nodes(); e = G.number_of_edges()
        adj_mem = n * 64 + e * 128          # rough bytes
        edge_mem = e * 2 * 32
        db_est  = e * 80 + n * 200

        if HAS_PLOTLY:
            fig = go.Figure(go.Bar(
                x=["Adjacency Dict\n(in-memory)", "Edge List\n(in-memory)", "SQLite\n(disk)"],
                y=[adj_mem, edge_mem, db_est],
                marker_color=["#4fc3f7","#81d4fa","#29b6f6"],
            ))
            fig.update_layout(template="plotly_dark", title="Estimated Memory/Storage (bytes)",
                              paper_bgcolor="#0f1923", plot_bgcolor="#0a1520")
            st.plotly_chart(fig, use_container_width=True)

        comp_df = pd.DataFrame({
            "Approach": ["NetworkX dict", "Edge list (CSV)", "SQLite DB", "Neo4j"],
            "Read speed": ["⚡ Fast","🐢 Slow","⚡ Fast","⚡ Fast"],
            "Write speed": ["⚡ Fast","✅ Medium","✅ Medium","✅ Medium"],
            "Persistence": ["❌ None","✅ File","✅ File","✅ Server"],
            "Query flexibility": ["✅ Python API","❌ Low","✅ SQL","🌟 Cypher"],
            "Best for": ["Prototyping","Small export","Medium corpus","Large corpus"],
        })
        st.dataframe(comp_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE: MANAGE CORPUS
# ═══════════════════════════════════════════════════════════════════════════
elif page == "🗂️ Manage Corpus":
    st.markdown("<div class='section-title'>🗂️ Manage Corpus</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.info("No papers yet. Load demo or ingest papers.")
    else:
        # Delete
        st.markdown("**Remove a paper**")
        pid_del = st.selectbox("Select to remove", list(st.session_state["articles"].keys()))
        if st.button("🗑️ Remove Paper"):
            G.remove_node(pid_del)
            del st.session_state["articles"][pid_del]
            st.session_state["log"].append(f"🗑️ Removed: {pid_del}")
            st.success(f"Removed {pid_del}")
            st.rerun()

        st.markdown("---")
        # Export
        st.markdown("**Export**")
        col1, col2 = st.columns(2)
        with col1:
            papers_json = json.dumps(list(st.session_state["articles"].values()), indent=2)
            st.download_button("⬇️ Download Papers JSON", papers_json,
                               "papers.json", "application/json")
        with col2:
            edges = [{"source": u, "target": v} for u, v in G.edges()]
            st.download_button("⬇️ Download Edge List JSON", json.dumps(edges, indent=2),
                               "edges.json", "application/json")

        # Incremental update (re-resolve refs)
        st.markdown("---")
        st.markdown("**Re-resolve References**")
        if st.button("🔄 Re-scan all references"):
            added = 0
            for pid, art in st.session_state["articles"].items():
                for ref in art.get("refs", []):
                    if ref in st.session_state["articles"] and not G.has_edge(pid, ref):
                        G.add_edge(pid, ref); added += 1
            st.success(f"Re-scan complete. Added {added} new edges.")
            st.session_state["log"].append(f"🔄 Re-resolved refs, +{added} edges")


# ═══════════════════════════════════════════════════════════════════════════
#  PAGE: PROJECT GUIDE
# ═══════════════════════════════════════════════════════════════════════════
elif page == "📖 Project Guide":
    st.markdown("<div class='section-title'>📖 How to Ace DS3294 Project #13</div>", unsafe_allow_html=True)

    st.markdown("""
    <div class='tip-box'>
    This guide walks through each requirement of the brief, with concrete suggestions 
    for libraries, data sources, and implementation strategy.
    </div>
    """, unsafe_allow_html=True)

    # ── Section 1 ──────────────────────────────────────────────────────────
    st.markdown("### 1. Collect a Corpus")
    st.markdown("""
    **Recommended sources** (all open-access, machine-readable):
    | Source | URL | Notes |
    |--------|-----|-------|
    | arXiv | arxiv.org/abs/XXXX | 2M+ papers, free API |
    | Semantic Scholar | semanticscholar.org | Rich metadata JSON API |
    | CORE | core.ac.uk | Aggregates OA papers |
    | PubMed Central | ncbi.nlm.nih.gov/pmc | Biomedical domain |
    | ACL Anthology | aclanthology.org | NLP papers |

    **Suggested workflow:**
    ```
    arxiv API  →  download 20-50 PDFs in one domain  →  store in /data/pdfs/
    ```
    Keep it focused: pick one domain (e.g. *community detection in networks*, *transformers in NLP*).
    20–30 papers is enough to show a meaningful graph.
    """)

    # ── Section 2 ──────────────────────────────────────────────────────────
    st.markdown("### 2. Extract Metadata")
    st.markdown("""
    ```python
    # Option A – embedded metadata (fast, clean)
    import PyPDF2
    reader = PyPDF2.PdfReader("paper.pdf")
    meta = reader.metadata          # /Title, /Author, /Subject …

    # Option B – text heuristics (fallback)
    text = "\\n".join(p.extract_text() for p in reader.pages)
    # → regex for title (first large-font line), authors, year

    # Option C – Semantic Scholar API (best quality)
    import requests
    r = requests.get(f"[https://api.semanticscholar.org/graph/v1/paper/search](https://api.semanticscholar.org/graph/v1/paper/search)"
                     f"?query={title}&fields=title,authors,year,venue,externalIds")
    ```
    **Tip:** Use `pdfminer.six` for finer-grained text extraction (font size = title heuristic).
    """)

    # ── Section 3 ──────────────────────────────────────────────────────────
    st.markdown("### 3. Reference Extraction & Resolution")
    st.markdown("""
    ```python
    # Step 1 – isolate the References section
    ref_section = text[text.lower().rfind("references"):]

    # Step 2 – split on numbered markers  [1] … [2] …  or Author, Year patterns
    import re
    entries = re.split(r'\\[\\d+\\]|\\n(?=[A-Z][a-z]+,)', ref_section)

    # Step 3 – resolve to known papers (fuzzy title match)
    from fuzzywuzzy import fuzz
    def resolve(ref_text, known_papers):
        best, best_score = None, 0
        for pid, art in known_papers.items():
            score = fuzz.token_set_ratio(ref_text, art["title"])
            if score > best_score:
                best, best_score = pid, score
        return best if best_score > 75 else None

    # Step 4 – DOI-based matching (where available)
    doi = re.search(r'10\\.\\d{4,}/\\S+', ref_text)
    ```
    **Libraries:** `anystyle-parser` (Ruby, very accurate), `refextract` (Python, CERN tool),
    `grobid` (Java server, gold standard for PDFs).
    """)

    # ── Section 4 ──────────────────────────────────────────────────────────
    st.markdown("### 4. Build the Graph")
    st.markdown("""
    ```python
    import networkx as nx
    G = nx.DiGraph()

    for paper in corpus:
        G.add_node(paper["id"], **paper)          # node = paper
        for ref_id in paper["resolved_refs"]:
            G.add_edge(paper["id"], ref_id)       # edge = citation

    # Persist (two approaches to compare)
    import pickle
    pickle.dump(G, open("graph.pkl","wb"))        # Option A: in-memory

    import sqlite3                                # Option B: SQLite
    conn = sqlite3.connect("citations.db")
    conn.execute("CREATE TABLE IF NOT EXISTS edges(src TEXT, tgt TEXT)")
    conn.executemany("INSERT INTO edges VALUES(?,?)", G.edges())
    ```
    """)

    # ── Section 5 ──────────────────────────────────────────────────────────
    st.markdown("### 5. Analysis Checklist")
    st.markdown("""
    | Task | Code |
    |------|------|
    | Degree distribution | `Counter(dict(G.in_degree()).values())` |
    | PageRank | `nx.pagerank(G, alpha=0.85)` |
    | Weakly connected components | `nx.weakly_connected_components(G)` |
    | Longest citation chain | `nx.dag_longest_path_length(G)` |
    | Betweenness centrality | `nx.betweenness_centrality(G)` |
    | Community detection | `nx.community.greedy_modularity_communities(G.to_undirected())` |
    """)

    # ── Section 6 ──────────────────────────────────────────────────────────
    st.markdown("### 6. Visualisation Options")
    st.markdown("""
    | Library | Best for |
    |---------|---------|
    | **pyvis** | Interactive in-browser HTML graph |
    | **plotly** | Charts, histograms, bar plots |
    | **networkx + matplotlib** | Static publication-quality figures |
    | **Gephi** (external) | Large graph layout (ForceAtlas2) |
    | **Streamlit + pyvis** | Embedding interactive graph in this dashboard |

    ```python
    # Embed pyvis in Streamlit
    from pyvis.network import Network
    import streamlit.components.v1 as components

    net = Network(height="600px", directed=True, bgcolor="#0a1520", font_color="#fff")
    net.from_nx(G)
    net.save_graph("graph.html")
    with open("graph.html","r") as f:
        components.html(f.read(), height=600)
    ```
    """)

    # ── Section 7 ──────────────────────────────────────────────────────────
    st.markdown("### 7. Project Structure")
    st.markdown("""
    ```
    citation_graph/
    ├── data/
    │   ├── pdfs/           ← raw PDFs
    │   ├── papers.json     ← extracted metadata
    │   └── citations.db    ← SQLite edge store
    ├── src/
    │   ├── ingest.py       ← PDF download + metadata extraction
    │   ├── references.py   ← reference parsing + resolution
    │   ├── graph.py        ← graph build + persistence
    │   └── analysis.py     ← analytics functions
    ├── app.py              ← this Streamlit dashboard
    ├── requirements.txt
    └── README.md
    ```
    """)

    st.markdown("""
    <div class='tip-box'>
    <b>💡 Marking tip:</b> The brief explicitly rewards documenting what went wrong 
    and how you revised your approach. Keep a short <em>decisions.md</em> noting every 
    pipeline change — this demonstrates the iterative thinking assessors look for.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class='warn-box'>
    <b>⚠️ Common pitfalls:</b><br>
    • Reference sections vary wildly between publishers — build in fallback parsing.<br>
    • Many papers in your corpus may not cite each other → expect a sparse graph; that's fine.<br>
    • Fuzzy matching can create false edges — tune your threshold carefully (≥75 is usually safe).<br>
    • Store graph + metadata together or you'll lose node attributes on reload.
    </div>
    """, unsafe_allow_html=True)


# ── Footer ──────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#3a5f80;font-size:0.78rem;"
    "font-family:IBM Plex Mono,monospace;'>DS3294 Citation Graph Builder · "
    f"Built with Streamlit · {datetime.now().year}</p>",
    unsafe_allow_html=True
)