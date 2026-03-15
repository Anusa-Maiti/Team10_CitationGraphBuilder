"""
final_app.py  –  DS3294 Citation Graph Builder
Run:  streamlit run final_app.py
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

from styles import apply_custom_css
from data_handler import (
    CORPUS_PATH, SAMPLE_PAPERS, HAS_PYPDF, HAS_FUZZY,
    add_paper_to_graph, add_papers_bulk,
    export_edges_json, export_nodes_csv, export_papers_json,
    extract_paper_from_pdf, suggest_refs_from_text,
    get_known_ids, get_stats, init_state,
    load_corpus, load_sample, remove_paper, resolve_all_edges,
)
from visualizer import render_interactive_graph

try:
    import plotly.express as px
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

st.set_page_config(page_title="Citation Graph Builder", page_icon="🔬",
                   layout="wide", initial_sidebar_state="expanded")
apply_custom_css()
init_state()

# Auto-restore saved corpus on cold start
if get_stats()["nodes"] == 0 and CORPUS_PATH.exists():
    load_corpus()

# ── CRITICAL: always read G fresh from session_state ─────────────────────────
# Never do  G = st.session_state["graph"]  at module level — after Reset the
# session_state["graph"] is replaced with a new DiGraph but the cached variable
# still points to the old object. Always use st.session_state["graph"] inline.

with st.sidebar:
    st.markdown("<div style='color:#0277bd;font-family:IBM Plex Mono,monospace;font-size:0.8rem;letter-spacing:2px;'>DS3294 PROJECT</div>", unsafe_allow_html=True)
    st.markdown("## 🔬 Citation Graph")
    st.markdown("---")
    page = st.radio("Navigation", ["📊 Dashboard","📥 Ingest Papers",
                                   "🔍 Explore Graph","📈 Analytics",
                                   "🗂️ Manage Corpus","📖 Project Guide"])
    st.markdown("---")
    stats = get_stats()
    st.markdown(f"**Corpus:** `{stats['nodes']}` papers")
    st.markdown(f"**Citations:** `{stats['edges']}` edges")
    if stats["incremental"]:
        st.markdown(f"<span class='badge-new'>+{stats['incremental']} new</span>", unsafe_allow_html=True)
    st.markdown("---")
    if st.button("🗑️ Reset Graph", use_container_width=True):
        st.session_state["graph"]    = nx.DiGraph()
        st.session_state["articles"] = {}
        st.session_state["log"]      = []
        st.success("Graph reset.")
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
if page == "📊 Dashboard":
    st.markdown("""<div class='main-header'><div class='badge'>DS3294 · Practice Project #13</div>
    <h1>🔬 Citation Graph Builder</h1>
    <p>Extract · Connect · Analyse scientific literature at scale</p></div>""", unsafe_allow_html=True)

    stats = get_stats()
    cols  = st.columns(6)
    for col, (lbl, val, cc, vc) in zip(cols, [
        ("Papers",       stats["nodes"],       "metric-card",     "metric-val"),
        ("Citations",    stats["edges"],       "metric-card",     "metric-val"),
        ("Components",   stats["components"],  "metric-card",     "metric-val"),
        ("Avg Degree",   stats["avg_degree"],  "metric-card",     "metric-val"),
        ("Max In-Deg",   stats["max_indegree"],"metric-card",     "metric-val"),
        ("New Papers",   stats["incremental"], "metric-card-new", "metric-val-new"),
    ]):
        with col:
            st.markdown(f"<div class='{cc}'><div class='{vc}'>{val}</div>"
                        f"<div class='metric-label'>{lbl}</div></div>", unsafe_allow_html=True)

    st.markdown("---")
    col_l, col_r = st.columns([1.4, 1])
    with col_l:
        st.markdown("<div class='section-title'>Quick Start</div>", unsafe_allow_html=True)
        st.markdown("""<div class='tip-box'>
        <b>1.</b> Load the 30-paper baseline corpus below.<br>
        <b>2.</b> Go to <em>Ingest Papers</em> to add new papers — edges are wired automatically.<br>
        <b>3.</b> Use <em>Explore Graph</em> to view the interactive citation network.<br>
        <b>4.</b> Use <em>Analytics</em> for PageRank, centrality, and degree charts.
        </div>""", unsafe_allow_html=True)
        if st.button("🚀 Load Baseline Corpus (30 papers)", use_container_width=True, type="primary"):
            load_sample(); st.rerun()
        if CORPUS_PATH.exists():
            st.markdown(f"<div class='success-box'>💾 <code>{CORPUS_PATH}</code> auto-restored on startup.</div>", unsafe_allow_html=True)
        if st.session_state.get("log"):
            st.markdown("<div class='section-title'>Activity Log</div>", unsafe_allow_html=True)
            for msg in reversed(st.session_state["log"][-12:]):
                st.markdown(f"<small style='color:#486581'>{msg}</small>", unsafe_allow_html=True)
    with col_r:
        st.markdown("<div class='section-title'>Pipeline Overview</div>", unsafe_allow_html=True)
        for step, desc in [
            ("① Ingest",       "PDF / Manual / Batch JSON"),
            ("② Ref pick",     "User selects which papers it cites"),
            ("③ force_rewire()","Reads articles[], draws every possible edge"),
            ("④ Persist",      "Auto-saved to data/corpus.json"),
            ("⑤ Visualise",    "pyvis graph · PageRank · centrality"),
        ]:
            st.markdown(f"<div class='node-card'><h4>{step}</h4><p>{desc}</p></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
elif page == "📥 Ingest Papers":
    st.markdown("<div class='section-title'>📥 Ingest Papers</div>", unsafe_allow_html=True)
    st.markdown("""<div class='tip-box'>
    Papers are merged into the existing graph incrementally.
    <b>Edges are guaranteed</b> — the wiring step reads directly from the stored refs list,
    so there is no way to add a paper without its edges being drawn.
    </div>""", unsafe_allow_html=True)

    tab_pdf, tab_manual, tab_json = st.tabs(["📄 Upload PDF","✏️ Manual Entry","📋 Batch JSON"])

    # ── PDF ────────────────────────────────────────────────────────────────────
    with tab_pdf:
        if not HAS_PYPDF:
            st.warning("PyPDF2 not installed — `pip install PyPDF2`")

        uploaded = st.file_uploader("Drop a PDF", type=["pdf"], accept_multiple_files=False)
        if uploaded:
            file_bytes = uploaded.read()
            paper      = extract_paper_from_pdf(file_bytes, uploaded.name)
            raw_text   = paper.pop("_raw_text", "")

            st.markdown("**Step 1 — Review extracted metadata**")
            c1, c2 = st.columns(2)
            with c1:
                paper["id"]      = st.text_input("Paper ID *", value=paper["id"], key="pdf_id")
                paper["title"]   = st.text_input("Title *",    value=paper["title"], key="pdf_title")
                paper["authors"] = st.text_input("Authors",    value=paper["authors"], key="pdf_authors")
            with c2:
                paper["year"]    = st.number_input("Year", 1990, 2030, int(paper["year"]), key="pdf_year")
                paper["venue"]   = st.text_input("Venue", value=paper["venue"], key="pdf_venue")
                paper["url"]     = st.text_input("URL",   value=paper["url"],   key="pdf_url")
                paper["category"]= st.selectbox("Category",
                    ["Core","LLM","Vision","Efficient","Incremental"], index=4, key="pdf_cat")

            st.markdown("**Step 2 — Select which papers this PDF cites**")
            st.markdown("""<div class='tip-box'>
            These are the papers from your existing corpus that this PDF likely cites.
            <b>Tick the boxes</b> for the ones that are correct.  You can also type IDs manually below.
            </div>""", unsafe_allow_html=True)

            # Suggested candidates from fuzzy match on full PDF text
            suggestions = suggest_refs_from_text(raw_text) if raw_text else []
            checked_ids = []
            if suggestions:
                st.markdown("**Suggested (fuzzy-matched from PDF text):**")
                for sug in suggestions:
                    label = f"`{sug['id']}` — {sug['title']} (score: {sug['score']})"
                    if st.checkbox(label, key=f"sug_{sug['id']}"):
                        checked_ids.append(sug["id"])

            st.markdown("**Or type additional IDs manually (one per line):**")
            st.caption("Known IDs: " + "  ·  ".join(get_known_ids()[:15]) + "  …")
            manual_refs = st.text_area("Ref IDs", key="pdf_manual_refs", height=80)
            manual_ids  = [r.strip() for r in manual_refs.split("\n") if r.strip()]

            # Merge confirmed + manual
            all_refs = list(dict.fromkeys(checked_ids + manual_ids))  # deduplicate, preserve order
            if all_refs:
                st.markdown(f"**Will cite:** {', '.join(f'`{r}`' for r in all_refs)}")

                # Validate: warn if any ID not in corpus
                known = set(get_known_ids())
                bad   = [r for r in all_refs if r not in known]
                if bad:
                    st.warning(f"These IDs are not in the corpus — they will be skipped: {bad}")

            paper["refs"] = [r for r in all_refs if r in set(get_known_ids())]

            if st.button("➕ Add PDF Paper", type="primary", key="btn_pdf"):
                if not paper["id"].strip() or not paper["title"].strip():
                    st.error("Paper ID and Title are required.")
                elif paper["id"] in st.session_state["articles"]:
                    st.warning(f"'{paper['id']}' already in corpus.")
                else:
                    result = add_paper_to_graph(paper, source_tag="pdf")
                    if result:
                        # Immediately confirm edges were drawn
                        G    = st.session_state["graph"]
                        pid  = paper["id"]
                        drawn = [r for r in paper["refs"] if G.has_edge(pid, r)]
                        st.success(f"✅ Added '{pid}'. Edges drawn to: {drawn if drawn else 'none'}")
                        st.rerun()

    # ── Manual entry ───────────────────────────────────────────────────────────
    with tab_manual:
        st.markdown("Fill in the fields and click Add.")
        c1, c2 = st.columns(2)
        with c1:
            m_id      = st.text_input("Paper ID (e.g. smith2024llm) *", key="m_id")
            m_title   = st.text_input("Title *", key="m_title")
            m_authors = st.text_input("Authors", key="m_authors")
        with c2:
            m_year  = st.number_input("Year", 1990, 2030, 2024, key="m_year")
            m_venue = st.text_input("Venue", key="m_venue")
            m_cat   = st.selectbox("Category",
                ["Core","LLM","Vision","Efficient","Incremental"], index=4, key="m_cat")
        m_url = st.text_input("URL (arXiv / DOI)", key="m_url")

        st.markdown("**Select references from existing corpus:**")
        st.caption("Tick papers this new paper cites:")
        all_ids     = get_known_ids()
        checked_ref = []
        # Show in a compact grid
        cols_grid = st.columns(3)
        for i, pid_opt in enumerate(all_ids):
            art_opt = st.session_state["articles"].get(pid_opt, {})
            label   = f"`{pid_opt}` ({art_opt.get('year','')})"
            if cols_grid[i % 3].checkbox(label, key=f"mref_{pid_opt}"):
                checked_ref.append(pid_opt)

        # Also allow free-text in case they want to type IDs
        extra_refs = st.text_area("Or type extra IDs manually (one per line):", key="m_extra_refs", height=60)
        extra_ids  = [r.strip() for r in extra_refs.split("\n") if r.strip() and r.strip() in set(all_ids)]
        final_refs = list(dict.fromkeys(checked_ref + extra_ids))

        if final_refs:
            st.markdown(f"**Will cite:** {', '.join(f'`{r}`' for r in final_refs)}")

        if st.button("➕ Add Paper", type="primary", key="btn_manual"):
            if not m_id.strip() or not m_title.strip():
                st.error("Paper ID and Title are required.")
            elif m_id.strip() in st.session_state["articles"]:
                st.warning(f"'{m_id.strip()}' already exists in corpus.")
            else:
                paper = {"id": m_id.strip(), "title": m_title.strip(),
                         "authors": m_authors, "year": int(m_year),
                         "venue": m_venue, "category": m_cat,
                         "url": m_url, "refs": final_refs}
                add_paper_to_graph(paper, source_tag="manual")
                # Confirm edges
                G   = st.session_state["graph"]
                pid = m_id.strip()
                drawn = [r for r in final_refs if G.has_edge(pid, r)]
                st.success(f"✅ Added '{pid}'. Edges drawn to: {drawn if drawn else 'none'}")
                st.rerun()

    # ── Batch JSON ────────────────────────────────────────────────────────────
    with tab_json:
        st.markdown("""<div class='tip-box'>
        Paste a JSON array.  Each object needs at minimum <code>id, title, year</code>.
        The <code>refs</code> field must contain <b>exact IDs</b> from the existing corpus.
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
                    st.error("Must be a JSON array [ ... ]")
                else:
                    result = add_papers_bulk(papers, source_tag="json")
                    # Show edge confirmation per paper
                    G = st.session_state["graph"]
                    edge_summary = []
                    for p in papers:
                        pid   = p.get("id","")
                        refs  = p.get("refs",[])
                        drawn = [r for r in refs if G.has_node(pid) and G.has_edge(pid, r)]
                        if pid:
                            edge_summary.append(f"`{pid}` → {drawn}")
                    st.success(
                        f"✅ Added {result['added']}, skipped {result['skipped']}, "
                        f"{result['new_edges']} edges drawn.")
                    for line in edge_summary:
                        st.markdown(f"  {line}")
                    st.rerun()
            except json.JSONDecodeError as e:
                st.error(f"JSON error: {e}")

