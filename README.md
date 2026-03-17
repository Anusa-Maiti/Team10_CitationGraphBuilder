#  Citation Graph Builder

To find relationship patterns between major scientific papers in Human Evolution to highlight how research within a domain builds on and influences subsequent works.

##  Overview
This project builds a directed citation graph from research papers in human evolution. Nodes represent academic papers, and directed edges represent citation relationships (Paper A → Paper B means A cites B). The system extracts metadata from PDFs, resolves ambiguous references, and provides querying and visualization capabilities.

##  Data Sources
### Primary Repositories

| Source | Access Method | Content Type | Rate Limits |
|--------|---------------|--------------|-------------|
| **PubMed Central (PMC)** | OAI-PMH API, FTP bulk download | Full-text PDFs, XML | 3 requests/second |
| **Europe PMC** | REST API | PDFs, metadata | None documented| 
| **arXiv (q-bio)** | API | Preprint PDFs | 1 request/3 seconds | 
| **BioRxiv** | API | Preprint PDFs | 2 requests/second |

### Secondary Collection: 
All papers cited by these landmark papers, and all papers that cite them (forward/backward citation expansion)

### Data Storage Plan
```
data/
├── raw/                    # Original PDFs
│   ├── dart_1925.pdf
│   └── ...
├── processed/              # Extracted text/XML
│   ├── dart_1925_tei.xml   # GROBID output
│   └── ...
├──storedata.py             #generate csv file from metadata in corpus
├── metadata/               # Paper information
│   ├── corpus.json
    ├──papers_metadata.csv
    └── all_references.csv
    
└── graph/                  # Final graph data
    ├── nodes.csv
    ├── edges.csv
    └── graph.gexf          # For visualization
```
    
##  Preprocessing Plans
### Phase 1: PDF Acquisition
python
*Pseudocode for downloader*
1. Query source APIs with search terms:
   - "human evolution" + "australopithecus"
   - "Neanderthal" + "genome"
   - Author names: "Author eg.1", "Author eg.2"
   
2. Filter for open-access PDFs only
3. Download to /data/raw/ with consistent naming
4. Log all downloads with source URL, DOI, timestamp
5. Implement exponential backoff for rate limits
   
### Phase 2: Text Extraction
*GROBID* (GeneRation Of BIbliographic Data) - an open-source Java machine learning library for parsing, structuring, and extracting metadata, references, and full-text from academic PDFs into TEI-encoded XML

Run GROBID as Docker container
Process PDFs via Python
*Output*: TEI XML with structured metadata and parsed references

### Phase 3: Metadata Extraction
From GROBID XML extract title, author, year, venue

