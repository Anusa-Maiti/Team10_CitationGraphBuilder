#  Citation Graph Builder

To find relationship patterns between major scientific papers in Human Evolution to highlight how research within a domain builds on and influences subsequent works.

##  Overview
This project builds a directed citation graph from research papers in human evolution. Nodes represent academic papers, and directed edges represent citation relationships (Paper A → Paper B means A cites B). The system extracts metadata from PDFs, resolves ambiguous references, and provides querying and visualization capabilities.

##  Data Sources
### Primary Repositories

| Source | Access Method | Content Type | Rate Limits |
|--------|---------------|--------------|-------------|
| **PubMed Central (PMC)** | OAI-PMH API, OA service for real PDF URLs | Full-text PDFs, XML | 3 req/s (10/s with NCBI_API_KEY) |
| **Europe PMC** | REST API | PDFs, metadata, reference lists | None documented |
| **arXiv (q-bio)** | API | Preprint PDFs | 1 request/3 seconds |
| **BioRxiv** | API | Preprint PDFs | 2 requests/second |

### Query Terms
Papers are collected by running search queries against the APIs. Default queries are defined in `collect_data.py` and cover the main subfields of human evolution:

```
    "human evolution fossil hominin",
    "neanderthal genome ancient dna",
    "homo naledi new species",
    "australopithecus paleoanthropology",
    "archaic human introgression admixture",
    "modern human origins out of africa",
    "denisovan hominin phylogeny",
    "stone tool acheulean oldowan",
    "homo erectus migration dispersal",
    "early homo sapiens morphology",
```

Custom queries can be passed at runtime:
```bash
python collect_data.py --queries "your query" "another query"
```

Only papers published **1990 or later** with at least one structured identifier (DOI / PMID / PMCID) are collected — pre-1990 papers are excluded because EPMC  do not carry structured reference lists for them and cannot contribute edges to the citation graph.

### Adding Papers Manually (Dashboard Workflow)
A specific paper can be added to the corpus at any time by DOI or PMID, without re-running the full collection. This powers the dashboard's "add paper" feature:

```bash
python collect_data.py --add-doi 10.1038/nature12886
python collect_data.py --add-pmid 24352235
```

After adding, re-run `extract_references.py` to fetch its reference list and update the graph edges.

### Secondary Collection
All papers cited by the collected papers, and all papers that cite them (forward/backward citation expansion via Europe PMC and Semantic Scholar APIs). Disabled by default; enable with `--expand-depth 1`.

### Relevance Filtering
During citation expansion every candidate paper's title + venue + abstract is checked against two keyword sets before entering the corpus. This prevents off-topic papers (immunology, oncology, plant biology, etc.) from being pulled in via citation chains.

- **Must match at least one include term:** homo, hominin, neanderthal, denisovan, australopithecus, fossil, ancient dna, admixture, human evolution, paleoanthropology, phylogenetic, stone tool, and more.
- **Must match zero exclude terms:** cancer, vaccine, bacteria, covid, diabetes, mouse model, plant, drosophila, and more.

Both lists are editable at the top of `citation_expander.py`.

