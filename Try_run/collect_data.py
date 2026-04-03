"""
collect_data.py
---------------
Collects scientific papers on Human Evolution by querying open-access APIs
with configurable search terms, then optionally expands via citation links.

Usage:
    # Use default query terms
    python collect_data.py --max-papers 200 --skip-pdf

    # Custom query terms
    python collect_data.py --queries "neanderthal genome" "homo naledi" "ancient dna admixture"

    # With citation expansion
    python collect_data.py --max-papers 200 --skip-pdf --expand-depth 1

    # Add a single specific paper by DOI (for the dashboard add-paper workflow)
    python collect_data.py --add-doi 10.1038/nature12886
    python collect_data.py --add-pmid 24352235
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetchers.pmc_fetcher import PMCFetcher
from fetchers.europepmc_fetcher import EuropePMCFetcher
from fetchers.arxiv_fetcher import ArXivFetcher
from fetchers.biorxiv_fetcher import BioRxivFetcher
from citation_expander import CitationExpander
from storedata import store_metadata

# ── Directories ───────────────────────────────────────────────────────────────
DIRS = ["data/raw", "data/processed", "data/metadata"]
for _d in DIRS:
    Path(_d).mkdir(parents=True, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/collection.log"),
    ],
)
log = logging.getLogger(__name__)

# ── Default query terms ───────────────────────────────────────────────────────
# These are used when --queries is not passed on the command line.
# Each string becomes a separate API search query.
# Results from all queries are merged into a single corpus (deduplicated by DOI/PMID).
DEFAULT_QUERIES = [
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
]


# ── Eligibility filter ────────────────────────────────────────────────────────

def is_collectable(paper: dict) -> bool:
    """
    Only collect papers that APIs can retrieve reference lists for:
      - Published 1990 or later
      - Has at least one structured identifier (DOI, PMID, or PMCID)
    """
    year   = int(paper.get("year") or 0)
    has_id = bool(paper.get("doi") or paper.get("pmid") or paper.get("pmcid"))
    if year and year < 1990:
        return False
    if not has_id:
        return False
    return True


# ── Corpus I/O ────────────────────────────────────────────────────────────────

def load_corpus() -> dict:
    path = Path("data/metadata/corpus.json")
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def save_corpus(corpus: dict):
    path = Path("data/metadata/corpus.json")
    with open(path, "w") as f:
        json.dump(corpus, f, indent=2, default=str)
    log.info(f"Corpus saved: {len(corpus)} papers → {path}")


def corpus_key(paper: dict) -> str:
    return paper.get("doi") or paper.get("pmid") or paper.get("title", "").lower().strip()


# ── Query-based collection ────────────────────────────────────────────────────

def collect_by_queries(queries: list[str], corpus: dict,
                        max_papers: int, skip_pdf: bool) -> dict:
    """
    Run each query string against all four fetchers.
    Each fetcher's search() returns a list of candidates; we take the top results
    and fetch full metadata for each, up to max_papers total.
    """
    fetchers = [
        EuropePMCFetcher(output_dir="data/raw", rate_limit=5),
        PMCFetcher(output_dir="data/raw", rate_limit=3),
        ArXivFetcher(output_dir="data/raw", rate_limit=0.33),
        BioRxivFetcher(output_dir="data/raw", rate_limit=2),
    ]

    for query in queries:
        if len(corpus) >= max_papers:
            log.info(f"Reached max_papers={max_papers}, stopping query collection.")
            break

        log.info(f"Query: '{query}'")

        for fetcher in fetchers:
            if len(corpus) >= max_papers:
                break

            candidates = fetcher.search({"title": query})
            log.info(f"  {fetcher.__class__.__name__}: {len(candidates)} candidates")

            for candidate in candidates:
                if len(corpus) >= max_papers:
                    break

                metadata = fetcher.fetch_metadata(candidate)
                if not metadata:
                    continue
                if not is_collectable(metadata):
                    log.debug(f"  Skipping (pre-1990 or no ID): {metadata.get('title','?')[:60]}")
                    continue

                key = corpus_key(metadata)
                if key in corpus:
                    log.debug(f"  Already in corpus: {metadata.get('title','?')[:60]}")
                    continue

                if not skip_pdf:
                    pdf_path = fetcher.download_pdf(metadata)
                    if pdf_path:
                        metadata["pdf_path"] = pdf_path

                metadata.setdefault("source", fetcher.__class__.__name__)
                metadata.setdefault("collected_at", datetime.now().isoformat())
                corpus[key] = metadata
                log.info(f"  + {metadata.get('title','?')[:70]}")

    return corpus


# ── Add a single paper by identifier (for dashboard workflow) ─────────────────

def add_single_paper(corpus: dict, doi: str = None, pmid: str = None,
                      skip_pdf: bool = False) -> dict:
    """
    Fetch one specific paper by DOI or PMID and add it to the corpus.
    Used by the dashboard's "add paper" feature.
    """
    query = {"doi": doi, "pmid": pmid, "title": ""}

    fetchers = [
        EuropePMCFetcher(output_dir="data/raw", rate_limit=5),
        PMCFetcher(output_dir="data/raw", rate_limit=3),
    ]

    for fetcher in fetchers:
        result = fetcher.fetch(query, skip_pdf=skip_pdf)
        if result and is_collectable(result):
            key = corpus_key(result)
            if key in corpus:
                log.info(f"Paper already in corpus: {result.get('title','?')[:70]}")
            else:
                corpus[key] = result
                log.info(f"Added: {result.get('title','?')[:70]}")
            return corpus

    log.warning(f"Could not find paper: DOI={doi} PMID={pmid}")
    return corpus


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Collect Human Evolution papers by query.")
    parser.add_argument("--queries", nargs="+", default=None,
                        help="Search query strings (default: built-in human evolution terms)")
    parser.add_argument("--max-papers", type=int, default=200,
                        help="Max papers to collect across all queries")
    parser.add_argument("--skip-pdf", action="store_true",
                        help="Collect metadata only, skip PDF downloads")
    parser.add_argument("--expand-depth", type=int, default=0,
                        help="Citation expansion depth after query collection (default: 0)")
    parser.add_argument("--add-doi", type=str, default=None,
                        help="Add a single paper by DOI (for dashboard use)")
    parser.add_argument("--add-pmid", type=str, default=None,
                        help="Add a single paper by PMID (for dashboard use)")
    args = parser.parse_args()

    corpus = load_corpus()

    # ── Single paper add (dashboard workflow) ─────────────────────────────────
    if args.add_doi or args.add_pmid:
        corpus = add_single_paper(
            corpus, doi=args.add_doi, pmid=args.add_pmid, skip_pdf=args.skip_pdf
        )
        save_corpus(corpus)
        store_metadata(corpus)
        log.info("Single paper added. Re-run extract_references.py to update edges.")
        return

    # ── Query-based collection ─────────────────────────────────────────────────
    queries = args.queries or DEFAULT_QUERIES
    log.info(f"=== Phase 1: Collecting papers via {len(queries)} queries ===")
    corpus = collect_by_queries(queries, corpus, args.max_papers, args.skip_pdf)
    save_corpus(corpus)

    # ── Citation expansion ─────────────────────────────────────────────────────
    if args.expand_depth > 0:
        log.info(f"=== Phase 2: Expanding citations (depth={args.expand_depth}) ===")
        expander = CitationExpander(
            corpus=corpus,
            max_papers=args.max_papers,
            skip_pdf=args.skip_pdf,
            depth=args.expand_depth,
        )
        corpus = expander.expand()
        save_corpus(corpus)

    # ── CSVs ───────────────────────────────────────────────────────────────────
    log.info("=== Phase 3: Generating metadata CSVs ===")
    store_metadata(corpus)
    log.info(f"=== Done: {len(corpus)} papers in corpus ===")


if __name__ == "__main__":
    main()