# ─────────────────────────────────────────────────────────────────────────────
elif page == "🔍 Explore Graph":
    G = st.session_state["graph"]   # read fresh here, not at module level
    st.markdown("<div class='section-title'>🕸️ Interactive Citation Graph</div>", unsafe_allow_html=True)
    if G.number_of_nodes() == 0:
        st.warning("Load papers first."); st.stop()

    c1,c2,c3,c4 = st.columns(4)
    with c1: physics_on  = st.checkbox("Physics", value=True)
    with c2: show_labels = st.checkbox("Labels",  value=True)
    with c3: hi_new      = st.checkbox("Highlight new", value=True)
    with c4: max_nodes   = st.slider("Max nodes", 5, min(80, G.number_of_nodes()), min(G.number_of_nodes(), 35))

    if st.button("🔄 Render Graph", type="primary"):
        render_interactive_graph(G, st.session_state["articles"], max_nodes, physics_on, show_labels, hi_new)

    st.markdown("---")
    st.markdown("<div class='section-title'>Per-paper Neighbourhood</div>", unsafe_allow_html=True)
    ids      = list(st.session_state["articles"].keys())
    selected = st.selectbox("Select a paper", ids,
        format_func=lambda x: f"{x}  —  {st.session_state['articles'][x]['title'][:60]}")
    if selected:
        art   = st.session_state["articles"][selected]
        src   = art.get("source","baseline")
        badge = "<span class='badge-new'>incremental</span>" if src != "baseline" else ""
        cl, cr = st.columns([2,1])
        with cl:
            st.markdown(
                f"<div class='node-card'><h4>{art['title']} {badge}</h4>"
                f"<p>{art.get('authors','—')} · {art.get('year','—')} · {art.get('venue','—')}</p>"
                f"<p><b>Category:</b> {art.get('category','—')} · <b>Source:</b> {src}</p>"
                f"<p><b>Refs stored:</b> {art.get('refs',[])}</p></div>",
                unsafe_allow_html=True)
            if art.get("url"): st.markdown(f"[🔗 Open paper]({art['url']})")
        with cr:
            st.markdown(f"<div class='metric-card'><div class='metric-val'>{G.in_degree(selected)}</div><div class='metric-label'>Cited by</div></div>", unsafe_allow_html=True)
            st.markdown("")
            st.markdown(f"<div class='metric-card'><div class='metric-val'>{G.out_degree(selected)}</div><div class='metric-label'>References</div></div>", unsafe_allow_html=True)
        c_out, c_in = st.columns(2)
        with c_out:
            st.markdown("**Cites →**")
            for r in G.successors(selected):
                st.markdown(f"- `{r}` — {st.session_state['articles'].get(r,{}).get('title','?')[:50]}")
            if not list(G.successors(selected)): st.markdown("_None_")
        with c_in:
            st.markdown("**Cited by →**")
            for c in G.predecessors(selected):
                st.markdown(f"- `{c}` — {st.session_state['articles'].get(c,{}).get('title','?')[:50]}")
            if not list(G.predecessors(selected)): st.markdown("_None_")

    st.markdown("---")
    rows = [{"ID":pid,"Title":art.get("title","")[:65],"Year":art.get("year",""),
             "Cat":art.get("category",""),"Source":art.get("source",""),
             "Refs":str(art.get("refs",[])),
             "In":G.in_degree(pid),"Out":G.out_degree(pid)}
            for pid,art in st.session_state["articles"].items()]
    st.dataframe(pd.DataFrame(rows).sort_values("In",ascending=False),
                 use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
elif page == "📈 Analytics":
    G = st.session_state["graph"]
    st.markdown("<div class='section-title'>📈 Graph Analytics</div>", unsafe_allow_html=True)
    if G.number_of_nodes() == 0:
        st.warning("Load data first."); st.stop()

    tab1,tab2,tab3,tab4,tab5 = st.tabs(
        ["Degree Distribution","PageRank","Centrality","Components","Storage"])

    with tab1:
        in_d  = [G.in_degree(n)  for n in G.nodes()]
        out_d = [G.out_degree(n) for n in G.nodes()]
        if HAS_PLOTLY:
            fig = px.histogram(pd.DataFrame({"In-degree":in_d,"Out-degree":out_d}),
                barmode="overlay", opacity=0.75,
                color_discrete_map={"In-degree":"#0277bd","Out-degree":"#ef6c00"},
                title="Degree Distribution")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(pd.Series(Counter(in_d), name="In-degree"))
        c1,c2,c3 = st.columns(3)
        c1.metric("Max In-degree",  max(in_d))
        c2.metric("Max Out-degree", max(out_d))
        c3.metric("Mean In-degree", f"{np.mean(in_d):.2f}")

    with tab2:
        pr = nx.pagerank(G, alpha=0.85)
        pr_df = pd.DataFrame([
            {"Paper": st.session_state["articles"].get(k,{}).get("title","")[:60],
             "ID":k,"Category":st.session_state["articles"].get(k,{}).get("category",""),
             "Source":st.session_state["articles"].get(k,{}).get("source",""),
             "PageRank":round(v,6),"In-degree":G.in_degree(k)}
            for k,v in sorted(pr.items(),key=lambda x:-x[1])])
        if HAS_PLOTLY:
            fig = px.bar(pr_df.head(10), x="PageRank", y="Paper", orientation="h",
                color="PageRank", color_continuous_scale="Blues", title="Top 10 by PageRank")
            fig.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(pr_df, use_container_width=True, hide_index=True)

    with tab3:
        bc = nx.betweenness_centrality(G)
        try:    cc = nx.closeness_centrality(G)
        except: cc = {n:0 for n in G.nodes()}
        cent_df = pd.DataFrame([
            {"Paper":st.session_state["articles"].get(k,{}).get("title","")[:60],
             "ID":k,"Betweenness":round(v,6),"Closeness":round(cc.get(k,0),6),
             "In-degree":G.in_degree(k)}
            for k,v in sorted(bc.items(),key=lambda x:-x[1])])
        if HAS_PLOTLY:
            fig = px.scatter(cent_df,x="Betweenness",y="Closeness",size="In-degree",
                hover_name="Paper",color="Betweenness",color_continuous_scale="Blues",
                title="Betweenness vs Closeness Centrality")
            st.plotly_chart(fig, use_container_width=True)
        st.dataframe(cent_df, use_container_width=True, hide_index=True)

    with tab4:
        wcc = list(nx.weakly_connected_components(G))
        st.metric("Weakly Connected Components", len(wcc))
        comp_rows = sorted([{"Component":i+1,"Size":len(c),
            "Members":", ".join(list(c)[:5])+("…" if len(c)>5 else "")}
            for i,c in enumerate(wcc)],key=lambda x:-x["Size"])
        st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
        try:    st.metric("Longest Citation Chain", nx.dag_longest_path_length(G))
        except: st.info("Graph has cycles — longest path not applicable.")

    with tab5:
        n,e = G.number_of_nodes(), G.number_of_edges()
        if HAS_PLOTLY:
            fig = go.Figure(go.Bar(
                x=["NetworkX dict","Edge list (CSV)","SQLite"],
                y=[n*64+e*128, e*64, e*80+n*200],
                marker_color=["#0277bd","#29b6f6","#81d4fa"]))
            fig.update_layout(title="Estimated Storage (bytes)")
            st.plotly_chart(fig, use_container_width=True)
        comp_df = pd.DataFrame({
            "Approach":          ["NetworkX dict","Edge list (CSV)","SQLite DB","Neo4j"],
            "Read speed":        ["⚡ Fast","🐢 Slow","⚡ Fast","⚡ Fast"],
            "Write speed":       ["⚡ Fast","✅ Medium","✅ Medium","✅ Medium"],
            "Persistence":       ["❌ None","✅ File","✅ File","✅ Server"],
            "Query flexibility": ["✅ Python","❌ Low","✅ SQL","🌟 Cypher"],
            "Best for":          ["Prototyping","Small export","Medium corpus","Large corpus"],
        })
        st.dataframe(comp_df, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
elif page == "🗂️ Manage Corpus":
    G = st.session_state["graph"]
    st.markdown("<div class='section-title'>🗂️ Manage Corpus</div>", unsafe_allow_html=True)
    if G.number_of_nodes() == 0:
        st.info("No papers yet."); st.stop()

    st.markdown("**Remove a paper**")
    pid_del = st.selectbox("Select to remove", list(st.session_state["articles"].keys()),
        format_func=lambda x: f"{x}  —  {st.session_state['articles'][x]['title'][:55]}")
    if st.button("🗑️ Remove Paper", type="primary"):
        remove_paper(pid_del); st.success(f"Removed '{pid_del}'."); st.rerun()

    st.markdown("---")
    st.markdown("**Re-resolve all citation edges**")
    st.markdown("<div class='tip-box'>Runs force_rewire() — reads refs from every paper and draws all possible edges.</div>", unsafe_allow_html=True)
    if st.button("🔄 Re-resolve all edges"):
        n = resolve_all_edges()
        st.success(f"{n} new edges added." if n else "Graph already fully wired.")

    st.markdown("---")
    if CORPUS_PATH.exists():
        st.markdown("**Restore from saved corpus**")
        if st.button("📂 Reload corpus.json"):
            n = load_corpus(); st.success(f"Restored {n} papers."); st.rerun()

    st.markdown("---")
    st.markdown("**Export**")
    ec1,ec2,ec3 = st.columns(3)
    with ec1: st.download_button("⬇️ Papers JSON", export_papers_json(), "papers.json","application/json")
    with ec2: st.download_button("⬇️ Edges JSON",  export_edges_json(),  "edges.json", "application/json")
    with ec3: st.download_button("⬇️ Nodes CSV",   export_nodes_csv(),   "nodes.csv",  "text/csv")

    st.markdown("---")
    st.markdown("**Corpus inventory** (refs column shows what's stored)")
    inv = [{"ID":pid,"Title":art.get("title","")[:60],"Year":art.get("year",""),
             "Cat":art.get("category",""),"Source":art.get("source",""),
             "Refs":str(art.get("refs",[])),
             "In":G.in_degree(pid),"Out":G.out_degree(pid)}
           for pid,art in st.session_state["articles"].items()]
    st.dataframe(pd.DataFrame(inv).sort_values("In",ascending=False),
                 use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
elif page == "📖 Project Guide":
    st.markdown("<div class='section-title'>📖 Project #13 — Implementation Guide</div>", unsafe_allow_html=True)
    st.markdown("""
### Why edges were missing — and how it's fixed

The old code had three bugs:
1. `G = st.session_state["graph"]` at module level → after Reset, this cached variable still pointed to the OLD graph object.
2. `_wire_edges()` read from the passed-in dict instead of from `articles[]`. If the dict drifted, refs were empty.
3. PDF extraction returned `refs=[]` because the fuzzy matcher almost never matched raw PDF reference text to clean titles.

**The fix:**  
- `_G()` function always fetches the live graph from session_state — never cached.  
- `force_rewire()` reads from `articles[]` (single source of truth) and draws ALL possible edges unconditionally. Called after every mutation.  
- PDF tab now shows suggested matches and a checkbox grid — user confirms refs before commit.

### Incremental add in 3 lines
```python
paper = {"id": "gpt4_2023", "title": "GPT-4 Technical Report",
         "refs": ["brown2020", "ouyang2022"], ...}
add_paper_to_graph(paper, source_tag="incremental")
# → force_rewire() runs → edges gpt4_2023→brown2020 and gpt4_2023→ouyang2022 drawn
# → corpus.json updated automatically
```

### Ref ID rules
- IDs are **case-sensitive** and must match exactly: `vaswani2017` not `Vaswani2017`
- Trailing spaces are stripped automatically
- If you type an ID that doesn't exist in the corpus, it is silently skipped
- Run **Re-resolve all edges** after any bulk import to catch anything missed

### File structure
```
project/
├── final_app.py      ← entry point  (streamlit run final_app.py)
├── data_handler.py   ← all graph logic + force_rewire()
├── visualizer.py     ← pyvis graph renderer
├── styles.py         ← CSS
└── data/
    └── corpus.json   ← auto-saved after every change
```
""")

# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"<p style='text-align:center;color:#829ab1;font-size:0.78rem;"
            f"font-family:IBM Plex Mono,monospace;'>DS3294 Citation Graph Builder · {datetime.now().year}</p>",
            unsafe_allow_html=True)
