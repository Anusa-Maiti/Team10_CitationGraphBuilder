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
| **Semantic Scholar** | Graph API | Reference lists, metadata | ~1 request/second |

### Seed Papers
The pipeline starts from these 7 landmark human evolution papers. Only papers published **1990 or later** with at least one structured identifier (DOI / PMID / PMCID) are eligible — pre-1990 papers (e.g. Dart 1925, Darwin 1871) are excluded because EPMC and Semantic Scholar do not carry structured reference lists for them and cannot contribute edges to the citation graph.

| Paper | Year | DOI |
|-------|------|-----|
| Morphological affinities of the earliest modern humans | 2010 | 10.1126/science.1193975 |
| The complete genome sequence of a Neanderthal from the Altai Mountains | 2014 | 10.1038/nature12886 |
| Genomic history of the Acheulean stone tool-making Homo erectus | 2018 | 10.1126/science.aao6266 |
| Homo naledi, a new species of the genus Homo from the Dinaledi Chamber | 2015 | 10.7554/eLife.09560 |
| Fossil hominin shoulders support an African ape-like last common ancestor | 2015 | 10.1073/pnas.1511220112 |
| The genomic landscape of Neanderthal ancestry in present-day humans | 2014 | 10.1038/nature12961 |
| A Draft Sequence of the Neandertal Genome | 2010 | 10.1126/science.1188021 |

### Secondary Collection
All papers cited by these landmark papers, and all papers that cite them (forward/backward citation expansion via Europe PMC and Semantic Scholar APIs).

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
├── processed/              # Extracted text/XML
│   ├── dart_1925_tei.xml   # GROBID output
│   └── ...
├── metadata/               # Paper information
│   ├── corpus.json
│   ├── papers_metadata.csv
│   └── all_references.csv
└── graph/                  # Final graph data
    ├── nodes.csv
    ├── edges.csv
    └── graph.gexf          # For visualization
```

##  Preprocessing Plans
### Phase 1: Data Collection
```
1. Query source APIs starting from seed papers:
   - "human evolution" + "homo" + "neanderthal"
   - Author names from landmark papers

2. Filter: open-access only, published 1990+, must have DOI/PMID/PMCID
3. Expand citations: fetch papers that cite seeds (forward) and papers seeds cite (backward)
4. Apply relevance filter on every candidate before adding to corpus
5. Download PDFs to data/raw/ via PMC OA service (not the redirect /pdf/ URL)
6. Log all downloads with source, DOI, timestamp in data/collection.log
7. Implement rate limiting per source (see table above)
```

### Phase 2: Reference Extraction
Reference lists are fetched directly from APIs — no PDF parsing required.

- **Primary:** Europe PMC `/references` endpoint. Uses PMID or PMCID directly; if only a DOI is available it resolves it to a PMID via EPMC search first.
- **Fallback:** Semantic Scholar `/references` endpoint. Uses DOI or PMID if available; if neither exists, performs a title search to get a Semantic Scholar paper ID first.

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
citation-graph-builder/
│
├── README.md
├── requirements.txt
│
├── collect_data.py          # Phase 1: seed collection + citation expansion
├── extract_references.py    # Phase 2: reference list extraction via EPMC / S2
├── storedata.py             # Generates papers_metadata.csv + all_references.csv
├── citation_expander.py     # BFS expansion with relevance + eligibility filters
├── redownload_pdfs.py       # Detects and repairs broken PDF downloads
├── debug_pdf.py             # Inspects PDF text content for diagnostics
│
├── fetchers/                # Source-specific API clients
│   ├── __init__.py
│   ├── base_fetcher.py      # Shared rate limiting, HTTP helpers, PDF download
│   ├── pmc_fetcher.py       # PubMed Central (uses OA service for real PDF URLs)
│   ├── europepmc_fetcher.py # Europe PMC REST API
│   ├── arxiv_fetcher.py     # arXiv q-bio categories
│   └── biorxiv_fetcher.py   # bioRxiv evolutionary biology category
│
├── resolution/              # Entity resolution and matching         [planned]
│   ├── __init__.py
│   ├── matcher.py
│   ├── fuzzy_matcher.py
│   ├── doi_matcher.py
│   └── placeholder.py
│
├── graph/                   # Graph construction and storage         [planned]
│   ├── __init__.py
│   ├── builder.py
│   ├── networkx_storage.py
│   ├── neo4j_storage.py
│   └── sqlite_storage.py
│
├── query/                   # Query and visualization interface      [planned]
│   ├── __init__.py
│   ├── cli.py
│   ├── queries.py
│   └── visualization.py
│
└── analysis/                # Graph analysis utilities               [planned]
    ├── __init__.py
    ├── statistics.py
    └── compare_storage.py
```