### Data Storage Plan
```
data/
├── raw/                    # Original PDFs
│   ├── homo_naledi_...pdf
│   └── ...
├── processed/              # Extracted text/XML (reserved for future full-text work)
├── metadata/               # Paper information
│   ├── corpus.json
│   ├── papers_metadata.csv
│   └── all_references.csv

##  Preprocessing Plans
### Phase 1: Data Collection
```
1. Run each query string against all four source APIs (EPMC, PMC, arXiv, bioRxiv)
2. Filter results: published 1990+, must have DOI/PMID/PMCID
3. Apply relevance filter (INCLUDE_TERMS / EXCLUDE_TERMS in citation_expander.py)
4. Deduplicate across queries by DOI/PMID
5. Optionally download PDFs via PMC OA service (--skip-pdf to collect metadata only)
6. Log all results with source, DOI, timestamp in data/collection.log
7. Optionally expand citations (--expand-depth 1) to pull in related papers
```

### Phase 2: Reference Extraction
Reference lists are fetched directly from APIs — no PDF parsing required.

- **Primary:** Europe PMC `/references` endpoint. Uses PMID or PMCID directly; if only a DOI is available it resolves it to a PMID via EPMC search first.
- **Fallback:** Uses DOI or PMID if available; if neither exists, performs a title search to get a Semantic Scholar paper ID first.

Each reference is then resolved to a corpus paper via the cascade in Phase 3. Papers with no structured identifier or published before 1990 are skipped — these are not indexed in either API.

```bash
python extract_references.py           # all papers
python extract_references.py --limit 10   # test on first 10
python extract_references.py --force      # re-fetch already-extracted papers
```

*Output*: `all_references.csv` with one row per citation edge, `corpus.json` updated with `references` field on each paper.

### Phase 3: Metadata Extraction
All metadata (title, authors, year, venue, DOI, PMID, PMCID, abstract, citation count, open-access status) is extracted directly from API responses during collection and stored in `corpus.json`. Running `storedata.py` flattens this into `papers_metadata.csv`.

### Phase 4: Entity Resolution
Match a parsed reference to a paper in the corpus using a cascade:
1. Exact DOI match
2. Exact PMID / PMCID match
3. Exact title match
4. Fuzzy match on title + first author + year (Jaccard similarity ≥ 0.55)

Unmatched references: create placeholder nodes with extracted metadata and flag `is_placeholder = True`

The `resolution_method` column in `all_references.csv` records how each edge was resolved.

#  Code Structure
```
Team10_CitationGraphBuilder/
│
├── README.md
│
├── data_collection/                     # Main data pipeline scripts
│   ├── data/                            # Collected data outputs
│   ├── fetchers/                        # Source-specific API clients
│   │   ├── __init__.py
│   │   ├── base_fetcher.py              # Shared rate limiting, HTTP helpers, PDF download
│   │   ├── pmc_fetcher.py               # PubMed Central (uses OA service for real PDF URLs)
│   │   ├── europepmc_fetcher.py         # Europe PMC REST API
│   │   ├── arxiv_fetcher.py             # arXiv q-bio categories
│   │   └── biorxiv_fetcher.py           # bioRxiv evolutionary biology category
│   │
│   ├── citation_expander.py             # BFS expansion with relevance + eligibility filters
│   ├── collect_data.py                  # Phase 1: seed collection + citation expansion
│   ├── collect_data_seeded.py           # Phase 1 (seeded variant): fixed seed paper list
│   ├── debug_pdf.py                     # Inspects PDF text content for diagnostics
│   ├── extract_references.py            # Phase 2: reference list extraction via EPMC / S2
│   ├── improved_GC_dashboard.py         # Gestalt-principles dashboard (alternate UI)
│   ├── redownload_pdfs.py               # Detects and repairs broken PDF downloads
│   ├── requirements.txt                 # Python dependencies
│   └── storedata.py                     # Generates papers_metadata.csv + all_references.csv
│
├── graph/                               # Graph construction and storage
│   ├── citation_graph.db                # SQLite graph database
│   ├── edges_list.csv                   # Citation edges
│   ├── network_map.gexf                 # Gephi-compatible graph export
│   ├── networkx_analysis.py             # NetworkX graph analysis utilities
│   ├── nodes_list.csv                   # Graph nodes
│   └── sqlite_storage.py                # SQLite storage backend
│
├── final_run_dashboard/                 # Entry point — run the dashboard from here
│   ├── data/                            # Dashboard data directory
│   ├── fetchers/                        # Fetcher modules (mirrored for standalone use)
│   ├── lib/                             # Shared library modules
│   ├── citation_expander.py
│   ├── collect_data.py
│   ├── collect_data_seeded.py
│   ├── dashboard.py                     #  Main dashboard entry point
│   ├── debug_pdf.py
│   ├── extract_references.py
│   ├── redownload_pdfs.py
│   ├── requirements.txt
│   └── storedata.py
│
└── analysis/                            # Graph analysis utilities
    ├── __init__.py
    ├── statistics.py                    # Degree distributions, components, centrality
    └── compare_storage.py               # Performance benchmarks across storage backends
```

#  Running the Dashboard

## Quick Start (Recommended)

The dashboard is the primary interface for exploring the citation graph. Run it from the `final_run_dashboard/` directory:

```bash
(create and activate venv)
cd final_run_dashboard/

# Install dependencies
pip install -r requirements.txt

# Optional: set NCBI API key to raise PMC rate limit to 10 req/s
export NCBI_API_KEY=your_key_here

# Launch the dashboard
python -m streamlit run dashboard.py
```

## Full Pipeline (from scratch)

```bash
cd final_run_dashboard/

# 1. Collect papers (metadata only, no PDFs)
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1

# 2. Extract reference lists via EPMC + Semantic Scholar APIs
python extract_references.py

# 3. Generate CSVs
python storedata.py --validate

# 4. Launch dashboard
python -m streamlit run dashboard.py
```

## Add a Single Paper

```bash
cd final_run_dashboard/

python collect_data.py --add-doi 10.1038/nature12886
python collect_data.py --add-pmid 24352235

