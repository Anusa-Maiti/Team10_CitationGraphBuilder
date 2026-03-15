"""
visualizer.py  –  DS3294 Citation Graph Builder
================================================
Renders the interactive pyvis citation graph.
Colour-codes nodes by category (Core / Vision / Efficient / LLM / Incremental).
Node size ∝ PageRank.  Hover tooltip includes clickable DOI link.
"""

import os
import tempfile

import networkx as nx
import streamlit as st

try:
    from pyvis.network import Network
    import streamlit.components.v1 as components
    HAS_PYVIS = True
except ImportError:
    HAS_PYVIS = False


# ── category colour palette ───────────────────────────────────────────────────
COLOUR_MAP = {
    "Core":        {"background": "#29b6f6", "border": "#0277bd"},
    "Vision":      {"background": "#ffa726", "border": "#ef6c00"},
    "Efficient":   {"background": "#66bb6a", "border": "#2e7d32"},
    "LLM":         {"background": "#ab47bc", "border": "#6a1b9a"},
    # New incremental papers get a distinct teal so they stand out
    "Incremental": {"background": "#26c6da", "border": "#00838f"},
}
_DEFAULT_COLOUR = {"background": "#90a4ae", "border": "#546e7a"}


def render_interactive_graph(
    G: nx.DiGraph,
    articles_dict: dict,
    max_nodes: int,
    physics_on: bool,
    show_labels: bool,
    highlight_incremental: bool = True,
) -> None:
    """
    Render the citation graph with pyvis inside a Streamlit component.

    Parameters
    ----------
    G                    : the full DiGraph from session state
    articles_dict        : session_state["articles"]
    max_nodes            : cap (top N nodes by degree)
    physics_on           : barnes-hut physics toggle
    show_labels          : show node ID labels
    highlight_incremental: give incremental papers a gold ring border
    """
    if not HAS_PYVIS:
        st.error("pyvis not installed. Run: `pip install pyvis`")
        return

    if G.number_of_nodes() == 0:
        st.warning("No papers loaded yet.")
        return

    # ── subgraph: top N by degree ─────────────────────────────────────────────
    top_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:max_nodes]
    sub       = G.subgraph(top_nodes)

    # ── pyvis setup ───────────────────────────────────────────────────────────
    net = Network(
        height="670px", width="100%",
        directed=True, bgcolor="#fcfcfc", font_color="#1a1a1a",
    )

    if physics_on:
        net.barnes_hut(
            gravity=-4000, central_gravity=0.15,
            spring_length=120, spring_strength=0.08,
            damping=0.8, overlap=0,
        )
    else:
        net.toggle_physics(False)

    # ── PageRank for node sizing ───────────────────────────────────────────────
    pr     = nx.pagerank(sub, alpha=0.85) if sub.number_of_nodes() > 1 else {n: 1 for n in sub.nodes()}
    pr_max = max(pr.values()) if pr else 1

    # ── add nodes ─────────────────────────────────────────────────────────────
    for node in sub.nodes():
        art   = articles_dict.get(node, {})
        cat   = art.get("category", "Core")
        src   = art.get("source", "baseline")
        size  = 15 + 35 * (pr.get(node, 0) / pr_max)
        label = node if show_labels else ""

        colour = COLOUR_MAP.get(cat, _DEFAULT_COLOUR)

        # Gold ring for freshly added incremental papers
        border_width = 2
        if highlight_incremental and src not in ("baseline",):
            colour = dict(colour)          # don't mutate the constant
            colour["border"] = "#f9a825"
            colour["highlight"] = {"border": "#f57f17", "background": colour["background"]}
            border_width = 4

        url     = art.get("url", "#")
        year    = art.get("year", "")
        authors = art.get("authors", "")
        title   = art.get("title", node)
        added   = art.get("added_at", "")
        src_tag = f"<span style='background:#e0f2f1;color:#00695c;padding:2px 6px;border-radius:4px;font-size:11px;'>{src}</span>" if src != "baseline" else ""

        tip_html = f"""
        <div style='font-family:sans-serif;padding:8px;min-width:220px;max-width:320px;'>
          <b style='color:#111;font-size:14px;'>{title}</b><br>
          <span style='color:#555;font-size:12px;'>{authors}</span><br>
          <div style='margin:5px 0;'>
            <span style='color:#555;font-size:12px;'>{year}</span>&nbsp;
            <span style='background:#eee;color:#333;padding:2px 6px;border-radius:4px;font-size:11px;font-weight:bold;'>{cat}</span>
            &nbsp;{src_tag}
          </div>
          {"<small style='color:#888;'>Added: " + added[:10] + "</small><br>" if added else ""}
          <a href='{url}' target='_blank'
             style='display:inline-block;margin-top:6px;background:#0277bd;color:#fff;
                    padding:5px 10px;border-radius:4px;text-decoration:none;font-size:12px;font-weight:bold;'>
            🔗 Open Paper
          </a>
        </div>
        """

        net.add_node(
            node, label=label, title=tip_html, size=size,
            color=colour, borderWidth=border_width, borderWidthSelected=5,
            shadow={"enabled": True, "color": "rgba(0,0,0,0.12)", "size": 6, "x": 2, "y": 3},
        )

    # ── add edges ─────────────────────────────────────────────────────────────
    for src_node, tgt_node in sub.edges():
        net.add_edge(
            src_node, tgt_node,
            color={"color": "rgba(100,110,120,0.22)", "highlight": "#ff5722"},
            arrows="to",
            smooth={"type": "curvedCW", "roundness": 0.2},
        )

    # ── interaction options ───────────────────────────────────────────────────
    net.set_options("""
    var options = {
      "interaction": {
        "hover": true,
        "tooltipDelay": 100,
        "hoverConnectedEdges": true,
        "navigationButtons": true
      }
    }
    """)

    # ── save + embed  (Windows-safe: no delete while file is open) ────────────
    tmp_path = os.path.join(tempfile.gettempdir(), "citation_graph_pyvis.html")
    net.save_graph(tmp_path)
    with open(tmp_path, "r", encoding="utf-8") as fh:
        html_out = fh.read()

    st.markdown("<div class='graph-container'>", unsafe_allow_html=True)
    components.html(html_out, height=680, scrolling=False)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── legend ────────────────────────────────────────────────────────────────
    legend_parts = []
    for cat, col in COLOUR_MAP.items():
        legend_parts.append(
            f"<span style='display:inline-flex;align-items:center;gap:4px;margin-right:12px;'>"
            f"<span style='width:12px;height:12px;border-radius:50%;background:{col['background']};"
            f"border:2px solid {col['border']};display:inline-block;'></span>"
            f"<span style='font-size:12px;color:#555;'>{cat}</span></span>"
        )
    legend_parts.append(
        "<span style='display:inline-flex;align-items:center;gap:4px;margin-right:12px;'>"
        "<span style='width:12px;height:12px;border-radius:50%;background:#90a4ae;"
        "border:4px solid #f9a825;display:inline-block;'></span>"
        "<span style='font-size:12px;color:#555;'>New (incremental)</span></span>"
    )
    st.markdown(
        "<div style='margin-top:6px;padding:6px 0;'>" + "".join(legend_parts) + "</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Showing {len(list(sub.nodes()))} nodes · "
        f"{len(list(sub.edges()))} edges · "
        "Node size ∝ PageRank · Hover for details · Gold border = newly added"
    )
