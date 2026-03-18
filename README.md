# Citation Graph Builder
### Human Evolution Research — Citation Network Analysis

Find relationship patterns between major scientific papers in human evolution to highlight how research within a domain builds on and influences subsequent works.

---

## Overview

This project builds a directed citation graph from research papers in human evolution. Nodes represent academic papers and directed edges represent citation relationships (Paper A → Paper B means A cites B). The system collects metadata from open-access APIs, resolves references, and produces structured graph-ready CSVs.

---

## Project Structure

```
citation-graph-builder/
│
├── collect_data.py          # Phase 1: Collect seed papers + citation expansion
├── extract_references.py    # Phase 2: Fetch reference lists via EPMC / Semantic Scholar
├── storedata.py             # Phase 3: Generate final CSVs from corpus
├── citation_expander.py     # BFS citation expansion with relevance filtering
├── redownload_pdfs.py       # Repair broken PDF downloads
├── debug_pdf.py             # Diagnostic tool for PDF text inspection
├── requirements.txt         # Python dependencies
│
├── fetchers/                # Source-specific API clients
│   ├── __init__.py
│   ├── base_fetcher.py      # Shared rate limiting, HTTP, PDF download logic
│   ├── pmc_fetcher.py       # PubMed Central (OA service for real PDF URLs)
│   ├── europepmc_fetcher.py # Europe PMC REST API
│   ├── arxiv_fetcher.py     # arXiv (q-bio.PE, q-bio.GN categories)
│   └── biorxiv_fetcher.py   # bioRxiv (evolutionary biology category)
│
└── data/
    ├── raw/                 # Downloaded PDFs
    ├── processed/           # Extracted text / GROBID XML (future)
    └── metadata/
        ├── corpus.json          # All collected paper metadata
        ├── papers_metadata.csv  # One row per paper (16 columns)
        └── all_references.csv   # One row per citation edge
```

---

## Data Sources

| Source | Access Method | Rate Limit |
|--------|---------------|------------|
| PubMed Central (PMC) | E-utilities API + OA service for PDFs | 3 req/s (10/s with API key) |
| Europe PMC | REST API | ~5 req/s |
| arXiv | Atom feed API | 1 req/3s |
| bioRxiv | REST API | 2 req/s |
| Semantic Scholar | Graph API | ~1 req/s |

Reference extraction uses **Europe PMC `/references` endpoint** (primary) and **Semantic Scholar `/references` endpoint** (fallback). No PDFs are required for reference extraction.

---

## Seed Papers

The pipeline starts from these landmark human evolution papers (all post-1990, all with DOI/PMID):

| Paper | Year | DOI |
|-------|------|-----|
| Morphological affinities of the earliest modern humans | 2010 | 10.1126/science.1193975 |
| The complete genome sequence of a Neanderthal from the Altai Mountains | 2014 | 10.1038/nature12886 |
| Genomic history of the Acheulean stone tool-making Homo erectus | 2018 | 10.1126/science.aao6266 |
| Homo naledi, a new species of the genus Homo | 2015 | 10.7554/eLife.09560 |
| Fossil hominin shoulders support an African ape-like last common ancestor | 2015 | 10.1073/pnas.1511220112 |
| The genomic landscape of Neanderthal ancestry in present-day humans | 2014 | 10.1038/nature12961 |
| A Draft Sequence of the Neandertal Genome | 2010 | 10.1126/science.1188021 |

> **Why no Dart 1925 / Darwin 1871?** Pre-1990 papers and books are excluded because EPMC and Semantic Scholar do not carry structured reference lists for them and cannot contribute edges to the citation graph.

---

## Relevance Filtering

During citation expansion, every candidate paper is checked against two keyword sets before being added to the corpus. This prevents off-topic papers (immunology, oncology, plant biology, etc.) from being pulled in via citation chains.

**A paper must match at least one include term:**
homo, hominin, neanderthal, denisovan, australopithecus, fossil, ancient dna, admixture, human evolution, paleoanthropology, phylogenetic, stone tool, and more.

**A paper must match zero exclude terms:**
cancer, vaccine, bacteria, covid, diabetes, mouse model, plant, drosophila, and more.

Both lists are editable at the top of `citation_expander.py`.

---

## Setup

```bash
# Install dependencies
pip install -r requirements.txt
```

Optional: set your NCBI API key to raise PMC rate limit to 10 req/s:
```bash
export NCBI_API_KEY=your_key_here
```

---

## Running the Pipeline

### Fresh start (recommended)