#  Testing and Debugging
## Unit Tests
### Matcher() for testing exact and fuzzy matches
Test pipeline on 3 known papers:
1. Download 3 test PDFs (if not exists)
2. Extract metadata
3. Build graph
4. Verify known citation relationships

Example: Green 2010 should cite Green 2006
```python
assert graph.has_edge('green_2010', 'green_2006')
```

## Debugging Strategy
```
debug/
├── unmatched_references.csv    # References that failed matching
│                               # (rows in all_references.csv where cited_paper_id is blank)
├── parsing_errors.csv          # PDFs that failed extraction
├── sample_references/          # Random sample for manual inspection
│   ├── paper_123_refs.txt
│   └── ...
└── matching_decisions.log      # resolution_method column in all_references.csv
                                # records why each match was made/rejected
```

### PDF Diagnostics
```bash
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

#  Running the Pipeline
## Quick Start
```bash
# 1. Install
pip install -r requirements.txt
export NCBI_API_KEY=your_key_here   # optional — raises PMC rate limit to 10 req/s

# 2. Collect papers (metadata only, no PDFs)
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1

# 3. Extract reference lists via EPMC + Semantic Scholar APIs
python extract_references.py

# 4. Generate CSVs
python storedata.py --validate

# 5. Build graph  [planned]
python scripts/build_graph.py --storage sqlite

# 6. Explore  [planned]
python scripts/query_cli.py --interactive
```

### With PDFs (for GROBID / full-text work)
```bash
python collect_data.py --max-papers 200 --expand-depth 1
python redownload_pdfs.py    # fix any broken downloads
python extract_references.py
python storedata.py --validate
```

### Full reset
```bash
rm -rf data/
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1
python extract_references.py
python storedata.py --validate
```

### expand-depth guide
| Value | Scope | Recommended |
|-------|-------|-------------|
| `0` | Seed papers only (7 papers) | Testing |
| `1` | Seeds + direct citation neighbours | ✅ Normal use |
| `2` | Two hops out — grows very fast | Use with low --max-papers |

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

# Expected Outputs
After running the pipeline, you should have:

**Citation Graph Data**
- `data/metadata/papers_metadata.csv` — all papers with 16 metadata columns
- `data/metadata/all_references.csv` — all citation edges with resolution method
- `data/graph/nodes.csv` — graph nodes
- `data/graph/edges.csv` — graph edges
- `data/graph/graph.gexf` — for Gephi visualization

**Statistics**
- `reports/statistics.json` — degree distributions, components
- `reports/storage_comparison.json` — performance benchmarks

**Query Interface**
- Command-line tool for exploring the graph
- Sample visualizations in notebooks/

#  Common Issues and Solutions

| Issue | Symptom | Solution |
|:------|:--------|:---------|
| **Broken PDFs** | File contains "Preparing to download" | Run `python redownload_pdfs.py` — uses PMC OA service for real URLs |
| **0 rows in all_references.csv** | CSV written before extraction | Run `extract_references.py` before `storedata.py` |
| **No references found** | Pre-1990 or unindexed paper | Expected — pre-1990 papers are skipped; check `data/collection.log` |
| **Off-topic papers** | Immunology/oncology in corpus | Edit `INCLUDE_TERMS`/`EXCLUDE_TERMS` in `citation_expander.py` |
| **No module named fetchers** | Wrong working directory | Run all scripts from the project root |
| **Rate limiting** | Downloads fail with 429 | Set `NCBI_API_KEY`; fetchers enforce limits automatically |
| **Poor matching** | Many unresolved references | Lower fuzzy threshold (0.55 → 0.45) in `extract_references.py` |
| **Memory error** | Graph building crashes | Switch from NetworkX to SQLite or Neo4j storage |
| **Duplicate nodes** | Same paper appears twice | Primary dedup key is DOI; check `make_paper_id()` in `storedata.py` |
| **Encoding issues** | Special chars (Pääbo) garbled | UTF-8 encoding enforced in all CSV writers |
| **API quota exceeded** | 403/429 from Semantic Scholar | Add delay; S2 enforces 1 req/s — reduce `--max-papers` |
