"""
data_handler.py  –  DS3294 Citation Graph Builder
==================================================
Responsibilities
  1.  Hold the 30-paper baseline corpus (SAMPLE_PAPERS)
  2.  Manage session state (graph + metadata dict)
  3.  Add papers to the graph (nodes + edges)
  4.  PERSIST the corpus to  data/corpus.json  so it survives app restarts
  5.  INCREMENTAL UPDATE  – add new papers at any time and re-wire all edges
  6.  PDF text extraction  (PyPDF2, graceful fallback)
  7.  Fuzzy reference resolution  (fuzzywuzzy, graceful fallback)
  8.  Stats helper used by the sidebar and dashboard
"""

from __future__ import annotations

import json
import os
import re
import io
from pathlib import Path
from datetime import datetime

import streamlit as st
import networkx as nx

# ── optional libraries (graceful degradation) ─────────────────────────────────
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

# ── persistence path ───────────────────────────────────────────────────────────
CORPUS_PATH = Path("data/corpus.json")

# ══════════════════════════════════════════════════════════════════════════════
#  BASELINE CORPUS  –  30 Transformer / NLP papers
# ══════════════════════════════════════════════════════════════════════════════
SAMPLE_PAPERS = [
    # ── Core architecture ──────────────────────────────────────────────────────
    {
        "id": "vaswani2017", "title": "Attention Is All You Need",
        "authors": "Vaswani et al.", "year": 2017, "venue": "NeurIPS",
        "category": "Core", "url": "https://arxiv.org/abs/1706.03762",
        "refs": [], "source": "baseline", "added_at": "2017-01-01",
    },
    {
        "id": "devlin2018",
        "title": "BERT: Pre-training of Deep Bidirectional Transformers",
        "authors": "Devlin et al.", "year": 2018, "venue": "NAACL",
        "category": "Core", "url": "https://arxiv.org/abs/1810.04805",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2018-01-01",
    },
    {
        "id": "radford2018",
        "title": "Improving Language Understanding by Generative Pre-Training",
        "authors": "Radford et al.", "year": 2018, "venue": "OpenAI",
        "category": "Core",
        "url": "https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2018-01-01",
    },
    {
        "id": "radford2019",
        "title": "Language Models are Unsupervised Multitask Learners",
        "authors": "Radford et al.", "year": 2019, "venue": "OpenAI",
        "category": "LLM",
        "url": "https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf",
        "refs": ["radford2018", "vaswani2017"], "source": "baseline", "added_at": "2019-01-01",
    },
    {
        "id": "brown2020",
        "title": "Language Models are Few-Shot Learners (GPT-3)",
        "authors": "Brown et al.", "year": 2020, "venue": "NeurIPS",
        "category": "LLM", "url": "https://arxiv.org/abs/2005.14165",
        "refs": ["radford2019", "vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    {
        "id": "liu2019",
        "title": "RoBERTa: A Robustly Optimized BERT Pretraining Approach",
        "authors": "Liu et al.", "year": 2019, "venue": "arXiv",
        "category": "Core", "url": "https://arxiv.org/abs/1907.11692",
        "refs": ["devlin2018"], "source": "baseline", "added_at": "2019-01-01",
    },
    {
        "id": "raffel2019",
        "title": "Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer (T5)",
        "authors": "Raffel et al.", "year": 2019, "venue": "JMLR",
        "category": "Core", "url": "https://arxiv.org/abs/1910.10683",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2019-01-01",
    },
    # ── Efficient Transformers ──────────────────────────────────────────────────
    {
        "id": "lan2019",
        "title": "ALBERT: A Lite BERT for Self-supervised Learning",
        "authors": "Lan et al.", "year": 2019, "venue": "ICLR",
        "category": "Efficient", "url": "https://arxiv.org/abs/1909.11942",
        "refs": ["devlin2018"], "source": "baseline", "added_at": "2019-01-01",
    },
    {
        "id": "sanh2019", "title": "DistilBERT, a distilled version of BERT",
        "authors": "Sanh et al.", "year": 2019, "venue": "arXiv",
        "category": "Efficient", "url": "https://arxiv.org/abs/1910.01108",
        "refs": ["devlin2018"], "source": "baseline", "added_at": "2019-01-01",
    },
    {
        "id": "kitaev2020", "title": "Reformer: The Efficient Transformer",
        "authors": "Kitaev et al.", "year": 2020, "venue": "ICLR",
        "category": "Efficient", "url": "https://arxiv.org/abs/2001.04451",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    {
        "id": "wang2020",
        "title": "Linformer: Self-Attention with Linear Complexity",
        "authors": "Wang et al.", "year": 2020, "venue": "arXiv",
        "category": "Efficient", "url": "https://arxiv.org/abs/2006.04768",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    {
        "id": "beltagy2020",
        "title": "Longformer: The Long-Document Transformer",
        "authors": "Beltagy et al.", "year": 2020, "venue": "arXiv",
        "category": "Efficient", "url": "https://arxiv.org/abs/2004.05150",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    {
        "id": "zaheer2020",
        "title": "Big Bird: Transformers for Longer Sequences",
        "authors": "Zaheer et al.", "year": 2020, "venue": "NeurIPS",
        "category": "Efficient", "url": "https://arxiv.org/abs/2007.14062",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    {
        "id": "choromanski2020",
        "title": "Rethinking Attention with Performers",
        "authors": "Choromanski et al.", "year": 2020, "venue": "ICLR",
        "category": "Efficient", "url": "https://arxiv.org/abs/2009.14794",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    # ── Vision Transformers ────────────────────────────────────────────────────
    {
        "id": "dosovitskiy2020",
        "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale (ViT)",
        "authors": "Dosovitskiy et al.", "year": 2020, "venue": "ICLR",
        "category": "Vision", "url": "https://arxiv.org/abs/2010.11929",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    {
        "id": "touvron2020",
        "title": "Training data-efficient image transformers & distillation through attention (DeiT)",
        "authors": "Touvron et al.", "year": 2020, "venue": "ICML",
        "category": "Vision", "url": "https://arxiv.org/abs/2012.12877",
        "refs": ["dosovitskiy2020"], "source": "baseline", "added_at": "2020-01-01",
    },
    {
        "id": "liu2021",
        "title": "Swin Transformer: Hierarchical Vision Transformer using Shifted Windows",
        "authors": "Liu et al.", "year": 2021, "venue": "ICCV",
        "category": "Vision", "url": "https://arxiv.org/abs/2103.14030",
        "refs": ["dosovitskiy2020"], "source": "baseline", "added_at": "2021-01-01",
    },
    {
        "id": "radford2021",
        "title": "Learning Transferable Visual Models From Natural Language Supervision (CLIP)",
        "authors": "Radford et al.", "year": 2021, "venue": "ICML",
        "category": "Vision", "url": "https://arxiv.org/abs/2103.00020",
        "refs": ["dosovitskiy2020", "radford2019"], "source": "baseline", "added_at": "2021-01-01",
    },
    {
        "id": "carion2020",
        "title": "End-to-End Object Detection with Transformers (DETR)",
        "authors": "Carion et al.", "year": 2020, "venue": "ECCV",
        "category": "Vision", "url": "https://arxiv.org/abs/2005.12872",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2020-01-01",
    },
    # ── LLM scaling era ────────────────────────────────────────────────────────
    {
        "id": "ouyang2022",
        "title": "Training language models to follow instructions with human feedback (InstructGPT)",
        "authors": "Ouyang et al.", "year": 2022, "venue": "NeurIPS",
        "category": "LLM", "url": "https://arxiv.org/abs/2203.02155",
        "refs": ["brown2020"], "source": "baseline", "added_at": "2022-01-01",
    },
    {
        "id": "rae2021",
        "title": "Scaling Language Models: Methods, Analysis & Insights from Training Gopher",
        "authors": "Rae et al.", "year": 2021, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2112.11446",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2021-01-01",
    },
    {
        "id": "hoffmann2022",
        "title": "Training Compute-Optimal Large Language Models (Chinchilla)",
        "authors": "Hoffmann et al.", "year": 2022, "venue": "NeurIPS",
        "category": "LLM", "url": "https://arxiv.org/abs/2203.15556",
        "refs": ["rae2021"], "source": "baseline", "added_at": "2022-01-01",
    },
    {
        "id": "chowdhery2022",
        "title": "PaLM: Scaling Language Modeling with Pathways",
        "authors": "Chowdhery et al.", "year": 2022, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2204.02311",
        "refs": ["vaswani2017"], "source": "baseline", "added_at": "2022-01-01",
    },
    {
        "id": "touvron2023",
        "title": "LLaMA: Open and Efficient Foundation Language Models",
        "authors": "Touvron et al.", "year": 2023, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2302.13971",
        "refs": ["brown2020", "hoffmann2022", "chowdhery2022"],
        "source": "baseline", "added_at": "2023-01-01",
    },
    {
        "id": "touvron2023b",
        "title": "Llama 2: Open Foundation and Fine-Tuned Chat Models",
        "authors": "Touvron et al.", "year": 2023, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2307.09288",
        "refs": ["touvron2023"], "source": "baseline", "added_at": "2023-01-01",
    },
    {
        "id": "zhang2022",
        "title": "OPT: Open Pre-trained Transformer Language Models",
        "authors": "Zhang et al.", "year": 2022, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2205.01068",
        "refs": ["brown2020"], "source": "baseline", "added_at": "2022-01-01",
    },
    {
        "id": "scao2022",
        "title": "BLOOM: A 176B-Parameter Open-Access Multilingual Language Model",
        "authors": "Scao et al.", "year": 2022, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2211.05100",
        "refs": ["brown2020"], "source": "baseline", "added_at": "2022-01-01",
    },
    {
        "id": "jiang2023", "title": "Mistral 7B",
        "authors": "Jiang et al.", "year": 2023, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2310.06825",
        "refs": ["touvron2023"], "source": "baseline", "added_at": "2023-01-01",
    },
    {
        "id": "bubeck2023",
        "title": "Sparks of Artificial General Intelligence: Early experiments with GPT-4",
        "authors": "Bubeck et al.", "year": 2023, "venue": "arXiv",
        "category": "LLM", "url": "https://arxiv.org/abs/2303.12712",
        "refs": ["brown2020", "ouyang2022"], "source": "baseline", "added_at": "2023-01-01",
    },
    {
        "id": "wei2022",
        "title": "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
        "authors": "Wei et al.", "year": 2022, "venue": "NeurIPS",
        "category": "LLM", "url": "https://arxiv.org/abs/2201.11903",
        "refs": ["brown2020", "chowdhery2022"], "source": "baseline", "added_at": "2022-01-01",
    },
]

# ══════════════════════════════════════════════════════════════════════════════
#  SESSION STATE  –  initialise once per browser session
# ══════════════════════════════════════════════════════════════════════════════

def init_state() -> None:
    """Create all session-state keys if they don't already exist."""
    defaults: dict = {
        "graph":          nx.DiGraph(),
        "articles":       {},          # pid -> paper dict
        "uploaded_count": 0,
        "log":            [],
        # ── incremental update tracking ──────────────────────────────────────
        "corpus_version": 0,           # bumped on every save
        "pending_edges":  [],          # (src, tgt) pairs waiting for both nodes
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ══════════════════════════════════════════════════════════════════════════════
#  PERSISTENCE  –  save / load  data/corpus.json
# ══════════════════════════════════════════════════════════════════════════════

def save_corpus() -> None:
    """
    Persist the current in-memory corpus to  data/corpus.json.
    Called automatically after every add / remove / update operation.
    This is what makes incremental updates reproducible — restart the app
    and load_corpus() restores the exact same graph.
    """
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version":    st.session_state.get("corpus_version", 0) + 1,
        "saved_at":   datetime.now().isoformat(timespec="seconds"),
        "papers":     list(st.session_state["articles"].values()),
    }
    CORPUS_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    st.session_state["corpus_version"] = payload["version"]


def load_corpus() -> int:
    """
    Load  data/corpus.json  into session state and rebuild the graph from it.
    Returns the number of papers loaded (0 if file doesn't exist).
    This is the INCREMENTAL RESTORE path — the graph is reconstructed exactly
    as it was when save_corpus() was last called.
    """
    if not CORPUS_PATH.exists():
        return 0

    try:
        payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return 0

    papers = payload.get("papers", [])
    # Clear and rebuild
    st.session_state["articles"] = {}
    st.session_state["graph"]    = nx.DiGraph()
    st.session_state["pending_edges"] = []

    for paper in papers:
        _add_node_only(paper)               # first pass: nodes only

    for paper in papers:                    # second pass: edges
        _wire_edges(paper)

    _flush_pending_edges()

    count = len(papers)
    v     = payload.get("version", "?")
    st.session_state["log"].append(
        f"📂 Restored {count} papers from corpus.json (version {v}, "
        f"saved {payload.get('saved_at', '?')})"
    )
    return count


# ══════════════════════════════════════════════════════════════════════════════
#  INTERNAL GRAPH HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _node_attrs(paper: dict) -> dict:
    """Return attributes to store on the nx node (everything except 'refs')."""
    return {k: v for k, v in paper.items() if k != "refs"}


def _add_node_only(paper: dict) -> None:
    """Add/update a node without touching edges."""
    G   = st.session_state["graph"]
    pid = paper["id"]
    st.session_state["articles"][pid] = paper
    if G.has_node(pid):
        nx.set_node_attributes(G, {pid: _node_attrs(paper)})
    else:
        G.add_node(pid, **_node_attrs(paper))


def _wire_edges(paper: dict) -> None:
    """
    Draw edges from this paper to everything it references.
    If the referenced node doesn't exist yet, stash in pending_edges
    so _flush_pending_edges() can retry later.
    """
    G   = st.session_state["graph"]
    pid = paper["id"]
    for ref in paper.get("refs", []):
        if G.has_node(ref):
            if not G.has_edge(pid, ref):
                G.add_edge(pid, ref)
        else:
            # referenced paper not in corpus yet – remember for later
            st.session_state["pending_edges"].append((pid, ref))


def _flush_pending_edges() -> int:
    """
    Retry all stashed (src, tgt) pairs.
    Returns the number of new edges added.
    This is called after every incremental add so that a new paper
    can immediately wire up to both older papers it cites AND newer
    papers that cite it.
    """
    G       = st.session_state["graph"]
    still   = []
    added   = 0
    for src, tgt in st.session_state.get("pending_edges", []):
        if G.has_node(src) and G.has_node(tgt):
            if not G.has_edge(src, tgt):
                G.add_edge(src, tgt)
                added += 1
        else:
            still.append((src, tgt))
    st.session_state["pending_edges"] = still
    return added


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API  –  used by app.py and other pages
# ══════════════════════════════════════════════════════════════════════════════

def add_paper_to_graph(paper: dict, source_tag: str = "manual") -> bool:
    """
    Add a single paper to the in-memory graph and persist to disk.

    Parameters
    ----------
    paper : dict
        Must have at least  id, title, year.  refs is optional.
    source_tag : str
        Provenance label – 'baseline', 'manual', 'pdf', 'json', 'url'.

    Returns
    -------
    bool  – True if newly added, False if it was already present (no-op).
    """
    pid = paper.get("id", "").strip()
    if not pid:
        return False

    # ── stamp provenance ──────────────────────────────────────────────────────
    paper.setdefault("source",   source_tag)
    paper.setdefault("added_at", datetime.now().isoformat(timespec="seconds"))
    paper.setdefault("refs",     [])
    paper.setdefault("category", "Incremental")

    already_exists = pid in st.session_state["articles"]

    _add_node_only(paper)
    _wire_edges(paper)
    new_edges = _flush_pending_edges()

    if not already_exists:
        save_corpus()
        st.session_state["log"].append(
            f"➕ Added '{paper['title'][:55]}' ({pid}) — "
            f"{len(paper['refs'])} refs, {new_edges} new edges resolved."
        )
        return True

    # Paper existed — still re-resolve in case new neighbours arrived
    if new_edges:
        save_corpus()
        st.session_state["log"].append(
            f"🔄 Re-wired existing paper '{pid}' — {new_edges} new edges."
        )
    return False


def add_papers_bulk(papers: list[dict], source_tag: str = "json") -> dict:
    """
    Incrementally add a list of papers.
    Two-pass: nodes first, then edges — guarantees every cross-ref is wired
    even when papers reference each other within the same batch.

    Returns a summary dict  {added, skipped, new_edges}.
    """
    added = skipped = 0

    # Pass 1 – nodes
    for paper in papers:
        pid = paper.get("id", "").strip()
        if not pid:
            skipped += 1
            continue
        paper.setdefault("source",   source_tag)
        paper.setdefault("added_at", datetime.now().isoformat(timespec="seconds"))
        paper.setdefault("refs",     [])
        paper.setdefault("category", "Incremental")

        if pid in st.session_state["articles"]:
            skipped += 1
        else:
            _add_node_only(paper)
            added += 1

    # Pass 2 – edges for ALL papers in the batch
    for paper in papers:
        if paper.get("id") in st.session_state["articles"]:
            _wire_edges(paper)

    new_edges = _flush_pending_edges()

    if added:
        save_corpus()
        st.session_state["log"].append(
            f"📦 Bulk import: +{added} new, {skipped} skipped, "
            f"{new_edges} edges resolved."
        )

    return {"added": added, "skipped": skipped, "new_edges": new_edges}


def load_sample() -> None:
    """Load the 30-paper baseline corpus (only papers not already present)."""
    result = add_papers_bulk(SAMPLE_PAPERS, source_tag="baseline")
    st.session_state["log"].append(
        f"✅ Baseline loaded — {result['added']} new papers, "
        f"{result['skipped']} already present, "
        f"{result['new_edges']} citation edges."
    )


def remove_paper(pid: str) -> bool:
    """
    Remove a paper from the graph and persist.
    Edges to/from it are automatically removed by NetworkX.
    Returns True if it existed, False otherwise.
    """
    G = st.session_state["graph"]
    if pid not in st.session_state["articles"]:
        return False

    title = st.session_state["articles"][pid].get("title", pid)
    G.remove_node(pid)
    del st.session_state["articles"][pid]

    # Also remove any stashed pending edges involving this paper
    st.session_state["pending_edges"] = [
        (s, t) for s, t in st.session_state.get("pending_edges", [])
        if s != pid and t != pid
    ]

    save_corpus()
    st.session_state["log"].append(f"🗑️ Removed '{title[:55]}' ({pid}).")
    return True


def resolve_all_edges() -> int:
    """
    Re-scan every paper's refs and wire any edges that are now possible
    (useful after a bulk import or after removing then re-adding a paper).
    Returns total new edges added.
    """
    G     = st.session_state["graph"]
    added = 0
    for pid, paper in st.session_state["articles"].items():
        for ref in paper.get("refs", []):
            if G.has_node(ref) and not G.has_edge(pid, ref):
                G.add_edge(pid, ref)
                added += 1
    if added:
        save_corpus()
        st.session_state["log"].append(f"🔄 Re-resolution complete: +{added} new edges.")
    return added


# ══════════════════════════════════════════════════════════════════════════════
#  PDF  –  extract text → metadata + refs
# ══════════════════════════════════════════════════════════════════════════════

def _extract_text_from_pdf(file_bytes: bytes) -> str:
    if not HAS_PYPDF:
        return ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return ""


def _extract_embedded_metadata(file_bytes: bytes) -> dict:
    """Pull /Title, /Author from embedded PDF metadata if present."""
    if not HAS_PYPDF:
        return {}
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        meta   = reader.metadata or {}
        out    = {}
        if meta.get("/Title"):
            out["title"] = meta["/Title"].strip()
        if meta.get("/Author"):
            out["authors"] = meta["/Author"].strip()
        return out
    except Exception:
        return {}


def _parse_metadata_from_text(text: str, filename: str) -> dict:
    """
    Heuristic extraction of title / authors / year from raw PDF text.
    Tries three strategies in order of confidence.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    # title — first non-trivial line (or filename as fallback)
    title = lines[0][:160] if lines else filename.replace(".pdf", "")

    # year — first 4-digit year in range 1990-2030
    year_m = re.search(r"\b(19[9]\d|20[012]\d)\b", text)
    year   = int(year_m.group()) if year_m else 2000

    # authors — look for  Surname, F.  or  F. Surname  patterns in first 8 lines
    authors = "Unknown"
    for line in lines[1:8]:
        if re.search(r"[A-Z][a-z]+,\s+[A-Z]\.?", line):
            authors = line[:120]
            break

    # arXiv ID
    arxiv_m = re.search(r"\b(\d{4}\.\d{4,5})\b", text)
    arxiv   = arxiv_m.group(1) if arxiv_m else ""

    # DOI
    doi_m = re.search(r"10\.\d{4,}/\S+", text)
    doi   = doi_m.group().rstrip(".,)") if doi_m else ""

    return {
        "title":    title,
        "authors":  authors,
        "year":     year,
        "venue":    "Unknown",
        "arxiv_id": arxiv,
        "doi":      doi,
    }


def _find_ref_section(text: str) -> str:
    lower = text.lower()
    for heading in ["references\n", "bibliography\n", "works cited\n"]:
        pos = lower.rfind(heading)
        if pos != -1:
            return text[pos:]
    return text[-5000:]


def _parse_raw_refs(ref_text: str) -> list[str]:
    """Split reference section into individual raw-text entries."""
    # Numbered style  [1] ...
    numbered = re.findall(r"^\s*\[\d{1,3}\]\s*(.+)", ref_text, re.MULTILINE)
    if len(numbered) >= 2:
        return [e.strip() for e in numbered]
    # Blank-line separated
    chunks = re.split(r"\n{2,}", ref_text)
    return [c.strip() for c in chunks if len(c.strip()) > 20]


def _fuzzy_score(a: str, b: str) -> int:
    if HAS_FUZZY:
        return fuzz.token_set_ratio(a.lower(), b.lower())
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    return int(100 * len(wa & wb) / max(len(wa | wb), 1))


def resolve_refs_from_text(raw_refs: list[str]) -> list[str]:
    """
    Match a list of raw reference strings against the current corpus.
    Uses three strategies (DOI → arXiv ID → fuzzy title).
    Returns list of matched paper IDs.

    This implements the Entity Resolution step described in the README
    (Phase 5: exact DOI match, then fuzzy title + first author + year).
    """
    known    = st.session_state["articles"]
    resolved = []

    for entry in raw_refs:
        matched = None

        # Strategy 1 – DOI
        doi_m = re.search(r"10\.\d{4,}/\S+", entry)
        if doi_m:
            doi = doi_m.group().rstrip(".,)")
            for pid, art in known.items():
                if art.get("doi") and doi in art["doi"]:
                    matched = pid
                    break

        # Strategy 2 – arXiv ID
        if not matched:
            ax_m = re.search(r"\b(\d{4}\.\d{4,5})\b", entry)
            if ax_m:
                aid = ax_m.group(1)
                for pid, art in known.items():
                    if aid in art.get("url", "") or aid in art.get("arxiv_id", ""):
                        matched = pid
                        break

        # Strategy 3 – fuzzy title match  (threshold 72)
        if not matched:
            best_pid, best_score = None, 0
            for pid, art in known.items():
                score = _fuzzy_score(entry, art.get("title", ""))
                if score > best_score:
                    best_score, best_pid = score, pid
            if best_score >= 72:
                matched = best_pid

        if matched and matched not in resolved:
            resolved.append(matched)

    return resolved


def extract_paper_from_pdf(file_bytes: bytes, filename: str) -> dict:
    """
    Full pipeline for a single uploaded PDF:
      1. Extract embedded /Title, /Author metadata
      2. Extract raw text
      3. Parse title / authors / year from text (fallback)
      4. Extract reference section and resolve to known IDs
    Returns a paper dict ready for add_paper_to_graph().
    """
    embedded = _extract_embedded_metadata(file_bytes)
    text     = _extract_text_from_pdf(file_bytes)
    parsed   = _parse_metadata_from_text(text, filename)

    # Merge: embedded metadata wins over heuristic
    title   = embedded.get("title")   or parsed["title"]
    authors = embedded.get("authors") or parsed["authors"]
    year    = parsed["year"]
    arxiv   = parsed.get("arxiv_id", "")
    doi     = parsed.get("doi", "")

    # Build a stable slug ID from title + year
    slug = re.sub(r"[^\w]", "", title[:20].lower()) + str(year)

    # Resolve references
    raw_refs = _parse_raw_refs(_find_ref_section(text))
    refs     = resolve_refs_from_text(raw_refs)

    return {
        "id":       slug,
        "title":    title,
        "authors":  authors,
        "year":     year,
        "venue":    "Unknown",
        "category": "Incremental",
        "url":      f"https://arxiv.org/abs/{arxiv}" if arxiv else "",
        "arxiv_id": arxiv,
        "doi":      doi,
        "refs":     refs,
        "source":   "pdf",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  STATS  –  used by sidebar and dashboard
# ══════════════════════════════════════════════════════════════════════════════

def get_stats() -> dict:
    G     = st.session_state["graph"]
    nodes = G.number_of_nodes()
    edges = G.number_of_edges()
    if nodes == 0:
        return {
            "nodes": 0, "edges": 0, "density": 0,
            "components": 0, "avg_degree": 0, "max_indegree": 0,
            "baseline": 0, "incremental": 0, "pending_edges": 0,
        }

    baseline    = sum(
        1 for p in st.session_state["articles"].values()
        if p.get("source") == "baseline"
    )
    incremental = nodes - baseline

    return {
        "nodes":         nodes,
        "edges":         edges,
        "density":       round(nx.density(G), 5),
        "components":    nx.number_weakly_connected_components(G),
        "avg_degree":    round(sum(dict(G.degree()).values()) / nodes, 2),
        "max_indegree":  max((d for _, d in G.in_degree()), default=0),
        "baseline":      baseline,
        "incremental":   incremental,
        "pending_edges": len(st.session_state.get("pending_edges", [])),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def export_papers_json() -> str:
    return json.dumps(list(st.session_state["articles"].values()),
                      indent=2, ensure_ascii=False)


def export_edges_json() -> str:
    G     = st.session_state["graph"]
    edges = [{"source": u, "target": v} for u, v in G.edges()]
    return json.dumps(edges, indent=2)


def export_nodes_csv() -> str:
    lines = ["id,title,authors,year,venue,category,source"]
    for pid, art in st.session_state["articles"].items():
        row = ",".join([
            f'"{art.get(f, "")}"'
            for f in ["id", "title", "authors", "year", "venue", "category", "source"]
        ])
        lines.append(row)
    return "\n".join(lines)
