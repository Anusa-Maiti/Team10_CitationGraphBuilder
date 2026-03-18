# Citation Graph Builder
### Human Evolution Research — Citation Network Analysis

Find relationship patterns between major scientific papers in human evolution to highlight how research within a domain builds on and influences subsequent works.

---

## Overview

This project builds a directed citation graph from research papers in human evolution. Nodes represent academic papers and directed edges represent citation relationships (Paper A → Paper B means A cites B). The pipeline covers five phases: data collection, reference extraction, entity resolution, graph construction, and querying/visualisation.

---

## Project Structure

```
citation-graph-builder/
│
├── collect_data.py          # Phase 1: Collect seed papers + citation expansion
├── extract_references.py    # Phase 2: Fetch reference lists via EPMC / Semantic Scholar
├── storedata.py             # Phase 2: Generate CSVs from corpus
├── citation_expander.py     # BFS citation expansion with relevance filtering
├── redownload_pdfs.py       # Repair broken PDF downloads
├── debug_pdf.py             # Diagnostic tool for PDF text inspection
├── requirements.txt
│
├── fetchers/                # Source-specific API clients
│   ├── base_fetcher.py      # Shared rate limiting, HTTP, PDF download
│   ├── pmc_fetcher.py       # PubMed Central
│   ├── europepmc_fetcher.py # Europe PMC
│   ├── arxiv_fetcher.py     # arXiv (q-bio.PE / q-bio.GN)
│   └── biorxiv_fetcher.py   # bioRxiv
│
├── resolution/              # Phase 3: Entity resolution          [planned]
│   ├── matcher.py           # Orchestration: DOI → fuzzy → placeholder
│   ├── doi_matcher.py       # Exact DOI matching
│   ├── fuzzy_matcher.py     # Title + author similarity matching
│   └── placeholder.py       # Creates placeholder nodes for unmatched refs
│
├── graph/                   # Phase 4: Graph construction          [planned]
│   ├── builder.py           # Builds NetworkX graph from resolved edges
│   ├── networkx_storage.py  # In-memory storage
│   ├── sqlite_storage.py    # SQLite relational storage
│   └── neo4j_storage.py     # Neo4j graph database
│
├── query/                   # Phase 5: Query & visualisation       [planned]
│   ├── cli.py               # Interactive command-line query tool
│   ├── queries.py           # in-degree, out-degree, neighbourhood, paths
│   └── visualization.py     # matplotlib / pyvis graph plots
│
├── analysis/                # Phase 5: Structural analysis         [planned]
│   ├── statistics.py        # Degree distributions, connected components
│   └── compare_storage.py   # Benchmark storage backends
│
└── data/
    ├── raw/                 # Downloaded PDFs
    ├── processed/           # GROBID TEI XML output
    ├── metadata/
    │   ├── corpus.json
    │   ├── papers_metadata.csv
    │   └── all_references.csv
    └── graph/
        ├── nodes.csv
        ├── edges.csv
        └── graph.gexf       # For Gephi / network visualisation
```

---

## Pipeline

### Phase 1 — Data Collection ✅

Collects paper metadata from four open-access sources (PMC, Europe PMC, arXiv, bioRxiv) starting from 7 landmark seed papers in human evolution, then expands outward via forward and backward citation links.

**Relevance filter:** every expanded paper's title + venue + abstract is checked against human evolution keyword lists (`INCLUDE_TERMS` / `EXCLUDE_TERMS` in `citation_expander.py`) before entering the corpus, preventing off-topic papers from citation chains (immunology, oncology, etc.).

**Eligibility filter:** only papers published 1990 or later with at least one structured identifier (DOI / PMID / PMCID) are collected, since pre-1990 papers have no structured reference lists in any digital database.

```bash
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1
```

Outputs: `data/metadata/corpus.json`

---

### Phase 2 — Reference Extraction ✅

For each paper in the corpus, fetches its full reference list from the Europe PMC `/references` API (primary) or Semantic Scholar `/references` API (fallback). No PDFs required.

Each reference is resolved to a corpus paper using a cascade: exact DOI → exact PMID → exact title → fuzzy title match (Jaccard ≥ 0.55) → unresolved. Unresolved references are kept as rows with a blank `cited_paper_id` for use as placeholder nodes later.