### Phase 4: Reference Parsing 
AnyStyle (free, machine learning-powered web application that parses unstructured bibliographic references into formats like BibTeX or CSL/CiteProc JSON

### Phase 5: Entity Resolution
Match a parsed reference to a paper in our corpus :
1. Exact DOI match
2. Fuzzy match on title + first author + year
Unmatched references: Create placeholder nodes with extracted metadata and flag is_placeholder = True

#  Code Structure
```
citation-graph-builder/
│
├── README.md                    # Project overview, setup instructions, and documentation
├── requirements.txt             # Python dependencies (networkx, streamlit, PyPDF2, etc.)
├── config.yaml                  # Configuration file for API keys, paths, matching thresholds
├── setup.py                     # Package installation script
│
├── src/                         # Main source code directory
│   ├── __init__.py              # Makes src a Python package
│   ├──data_collection.py        #Data extraction from web-sources
│   ├── data                     # Input data storage modules
        ├──raw
        ├──processed
        ├──metadata
            ├── corpus.json
            ├── papers_metadata.csv     # Main papers CSV
            └── all_references.csv      # References CSV 
│   │
│   ├── resolution/              # Entity resolution and matching
│   │   ├── __init__.py          # Package initializer
│   │   ├── matcher.py           # Main orchestration logic for matching references
│   │   ├── fuzzy_matcher.py     # Fuzzy string matching utilities (title/author similarity)
│   │   ├── doi_matcher.py       # DOI-based exact matching
│   │   └── placeholder.py       # Creates placeholder nodes for unmatched references
│   │
│   ├── graph/                    # Graph construction and storage
│   │   ├── __init__.py           # Package initializer
│   │   ├── builder.py            # Builds NetworkX graph from matched papers
│   │   ├── storage.py            # Abstract interface for graph storage
│   │   ├── networkx_storage.py   # In-memory storage using NetworkX
│   │   ├── neo4j_storage.py      # Neo4j graph database implementation
│   │   └── sqlite_storage.py     # SQLite relational storage for graphs
│   │
│   ├── query/                     # Query and visualization interface
│   │   ├── __init__.py            # Package initializer
│   │   ├── cli.py                 # Command-line interface for queries
│   │   ├── queries.py             # Core query functions (in-degree, out-degree, neighbors)
│   │   └── visualization.py       # Graph plotting with matplotlib/NetworkX
│   │
│   └── analysis/                   # Graph analysis utilities
│       ├── __init__.py             # Package initializer
│       ├── statistics.py           # Computes degree distributions, connected components
│       └── compare_storage.py      # Benchmarks different storage approaches
│
├── tests/                          # Testing directory
│   ├── __init__.py                 # Makes tests a package
│   ├── test_downloader.py          # Tests for downloader modules
│   ├── test_parser.py              # Tests for PDF parsing functions
│   ├── test_matcher.py             # Tests for entity resolution logic
│   ├── test_graph.py               # Tests for graph construction
│   └── fixtures/                    # Test data files
│       ├── sample_paper.pdf        # Small PDF for testing extraction
│       └── expected_output.json    # Expected metadata for validation
│
├── scripts/                         # Executable pipeline scripts
│   ├── run_pipeline.py              # Master script to run entire pipeline end-to-end
│   ├── download_corpus.py           # Step 1: Download PDFs from sources
│   ├── extract_all.py               # Step 2: Process all PDFs and extract metadata
│   ├── build_graph.py               # Step 3: Build citation graph from extracted data
│   ├── query_cli.py                  # Interactive query tool for exploring the graph
│   └── benchmark_storage.py          # Compares performance of storage backends
│
└── notebooks/                        # Jupyter notebooks for exploration
    ├── 01_exploratory_analysis.ipynb # Initial data exploration
    ├── 02_citation_network_viz.ipynb # Network visualization experiments
    └── 03_storage_comparison.ipynb   # Detailed storage performance analysis
```    
#  Testing and Debugging
## Unit Tests
Matcher() for testing exact and fuzzy matches
Test pipeline on 3 known papers"""
    # Download 3 test PDFs (if not exists)
    # Extract metadata
    # Build graph
    # Verify known citation relationships
    # Example: Green 2010 should cite Green 2006
    assert graph.has_edge('green_2010', 'green_2006')


## Debugging Strategy
```
debug/
├── unmatched_references.csv    # References that failed matching
├── parsing_errors.csv          # PDFs that failed extraction
├── sample_references/           # Random sample for manual inspection
│   ├── paper_123_refs.txt
│   └── ...
└── matching_decisions.log      # Why each match was made/rejected
```

Validation Checks:
1. No self-citations
2. All cited papers exist as nodes
3. Reasonable statistics
   
#  Running the Pipeline
## Quick Start
bash
*1. Clone and install*
git clone https://github.com/yourname/citation-graph-builder
cd citation-graph-builder
pip install -r requirements.txt

*2. Configure*
cp config.yaml.example config.yaml
### Edit config.yaml with our preferences

*3. Run GROBID (if using)*
  ```
    # Run CPU version (simplest)
    docker run -d --name grobid -p 8070:8070 grobid/grobid:0.8.0
    # Wait 30 seconds
    echo "Waiting 30 seconds for GROBID to start..."
    sleep 30
    # Test it
    curl http://localhost:8070/api/isalive
    # Run script for metadata extraction
    python data_collection.py --count 5
    timeout: 30  # seconds
```
*4. Download papers*
python scripts/download_corpus.py --domain "human_evolution" --max-papers 50

*5. Extract metadata*
python scripts/extract_all.py --method grobid

*6. Build graph*
python scripts/build_graph.py --storage sqlite

*7. Explore*
python scripts/query_cli.py --interactive
Configuration Example (config.yaml)
yaml
project:
  name: "human_evolution_citation_graph"
  data_dir: "./data"

acquisition:
  sources:
    pmc:
      enabled: true
      rate_limit: 3  # requests/second
      search_terms:
        - "human evolution"
        - "australopithecus"
        - "neanderthal genome"
    arxiv:
      enabled: true
      categories: ["q-bio.PE"]  # Population Biology
      
extraction:
  method: "grobid"  # or "pdfplumber"
  grobid_url: "http://localhost:8070"

matching:
  thresholds:
    doi: 1.0
    fuzzy_title: 0.85
  create_placeholders: true
  
graph:
  storage:
    primary: "sqlite"  # Options: networkx, sqlite, neo4j
    compare_with: ["networkx", "neo4j"]  # For benchmark
  
query:
  visualization:
    max_neighbors: 50
    layout: "spring_layout"

    
# Expected Outputs
After running the pipeline, you should have:

Citation Graph Data

data/graph/nodes.csv - All papers with metadata

data/graph/edges.csv - All citation relationships

data/graph/graph.gexf - For Gephi visualization

Statistics

reports/statistics.json - Degree distributions, components

reports/storage_comparison.json - Performance benchmarks

Query Interface

Command-line tool for exploring the graph

Sample visualizations in notebooks/

#  Common Issues and Solutions

| Issue | Symptom | Solution |
|:------|:--------|:---------|
| **Rate limiting** | Downloads fail with 429 error | Increase delay between requests in `config.yaml` (e.g., from 1s to 3s) |
| **GROBID timeout** | Extraction hangs or fails | Reduce PDF size (split large documents), increase timeout in config |
| **Poor matching** | Many unmatched references | Lower similarity threshold (0.85 → 0.75), check reference parsing quality |
| **Memory error** | Graph building crashes with MemoryError | Switch from in-memory (NetworkX) to database storage (SQLite/Neo4j) |
| **Missing PDFs** | Paper not found in repository | Try alternative source (arXiv if PMC fails, or vice versa) |
| **PDF parsing errors** | Garbled or missing text | Use `pdfplumber` instead of `PyPDF2`, check for scanned images |
| **Duplicate nodes** | Same paper appears multiple times | Improve deduplication logic, add DOI matching as primary key |
| **Wrong year extracted** | Paper shows incorrect year | Refine regex patterns, check for multiple dates (submitted vs published) |
| **Encoding issues** | Special characters (Pääbo) show as garbage | Set UTF-8 encoding, use Unicode normalization |
| **API quota exceeded** | API returns 403/429 | Add API keys if available, implement exponential backoff |