```bash
# Step 1: Collect seed papers and expand citations (metadata only, no PDFs)
python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1

# Step 2: Fetch reference lists for every paper via EPMC + Semantic Scholar
python extract_references.py

# Step 3: Generate final CSVs
python storedata.py --validate
```

### With PDFs (for future full-text work)

```bash
python collect_data.py --max-papers 200 --expand-depth 1
python redownload_pdfs.py        # fix any broken downloads
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

---

## CLI Reference

### collect_data.py

| Flag | Default | Description |
|------|---------|-------------|
| `--max-papers` | 200 | Hard cap on total papers in corpus |
| `--skip-pdf` | False | Collect metadata only, skip PDF downloads |
| `--expand-depth` | 1 | Citation expansion hops from seeds (0 = seeds only, 1 = direct neighbours, 2 = neighbours of neighbours) |

**Expand depth guide:**
- `0` — 7 seed papers only
- `1` — seeds + papers they cite + papers that cite them *(recommended)*
- `2` — one further hop; grows very fast, use with a low `--max-papers`

### extract_references.py

| Flag | Description |
|------|-------------|
| `--limit N` | Only process first N papers |
| `--force` | Re-fetch even if already extracted |

### storedata.py

| Flag | Description |
|------|-------------|
| `--corpus PATH` | Custom path to corpus.json |
| `--validate` | Print QA summary after writing CSVs |

---

## Output Files

### `data/metadata/papers_metadata.csv`
One row per paper.

| Column | Description |
|--------|-------------|
| paper_id | Stable ID (DOI slug / pmid_X / hash_X) |
| title | Paper title |
| authors | Pipe-separated author list |
| year | Publication year |
| venue | Journal or conference |
| doi / pmid / pmcid / arxiv_id | Identifiers |
| source | Which fetcher collected this paper |
| has_pdf | yes/no |
| pdf_path | Local path to PDF if downloaded |
| abstract_snippet | First 300 chars of abstract |
| citation_count | From Europe PMC (where available) |
| is_open_access | yes/no |

### `data/metadata/all_references.csv`
One row per directed citation edge.

| Column | Description |
|--------|-------------|
| citing_paper_id | paper_id of the citing paper |
| cited_paper_id | paper_id of the cited paper (blank if unresolved) |
| citing_title | Title of citing paper |
| raw_reference | Raw reference string from API |
| parsed_authors / parsed_year / parsed_title / parsed_venue / parsed_doi | Parsed fields |
| resolution_method | How the match was made: `exact_doi`, `exact_pmid`, `exact_title`, `fuzzy_0.72`, or `unresolved` |

---

## Reference Resolution

Each reference is matched back to a corpus paper using a cascade:

1. **Exact DOI match** — most reliable
2. **Exact PMID match**
3. **Exact PMCID match**
4. **Exact title match** (lowercased)
5. **Fuzzy title match** — Jaccard similarity on words > 3 chars, threshold ≥ 0.55
6. **Unresolved** — kept in CSV with blank `cited_paper_id`

Unresolved references still appear as rows so they can be inspected and used as placeholder nodes in the graph.

---

## Debugging

### PDF issues

```bash
# Check which PDFs are broken (fake HTML pages saved as .pdf)
python redownload_pdfs.py --check

# Attempt to re-download broken PDFs
python redownload_pdfs.py

# Inspect raw text content of PDFs
python debug_pdf.py --search "References"
python debug_pdf.py --pdf data/raw/specific_paper.pdf
```

### Reference extraction

Check `data/collection.log` for per-paper results. The `resolution_method` column in `all_references.csv` shows exactly how each edge was resolved. Filter for `unresolved` rows to find references that need manual review.

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `No module named fetchers` | Script run from wrong directory | All scripts use `sys.path.insert` — run from the project root |
| PDFs contain "Preparing to download" | PMC redirect page saved as PDF | Run `python redownload_pdfs.py` |
| `No references found` for a paper | Paper not indexed in EPMC or S2 | Expected for pre-1990 papers; check `collection.log` |
| Off-topic papers in corpus | Citation chains lead outside domain | Tune `INCLUDE_TERMS` / `EXCLUDE_TERMS` in `citation_expander.py` |
| `TypeError: NoneType has no attribute 'get'` | Stale local script | Replace with latest version from outputs |
| Rate limit 429 errors | Too many requests | Fetchers enforce rate limits automatically; reduce `--max-papers` or add `NCBI_API_KEY` |
| 0 rows in all_references.csv | extract_references.py not run | Run step 2 before step 3 |
