"""
data_handler.py  –  DS3294 Citation Graph Builder
==================================================
Bug fixes in this version:
  1. _G() function — always fetches LIVE graph from session_state (never stale ref)
  2. force_rewire() — reads refs from articles[] (single source of truth), not passed dict
  3. Ref IDs normalised on store (strip whitespace)
  4. PDF tab no longer auto-wires refs — suggests candidates, user confirms
  5. suggest_refs_from_text() for UI-assisted ref picking
"""
from __future__ import annotations
import io, json, re
from datetime import datetime
from pathlib import Path
import streamlit as st
import networkx as nx

try:
    import PyPDF2; HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from fuzzywuzzy import fuzz; HAS_FUZZY = True
except ImportError:
    HAS_FUZZY = False

CORPUS_PATH = Path("data/corpus.json")

SAMPLE_PAPERS = [
    {"id":"vaswani2017","title":"Attention Is All You Need","authors":"Vaswani et al.","year":2017,"venue":"NeurIPS","category":"Core","url":"https://arxiv.org/abs/1706.03762","refs":[],"source":"baseline"},
    {"id":"devlin2018","title":"BERT: Pre-training of Deep Bidirectional Transformers","authors":"Devlin et al.","year":2018,"venue":"NAACL","category":"Core","url":"https://arxiv.org/abs/1810.04805","refs":["vaswani2017"],"source":"baseline"},
    {"id":"radford2018","title":"Improving Language Understanding by Generative Pre-Training","authors":"Radford et al.","year":2018,"venue":"OpenAI","category":"Core","url":"https://cdn.openai.com/research-covers/language-unsupervised/language_understanding_paper.pdf","refs":["vaswani2017"],"source":"baseline"},
    {"id":"radford2019","title":"Language Models are Unsupervised Multitask Learners (GPT-2)","authors":"Radford et al.","year":2019,"venue":"OpenAI","category":"LLM","url":"https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf","refs":["radford2018","vaswani2017"],"source":"baseline"},
    {"id":"brown2020","title":"Language Models are Few-Shot Learners (GPT-3)","authors":"Brown et al.","year":2020,"venue":"NeurIPS","category":"LLM","url":"https://arxiv.org/abs/2005.14165","refs":["radford2019","vaswani2017"],"source":"baseline"},
    {"id":"liu2019","title":"RoBERTa: A Robustly Optimized BERT Pretraining Approach","authors":"Liu et al.","year":2019,"venue":"arXiv","category":"Core","url":"https://arxiv.org/abs/1907.11692","refs":["devlin2018"],"source":"baseline"},
    {"id":"raffel2019","title":"Exploring the Limits of Transfer Learning with a Unified Text-to-Text Transformer (T5)","authors":"Raffel et al.","year":2019,"venue":"JMLR","category":"Core","url":"https://arxiv.org/abs/1910.10683","refs":["vaswani2017"],"source":"baseline"},
    {"id":"lan2019","title":"ALBERT: A Lite BERT for Self-supervised Learning","authors":"Lan et al.","year":2019,"venue":"ICLR","category":"Efficient","url":"https://arxiv.org/abs/1909.11942","refs":["devlin2018"],"source":"baseline"},
    {"id":"sanh2019","title":"DistilBERT, a distilled version of BERT","authors":"Sanh et al.","year":2019,"venue":"arXiv","category":"Efficient","url":"https://arxiv.org/abs/1910.01108","refs":["devlin2018"],"source":"baseline"},
    {"id":"dosovitskiy2020","title":"An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale (ViT)","authors":"Dosovitskiy et al.","year":2020,"venue":"ICLR","category":"Vision","url":"https://arxiv.org/abs/2010.11929","refs":["vaswani2017"],"source":"baseline"},
    {"id":"touvron2020","title":"Training data-efficient image transformers & distillation through attention (DeiT)","authors":"Touvron et al.","year":2020,"venue":"ICML","category":"Vision","url":"https://arxiv.org/abs/2012.12877","refs":["dosovitskiy2020"],"source":"baseline"},
    {"id":"liu2021","title":"Swin Transformer: Hierarchical Vision Transformer using Shifted Windows","authors":"Liu et al.","year":2021,"venue":"ICCV","category":"Vision","url":"https://arxiv.org/abs/2103.14030","refs":["dosovitskiy2020"],"source":"baseline"},
    {"id":"radford2021","title":"Learning Transferable Visual Models From Natural Language Supervision (CLIP)","authors":"Radford et al.","year":2021,"venue":"ICML","category":"Vision","url":"https://arxiv.org/abs/2103.00020","refs":["dosovitskiy2020","radford2019"],"source":"baseline"},
    {"id":"carion2020","title":"End-to-End Object Detection with Transformers (DETR)","authors":"Carion et al.","year":2020,"venue":"ECCV","category":"Vision","url":"https://arxiv.org/abs/2005.12872","refs":["vaswani2017"],"source":"baseline"},
    {"id":"kitaev2020","title":"Reformer: The Efficient Transformer","authors":"Kitaev et al.","year":2020,"venue":"ICLR","category":"Efficient","url":"https://arxiv.org/abs/2001.04451","refs":["vaswani2017"],"source":"baseline"},
    {"id":"wang2020","title":"Linformer: Self-Attention with Linear Complexity","authors":"Wang et al.","year":2020,"venue":"arXiv","category":"Efficient","url":"https://arxiv.org/abs/2006.04768","refs":["vaswani2017"],"source":"baseline"},
    {"id":"beltagy2020","title":"Longformer: The Long-Document Transformer","authors":"Beltagy et al.","year":2020,"venue":"arXiv","category":"Efficient","url":"https://arxiv.org/abs/2004.05150","refs":["vaswani2017"],"source":"baseline"},
    {"id":"zaheer2020","title":"Big Bird: Transformers for Longer Sequences","authors":"Zaheer et al.","year":2020,"venue":"NeurIPS","category":"Efficient","url":"https://arxiv.org/abs/2007.14062","refs":["vaswani2017"],"source":"baseline"},
    {"id":"choromanski2020","title":"Rethinking Attention with Performers","authors":"Choromanski et al.","year":2020,"venue":"ICLR","category":"Efficient","url":"https://arxiv.org/abs/2009.14794","refs":["vaswani2017"],"source":"baseline"},
    {"id":"ouyang2022","title":"Training language models to follow instructions with human feedback (InstructGPT)","authors":"Ouyang et al.","year":2022,"venue":"NeurIPS","category":"LLM","url":"https://arxiv.org/abs/2203.02155","refs":["brown2020"],"source":"baseline"},
    {"id":"touvron2023","title":"LLaMA: Open and Efficient Foundation Language Models","authors":"Touvron et al.","year":2023,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2302.13971","refs":["brown2020","hoffmann2022","chowdhery2022"],"source":"baseline"},
    {"id":"touvron2023b","title":"Llama 2: Open Foundation and Fine-Tuned Chat Models","authors":"Touvron et al.","year":2023,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2307.09288","refs":["touvron2023"],"source":"baseline"},
    {"id":"chowdhery2022","title":"PaLM: Scaling Language Modeling with Pathways","authors":"Chowdhery et al.","year":2022,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2204.02311","refs":["vaswani2017"],"source":"baseline"},
    {"id":"hoffmann2022","title":"Training Compute-Optimal Large Language Models (Chinchilla)","authors":"Hoffmann et al.","year":2022,"venue":"NeurIPS","category":"LLM","url":"https://arxiv.org/abs/2203.15556","refs":["rae2021"],"source":"baseline"},
    {"id":"rae2021","title":"Scaling Language Models: Methods, Analysis & Insights from Training Gopher","authors":"Rae et al.","year":2021,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2112.11446","refs":["vaswani2017"],"source":"baseline"},
    {"id":"zhang2022","title":"OPT: Open Pre-trained Transformer Language Models","authors":"Zhang et al.","year":2022,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2205.01068","refs":["brown2020"],"source":"baseline"},
    {"id":"scao2022","title":"BLOOM: A 176B-Parameter Open-Access Multilingual Language Model","authors":"Scao et al.","year":2022,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2211.05100","refs":["brown2020"],"source":"baseline"},
    {"id":"jiang2023","title":"Mistral 7B","authors":"Jiang et al.","year":2023,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2310.06825","refs":["touvron2023"],"source":"baseline"},
    {"id":"bubeck2023","title":"Sparks of Artificial General Intelligence: Early experiments with GPT-4","authors":"Bubeck et al.","year":2023,"venue":"arXiv","category":"LLM","url":"https://arxiv.org/abs/2303.12712","refs":["brown2020","ouyang2022"],"source":"baseline"},
    {"id":"wei2022","title":"Chain-of-Thought Prompting Elicits Reasoning in Large Language Models","authors":"Wei et al.","year":2022,"venue":"NeurIPS","category":"LLM","url":"https://arxiv.org/abs/2201.11903","refs":["brown2020","chowdhery2022"],"source":"baseline"},
]

def init_state() -> None:
    defaults = {"graph": nx.DiGraph(), "articles": {}, "uploaded_count": 0,
                "log": [], "corpus_version": 0}
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def _G() -> nx.DiGraph:
    """Always return the LIVE graph from session_state. Never cache this."""
    return st.session_state["graph"]

def save_corpus() -> None:
    CORPUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    version = st.session_state.get("corpus_version", 0) + 1
    payload = {"version": version,
               "saved_at": datetime.now().isoformat(timespec="seconds"),
               "papers": [{k:v for k,v in p.items() if k != "_raw_text"}
                          for p in st.session_state["articles"].values()]}
    CORPUS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    st.session_state["corpus_version"] = version

def load_corpus() -> int:
    if not CORPUS_PATH.exists():
        return 0
    try:
        payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        papers  = payload.get("papers", [])
    except Exception:
        return 0
    st.session_state["articles"] = {}
    st.session_state["graph"]    = nx.DiGraph()
    for p in papers:
        _register_node(p)
    force_rewire()
    v = payload.get("version", "?")
    st.session_state["log"].append(
        f"Restored {len(papers)} papers (v{v}, {payload.get('saved_at','?')})")
    return len(papers)

def _register_node(paper: dict) -> None:
    """Store paper in articles AND add nx node. Normalises ref IDs."""
    G   = _G()
    pid = paper["id"]
    paper["refs"] = [r.strip() for r in paper.get("refs", []) if r.strip()]
    st.session_state["articles"][pid] = paper
    attrs = {k: v for k, v in paper.items() if k not in ("refs", "_raw_text")}
    if G.has_node(pid):
        for k, v in attrs.items():
            G.nodes[pid][k] = v
    else:
        G.add_node(pid, **attrs)

def force_rewire() -> int:
    """
    THE single authoritative edge-drawing function.
    Reads from articles[] (not from any passed dict).
    Called after every mutation. Returns edges added this call.
    """
    G = _G()
    added = 0
    for pid, paper in st.session_state["articles"].items():
        for ref in paper.get("refs", []):
            ref = ref.strip()
            if ref and G.has_node(ref) and not G.has_edge(pid, ref):
                G.add_edge(pid, ref)
                added += 1
    return added

def add_paper_to_graph(paper: dict, source_tag: str = "manual") -> bool:
    pid = paper.get("id", "").strip()
    if not pid:
        return False
    paper["id"] = pid
    paper.setdefault("source",   source_tag)
    paper.setdefault("added_at", datetime.now().isoformat(timespec="seconds"))
    paper.setdefault("refs",     [])
    paper.setdefault("category", "Incremental")
    is_new = pid not in st.session_state["articles"]
    _register_node(paper)
    new_edges = force_rewire()
    if is_new:
        save_corpus()
        st.session_state["log"].append(
            f"Added '{paper['title'][:50]}' ({pid}) — "
            f"refs={paper['refs']} → {new_edges} edge(s).")
        return True
    if new_edges:
        save_corpus()
        st.session_state["log"].append(f"Re-wired '{pid}' — {new_edges} new edges.")
    return False

def add_papers_bulk(papers: list[dict], source_tag: str = "json") -> dict:
    added = skipped = 0
    for paper in papers:
        pid = paper.get("id", "").strip()
        if not pid:
            skipped += 1; continue
        paper["id"] = pid
        paper.setdefault("source",   source_tag)
        paper.setdefault("added_at", datetime.now().isoformat(timespec="seconds"))
        paper.setdefault("refs",     [])
        paper.setdefault("category", "Incremental")
        if pid in st.session_state["articles"]:
            skipped += 1
        else:
            _register_node(paper); added += 1
    new_edges = force_rewire()
    if added:
        save_corpus()
        st.session_state["log"].append(
            f"Bulk: +{added} papers, {skipped} skipped, {new_edges} edges.")
    return {"added": added, "skipped": skipped, "new_edges": new_edges}

def load_sample() -> None:
    r = add_papers_bulk(SAMPLE_PAPERS, source_tag="baseline")
    st.session_state["log"].append(
        f"Baseline: {r['added']} new, {r['skipped']} present, {r['new_edges']} edges.")

def remove_paper(pid: str) -> bool:
    if pid not in st.session_state["articles"]:
        return False
    title = st.session_state["articles"][pid].get("title", pid)
    _G().remove_node(pid)
    del st.session_state["articles"][pid]
    save_corpus()
    st.session_state["log"].append(f"Removed '{title[:50]}' ({pid}).")
    return True

def resolve_all_edges() -> int:
    added = force_rewire()
    save_corpus()
    st.session_state["log"].append(
        f"Re-resolve: +{added} new edges." if added else "Re-resolve: already fully wired.")
    return added

def get_known_ids() -> list[str]:
    return sorted(st.session_state["articles"].keys())

def _pdf_text(file_bytes: bytes) -> str:
    if not HAS_PYPDF:
        return ""
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception:
        return ""

def _pdf_embedded_meta(file_bytes: bytes) -> dict:
    if not HAS_PYPDF:
        return {}
    try:
        meta = PyPDF2.PdfReader(io.BytesIO(file_bytes)).metadata or {}
        out  = {}
        if meta.get("/Title"):  out["title"]   = meta["/Title"].strip()
        if meta.get("/Author"): out["authors"] = meta["/Author"].strip()
        return out
    except Exception:
        return {}

def _parse_meta_from_text(text: str, filename: str) -> dict:
    lines   = [l.strip() for l in text.split("\n") if l.strip()]
    title   = lines[0][:160] if lines else filename.replace(".pdf", "")
    year_m  = re.search(r"\b(19[9]\d|20[012]\d)\b", text)
    year    = int(year_m.group()) if year_m else 2000
    authors = "Unknown"
    for line in lines[1:8]:
        if re.search(r"[A-Z][a-z]+,\s+[A-Z]\.?", line):
            authors = line[:120]; break
    arxiv_m = re.search(r"\b(\d{4}\.\d{4,5})\b", text)
    doi_m   = re.search(r"10\.\d{4,}/\S+", text)
    return {"title": title, "authors": authors, "year": year, "venue": "Unknown",
            "arxiv_id": arxiv_m.group(1) if arxiv_m else "",
            "doi":      doi_m.group().rstrip(".,)") if doi_m else ""}

def _fuzzy_score(a: str, b: str) -> int:
    if HAS_FUZZY:
        return fuzz.token_set_ratio(a.lower(), b.lower())
    wa, wb = set(a.lower().split()), set(b.lower().split())
    return int(100 * len(wa & wb) / max(len(wa | wb), 1))

def suggest_refs_from_text(raw_text: str, top_n: int = 10) -> list[dict]:
    """Suggest which corpus papers the PDF likely cites. User confirms in UI."""
    known     = st.session_state["articles"]
    lower     = raw_text.lower()
    ref_start = lower.rfind("references\n")
    ref_text  = raw_text[ref_start:] if ref_start != -1 else raw_text[-6000:]
    results   = []
    for pid, art in known.items():
        score = _fuzzy_score(ref_text, art.get("title", ""))
        if score >= 30:
            results.append({"id": pid, "title": art.get("title","")[:70], "score": score})
    results.sort(key=lambda x: -x["score"])
    return results[:top_n]

def extract_paper_from_pdf(file_bytes: bytes, filename: str) -> dict:
    embedded = _pdf_embedded_meta(file_bytes)
    text     = _pdf_text(file_bytes)
    parsed   = _parse_meta_from_text(text, filename)
    title    = embedded.get("title")   or parsed["title"]
    authors  = embedded.get("authors") or parsed["authors"]
    arxiv    = parsed.get("arxiv_id", "")
    doi      = parsed.get("doi", "")
    slug     = re.sub(r"[^\w]", "", title[:20].lower()) + str(parsed["year"])
    return {"id": slug, "title": title, "authors": authors, "year": parsed["year"],
            "venue": "Unknown", "category": "Incremental",
            "url": f"https://arxiv.org/abs/{arxiv}" if arxiv else "",
            "arxiv_id": arxiv, "doi": doi, "refs": [], "source": "pdf",
            "_raw_text": text}

def get_stats() -> dict:
    G     = _G()
    nodes = G.number_of_nodes()
    edges = G.number_of_edges()
    if nodes == 0:
        return {"nodes":0,"edges":0,"density":0,"components":0,
                "avg_degree":0,"max_indegree":0,"baseline":0,"incremental":0}
    baseline    = sum(1 for p in st.session_state["articles"].values() if p.get("source")=="baseline")
    return {"nodes": nodes, "edges": edges,
            "density":      round(nx.density(G), 5),
            "components":   nx.number_weakly_connected_components(G),
            "avg_degree":   round(sum(dict(G.degree()).values()) / nodes, 2),
            "max_indegree": max((d for _, d in G.in_degree()), default=0),
            "baseline":     baseline, "incremental": nodes - baseline}

def export_papers_json() -> str:
    clean = [{k:v for k,v in p.items() if k != "_raw_text"}
             for p in st.session_state["articles"].values()]
    return json.dumps(clean, indent=2, ensure_ascii=False)

def export_edges_json() -> str:
    return json.dumps([{"source":u,"target":v} for u,v in _G().edges()], indent=2)

def export_nodes_csv() -> str:
    lines = ["id,title,authors,year,venue,category,source,refs"]
    for art in st.session_state["articles"].values():
        refs_str = "|".join(art.get("refs",[]))
        row = ",".join([f'"{art.get(f,"")}"' for f in
                        ["id","title","authors","year","venue","category","source"]]
                       + [f'"{refs_str}"'])
        lines.append(row)
    return "\n".join(lines)
