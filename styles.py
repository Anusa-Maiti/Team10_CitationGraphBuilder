"""
styles.py  –  DS3294 Citation Graph Builder
============================================
All custom CSS in one place.  Call apply_custom_css() once at the top of
final_app.py  (already done).  Light / professional theme.
"""

import streamlit as st


def apply_custom_css() -> None:
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=DM+Serif+Display&family=DM+Sans:wght@300;400;500&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
        color: #1a1a1a;
    }

    /* ── header ─────────────────────────────────────────────────────────── */
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
    .main-header p { color: #334e68; margin: 0; font-size: 0.95rem; font-weight: 400; }
    .badge {
        display: inline-block;
        background: #0277bd; color: #ffffff;
        padding: 2px 10px; border-radius: 20px;
        font-size: 0.75rem; font-family: 'IBM Plex Mono', monospace;
        margin-bottom: 0.8rem;
    }
    .badge-new {
        display: inline-block;
        background: #f9a825; color: #212121;
        padding: 2px 10px; border-radius: 20px;
        font-size: 0.75rem; font-family: 'IBM Plex Mono', monospace;
    }

    /* ── metric cards ────────────────────────────────────────────────────── */
    .metric-card {
        background: #ffffff;
        border: 1px solid #d9e2ec;
        border-radius: 10px;
        padding: 1.2rem 1rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .metric-card-new {                  /* highlight card for incremental count */
        background: #fffde7;
        border: 1px solid #f9a825;
        border-radius: 10px;
        padding: 1.2rem 1rem;
        text-align: center;
        box-shadow: 0 2px 4px rgba(249,168,37,0.15);
    }
    .metric-val       { font-family: 'IBM Plex Mono', monospace; font-size: 2.2rem; font-weight: 600; color: #0277bd; line-height: 1; }
    .metric-val-new   { font-family: 'IBM Plex Mono', monospace; font-size: 2.2rem; font-weight: 600; color: #e65100; line-height: 1; }
    .metric-label     { color: #627d98; font-size: 0.78rem; margin-top: 0.3rem; text-transform: uppercase; letter-spacing: 1px; }

    /* ── section title ───────────────────────────────────────────────────── */
    .section-title {
        font-family: 'DM Serif Display', serif;
        font-size: 1.3rem; color: #102a43;
        margin: 1.5rem 0 0.8rem 0;
        border-left: 4px solid #0277bd;
        padding-left: 0.6rem;
    }

    /* ── info / warning boxes ────────────────────────────────────────────── */
    .tip-box {
        background: rgba(2,119,189,0.06);
        border: 1px solid rgba(2,119,189,0.25);
        border-radius: 8px; padding: 1rem 1.2rem;
        margin: 0.8rem 0; color: #01579b; font-size: 0.88rem;
    }
    .warn-box {
        background: rgba(239,108,0,0.07);
        border: 1px solid rgba(239,108,0,0.3);
        border-radius: 8px; padding: 1rem 1.2rem;
        margin: 0.8rem 0; color: #bf360c; font-size: 0.88rem;
    }
    .success-box {
        background: rgba(46,125,50,0.07);
        border: 1px solid rgba(46,125,50,0.3);
        border-radius: 8px; padding: 1rem 1.2rem;
        margin: 0.8rem 0; color: #1b5e20; font-size: 0.88rem;
    }

    /* ── graph wrapper ───────────────────────────────────────────────────── */
    .graph-container {
        background: #ffffff;
        border-radius: 12px; padding: 10px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.08);
        border: 1px solid #e0e0e0;
    }

    /* ── node card (explore page) ────────────────────────────────────────── */
    .node-card {
        background: #f8fafc; border: 1px solid #d9e2ec;
        border-radius: 8px; padding: 1rem; margin: 0.4rem 0;
    }
    .node-card h4 { color: #0277bd; margin: 0 0 0.3rem 0; font-size: 0.95rem; }
    .node-card p  { color: #486581; margin: 0; font-size: 0.82rem; }

    /* ── sidebar ─────────────────────────────────────────────────────────── */
    [data-testid="stSidebar"] { background: #f0f4f8; border-right: 1px solid #d9e2ec; }
    </style>
    """, unsafe_allow_html=True)