```bash
python extract_references.py
python storedata.py --validate
```

Outputs: `data/metadata/papers_metadata.csv`, `data/metadata/all_references.csv`

---

### Phase 3 — Entity Resolution [planned]

The `resolution/` module will handle disambiguation of references that survive Phase 2 unresolved:

- **DOI matching** (`doi_matcher.py`) — query Crossref/EPMC with partial DOIs or inferred DOIs
- **Fuzzy matching** (`fuzzy_matcher.py`) — title + first author + year similarity using `rapidfuzz`, threshold configurable
- **Placeholder creation** (`placeholder.py`) — unmatched references become placeholder nodes with `is_placeholder = True` flag, preserving the edge in the graph

Resolution strategy is documented per-reference in `all_references.csv` via the `resolution_method` column.

---

### Phase 4 — Graph Construction [planned]

The `graph/` module builds a directed NetworkX graph from `nodes.csv` and `edges.csv` and supports three storage backends for comparison:

| Backend | Module | Use case |
|---------|--------|----------|
| NetworkX (in-memory) | `networkx_storage.py` | Fast querying, small corpora |
| SQLite | `sqlite_storage.py` | Persistent, no server needed |
| Neo4j | `neo4j_storage.py` | Native graph queries, large corpora |

```bash
python scripts/build_graph.py --storage sqlite
```

Outputs: `data/graph/nodes.csv`, `data/graph/edges.csv`, `data/graph/graph.gexf`

---

### Phase 5 — Querying & Analysis [planned]

The `query/` and `analysis/` modules will provide:

- In-degree / out-degree per paper (how much a paper is cited / how many it cites)
- Local citation neighbourhood exploration
- Shortest path between any two papers
- Degree distribution, connected components, citation depth
- Storage backend benchmarks
- Interactive CLI: `python scripts/query_cli.py --interactive`
- Graph visualisation via matplotlib (static) and pyvis (interactive HTML)

---

## Running the Full Pipeline

```bash
# 1. Collect
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1

# 2. Extract references
python extract_references.py

# 3. Generate CSVs
python storedata.py --validate

# 4. Build graph  [planned]
python scripts/build_graph.py --storage sqlite

# 5. Query        [planned]
python scripts/query_cli.py --interactive
```

Full reset:
```bash
rm -rf data/
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1
python extract_references.py
python storedata.py --validate
```

---

## Key Parameters

| Flag | Script | Default | Description |
|------|--------|---------|-------------|
| `--max-papers` | collect_data.py | 200 | Hard cap on corpus size |
| `--skip-pdf` | collect_data.py | False | Metadata only, no PDF downloads |
| `--expand-depth` | collect_data.py | 1 | Citation hops from seeds (0=seeds only, 1=direct neighbours, 2=two hops) |
| `--force` | extract_references.py | False | Re-fetch even if already extracted |
| `--limit N` | extract_references.py | all | Process only first N papers |
| `--validate` | storedata.py | False | Print QA summary after writing CSVs |

---

## Output Schema

### papers_metadata.csv
`paper_id`, `title`, `authors`, `year`, `venue`, `doi`, `pmid`, `pmcid`, `arxiv_id`, `source`, `has_pdf`, `pdf_path`, `abstract_snippet`, `citation_count`, `is_open_access`, `collected_at`

### all_references.csv
`citing_paper_id`, `cited_paper_id`, `citing_title`, `raw_reference`, `parsed_authors`, `parsed_year`, `parsed_title`, `parsed_venue`, `parsed_doi`, `resolution_method`

---

## Common Issues

| Issue | Solution |
|-------|----------|
| PDFs contain "Preparing to download" | Run `python redownload_pdfs.py` |
| `No module named fetchers` | Run scripts from the project root directory |
| 0 rows in all_references.csv | Run `extract_references.py` before `storedata.py` |
| Off-topic papers in corpus | Edit `INCLUDE_TERMS` / `EXCLUDE_TERMS` in `citation_expander.py` |
| No references found for a paper | Expected for pre-1990 papers; check `data/collection.log` |
| Rate limit 429 errors | Set `NCBI_API_KEY` env var; fetchers enforce limits automatically |
