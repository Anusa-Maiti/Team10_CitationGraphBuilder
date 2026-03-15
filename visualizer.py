import streamlit as st
import networkx as nx
import tempfile
import os

try:
    from pyvis.network import Network
    import streamlit.components.v1 as components
    HAS_PYVIS = True
except ImportError:
    HAS_PYVIS = False

def render_interactive_graph(G: nx.DiGraph, articles_dict: dict, max_nodes: int, physics_on: bool, show_labels: bool):
    if not HAS_PYVIS:
        st.error("pyvis not installed. Please install it using `pip install pyvis`.")
        return

    top_nodes = sorted(G.nodes(), key=lambda n: G.degree(n), reverse=True)[:max_nodes]
    sub = G.subgraph(top_nodes)
    
    net = Network(height="650px", width="100%", directed=True, bgcolor="#fcfcfc", font_color="#1a1a1a")
    
    color_map = {
        "Core": {"background": "#29b6f6", "border": "#0277bd"},    
        "Vision": {"background": "#ffa726", "border": "#ef6c00"},  
        "Efficient": {"background": "#66bb6a", "border": "#2e7d32"},
        "LLM": {"background": "#ab47bc", "border": "#6a1b9a"}      
    }

    if physics_on:
        net.barnes_hut(
            gravity=-4000, central_gravity=0.15, spring_length=120, 
            spring_strength=0.08, damping=0.8, overlap=0
        )
    
    pr = nx.pagerank(sub, alpha=0.85) if sub.number_of_nodes() > 1 else {n: 1 for n in sub.nodes()}
    pr_max = max(pr.values()) if pr else 1
    
    for node in sub.nodes():
        art = articles_dict.get(node, {})
        size = 15 + 35 * (pr.get(node, 0) / pr_max)
        label = node if show_labels else ""
        cat = art.get('category', 'Core')
        
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
        
        net.add_node(
            node, label=label, title=tip_html, size=size,
            color=color_scheme, borderWidth=2, borderWidthSelected=4,
            shadow={"enabled": True, "color": "rgba(0,0,0,0.15)", "size": 6, "x": 2, "y": 3}
        )
    
    for src, tgt in sub.edges():
        net.add_edge(
            src, tgt, 
            color={"color": "rgba(100,110,120,0.25)", "highlight": "#ff5722"}, 
            arrows="to", smooth={"type": "curvedCW", "roundness": 0.2}
        )
    
    net.set_options("""
    var options = {
      "interaction": { "hover": true, "tooltipDelay": 150, "hoverConnectedEdges": true }
    }
    """)

    tmp_path = os.path.join(tempfile.gettempdir(), "citation_graph_pyvis.html")
    net.save_graph(tmp_path)
    with open(tmp_path, "r", encoding="utf-8") as f:
        html_out = f.read()
    
    st.markdown("<div class='graph-container'>", unsafe_allow_html=True)
    components.html(html_out, height=660, scrolling=False)
    st.markdown("</div>", unsafe_allow_html=True)
    st.caption("✨ **Gestalt Design:** Hover over nodes to see the 'Figure-Ground' isolation. Colors map to sub-fields (Similarity). Click links in popups to view papers.")