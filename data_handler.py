import streamlit as st
import networkx as nx

# Your 30-paper niche corpus
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

def add_paper_to_graph(paper: dict):
    G = st.session_state["graph"]
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
    G = st.session_state["graph"]
    nodes = G.number_of_nodes()
    edges = G.number_of_edges()
    if nodes == 0:
        return {"nodes": 0, "edges": 0, "density": 0, "components": 0, "avg_degree": 0, "max_indegree": 0}
    return {"nodes": nodes, "edges": edges,
            "density": round(nx.density(G), 5),
            "components": nx.number_weakly_connected_components(G),
            "avg_degree": round(sum(dict(G.degree()).values()) / nodes, 2),
            "max_indegree": max((d for _, d in G.in_degree()), default=0)}