"""
dashboard.py
============
Streamlit dashboard for the Human Evolution Citation Graph.

Run from your project root (same folder as collect_data.py):
    streamlit run dashboard.py

Requirements:
    pip install streamlit networkx plotly pandas requests
"""

import sys
import os
import json
import csv
import re
import time
import hashlib
import logging
import threading
import traceback
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx
import pandas as pd
import networkx as nx
import plotly.graph_objects as go
import plotly.express as px

# ── Project root on path ──────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── Paths ─────────────────────────────────────────────────────────────────────
CORPUS_JSON    = ROOT / "data" / "metadata" / "corpus.json"
METADATA_CSV   = ROOT / "data" / "metadata" / "papers_metadata.csv"
REFERENCES_CSV = ROOT / "data" / "metadata" / "all_references.csv"
COLLECTION_LOG = ROOT / "data" / "collection.log"

for p in [ROOT/"data"/"metadata", ROOT/"data"/"raw", ROOT/"data"/"processed"]:
    p.mkdir(parents=True, exist_ok=True)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Human Evolution · Citation Graph",
    page_icon=":bar_chart:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Theme / CSS (LIGHT THEME) ─────────────────────────────────────────────────
st.markdown("""
<style>
/* ── global ── */
[data-testid="stAppViewContainer"] { background: #f6f8fa; }
[data-testid="stSidebar"]          { background: #ffffff; border-right: 1px solid #d0d7de; }
[data-testid="stHeader"]           { background: transparent; }
.block-container { padding: 1rem 1.5rem; max-width: 100%; }

/* ── text ── */
h1,h2,h3,h4,p,label,li { color: #24292f !important; }
.stMarkdown p { color: #57606a !important; font-size: 13px; }

/* ── metric cards ── */
[data-testid="stMetric"] {
    background: #ffffff; border: 1px solid #d0d7de;
    border-radius: 8px; padding: 14px 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
[data-testid="stMetricValue"] { color: #0969da !important; font-size: 28px !important; }
[data-testid="stMetricLabel"] { color: #57606a !important; font-size: 12px !important; text-transform: uppercase; letter-spacing: 0.05em; }

/* ── buttons ── */
.stButton > button {
    background: #f6f8fa; color: #24292f;
    border: 1px solid #d0d7de; border-radius: 6px;
    font-size: 13px; font-weight: 600; width: 100%;
    padding: 8px 14px; transition: all 0.15s;
}
.stButton > button:hover { background: #f3f4f6; border-color: #0969da; }

/* ── primary button ── */
[data-testid="baseButton-primary"] > button,
button[kind="primary"] {
    background: #0969da !important; border-color: #0969da !important;
    color: white !important;
}
button[kind="primary"]:hover { background: #035fc7 !important; }

/* ── inputs ── */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox select {
    background: #ffffff !important; border: 1px solid #d0d7de !important;
    color: #24292f !important; border-radius: 6px !important; font-size: 13px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #0969da !important; box-shadow: 0 0 0 2px rgba(9,105,218,0.15) !important;
}

/* ── tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: #ffffff; border-bottom: 1px solid #d0d7de; gap: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent; color: #57606a !important;
    border-bottom: 2px solid transparent; padding: 10px 18px;
    font-size: 13px; font-weight: 600;
}
.stTabs [aria-selected="true"] {
    color: #0969da !important; border-bottom-color: #0969da !important;
    background: transparent !important;
}

/* ── expanders ── */
[data-testid="stExpander"] {
    background: #ffffff !important; border: 1px solid #d0d7de !important;
    border-radius: 8px !important;
}

/* ── dataframes ── */
[data-testid="stDataFrame"] { border: 1px solid #d0d7de; border-radius: 8px; }

/* ── sidebar labels ── */
[data-testid="stSidebar"] label { color: #57606a !important; font-size: 12px !important; }
[data-testid="stSidebar"] .stMarkdown p { color: #57606a !important; }

/* ── status boxes ── */
.status-ok   { background:#dafbe1; border:1px solid #4ac26b; border-radius:6px; padding:8px 12px; color:#1a7f37; font-size:13px; }
.status-warn { background:#fff8c5; border:1px solid #d4a72c; border-radius:6px; padding:8px 12px; color:#9a6700; font-size:13px; }
.status-err  { background:#ffebe9; border:1px solid #ff8182; border-radius:6px; padding:8px 12px; color:#cf222e; font-size:13px; }
.status-info { background:#ddf4ff; border:1px solid #54aeff; border-radius:6px; padding:8px 12px; color:#0969da; font-size:13px; }

/* ── paper card ── */
.paper-card {
    background:#ffffff; border:1px solid #d0d7de; border-radius:8px;
    padding:14px 16px; margin-bottom:10px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.paper-card:hover { border-color:#0969da; }
.paper-title { font-size:14px; font-weight:600; color:#24292f; line-height:1.4; }
.paper-meta  { font-size:12px; color:#57606a; margin-top:5px; }
.paper-badge {
    display:inline-block; padding:2px 8px; border-radius:12px;
    font-size:11px; font-weight:600; margin-right:5px; margin-top:4px;
}
.badge-epmc  { background:#dafbe1; color:#1a7f37; border:1px solid #4ac26b; }
.badge-pmc   { background:#ddf4ff; color:#0969da; border:1px solid #54aeff; }
.badge-biorxiv { background:#fff8c5; color:#9a6700; border:1px solid #d4a72c; }
.badge-arxiv { background:#fbeeff; color:#8250df; border:1px solid #c49bff; }
.badge-other { background:#f6f8fa; color:#57606a; border:1px solid #d0d7de; }

/* ── dividers ── */
hr { border-color: #d0d7de !important; margin: 12px 0 !important; }

/* ── log box ── */
.log-box {
    background:#ffffff; border:1px solid #d0d7de; border-radius:6px;
    padding:10px 12px; font-family:'Courier New',monospace; font-size:11px;
    color:#1a7f37; height:220px; overflow-y:auto; white-space:pre-wrap;
    word-break:break-all; line-height:1.5;
}

/* ── section headers ── */
.section-header {
    font-size:11px; font-weight:700; letter-spacing:0.1em;
    text-transform:uppercase; color:#0969da; margin:16px 0 8px;
    padding-bottom:5px; border-bottom:1px solid #d0d7de;
}
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
def _init_state():
    defaults = {
        "selected_node":   None,
        "job_running":     False,
        "job_name":        "",
        "job_log":         [],
        "job_thread":      None,
        "graph_filter":    "all",
        "search_query":    "",
        "show_isolated":   True,
        "layout_algo":     "spring",
        "node_color_by":   "source",
        "last_refresh":    0.0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    st.session_state["job_log"].append(line)

# ══════════════════════════════════════════════════════════════════════════════
# DATA I/O
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=5)
def load_corpus_cached():
    if not CORPUS_JSON.exists():
        return {}
    with open(CORPUS_JSON, encoding="utf-8") as f:
        return json.load(f)

@st.cache_data(ttl=5)
def load_metadata_cached():
    if not METADATA_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(METADATA_CSV, dtype=str).fillna("")

@st.cache_data(ttl=5)
def load_references_cached():
    if not REFERENCES_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(REFERENCES_CSV, dtype=str).fillna("")

def _bust_cache():
    load_corpus_cached.clear()
    load_metadata_cached.clear()
    load_references_cached.clear()
    st.session_state["last_refresh"] = time.time()

def save_corpus(corpus: dict):
    with open(CORPUS_JSON, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2, default=str)

def corpus_key(paper: dict) -> str:
    return paper.get("doi") or paper.get("pmid") or paper.get("title","").lower().strip()

def make_paper_id(paper: dict) -> str:
    if paper.get("doi"):
        return re.sub(r"[^\w.-]", "_", str(paper["doi"]).strip())
    if paper.get("pmid"):
        return f"pmid_{paper['pmid']}"
    if paper.get("pmcid"):
        return re.sub(r"[^\w.-]", "_", str(paper["pmcid"]).strip())
    if paper.get("arxiv_id"):
        return f"arxiv_{paper['arxiv_id']}"
    title = (paper.get("title") or "unknown").lower().strip()
    return "hash_" + hashlib.md5(title.encode()).hexdigest()[:12]

# ══════════════════════════════════════════════════════════════════════════════
# GRAPH BUILDER
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=5)
def build_networkx_graph():
    """Build a NetworkX DiGraph from the CSVs."""
    meta = load_metadata_cached()
    refs = load_references_cached()

    G = nx.DiGraph()

    if meta.empty:
        return G

    # Add nodes
    for _, row in meta.iterrows():
        pid = row.get("paper_id", "")
        if not pid:
            continue
        G.add_node(pid, **{
            "title":    row.get("title",""),
            "year":     row.get("year",""),
            "venue":    row.get("venue",""),
            "authors":  row.get("authors",""),
            "doi":      row.get("doi",""),
            "pmid":     row.get("pmid",""),
            "source":   row.get("source",""),
            "abstract": row.get("abstract_snippet",""),
            "has_pdf":  row.get("has_pdf","no"),
            "citation_count": row.get("citation_count",""),
        })

    # Add edges — only resolved
    if not refs.empty:
        resolved = refs[refs["resolution_method"] != "unresolved"]
        seen = set()
        for _, row in resolved.iterrows():
            src = row.get("citing_paper_id","")
            tgt = row.get("cited_paper_id","")
            if not src or not tgt:
                continue
            if src not in G.nodes or tgt not in G.nodes:
                continue
            key = (src, tgt)
            if key in seen:
                continue
            seen.add(key)
            G.add_edge(src, tgt,
                       citing_title=row.get("citing_title",""),
                       cited_title=row.get("cited_title",""),
                       resolution_method=row.get("resolution_method",""))

    return G

# ══════════════════════════════════════════════════════════════════════════════
# GRAPH LAYOUT
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=5)
def compute_layout(layout_algo: str):
    G = build_networkx_graph()
    if len(G.nodes) == 0:
        return {}
    if layout_algo == "spring":
        pos = nx.spring_layout(G, k=2.5, iterations=80, seed=42)
    elif layout_algo == "kamada_kawai":
        try:
            pos = nx.kamada_kawai_layout(G)
        except Exception:
            pos = nx.spring_layout(G, seed=42)
    elif layout_algo == "circular":
        pos = nx.circular_layout(G)
    elif layout_algo == "shell":
        pos = nx.shell_layout(G)
    else:
        pos = nx.spring_layout(G, seed=42)
    return pos

# ══════════════════════════════════════════════════════════════════════════════
# PLOTLY GRAPH FIGURE
# ══════════════════════════════════════════════════════════════════════════════
def make_graph_figure(
    G: nx.DiGraph,
    pos: dict,
    selected_node: str = None,
    highlight_neighbors: bool = True,
    node_color_by: str = "source",
    show_isolated: bool = True,
) -> go.Figure:

    if len(G.nodes) == 0:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            annotations=[dict(text="No graph data. Run the pipeline to collect papers.",
                              x=0.5, y=0.5, showarrow=False,
                              font=dict(color="#57606a", size=16))],
        )
        return fig

    # Which nodes to show
    nodes_to_draw = list(G.nodes)
    if not show_isolated:
        nodes_to_draw = [n for n in G.nodes if G.degree(n) > 0]

    # Neighbor highlight sets
    neighbors = set()
    if selected_node and selected_node in G.nodes:
        neighbors = set(G.predecessors(selected_node)) | set(G.successors(selected_node))

    # Degree for sizing
    in_deg  = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    # Color scheme (Light Mode High Contrast)
    SOURCE_COLORS = {
        "EuropePMC":          "#1a7f37",
        "EuropePMC_expansion":"#0969da",
        "PMC":                "#8250df",
        "arXiv":              "#9a6700",
        "bioRxiv":            "#cf222e",
    }
    YEAR_COLORSCALE = px.colors.sequential.Viridis

    def node_color(nid):
        if nid == selected_node:
            return "#b07d00"
        if selected_node and highlight_neighbors:
            if nid in neighbors:
                return "#54aeff"
            if nid not in neighbors and nid != selected_node:
                return "#d0d7de"
        data = G.nodes[nid]
        if node_color_by == "source":
            src = data.get("source","")
            for k, c in SOURCE_COLORS.items():
                if k in src:
                    return c
            return "#57606a"
        elif node_color_by == "year":
            yr = data.get("year","")
            try:
                y = int(str(yr)[:4])
                frac = max(0, min(1, (y - 2000) / 26))
                idx = int(frac * (len(YEAR_COLORSCALE)-1))
                return YEAR_COLORSCALE[idx]
            except:
                return "#57606a"
        elif node_color_by == "degree":
            deg = in_deg.get(nid, 0)
            if deg == 0: return "#d0d7de"
            if deg < 3:  return "#0969da"
            if deg < 8:  return "#1a7f37"
            return "#b07d00"
        return "#0969da"

    def node_opacity(nid):
        if selected_node is None or not highlight_neighbors:
            return 0.9
        if nid == selected_node or nid in neighbors:
            return 1.0
        return 0.15

    def node_size(nid):
        base = 12
        indeg = in_deg.get(nid, 0)
        return min(base + indeg * 3, 48)

    # ── Edge traces (draw per-edge for opacity control + hover tooltip) ──────
    edge_traces = []
    for src, tgt in G.edges():
        if src not in pos or tgt not in pos:
            continue
        if src not in nodes_to_draw or tgt not in nodes_to_draw:
            continue

        is_selected_edge = (selected_node and
                            (src == selected_node or tgt == selected_node))

        x0, y0 = pos[src]
        x1, y1 = pos[tgt]

        # Slightly shorten the line at the target end for arrow visibility
        dx, dy = x1-x0, y1-y0
        length = (dx**2+dy**2)**0.5
        if length > 0:
            shrink = 0.06
            xe = x1 - dx * shrink
            ye = y1 - dy * shrink
        else:
            xe, ye = x1, y1

        # Bolder, clearer edges with stronger contrast
        color   = "#0550ae" if is_selected_edge else "#6e7781"
        opacity = 1.0 if is_selected_edge else (0.12 if (selected_node and not is_selected_edge) else 0.55)
        width   = 3.5 if is_selected_edge else 2.0

        # Build edge hover tooltip with clickable links for both nodes
        src_data  = G.nodes.get(src, {})
        tgt_data  = G.nodes.get(tgt, {})
        src_title = src_data.get("title", src)[:60]
        tgt_title = tgt_data.get("title", tgt)[:60]
        src_doi   = src_data.get("doi", "")
        tgt_doi   = tgt_data.get("doi", "")
        src_year  = src_data.get("year", "")
        tgt_year  = tgt_data.get("year", "")

        def _doi_links(doi, title):
            links = []
            if doi:
                links.append(f"<a href='https://doi.org/{doi}' target='_blank' style='color:#0969da;text-decoration:underline;font-weight:600'>DOI</a>")
                gs_query = doi.replace("/", "%2F")
                links.append(f"<a href='https://scholar.google.com/scholar?q={gs_query}' target='_blank' style='color:#0969da;text-decoration:underline;font-weight:600'>Google Scholar</a>")
            else:
                safe_title = (title or "").replace(" ", "+")[:80]
                links.append(f"<a href='https://scholar.google.com/scholar?q={safe_title}' target='_blank' style='color:#0969da;text-decoration:underline;font-weight:600'>Google Scholar</a>")
            return " &nbsp;|&nbsp; ".join(links)

        edge_hover = (
            f"<b>Citation Edge</b><br><br>"
            f"<b>From (citing):</b> {src_title} ({src_year})<br>"
            f"<span style='font-size:11px'>{_doi_links(src_doi, src_title)}</span><br><br>"
            f"<b>To (cited):</b> {tgt_title} ({tgt_year})<br>"
            f"<span style='font-size:11px'>{_doi_links(tgt_doi, tgt_title)}</span>"
        )

        # Mid-point for hover hit area
        mx = (x0 + xe) / 2
        my = (y0 + ye) / 2

        edge_traces.append(go.Scatter(
            x=[x0, xe, None], y=[y0, ye, None],
            mode="lines",
            line=dict(color=color, width=width),
            opacity=opacity,
            hoverinfo="none",
            showlegend=False,
        ))

        # Invisible wide hover trace on midpoint for tooltip
        edge_traces.append(go.Scatter(
            x=[mx], y=[my],
            mode="markers",
            marker=dict(size=10, color=color, opacity=0.0),
            hovertext=edge_hover,
            hoverinfo="text",
            hoverlabel=dict(
                bgcolor="#ffffff",
                bordercolor="#d0d7de",
                font=dict(size=12, color="#24292f", family="sans-serif"),
            ),
            showlegend=False,
        ))

    # ── Arrow heads as scatter markers ───────────────────────────────────────
    arrow_x, arrow_y, arrow_colors, arrow_opacity = [], [], [], []
    for src, tgt in G.edges():
        if src not in pos or tgt not in pos:
            continue
        if src not in nodes_to_draw or tgt not in nodes_to_draw:
            continue
        x0, y0 = pos[src]
        x1, y1 = pos[tgt]
        dx, dy = x1-x0, y1-y0
        length = (dx**2+dy**2)**0.5
        if length == 0:
            continue
        shrink = node_size(tgt) / 2000
        xe = x1 - dx * shrink
        ye = y1 - dy * shrink
        arrow_x.append(xe)
        arrow_y.append(ye)
        is_sel = selected_node and (src==selected_node or tgt==selected_node)
        
        # BOLDER, CLEARER ARROWS
        arrow_colors.append("#0550ae" if is_sel else "#6e7781")
        arrow_opacity.append(1.0 if is_sel else (0.12 if selected_node else 0.55))

    # ── Node trace ────────────────────────────────────────────────────────────
    node_x, node_y = [], []
    node_colors, node_sizes, node_opacities = [], [], []
    node_text, node_hover = [], []
    node_ids_ordered = []

    for nid in nodes_to_draw:
        if nid not in pos:
            continue
        x, y = pos[nid]
        data = G.nodes[nid]
        node_x.append(x)
        node_y.append(y)
        node_colors.append(node_color(nid))
        node_sizes.append(node_size(nid))
        node_opacities.append(node_opacity(nid))
        node_ids_ordered.append(nid)

        title = data.get("title","")
        label = title[:35] + "…" if len(title) > 35 else title
        node_text.append(label)

        # Clickable links in node hover popup
        doi_val = data.get('doi','')
        title_val = data.get('title','')
        link_parts = []
        if doi_val:
            link_parts.append(f"<a href='https://doi.org/{doi_val}' target='_blank' style='color:#0969da;text-decoration:underline;font-weight:600'>Open DOI</a>")
            gs_q = doi_val.replace("/","%2F")
            link_parts.append(f"<a href='https://scholar.google.com/scholar?q={gs_q}' target='_blank' style='color:#0969da;text-decoration:underline;font-weight:600'>Google Scholar</a>")
        else:
            safe_q = (title_val or "").replace(" ","+")[:80]
            link_parts.append(f"<a href='https://scholar.google.com/scholar?q={safe_q}' target='_blank' style='color:#0969da;text-decoration:underline;font-weight:600'>Google Scholar</a>")
        doi_link = "<br><br>" + " &nbsp;|&nbsp; ".join(link_parts) if link_parts else ""

        hover = (
            f"<b>{title[:70]}</b><br>"
            f"Year: {data.get('year','')}  |  "
            f"Source: {data.get('source','')}<br>"
            f"Venue: {data.get('venue','')[:50]}<br>"
            f"In-degree: {in_deg.get(nid,0)}  |  Out-degree: {out_deg.get(nid,0)}"
            f"{doi_link}<br><br>"
            f"<i>Click node to view full details</i>"
        )
        node_hover.append(hover)

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(
            size=node_sizes,
            color=node_colors,
            opacity=node_opacities,
            line=dict(color="#ffffff", width=1.5),
            symbol="circle",
        ),
        text=node_text,
        textposition="top center",
        textfont=dict(size=9, color="#57606a"),
        hovertext=node_hover,
        hoverinfo="text",
        customdata=node_ids_ordered,
        showlegend=False,
    )

    # ── Legend entries ────────────────────────────────────────────────────────
    legend_traces = []
    if node_color_by == "source":
        for src_name, color in SOURCE_COLORS.items():
            legend_traces.append(go.Scatter(
                x=[None], y=[None], mode="markers",
                marker=dict(size=10, color=color),
                name=src_name, showlegend=True,
            ))

    # ── Assemble figure ───────────────────────────────────────────────────────
    all_traces = edge_traces + legend_traces + [node_trace]

    fig = go.Figure(data=all_traces)
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=0, b=0),
        height=620,
        showlegend=(node_color_by == "source"),
        legend=dict(
            bgcolor="#ffffff", bordercolor="#d0d7de", borderwidth=1,
            font=dict(color="#57606a", size=11),
            x=0.01, y=0.99, xanchor="left", yanchor="top",
        ),
        xaxis=dict(visible=False, showgrid=False, zeroline=False),
        yaxis=dict(visible=False, showgrid=False, zeroline=False),
        hovermode="closest",
        clickmode="event+select",
        dragmode="pan",
        uirevision="graph",  # preserve zoom on rerender
        hoverlabel=dict(
            bgcolor="#ffffff",
            bordercolor="#d0d7de",
            font_size=12,
            font_family="sans-serif",
            font_color="#24292f",
            namelength=0,
        )
    )

    # Selected node ring
    if selected_node and selected_node in pos:
        sx, sy = pos[selected_node]
        fig.add_trace(go.Scatter(
            x=[sx], y=[sy], mode="markers",
            marker=dict(size=node_size(selected_node)+10,
                        color="rgba(0,0,0,0)",
                        line=dict(color="#b07d00", width=2.5)),
            hoverinfo="none", showlegend=False,
        ))

    return fig

# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNERS (each runs in a background thread)
# ══════════════════════════════════════════════════════════════════════════════
def _run_in_thread(fn, *args, job_name="job"):
    """Launch fn(*args) in a daemon thread, setting job state around it."""
    st.session_state["job_running"] = True
    st.session_state["job_name"]    = job_name
    st.session_state["job_log"]     = []

    def _wrapper():
        try:
            fn(*args)
        except Exception as e:
            log(f"[ERROR] {e}")
            log(traceback.format_exc())
        finally:
            st.session_state["job_running"] = False
            st.session_state["job_name"]    = ""
            _bust_cache()

    t = threading.Thread(target=_wrapper, daemon=True)
    add_script_run_ctx(t) # Streamlit threading fix
    st.session_state["job_thread"] = t
    t.start()


def pipeline_collect(queries, max_papers, skip_pdf, expand_depth):
    try:
        from collect_data import (load_corpus, save_corpus as _sc,
                                   collect_by_queries, DEFAULT_QUERIES)
        from citation_expander import CitationExpander
    except ImportError as e:
        log(f"[ERROR] Import failed: {e}"); return

    corpus = load_corpus()
    log(f"Loaded corpus: {len(corpus)} existing papers")

    q = queries if queries else DEFAULT_QUERIES
    log(f"Running {len(q)} queries, max_papers={max_papers}, skip_pdf={skip_pdf}")

    corpus = collect_by_queries(q, corpus, max_papers, skip_pdf)
    _sc(corpus)
    log(f"After query collection: {len(corpus)} papers")

    if expand_depth > 0:
        log(f"Citation expansion depth={expand_depth}...")
        expander = CitationExpander(
            corpus=corpus, max_papers=max_papers,
            skip_pdf=skip_pdf, depth=expand_depth)
        corpus = expander.expand()
        _sc(corpus)
        log(f"After expansion: {len(corpus)} papers")

    log("Extracting references...")
    _pipeline_extract(corpus, force=False)
    log("Rebuilding CSVs...")
    _pipeline_store(corpus)
    log("✓ Pipeline complete.")


def _pipeline_extract(corpus, force=False):
    try:
        from extract_references import process as er_process, write_csv as er_write
    except ImportError as e:
        log(f"[ERROR] extract_references import failed: {e}"); return

    try:
        edges = er_process(corpus, force=force)
        save_corpus(corpus) # Memory amnesia fix. Saves newly extracted refs!
        er_write(edges)
        resolved = sum(1 for e in edges if e.get("cited_paper_id"))
        log(f"Reference extraction: {len(edges)} edges, {resolved} resolved")
    except Exception as e:
        log(f"[ERROR] extract_references failed: {e}")
        log(traceback.format_exc())


def _pipeline_store(corpus):
    try:
        from storedata import store_metadata
    except ImportError as e:
        log(f"[ERROR] storedata import failed: {e}"); return

    try:
        paper_rows, ref_rows = store_metadata(corpus)
        resolved = sum(1 for r in ref_rows if r.get("cited_paper_id"))
        log(f"Stored: {len(paper_rows)} papers, {resolved} resolved edges in CSV")
    except Exception as e:
        log(f"[ERROR] store_metadata failed: {e}")
        log(traceback.format_exc())


def pipeline_add_paper(doi, pmid):
    """
    Fetch one paper by DOI/PMID, add to corpus, extract its references,
    resolve them against existing corpus, rebuild CSVs.
    """
    try:
        from collect_data import load_corpus, add_single_paper
    except ImportError as e:
        log(f"[ERROR] Fetcher import failed: {e}"); return

    # Load fresh corpus
    corpus = {}
    if CORPUS_JSON.exists():
        with open(CORPUS_JSON, encoding="utf-8") as f:
            corpus = json.load(f)
    log(f"Corpus has {len(corpus)} papers")

    # --- Build lookup to check for duplicate ---
    existing_dois  = {p.get("doi","").lower().strip() for p in corpus.values() if p.get("doi")}
    existing_pmids = {str(p.get("pmid","")).strip() for p in corpus.values() if p.get("pmid")}

    doi_norm  = (doi or "").strip().lower()
    pmid_norm = (pmid or "").strip()

    if doi_norm  and doi_norm  in existing_dois:
        log(f"[INFO] DOI {doi} already in corpus."); return
    if pmid_norm and pmid_norm in existing_pmids:
        log(f"[INFO] PMID {pmid} already in corpus."); return

    # Native collection pipeline guarantees strict domain filters
    corpus = add_single_paper(corpus, doi=doi, pmid=pmid, skip_pdf=True)
    save_corpus(corpus)
    log(f"Paper processed through fetcher layer.")

    # --- Extract references for this paper (and any without cached refs) ---
    log("Extracting references...")
    _pipeline_extract(corpus, force=False)

    log("Rebuilding CSVs...")
    _pipeline_store(corpus)

    log(f"✓ Done. Check the graph — new edges may have been created.")


def pipeline_extract_only(force):
    corpus = {}
    if CORPUS_JSON.exists():
        with open(CORPUS_JSON, encoding="utf-8") as f:
            corpus = json.load(f)
    log(f"Corpus: {len(corpus)} papers")
    _pipeline_extract(corpus, force=force)
    _pipeline_store(corpus)
    log("✓ Done.")


def pipeline_rebuild_csv():
    corpus = {}
    if CORPUS_JSON.exists():
        with open(CORPUS_JSON, encoding="utf-8") as f:
            corpus = json.load(f)
    log(f"Rebuilding CSVs for {len(corpus)} papers...")
    _pipeline_store(corpus)
    log("✓ Done.")


# ══════════════════════════════════════════════════════════════════════════════
# HELPER UI COMPONENTS
# ══════════════════════════════════════════════════════════════════════════════
def badge_html(source: str) -> str:
    src = str(source)
    if "EuropePMC" in src:  cls = "badge-epmc"
    elif "PMC" in src:      cls = "badge-pmc"
    elif "bioRxiv" in src:  cls = "badge-biorxiv"
    elif "arXiv" in src:    cls = "badge-arxiv"
    else:                   cls = "badge-other"
    label = src.replace("EuropePMC_expansion","ePMC-exp").replace("EuropePMC","ePMC")
    return f'<span class="paper-badge {cls}">{label}</span>'

def paper_card_html(row: dict) -> str:
    title   = row.get("title","—")
    year    = row.get("year","")
    venue   = row.get("venue","")[:60]
    authors = row.get("authors","").replace("|"," ·")[:80]
    source  = row.get("source","")
    doi     = row.get("doi","")
    doi_link = f'<a href="https://doi.org/{doi}" target="_blank" style="color:#0969da;font-size:11px">doi:{doi[:30]}</a>' if doi else ""
    return f"""
    <div class="paper-card">
      <div class="paper-title">{title[:100]}</div>
      <div class="paper-meta">{year} · {venue}</div>
      <div class="paper-meta">{authors}</div>
      <div style="margin-top:5px">{badge_html(source)}{doi_link}</div>
    </div>
    """

def render_log_box():
    lines = st.session_state.get("job_log", [])
    content = "\n".join(lines[-60:]) if lines else "No log yet."
    st.markdown(f'<div class="log-box">{content}</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
def render_sidebar():
    with st.sidebar:
        st.markdown("## Citation Graph")
        st.markdown('<div class="stMarkdown"><p>Human Evolution Papers</p></div>',
                    unsafe_allow_html=True)
        st.divider()

        # Corpus status
        meta = load_metadata_cached()
        refs = load_references_cached()
        n_papers = len(meta)
        n_refs   = len(refs)
        n_resolved = int((refs["resolution_method"] != "unresolved").sum()) if not refs.empty else 0

        c1, c2 = st.columns(2)
        c1.metric("Papers", n_papers)
        c2.metric("Edges", n_resolved)
        c1, c2 = st.columns(2)
        c1.metric("Total refs", n_refs)
        rate = round(100*n_resolved/max(n_refs,1), 1)
        c2.metric("Resolved", f"{rate}%")

        st.divider()

        # Graph display options
        st.markdown('<div class="section-header">Graph Display</div>', unsafe_allow_html=True)

        st.session_state["layout_algo"] = st.selectbox(
            "Layout", ["spring", "kamada_kawai", "circular", "shell"],
            index=["spring","kamada_kawai","circular","shell"].index(
                st.session_state["layout_algo"]),
        )
        st.session_state["node_color_by"] = st.selectbox(
            "Color nodes by", ["source", "year", "degree"],
            index=["source","year","degree"].index(st.session_state["node_color_by"]),
        )
        st.session_state["show_isolated"] = st.checkbox(
            "Show isolated nodes", value=st.session_state["show_isolated"])

        if st.button("Recompute Layout"):
            compute_layout.clear()
            build_networkx_graph.clear()
            st.rerun()

        st.divider()

        # Search
        st.markdown('<div class="section-header">Search Papers</div>', unsafe_allow_html=True)
        st.session_state["search_query"] = st.text_input(
            "Search", value=st.session_state["search_query"],
            placeholder="Title, author, year…", label_visibility="collapsed")

        # Paper list under search
        if not meta.empty:
            q = st.session_state["search_query"].lower()
            filtered = meta
            if q:
                mask = (
                    meta["title"].str.lower().str.contains(q, na=False) |
                    meta["authors"].str.lower().str.contains(q, na=False) |
                    meta["year"].str.lower().str.contains(q, na=False) |
                    meta["venue"].str.lower().str.contains(q, na=False)
                )
                filtered = meta[mask]

            st.markdown(f'<p style="font-size:11px;color:#57606a">{len(filtered)} paper(s)</p>',
                        unsafe_allow_html=True)

            for _, row in filtered.head(40).iterrows():
                pid   = row.get("paper_id","")
                title = row.get("title","—")
                yr    = row.get("year","")
                label = f"{title[:42]}… ({yr})" if len(title)>42 else f"{title} ({yr})"
                is_sel = (st.session_state["selected_node"] == pid)
                style  = "color:#b07d00;font-weight:600" if is_sel else "color:#57606a"

                if st.button(label, key=f"plist_{pid}",
                             help=title):
                    st.session_state["selected_node"] = pid
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB: GRAPH
# ══════════════════════════════════════════════════════════════════════════════
def render_graph_tab():
    G   = build_networkx_graph()
    pos = compute_layout(st.session_state["layout_algo"])

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()

    if n_nodes == 0:
        st.markdown("""
        <div style="text-align:center;padding:60px;color:#57606a">
            <h2>No data yet</h2>
            <p>Go to the <b>Pipeline</b> tab and run collection to populate the graph.</p>
        </div>""", unsafe_allow_html=True)
        return

    # ── Graph + Detail side by side ───────────────────────────────────────────
    graph_col, detail_col = st.columns([3, 1.1], gap="small")

    with graph_col:
        # Toolbar row
        t1, t2, t3, t4 = st.columns([2, 2, 2, 2])
        with t1:
            if st.button("Clear selection", use_container_width=True):
                st.session_state["selected_node"] = None
                st.rerun()
        with t2:
            st.markdown(
                f'<div style="font-size:12px;color:#57606a;padding:6px 0">'
                f'<b style="color:#0969da">{n_nodes}</b> nodes · '
                f'<b style="color:#1a7f37">{n_edges}</b> edges</div>',
                unsafe_allow_html=True)
        with t3:
            show_labels = st.checkbox("Show labels", value=True)
        with t4:
            highlight = st.checkbox("Highlight neighbours", value=True)

        # Build figure
        fig = make_graph_figure(
            G, pos,
            selected_node       = st.session_state["selected_node"],
            highlight_neighbors = highlight,
            node_color_by       = st.session_state["node_color_by"],
            show_isolated       = st.session_state["show_isolated"],
        )

        # Turn off labels if unchecked
        if not show_labels:
            for trace in fig.data:
                if hasattr(trace, "mode") and "text" in str(trace.mode):
                    trace.mode = "markers"

        # Render
        clicked = st.plotly_chart(fig, use_container_width=True,
                                  config={"displayModeBar": True,
                                          "scrollZoom": True,
                                          "modeBarButtonsToRemove": ["lasso2d","select2d"]},
                                  on_select="rerun",
                                  selection_mode="points",
                                  key="main_graph")

        # Handle click
        if clicked and clicked.get("selection"):
            pts = clicked["selection"].get("points", [])
            if pts:
                idx = pts[0].get("point_index")
                # Find node id from node_trace (last data entry before selection ring)
                node_trace = [t for t in fig.data if hasattr(t,"customdata") and t.customdata is not None]
                if node_trace and idx is not None:
                    cdata = node_trace[0].customdata
                    if idx < len(cdata):
                        nid = cdata[idx]
                        if st.session_state["selected_node"] != nid:
                            st.session_state["selected_node"] = nid
                            st.rerun()

        # Gestalt proximity hint
        st.markdown(
            '<p style="font-size:11px;color:#6e7781;text-align:center">'
            'Scroll to zoom · Drag to pan · Click node to inspect · '
            'Node size = in-degree (times cited)</p>',
            unsafe_allow_html=True)

    # ── Detail panel ──────────────────────────────────────────────────────────
    with detail_col:
        sel = st.session_state["selected_node"]
        if not sel or sel not in G.nodes:
            st.markdown("""
            <div style="padding:20px 0;text-align:center;color:#57606a">
                <div style="font-size:32px;margin-bottom:12px;color:#d0d7de">○</div>
                <div style="font-size:13px">Click a node in the graph to see details</div>
            </div>""", unsafe_allow_html=True)
        else:
            data    = G.nodes[sel]
            in_deg  = G.in_degree(sel)
            out_deg = G.out_degree(sel)

            st.markdown(f"""
            <div class="paper-card" style="border-color:#b07d00">
              <div class="paper-title">{data.get('title','—')[:120]}</div>
              <div class="paper-meta" style="margin-top:8px">
                {data.get('year','')} &nbsp;|&nbsp; {data.get('venue','—')[:40]}
              </div>
              <div class="paper-meta">{data.get('authors','').replace('|','·')[:90]}</div>
              <div style="margin-top:8px">{badge_html(data.get('source',''))}</div>
            </div>""", unsafe_allow_html=True)

            m1, m2 = st.columns(2)
            m1.metric("Cites",       out_deg, help="Papers this paper cites (out-edges)")
            m2.metric("Cited by",    in_deg,  help="Papers that cite this (in-edges)")

            doi = data.get("doi","")
            if doi:
                st.markdown(f'<a href="https://doi.org/{doi}" target="_blank" style="color:#0969da;font-size:12px">Open DOI</a>',
                            unsafe_allow_html=True)

            abstr = data.get("abstract","")
            if abstr:
                with st.expander("Abstract"):
                    st.write(abstr)

            # Outgoing edges (papers this cites)
            succ = list(G.successors(sel))
            if succ:
                st.markdown('<div class="section-header">Cites →</div>', unsafe_allow_html=True)
                for s in succ[:15]:
                    sdata = G.nodes.get(s, {})
                    t = sdata.get("title","")[:55] or s
                    if st.button(f"→ {t}", key=f"out_{sel}_{s}",
                                 use_container_width=True):
                        st.session_state["selected_node"] = s
                        st.rerun()
                if len(succ) > 15:
                    st.caption(f"+{len(succ)-15} more")

            # Incoming edges (papers that cite this)
            pred = list(G.predecessors(sel))
            if pred:
                st.markdown('<div class="section-header">← Cited by</div>', unsafe_allow_html=True)
                for p in pred[:15]:
                    pdata = G.nodes.get(p, {})
                    t = pdata.get("title","")[:55] or p
                    if st.button(f"← {t}", key=f"in_{sel}_{p}",
                                 use_container_width=True):
                        st.session_state["selected_node"] = p
                        st.rerun()
                if len(pred) > 15:
                    st.caption(f"+{len(pred)-15} more")


# ══════════════════════════════════════════════════════════════════════════════
# TAB: PAPERS
# ══════════════════════════════════════════════════════════════════════════════
def render_papers_tab():
    meta = load_metadata_cached()
    if meta.empty:
        st.info("No papers yet. Run the pipeline to collect papers.")
        return

    G   = build_networkx_graph()
    in_deg  = dict(G.in_degree())
    out_deg = dict(G.out_degree())

    # Enrich with degree info
    df = meta.copy()
    df["in_degree"]  = df["paper_id"].map(lambda x: in_deg.get(x,0))
    df["out_degree"] = df["paper_id"].map(lambda x: out_deg.get(x,0))

    # Filter bar
    fc1, fc2, fc3 = st.columns([2, 2, 2])
    with fc1:
        srcs = ["All"] + sorted(df["source"].dropna().unique().tolist())
        src_filter = st.selectbox("Source", srcs)
    with fc2:
        yrs  = ["All"] + sorted(df["year"].dropna().unique().tolist(), reverse=True)
        yr_filter = st.selectbox("Year", yrs)
    with fc3:
        sort_by = st.selectbox("Sort by", ["year↓", "year↑", "in_degree↓", "title↑"])

    filtered = df.copy()
    if src_filter != "All":
        filtered = filtered[filtered["source"]==src_filter]
    if yr_filter != "All":
        filtered = filtered[filtered["year"]==yr_filter]

    sort_map = {
        "year↓":       ("year",       False),
        "year↑":       ("year",       True),
        "in_degree↓":  ("in_degree",  False),
        "title↑":      ("title",      True),
    }
    col, asc = sort_map[sort_by]
    filtered = filtered.sort_values(col, ascending=asc)

    st.markdown(f'<p style="color:#57606a;font-size:12px">{len(filtered)} of {len(df)} papers</p>',
                unsafe_allow_html=True)

    # Cards in two columns
    col_a, col_b = st.columns(2, gap="medium")
    for i, (_, row) in enumerate(filtered.iterrows()):
        target_col = col_a if i % 2 == 0 else col_b
        with target_col:
            pid      = row.get("paper_id","")
            title    = row.get("title","—")
            year     = row.get("year","")
            venue    = row.get("venue","")[:50]
            authors  = row.get("authors","").replace("|","·")[:80]
            source   = row.get("source","")
            doi      = row.get("doi","")
            ind      = row.get("in_degree",0)
            outd     = row.get("out_degree",0)

            st.markdown(paper_card_html(row), unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns(3)
            bc2.caption(f"↑{ind} cited")
            bc3.caption(f"↓{outd} cites")
            if bc1.button("Select", key=f"sel_{pid}", use_container_width=True):
                st.session_state["selected_node"] = pid
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB: PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
def render_pipeline_tab():
    job_running = st.session_state["job_running"]

    if job_running:
        st.markdown(
            f'<div class="status-warn">Running: <b>{st.session_state["job_name"]}</b> — '
            f'do not close the browser</div>',
            unsafe_allow_html=True)
        st.markdown("&nbsp;")

    # ── Section 1: Collect Papers ─────────────────────────────────────────────
    st.markdown('<div class="section-header">① Collect Papers</div>', unsafe_allow_html=True)
    st.markdown(
        '<p style="color:#57606a;font-size:12px">Queries all configured APIs (EuropePMC, PMC, arXiv, bioRxiv), '
        'deduplicates by DOI/PMID, then optionally expands via citation neighbours.</p>',
        unsafe_allow_html=True)

    pc1, pc2 = st.columns(2)
    with pc1:
        max_papers   = st.number_input("Max papers", min_value=10, max_value=5000,
                                        value=200, step=50)
        expand_depth = st.number_input("Expansion depth (0=off)", min_value=0,
                                        max_value=3, value=0)
    with pc2:
        skip_pdf  = st.checkbox("Skip PDF downloads", value=True)
        use_custom_q = st.checkbox("Use custom query terms")

    custom_queries = None
    if use_custom_q:
        raw = st.text_area(
            "Query terms (one per line)",
            placeholder="neanderthal genome ancient dna\nhomo naledi new species\nout of africa migration",
            height=110)
        custom_queries = [l.strip() for l in raw.split("\n") if l.strip()] if raw else None

    if st.button("Run Full Collection Pipeline",
                  disabled=job_running, type="primary"):
        _run_in_thread(pipeline_collect,
                       custom_queries, int(max_papers), skip_pdf, int(expand_depth),
                       job_name="collect")
        st.rerun()

    st.divider()

    # ── Section 2: Add Single Paper ───────────────────────────────────────────
    st.markdown('<div class="section-header">② Add a Single Paper</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p style="color:#57606a;font-size:12px">'
        'Fetches metadata from EuropePMC/PMC, adds to corpus, extracts its references, '
        'matches them against existing corpus nodes, and creates citation edges.</p>',
        unsafe_allow_html=True)

    a1, a2 = st.columns(2)
    with a1:
        add_doi  = st.text_input("DOI",  placeholder="10.1038/nature12886")
    with a2:
        add_pmid = st.text_input("PMID", placeholder="24352235")

    if st.button("+ Add & Process Paper",
                  disabled=job_running or (not add_doi and not add_pmid)):
        _run_in_thread(pipeline_add_paper, add_doi.strip(), add_pmid.strip(),
                       job_name="add_paper")
        st.rerun()

    st.divider()

    # ── Section 3: Maintenance ────────────────────────────────────────────────
    st.markdown('<div class="section-header">③ Maintenance</div>', unsafe_allow_html=True)

    m1, m2 = st.columns(2)
    with m1:
        force_reextract = st.checkbox("Force re-extract (ignore cache)")
        if st.button("Re-extract References",
                      disabled=job_running, use_container_width=True):
            _run_in_thread(pipeline_extract_only, force_reextract,
                           job_name="extract_references")
            st.rerun()
    with m2:
        st.markdown("&nbsp;")
        if st.button("Rebuild CSVs Only",
                      disabled=job_running, use_container_width=True):
            _run_in_thread(pipeline_rebuild_csv, job_name="rebuild_csv")
            st.rerun()

    st.divider()

    # ── Live Log ──────────────────────────────────────────────────────────────
    st.markdown('<div class="section-header">Live Log</div>', unsafe_allow_html=True)

    if job_running:
        # Auto-refresh every 2s during a job
        time.sleep(2)
        st.rerun()

    render_log_box()

    # Also show last 50 lines of collection.log
    if COLLECTION_LOG.exists():
        with st.expander("collection.log (last 50 lines)"):
            with open(COLLECTION_LOG, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            st.text("".join(lines[-50:]))


# ══════════════════════════════════════════════════════════════════════════════
# TAB: STATS
# ══════════════════════════════════════════════════════════════════════════════
def render_stats_tab():
    meta = load_metadata_cached()
    refs = load_references_cached()
    G    = build_networkx_graph()

    if meta.empty:
        st.info("No data yet.")
        return

    # ── Top metrics ───────────────────────────────────────────────────────────
    n_papers   = len(meta)
    n_edges    = G.number_of_edges()
    n_refs     = len(refs)
    n_resolved = int((refs["resolution_method"] != "unresolved").sum()) if not refs.empty else 0
    rate       = round(100*n_resolved/max(n_refs,1), 1)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Papers",          n_papers)
    c2.metric("Graph edges",     n_edges)
    c3.metric("Total ref rows",  n_refs)
    c4.metric("Resolved",        n_resolved)
    c5.metric("Resolution rate", f"{rate}%")

    st.divider()

    row1_l, row1_r = st.columns(2, gap="medium")

    # ── Papers by year ────────────────────────────────────────────────────────
    with row1_l:
        st.markdown("**Papers by year**")
        yr_counts = meta["year"].value_counts().sort_index().reset_index()
        yr_counts.columns = ["year", "count"]
        fig_yr = px.bar(yr_counts, x="year", y="count",
                         color_discrete_sequence=["#0969da"],
                         labels={"year":"Year","count":"Papers"})
        fig_yr.update_layout(
            template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", height=260, margin=dict(l=0,r=0,t=10,b=0),
            xaxis=dict(type="category"),
            font=dict(color="#57606a", size=11),
        )
        st.plotly_chart(fig_yr, use_container_width=True)

    # ── Papers by source ──────────────────────────────────────────────────────
    with row1_r:
        st.markdown("**Papers by source**")
        src_counts = meta["source"].value_counts().reset_index()
        src_counts.columns = ["source","count"]
        colors = {"EuropePMC":"#1a7f37","EuropePMC_expansion":"#0969da",
                  "PMC":"#8250df","arXiv":"#9a6700","bioRxiv":"#cf222e"}
        fig_src = px.pie(src_counts, values="count", names="source",
                          color="source", color_discrete_map=colors,
                          hole=0.45)
        fig_src.update_layout(
            template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
            height=260, margin=dict(l=0,r=0,t=10,b=0),
            legend=dict(font=dict(color="#57606a",size=11)),
            font=dict(color="#57606a",size=11),
        )
        st.plotly_chart(fig_src, use_container_width=True)

    row2_l, row2_r = st.columns(2, gap="medium")

    # ── Resolution methods ────────────────────────────────────────────────────
    with row2_l:
        st.markdown("**Edge resolution methods**")
        if not refs.empty:
            rm = refs["resolution_method"].value_counts().reset_index()
            rm.columns = ["method","count"]
            rm["resolved"] = rm["method"] != "unresolved"
            clr = rm["resolved"].map({True:"#1a7f37",False:"#cf222e"})
            fig_rm = px.bar(rm, x="count", y="method", orientation="h",
                             color="resolved",
                             color_discrete_map={True:"#1a7f37",False:"#cf222e"},
                             labels={"count":"Edges","method":"Method"})
            fig_rm.update_layout(
                template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", height=280, margin=dict(l=0,r=0,t=10,b=0),
                showlegend=False, font=dict(color="#57606a",size=11),
            )
            st.plotly_chart(fig_rm, use_container_width=True)

    # ── Degree distribution ───────────────────────────────────────────────────
    with row2_r:
        st.markdown("**In-degree distribution (times cited)**")
        in_degs = [d for _, d in G.in_degree() if d > 0]
        if in_degs:
            fig_deg = px.histogram(in_degs, nbins=20,
                                    color_discrete_sequence=["#8250df"],
                                    labels={"value":"In-degree","count":"Papers"})
            fig_deg.update_layout(
                template="plotly_white", paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)", height=280, margin=dict(l=0,r=0,t=10,b=0),
                font=dict(color="#57606a",size=11), showlegend=False,
            )
            st.plotly_chart(fig_deg, use_container_width=True)

    st.divider()

    # ── Top cited papers ──────────────────────────────────────────────────────
    st.markdown("**Most cited papers in corpus**")
    in_deg_dict = dict(G.in_degree())
    meta_with_deg = meta.copy()
    meta_with_deg["in_degree"] = meta_with_deg["paper_id"].map(
        lambda x: in_deg_dict.get(x, 0))
    top = meta_with_deg.nlargest(15, "in_degree")[
        ["title","year","venue","source","in_degree"]].reset_index(drop=True)
    top.index += 1
    st.dataframe(top, use_container_width=True,
                 column_config={
                     "title":     st.column_config.TextColumn("Title", width="large"),
                     "year":      st.column_config.TextColumn("Year",  width="small"),
                     "venue":     st.column_config.TextColumn("Venue", width="medium"),
                     "source":    st.column_config.TextColumn("Source",width="small"),
                     "in_degree": st.column_config.NumberColumn("Cited by",width="small"),
                 })

    # ── Network stats ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("**Network metrics**")
    n1, n2, n3, n4 = st.columns(4)
    n1.metric("Nodes", G.number_of_nodes())
    n2.metric("Edges", G.number_of_edges())
    try:
        largest_cc = max(nx.weakly_connected_components(G), key=len)
        n3.metric("Largest component", len(largest_cc))
    except:
        n3.metric("Largest component", "—")
    try:
        density = nx.density(G)
        n4.metric("Graph density", f"{density:.4f}")
    except:
        n4.metric("Graph density","—")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    render_sidebar()

    st.markdown("""
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:4px">
        <div>
            <h1 style="font-size:22px;margin:0;color:#24292f">Human Evolution · Citation Graph</h1>
            <p style="font-size:12px;color:#57606a;margin:0">
                Explore citation relationships between paleoanthropology papers
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Job status banner
    if st.session_state["job_running"]:
        st.markdown(
            f'<div class="status-warn" style="margin-bottom:10px">'
            f'<b>{st.session_state["job_name"]}</b> is running — '
            f'graph will refresh when complete</div>',
            unsafe_allow_html=True)

    tab_graph, tab_papers, tab_pipeline, tab_stats = st.tabs(
        ["Graph", "Papers", "Pipeline", "Stats"])

    with tab_graph:
        render_graph_tab()

    with tab_papers:
        render_papers_tab()

    with tab_pipeline:
        render_pipeline_tab()

    with tab_stats:
        render_stats_tab()


if __name__ == "__main__":
    main()
