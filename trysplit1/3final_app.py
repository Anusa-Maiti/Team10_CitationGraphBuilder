"""
final_app.py  –  DS3294 Citation Graph Builder
===============================================
Entry point.  Run with:   streamlit run final_app.py

Pages
  📊 Dashboard         — metrics, quick-start, activity log
  📥 Ingest Papers     — Upload PDF / Manual entry / Batch JSON  (incremental add)
  🔍 Explore Graph     — pyvis interactive graph + per-paper neighbourhood
  📈 Analytics         — PageRank, degree dist, centrality, components, storage
  🗂️  Manage Corpus    — remove, export, re-resolve, restore from disk
  📖 Project Guide     — implementation notes for the assignment
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
import streamlit as st

# ── local modules ─────────────────────────────────────────────────────────────
from styles import apply_custom_css
from data_handler import (
    CORPUS_PATH,
    SAMPLE_PAPERS,
    add_paper_to_graph,
    add_papers_bulk,
    export_edges_json,
    export_nodes_csv,
    export_papers_json,
    extract_paper_from_pdf,
    get_stats,
    init_state,
    load_corpus,
    load_sample,
    remove_paper,
    resolve_all_edges,
    HAS_PYPDF,
    HAS_FUZZY,
)
from visualizer import render_interactive_graph

# ── optional heavy deps ───────────────────────────────────────────────────────
try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG  (must be first Streamlit call)
# ═══════════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Citation Graph Builder",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_custom_css()

# ─── Session state + auto-restore ─────────────────────────────────────────────
init_state()
if get_stats()["nodes"] == 0 and CORPUS_PATH.exists():
    load_corpus()   # silently restore saved corpus on every cold start

G: nx.DiGraph = st.session_state["graph"]

# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<div style='color:#0277bd;font-family:IBM Plex Mono,monospace;font-size:0.8rem;letter-spacing:2px;'>DS3294 PROJECT</div>", unsafe_allow_html=True)
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
    if stats["incremental"]:
        st.markdown(f"<span class='badge-new'>+{stats['incremental']} new</span>", unsafe_allow_html=True)
    if stats.get("pending_edges", 0):
        st.caption(f"⚠️ {stats['pending_edges']} unresolved refs")

    st.markdown("---")
    if st.button("🗑️ Reset Graph", use_container_width=True):
        st.session_state["graph"]    = nx.DiGraph()
        st.session_state["articles"] = {}
        st.session_state["pending_edges"] = []
        st.session_state["log"]      = []
        st.success("Graph reset.")
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.markdown("""
    <div class='main-header'>
        <div class='badge'>DS3294 · Practice Project #13</div>
        <h1>🔬 Citation Graph Builder</h1>
        <p>Extract · Connect · Analyse scientific literature at scale</p>
    </div>""", unsafe_allow_html=True)

    stats = get_stats()
    cols  = st.columns(6)
    pairs = [
        ("Papers",        stats["nodes"],        "metric-card",     "metric-val"),
        ("Citations",     stats["edges"],        "metric-card",     "metric-val"),
        ("Components",    stats["components"],   "metric-card",     "metric-val"),
        ("Avg Degree",    stats["avg_degree"],   "metric-card",     "metric-val"),
        ("Max In-Degree", stats["max_indegree"], "metric-card",     "metric-val"),
        ("New Papers",    stats["incremental"],  "metric-card-new", "metric-val-new"),
    ]
    for col, (label, val, card_cls, val_cls) in zip(cols, pairs):
        with col:
            st.markdown(
                f"<div class='{card_cls}'><div class='{val_cls}'>{val}</div>"
                f"<div class='metric-label'>{label}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")
    col_l, col_r = st.columns([1.4, 1])

    with col_l:
        st.markdown("<div class='section-title'>Quick Start</div>", unsafe_allow_html=True)
        st.markdown("""
        <div class='tip-box'>
        <b>1.</b> Load the 30-paper baseline corpus below.<br>
        <b>2.</b> Go to <em>Ingest Papers</em> to add more papers incrementally.<br>
        <b>3.</b> Use <em>Explore Graph</em> to view the interactive citation network.<br>
        <b>4.</b> Use <em>Analytics</em> for PageRank, centrality, and degree charts.
        </div>""", unsafe_allow_html=True)

        if st.button("🚀 Load Baseline Corpus (30 papers)", use_container_width=True, type="primary"):
            load_sample()
            st.rerun()

        if CORPUS_PATH.exists():
            st.markdown(
                f"<div class='success-box'>💾 Saved corpus found at <code>{CORPUS_PATH}</code>. "
                "It was auto-restored on startup.</div>",
                unsafe_allow_html=True,
            )

        if st.session_state.get("log"):
            st.markdown("<div class='section-title'>Activity Log</div>", unsafe_allow_html=True)
            for msg in reversed(st.session_state["log"][-10:]):
                st.markdown(f"<small style='color:#486581'>{msg}</small>", unsafe_allow_html=True)

    with col_r:
        st.markdown("<div class='section-title'>Pipeline Overview</div>", unsafe_allow_html=True)
        for step, desc in [
            ("① PDF / JSON Ingest",      "Upload PDFs or paste JSON → extract metadata & refs"),
            ("② Reference Resolution",   "DOI match → arXiv ID → fuzzy title (threshold 72)"),
            ("③ Incremental Graph Build","add_papers_bulk() — two-pass, nodes then edges"),
            ("④ Persistence",            "Auto-saved to data/corpus.json after every change"),
            ("⑤ Analysis & Viz",         "PageRank · centrality · pyvis interactive graph"),
        ]:
            st.markdown(
                f"<div class='node-card'><h4>{step}</h4><p>{desc}</p></div>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: INGEST PAPERS  (incremental add)
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📥 Ingest Papers":
    st.markdown("<div class='section-title'>📥 Ingest Papers</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class='tip-box'>
    Add papers <b>incrementally</b> — they are merged into the existing graph and saved
    to <code>data/corpus.json</code> automatically.  Duplicate IDs are silently skipped.
    </div>""", unsafe_allow_html=True)

    tab_pdf, tab_manual, tab_json = st.tabs(["📄 Upload PDF", "✏️ Manual Entry", "📋 Batch JSON"])

    # ── PDF ────────────────────────────────────────────────────────────────────
    with tab_pdf:
        if not HAS_PYPDF:
            st.warning("PyPDF2 not installed — PDF parsing disabled. `pip install PyPDF2`")
        uploaded = st.file_uploader(
            "Drop PDFs here (one or more)", type=["pdf"], accept_multiple_files=True
        )
        if uploaded and st.button("➕ Process & Add PDFs", type="primary"):
            new_count = 0
            for f in uploaded:
                paper = extract_paper_from_pdf(f.read(), f.name)
                # Let user review / fix the extracted ID before committing
                st.write(f"**Extracted:** `{paper['id']}` — {paper['title'][:70]}")
                if add_paper_to_graph(paper, source_tag="pdf"):
                    new_count += 1
            st.success(f"Added {new_count} paper(s). Graph auto-saved.")
            st.rerun()

    # ── Manual entry ───────────────────────────────────────────────────────────
    with tab_manual:
        st.markdown("Fill in the fields below and click Add.")
        c1, c2 = st.columns(2)
        with c1:
            m_id      = st.text_input("Paper ID (slug, e.g. smith2024llm) *", key="m_id")
            m_title   = st.text_input("Title *", key="m_title")
            m_authors = st.text_input("Authors", key="m_authors")
        with c2:
            m_year    = st.number_input("Year", 1990, 2030, 2024, key="m_year")
            m_venue   = st.text_input("Venue / Journal", key="m_venue")
            m_cat     = st.selectbox("Category", ["Core","LLM","Vision","Efficient","Incremental"], index=4, key="m_cat")
        m_url  = st.text_input("URL (arXiv / DOI)", key="m_url")
        m_refs = st.text_area(
            "Reference IDs (one per line — must match existing paper IDs)",
            key="m_refs",
            help="e.g.\nvaswani2017\nbrown2020",
        )

        if st.button("➕ Add Paper", type="primary", key="btn_manual"):
            if not m_id.strip() or not m_title.strip():
                st.error("Paper ID and Title are required.")
            elif m_id.strip() in st.session_state["articles"]:
                st.warning(f"Paper '{m_id.strip()}' already exists in corpus.")
            else:
                refs = [r.strip() for r in m_refs.split("\n") if r.strip()]
                paper = {
                    "id": m_id.strip(), "title": m_title.strip(),
                    "authors": m_authors, "year": int(m_year),
                    "venue": m_venue, "category": m_cat,
                    "url": m_url, "refs": refs,
                }
                add_paper_to_graph(paper, source_tag="manual")
                st.success(f"✅ Added '{m_id.strip()}'. Graph saved.")
                st.rerun()

    # ── Batch JSON ────────────────────────────────────────────────────────────
    with tab_json:
        st.markdown("""
        <div class='tip-box'>
        Paste a JSON array of paper objects.  Each needs at minimum:
        <code>id, title, year</code>.  Optional: <code>refs, authors, venue, url, category</code>.
        </div>""", unsafe_allow_html=True)

        default_example = json.dumps([
            {"id":"he2022","title":"Masked Autoencoders Are Scalable Vision Learners",
             "authors":"He et al.","year":2022,"venue":"CVPR","category":"Vision",
             "url":"https://arxiv.org/abs/2111.06377","refs":["dosovitskiy2020","vaswani2017"]},
            {"id":"chung2022","title":"Scaling Instruction-Finetuned Language Models (Flan-T5)",
             "authors":"Chung et al.","year":2022,"venue":"arXiv","category":"LLM",
             "url":"https://arxiv.org/abs/2210.11416","refs":["raffel2019","brown2020"]},
            {"id":"openai2023","title":"GPT-4 Technical Report",
             "authors":"OpenAI","year":2023,"venue":"arXiv","category":"LLM",
             "url":"https://arxiv.org/abs/2303.08774","refs":["brown2020","ouyang2022"]},
            {"id":"li2023","title":"BLIP-2: Bootstrapping Language-Image Pre-training",
             "authors":"Li et al.","year":2023,"venue":"ICML","category":"Vision",
             "url":"https://arxiv.org/abs/2301.12597","refs":["radford2021","vaswani2017"]},
            {"id":"zeng2022","title":"GLM-130B: An Open Bilingual Pre-trained Model",
             "authors":"Zeng et al.","year":2022,"venue":"ICLR","category":"LLM",
             "url":"https://arxiv.org/abs/2210.02414","refs":["brown2020","vaswani2017"]},
        ], indent=2)

        json_text = st.text_area("Paste JSON array here", value=default_example, height=260)

        if st.button("📤 Import & Add to Graph", type="primary", key="btn_json"):
            try:
                papers = json.loads(json_text)
                if not isinstance(papers, list):
                    st.error("JSON must be an array [ ... ]")
                else:
                    result = add_papers_bulk(papers, source_tag="json")
                    st.success(
                        f"✅ Added {result['added']} new papers, "
                        f"skipped {result['skipped']} duplicates, "
                        f"resolved {result['new_edges']} citation edges."
                    )
                    st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"JSON parse error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: EXPLORE GRAPH
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Explore Graph":
    st.markdown("<div class='section-title'>🕸️ Interactive Citation Graph</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.warning("No papers loaded. Go to Dashboard and load the baseline corpus.")
        st.stop()

    # ── controls ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1: physics_on  = st.checkbox("Physics simulation", value=True)
    with c2: show_labels = st.checkbox("Show node labels", value=True)
    with c3: hi_new      = st.checkbox("Highlight new papers", value=True)
    with c4: max_nodes   = st.slider("Max nodes", 5, min(80, G.number_of_nodes()), min(G.number_of_nodes(), 35))

    if st.button("🔄 Render Graph", type="primary"):
        render_interactive_graph(G, st.session_state["articles"], max_nodes, physics_on, show_labels, hi_new)

    # ── per-paper neighbourhood ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("<div class='section-title'>Per-paper Neighbourhood</div>", unsafe_allow_html=True)

    ids = list(st.session_state["articles"].keys())
    selected = st.selectbox(
        "Select a paper",
        ids,
        format_func=lambda x: f"{x}  —  {st.session_state['articles'][x]['title'][:60]}",
    )
    if selected:
        art   = st.session_state["articles"][selected]
        src   = art.get("source", "baseline")
        badge = f"<span class='badge-new'>incremental</span>" if src != "baseline" else ""
        c_l, c_r = st.columns([2, 1])
        with c_l:
            st.markdown(
                f"<div class='node-card'>"
                f"<h4>📄 {art['title']} {badge}</h4>"
                f"<p><b>Authors:</b> {art.get('authors','—')}</p>"
                f"<p><b>Year:</b> {art.get('year','—')} &nbsp;|&nbsp; "
                f"<b>Venue:</b> {art.get('venue','—')} &nbsp;|&nbsp; "
                f"<b>Category:</b> {art.get('category','—')}</p>"
                f"<p><b>Added:</b> {art.get('added_at','—')[:10]}</p>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if art.get("url"):
                st.markdown(f"[🔗 Open paper]({art['url']})")
        with c_r:
            st.markdown(f"<div class='metric-card'><div class='metric-val'>{G.in_degree(selected)}</div><div class='metric-label'>Cited by</div></div>", unsafe_allow_html=True)
            st.markdown("")
            st.markdown(f"<div class='metric-card'><div class='metric-val'>{G.out_degree(selected)}</div><div class='metric-label'>References</div></div>", unsafe_allow_html=True)

        col_cites, col_refs = st.columns(2)
        with col_cites:
            st.markdown("**Papers this cites →**")
            for r in G.successors(selected):
                a = st.session_state["articles"].get(r, {})
                st.markdown(f"- `{r}` — {a.get('title','?')[:55]}")
            if not list(G.successors(selected)):
                st.markdown("_None in corpus_")
        with col_refs:
            st.markdown("**Papers that cite this →**")
            for c in G.predecessors(selected):
                a = st.session_state["articles"].get(c, {})
                st.markdown(f"- `{c}` — {a.get('title','?')[:55]}")
            if not list(G.predecessors(selected)):
                st.markdown("_None in corpus_")

    # ── full table ────────────────────────────────────────────────────────────
    st.markdown("---")
    rows = [
        {"ID": pid, "Title": art.get("title","")[:70], "Year": art.get("year",""),
         "Category": art.get("category",""), "Source": art.get("source",""),
         "In": G.in_degree(pid), "Out": G.out_degree(pid)}
        for pid, art in st.session_state["articles"].items()
    ]
    df = pd.DataFrame(rows).sort_values("In", ascending=False)
    st.dataframe(df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: ANALYTICS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📈 Analytics":
    st.markdown("<div class='section-title'>📈 Graph Analytics</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.warning("Load data first.")
        st.stop()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Degree Distribution", "PageRank", "Centrality", "Components", "Storage Comparison"]
    )

    # ── degree distribution ───────────────────────────────────────────────────
    with tab1:
        in_d  = [G.in_degree(n)  for n in G.nodes()]
        out_d = [G.out_degree(n) for n in G.nodes()]
        if HAS_PLOTLY:
            fig = px.histogram(
                pd.DataFrame({"In-degree": in_d, "Out-degree": out_d}),
                barmode="overlay", opacity=0.75,
                color_discrete_map={"In-degree": "#0277bd", "Out-degree": "#ef6c00"},
                title="Degree Distribution",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(pd.Series(Counter(in_d), name="In-degree"))
        c1, c2, c3 = st.columns(3)
        c1.metric("Max In-degree",  max(in_d))
        c2.metric("Max Out-degree", max(out_d))
        c3.metric("Mean In-degree", f"{np.mean(in_d):.2f}")

    # ── PageRank ──────────────────────────────────────────────────────────────
    with tab2:
        pr    = nx.pagerank(G, alpha=0.85)
        pr_df = pd.DataFrame([
            {"Paper":     st.session_state["articles"].get(k, {}).get("title", "")[:60],
             "ID":        k,
             "Category":  st.session_state["articles"].get(k, {}).get("category", ""),
             "Source":    st.session_state["articles"].get(k, {}).get("source", ""),
             "PageRank":  round(v, 6),
             "In-degree": G.in_degree(k)}
            for k, v in sorted(pr.items(), key=lambda x: -x[1])
        ])
        if HAS_PLOTLY:
            fig = px.bar(
                pr_df.head(10), x="PageRank", y="Paper", orientation="h",
                color="PageRank", color_continuous_scale="Blues",
                title="Top 10 Papers by PageRank",
            )
            fig.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(pr_df, use_container_width=True, hide_index=True)

    # ── centrality ────────────────────────────────────────────────────────────
    with tab3:
        bc  = nx.betweenness_centrality(G)
        try:    cc = nx.closeness_centrality(G)
        except: cc = {n: 0 for n in G.nodes()}
        cent_df = pd.DataFrame([
            {"Paper":       st.session_state["articles"].get(k, {}).get("title", "")[:60],
             "ID":          k,
             "Betweenness": round(v, 6),
             "Closeness":   round(cc.get(k, 0), 6),
             "In-degree":   G.in_degree(k)}
            for k, v in sorted(bc.items(), key=lambda x: -x[1])
        ])
        if HAS_PLOTLY:
            fig = px.scatter(
                cent_df, x="Betweenness", y="Closeness",
                size="In-degree", hover_name="Paper",
                color="Betweenness", color_continuous_scale="Blues",
                title="Betweenness vs Closeness Centrality",
            )
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(cent_df, use_container_width=True, hide_index=True)

    # ── connected components ──────────────────────────────────────────────────
    with tab4:
        wcc = list(nx.weakly_connected_components(G))
        st.metric("Weakly Connected Components", len(wcc))
        comp_rows = sorted(
            [{"Component": i+1, "Size": len(c),
              "Members": ", ".join(list(c)[:5]) + ("…" if len(c) > 5 else "")}
             for i, c in enumerate(wcc)],
            key=lambda x: -x["Size"],
        )
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
        try:
            st.metric("Longest Citation Chain", nx.dag_longest_path_length(G))
        except Exception:
            st.info("Graph has cycles — longest path not applicable.")

    # ── storage comparison ────────────────────────────────────────────────────
    with tab5:
        n, e = G.number_of_nodes(), G.number_of_edges()
        if HAS_PLOTLY:
            fig = go.Figure(go.Bar(
                x=["NetworkX dict\n(in-memory)", "Edge list\n(CSV)", "SQLite\n(disk)"],
                y=[n*64 + e*128, e*2*32, e*80 + n*200],
                marker_color=["#0277bd", "#29b6f6", "#81d4fa"],
            ))
            fig.update_layout(title="Estimated Storage (bytes)")
            st.plotly_chart(fig, use_container_width=True)
        comp_df = pd.DataFrame({
            "Approach":          ["NetworkX dict", "Edge list (CSV)", "SQLite DB", "Neo4j"],
            "Read speed":        ["⚡ Fast",   "🐢 Slow",    "⚡ Fast",    "⚡ Fast"],
            "Write speed":       ["⚡ Fast",   "✅ Medium",  "✅ Medium",  "✅ Medium"],
            "Persistence":       ["❌ None",   "✅ File",    "✅ File",    "✅ Server"],
            "Query flexibility": ["✅ Python", "❌ Low",     "✅ SQL",     "🌟 Cypher"],
            "Best for":          ["Prototyping","Small export","Medium corpus","Large corpus"],
        })
        st.dataframe(comp_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: MANAGE CORPUS
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "🗂️ Manage Corpus":
    st.markdown("<div class='section-title'>🗂️ Manage Corpus</div>", unsafe_allow_html=True)

    if G.number_of_nodes() == 0:
        st.info("No papers yet. Load baseline on the Dashboard.")
        st.stop()

    # ── remove ────────────────────────────────────────────────────────────────
    st.markdown("**Remove a paper**")
    pid_del = st.selectbox(
        "Select paper to remove",
        list(st.session_state["articles"].keys()),
        format_func=lambda x: f"{x}  —  {st.session_state['articles'][x]['title'][:55]}",
    )
    if st.button("🗑️ Remove Paper", type="primary"):
        remove_paper(pid_del)
        st.success(f"Removed '{pid_del}' and saved corpus.")
        st.rerun()

    st.markdown("---")

    # ── re-resolve ────────────────────────────────────────────────────────────
    st.markdown("**Re-resolve all citation edges**")
    st.markdown(
        "<div class='tip-box'>Run this after any bulk import to wire any edges that "
        "couldn't be drawn because the target paper hadn't been added yet.</div>",
        unsafe_allow_html=True,
    )
    if st.button("🔄 Re-resolve all edges"):
        n = resolve_all_edges()
        st.success(f"Done — {n} new edges added and corpus saved.")

    st.markdown("---")

    # ── restore from disk ─────────────────────────────────────────────────────
    st.markdown("**Restore from saved corpus**")
    if CORPUS_PATH.exists():
        if st.button("📂 Reload corpus.json"):
            n = load_corpus()
            st.success(f"Restored {n} papers from {CORPUS_PATH}.")
            st.rerun()
    else:
        st.info("No saved corpus found at data/corpus.json.")

    st.markdown("---")

    # ── export ────────────────────────────────────────────────────────────────
    st.markdown("**Export**")
    ec1, ec2, ec3 = st.columns(3)
    with ec1:
        st.download_button("⬇️ Papers JSON",  export_papers_json(), "papers.json",  "application/json")
    with ec2:
        st.download_button("⬇️ Edges JSON",   export_edges_json(),  "edges.json",   "application/json")
    with ec3:
        st.download_button("⬇️ Nodes CSV",    export_nodes_csv(),   "nodes.csv",    "text/csv")

    st.markdown("---")

    # ── corpus inventory ──────────────────────────────────────────────────────
    st.markdown("**Corpus inventory**")
    inv = [
        {"ID": pid, "Title": art.get("title","")[:65],
         "Year": art.get("year",""), "Category": art.get("category",""),
         "Source": art.get("source",""), "Added": art.get("added_at","")[:10],
         "In": G.in_degree(pid), "Out": G.out_degree(pid)}
        for pid, art in st.session_state["articles"].items()
    ]
    df_inv = pd.DataFrame(inv).sort_values("Added", ascending=False)
    st.dataframe(df_inv, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: PROJECT GUIDE
# ═══════════════════════════════════════════════════════════════════════════════
elif page == "📖 Project Guide":
    st.markdown("<div class='section-title'>📖 Project #13 — Implementation Guide</div>", unsafe_allow_html=True)
    st.markdown("""
    <div class='tip-box'>
    This guide covers every requirement in the brief, with concrete code examples.
    </div>""", unsafe_allow_html=True)

    st.markdown("### 1. Corpus Collection")
    st.markdown("""
| Source | Access | Rate Limit | Search Terms |
|--------|--------|------------|--------------|
| arXiv | REST API | 1 req/3 s | `all:transformer attention` |
| Semantic Scholar | Graph API | 100/min | title, DOI, arXiv ID |
| PubMed Central | OAI-PMH | 3 req/s | full-text PDFs, XML |

```bash
# Download 30 arXiv PDFs on Transformers
python arxiv_downloader.py --query "attention transformer" --max 30
```""")

    st.markdown("### 2. Metadata Extraction")
    st.markdown("""
```python
# Embedded metadata (clean when available)
reader = PyPDF2.PdfReader("paper.pdf")
meta   = reader.metadata          # /Title, /Author

# Text heuristics (fallback)
text   = "\\n".join(p.extract_text() for p in reader.pages)
year   = re.search(r"\\b(19[9]\\d|20[012]\\d)\\b", text).group()
```""")

    st.markdown("### 3. Reference Resolution (Phase 5 of README)")
    st.markdown("""
Three strategies in order of confidence:
1. **DOI exact match** — `10.\\d{4,}/\\S+`
2. **arXiv ID match** — `\\d{4}\\.\\d{4,5}`
3. **Fuzzy title match** — `fuzz.token_set_ratio ≥ 72`

```python
from data_handler import resolve_refs_from_text
matched_ids = resolve_refs_from_text(raw_ref_strings)
```""")

    st.markdown("### 4. Incremental Update")
    st.markdown("""
```python
from data_handler import add_papers_bulk

new_papers = [{"id":"gpt4_2023", "title":"GPT-4 Technical Report",
               "refs":["brown2020","ouyang2022"], ...}]
result = add_papers_bulk(new_papers, source_tag="incremental")
# → {added: 1, skipped: 0, new_edges: 2}
# corpus.json updated automatically
```
**How it works:**
- Pass 1 adds all nodes
- Pass 2 wires all edges (including intra-batch cross-refs)
- `pending_edges` stash retries unresolved refs on every future add""")

    st.markdown("### 5. Graph Analysis")
    st.markdown("""
| Metric | Code |
|--------|------|
| PageRank | `nx.pagerank(G, alpha=0.85)` |
| Degree distribution | `Counter(dict(G.in_degree()).values())` |
| Betweenness centrality | `nx.betweenness_centrality(G)` |
| Weakly connected components | `nx.weakly_connected_components(G)` |
| Longest citation chain | `nx.dag_longest_path_length(G)` |""")

    st.markdown("### 6. File Structure")
    st.markdown("""
```
project/
├── final_app.py       ← Streamlit entry point  (this file)
├── data_handler.py    ← corpus, graph, persistence, PDF extraction
├── visualizer.py      ← pyvis interactive graph renderer
├── styles.py          ← all CSS in one place
├── data/
│   ├── corpus.json    ← auto-saved after every change
│   └── pdfs/          ← downloaded PDFs
└── requirements.txt
```""")

    st.markdown("""
    <div class='warn-box'>
    <b>⚠️ Common pitfalls:</b><br>
    • Add papers whose IDs already exist in corpus → silently skipped (by design).<br>
    • Refs pointing to IDs not yet in corpus → stored in <code>pending_edges</code>,
      resolved when those papers are added.<br>
    • Run <em>Re-resolve all edges</em> after any large batch import to clean up.
    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown("---")
st.markdown(
    f"<p style='text-align:center;color:#829ab1;font-size:0.78rem;"
    f"font-family:IBM Plex Mono,monospace;'>DS3294 Citation Graph Builder · "
    f"Streamlit · {datetime.now().year}</p>",
    unsafe_allow_html=True,
)