# Then update the graph edges
python extract_references.py
```

## Full Reset

```bash
cd final_run_dashboard/
rm -rf data/
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1
python extract_references.py
python storedata.py --validate
python dashboard.py
```

### expand-depth guide
| Value | Scope | Recommended |
|-------|-------|-------------|
| `0` | Seed papers only (~7 papers) | Testing |
| `1` | Seeds + direct citation neighbours | Normal use |
| `2` | Two hops out — grows very fast | Use with low --max-papers |

## Graph Analysis

After the pipeline has run, compute graph statistics and compare storage backends:

```bash
# From the project root
python analysis/statistics.py --input graph/citation_graph.db --output reports/

# Compare NetworkX vs SQLite vs Neo4j performance
python analysis/compare_storage.py --output reports/storage_comparison.json
```

### Configuration (config.yaml) [planned]
```yaml
project:
  name: "human_evolution_citation_graph"
  data_dir: "./data"

acquisition:
  min_year: 1990
  require_identifier: true   # must have DOI, PMID, or PMCID
  sources:
    pmc:
      enabled: true
      rate_limit: 3
    arxiv:
      enabled: true
      categories: ["q-bio.PE"]

extraction:
  method: "api"          # Europe PMC + Semantic Scholar (no PDF parsing required)

matching:
  thresholds:
    doi: 1.0
    fuzzy_title: 0.55
  create_placeholders: true

graph:
  storage:
    primary: "sqlite"
    compare_with: ["networkx", "neo4j"]

query:
  visualization:
    max_neighbors: 50
    layout: "spring_layout"
```
## Debugging Strategy
```
bash
# Check which PDFs downloaded correctly (broken ones contain "Preparing to download")
python redownload_pdfs.py --check

# Re-download broken PDFs via PMC OA service + Europe PMC + Unpaywall fallback
python redownload_pdfs.py

# Inspect raw text content and find reference section headers
python debug_pdf.py --search "References"
python debug_pdf.py --pdf data/raw/specific_paper.pdf
```

### Validation Checks:
1. No self-citations
2. All cited papers exist as nodes (or are flagged as placeholders)
3. Reasonable statistics — check `resolution_method` distribution in `all_references.csv`
4. All papers in corpus are post-1990 with at least one identifier

# Expected Outputs
After running the pipeline, we should have:

**Citation Graph Data**
- `data/metadata/papers_metadata.csv` — all papers with 16 metadata columns
- `data/metadata/all_references.csv` — all citation edges with resolution method
- `graph/nodes_list.csv` — graph nodes
- `graph/edges_list.csv` — graph edges
- `graph/network_map.gexf` — for Gephi visualization
- `graph/citation_graph.db` — SQLite graph database

**Statistics**
- `reports/statistics.json` — degree distributions, components, centrality
- `reports/storage_comparison.json` — performance benchmarks

**Query Interface**
- Dashboard launched via `python final_run_dashboard/dashboard.py`
- Sample visualizations

#  Common Issues and Solutions

| Issue | Symptom | Solution |
|:------|:--------|:---------|
| **Broken PDFs** | File contains "Preparing to download" | Run `python redownload_pdfs.py` — uses PMC OA service for real URLs |
| **0 rows in all_references.csv** | CSV written before extraction | Run `extract_references.py` before `storedata.py` |
| **No references found** | Pre-1990 or unindexed paper | Expected — pre-1990 papers are skipped; check `data/collection.log` |
| **Off-topic papers** | Immunology/oncology in corpus | Edit `INCLUDE_TERMS`/`EXCLUDE_TERMS` in `citation_expander.py` |
| **No module named fetchers** | Wrong working directory | Run all scripts from `final_run_dashboard/` |
| **Rate limiting** | Downloads fail with 429 | Set `NCBI_API_KEY`; fetchers enforce limits automatically |
| **Poor matching** | Many unresolved references | Lower fuzzy threshold (0.55 → 0.45) in `extract_references.py` |
| **Memory error** | Graph building crashes | Switch from NetworkX to SQLite or Neo4j storage |
| **Duplicate nodes** | Same paper appears twice | Primary dedup key is DOI; check `make_paper_id()` in `storedata.py` |
| **Encoding issues** | Special chars (Pääbo) garbled | UTF-8 encoding enforced in all CSV writers |
| **API quota exceeded** | 403/429 from Semantic Scholar | Add delay; S2 enforces 1 req/s — reduce `--max-papers` |
| **Dashboard won't start** | ModuleNotFoundError | Run from `final_run_dashboard/` directory, not project root |
