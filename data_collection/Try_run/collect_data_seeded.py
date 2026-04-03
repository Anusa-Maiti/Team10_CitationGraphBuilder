"""
collect_data.py
---------------
Main orchestrator for collecting scientific papers on Human Evolution.
Downloads PDFs and metadata from PMC, Europe PMC, arXiv, and BioRxiv.
Expands citations forward (papers that cite seeds) and backward (papers cited by seeds).

Usage:
    python collect_data.py [--max-papers N] [--skip-pdf] [--expand-depth D]
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Ensure the project root is always on sys.path so `fetchers` is importable
# regardless of the working directory you launch from.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetchers.pmc_fetcher import PMCFetcher
from fetchers.europepmc_fetcher import EuropePMCFetcher
from fetchers.arxiv_fetcher import ArXivFetcher
from fetchers.biorxiv_fetcher import BioRxivFetcher
from citation_expander import CitationExpander
from storedata import store_metadata

# ── Directory Layout ──────────────────────────────────────────────────────────
DIRS = ["data/raw", "data/processed", "data/metadata"]

# ── Logging (after dirs are guaranteed to exist) ──────────────────────────────
# Create data/ dir early so the FileHandler doesn't fail on first run.
for _d in DIRS:
    Path(_d).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/collection.log"),
    ],
)
log = logging.getLogger(__name__)

# ── Seed Papers (landmark works in Human Evolution) ──────────────────────────
# Only papers published 1990+ with at least one structured identifier (DOI/PMID/PMCID).
# Pre-1990 papers and books are excluded because EPMC and Semantic Scholar do not
# carry structured reference lists for them, so they cannot contribute edges to the
# citation graph.
SEED_PAPERS = [
    {"title": "Morphological affinities of the earliest modern humans",
     "doi": "10.1126/science.1193975", "pmid": "20378817", "year": 2010, "author": "Lieberman"},
    {"title": "The complete genome sequence of a Neanderthal from the Altai Mountains",
     "doi": "10.1038/nature12886", "pmid": "24352235", "year": 2014, "author": "Prüfer et al."},
    {"title": "Genomic history of the Acheulean stone tool-making Homo erectus",
     "doi": "10.1126/science.aao6266", "pmid": None, "year": 2018, "author": "Antón et al."},
    {"title": "Homo naledi, a new species of the genus Homo from the Dinaledi Chamber, South Africa",
     "doi": "10.7554/eLife.09560", "pmid": "26354291", "year": 2015, "author": "Berger et al."},
    {"title": "Fossil hominin shoulders support an African ape-like last common ancestor of humans and chimpanzees",
     "doi": "10.1073/pnas.1511220112", "pmid": "26627241", "year": 2015, "author": "Young et al."},
    {"title": "The genomic landscape of Neanderthal ancestry in present-day humans",
     "doi": "10.1038/nature12961", "pmid": "24476815", "year": 2014, "author": "Sankararaman et al."},
    {"title": "A Draft Sequence of the Neandertal Genome",
     "doi": "10.1126/science.1188021", "pmid": "20448178", "year": 2010, "author": "Green et al."},
]


def setup_directories():
    for d in DIRS:
        Path(d).mkdir(parents=True, exist_ok=True)
    log.info("Directory structure ready.")


def load_existing_corpus() -> dict:
    corpus_path = Path("data/metadata/corpus.json")
    if corpus_path.exists():
        with open(corpus_path) as f:
            return json.load(f)
    return {}


def save_corpus(corpus: dict):
    corpus_path = Path("data/metadata/corpus.json")
    with open(corpus_path, "w") as f:
        json.dump(corpus, f, indent=2, default=str)
    log.info(f"Corpus saved: {len(corpus)} papers → {corpus_path}")


def is_collectable(paper: dict) -> bool:
    """
    Returns True only for papers that APIs can actually retrieve references for:
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


def collect_seeds(corpus: dict, skip_pdf: bool = False) -> dict:
    fetchers = [
        PMCFetcher(output_dir="data/raw", rate_limit=3),
        EuropePMCFetcher(output_dir="data/raw", rate_limit=5),
        ArXivFetcher(output_dir="data/raw", rate_limit=0.33),
        BioRxivFetcher(output_dir="data/raw", rate_limit=2),
    ]

    for seed in SEED_PAPERS:
        seed_key = seed.get("doi") or seed["title"]
        if seed_key in corpus:
            log.info(f"Seed already collected: {seed['title'][:60]}")
            continue

        log.info(f"Fetching seed: {seed['title'][:60]} ({seed['year']})")
        for fetcher in fetchers:
            result = fetcher.fetch(seed, skip_pdf=skip_pdf)
            if result:
                corpus[seed_key] = result
                log.info(f"  ✓ {fetcher.__class__.__name__}: {result.get('pdf_path', 'metadata only')}")
                break
        else:
            log.warning(f"  ✗ No fetcher succeeded for: {seed['title'][:60]}")
            corpus[seed_key] = {**seed, "status": "not_found", "collected_at": datetime.now().isoformat()}

    return corpus


def main():
    parser = argparse.ArgumentParser(description="Collect Human Evolution papers.")
    parser.add_argument("--max-papers", type=int, default=200)
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--expand-depth", type=int, default=1)
    args = parser.parse_args()

    setup_directories()
    corpus = load_existing_corpus()

    log.info("=== Phase 1: Collecting seed papers ===")
    corpus = collect_seeds(corpus, skip_pdf=args.skip_pdf)
    save_corpus(corpus)

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

    log.info("=== Phase 3: Generating metadata CSVs ===")
    store_metadata(corpus)

    log.info(f"=== Collection complete: {len(corpus)} papers in corpus ===")


if __name__ == "__main__":
    main()
