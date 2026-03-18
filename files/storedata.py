"""
storedata.py
------------
Reads the collected corpus (data/metadata/corpus.json) and generates:

  data/metadata/papers_metadata.csv
      One row per paper: paper_id, title, authors, year, venue, doi,
      pmid, pmcid, arxiv_id, source, has_pdf, pdf_path, abstract_snippet,
      citation_count, is_open_access, collected_at

  data/metadata/all_references.csv
      One row per directed citation edge:
      citing_paper_id, cited_paper_id, citing_title, cited_title,
      citing_year, cited_year, resolution_method

Usage:
    python storedata.py                        # uses default corpus.json
    python storedata.py --corpus path/to.json  # custom corpus path
    python storedata.py --validate             # also print QA summary
"""

import csv
import json
import argparse
import hashlib
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

# Output paths
METADATA_CSV   = Path("data/metadata/papers_metadata.csv")
REFERENCES_CSV = Path("data/metadata/all_references.csv")
CORPUS_JSON    = Path("data/metadata/corpus.json")

# CSV column schemas
PAPERS_COLUMNS = [
    "paper_id",
    "title",
    "authors",
    "year",
    "venue",
    "doi",
    "pmid",
    "pmcid",
    "arxiv_id",
    "source",
    "has_pdf",
    "pdf_path",
    "abstract_snippet",
    "citation_count",
    "is_open_access",
    "collected_at",
]

REFERENCES_COLUMNS = [
    "citing_paper_id",
    "cited_paper_id",
    "citing_title",
    "cited_title",
    "citing_year",
    "cited_year",
    "resolution_method",
]


# ── ID generation ─────────────────────────────────────────────────────────────

def make_paper_id(paper: dict) -> str:
    """
    Create a stable, unique identifier for a paper.
    Priority: DOI → PMID → PMCID → arXiv ID → title hash.
    """
    if paper.get("doi"):
        return _slugify(paper["doi"])
    if paper.get("pmid"):
        return f"pmid_{paper['pmid']}"
    if paper.get("pmcid"):
        return _slugify(paper["pmcid"])
    if paper.get("arxiv_id"):
        return f"arxiv_{paper['arxiv_id']}"
    # Fallback: short SHA of lowercased title
    title = (paper.get("title") or "unknown").lower().strip()
    return "hash_" + hashlib.md5(title.encode()).hexdigest()[:12]


def _slugify(text: str) -> str:
    """Convert a DOI or ID to a filesystem/CSV-safe slug."""
    import re
    return re.sub(r"[^\w.-]", "_", str(text).strip())


# ── Paper row builder ─────────────────────────────────────────────────────────

def paper_to_row(paper_id: str, paper: dict) -> dict:
    """Map a corpus entry to a papers_metadata.csv row."""
    authors = paper.get("authors", [])
    if isinstance(authors, list):
        authors_str = " | ".join(authors)
    else:
        authors_str = str(authors)

    abstract = paper.get("abstract") or ""
    abstract_snippet = abstract[:300].replace("\n", " ").strip()
    if len(abstract) > 300:
        abstract_snippet += "…"

    return {
        "paper_id":         paper_id,
        "title":            (paper.get("title") or "").replace("\n", " ").strip(),
        "authors":          authors_str,
        "year":             paper.get("year", ""),
        "venue":            paper.get("venue", ""),
        "doi":              paper.get("doi", ""),
        "pmid":             paper.get("pmid", ""),
        "pmcid":            paper.get("pmcid", ""),
        "arxiv_id":         paper.get("arxiv_id", ""),
        "source":           paper.get("source", ""),
        "has_pdf":          "yes" if paper.get("pdf_path") else "no",
        "pdf_path":         paper.get("pdf_path", ""),
        "abstract_snippet": abstract_snippet,
        "citation_count":   paper.get("citation_count", ""),
        "is_open_access":   paper.get("is_open_access", ""),
        "collected_at":     paper.get("collected_at", ""),
    }


# ── Reference extraction ──────────────────────────────────────────────────────

def build_id_lookup(corpus: dict) -> dict:
    """
    Build a lookup: (doi|pmid|pmcid|title_lower) → paper_id
    Used to resolve references to canonical IDs.
    """
    lookup = {}
    for key, paper in corpus.items():
        pid = make_paper_id(paper)
        for field in ("doi", "pmid", "pmcid", "arxiv_id"):
            val = paper.get(field)
            if val:
                lookup[str(val).strip().lower()] = pid
        title = (paper.get("title") or "").lower().strip()
        if title:
            lookup[title] = pid
    return lookup


def resolve_reference(ref: dict, lookup: dict) -> tuple[str | None, str]:
    """
    Try to match a reference record to a corpus paper_id.
    Returns (paper_id | None, resolution_method).
    """
    for field in ("doi", "pmid", "pmcid"):
        val = str(ref.get(field) or "").strip().lower()
        if val and val in lookup:
            return lookup[val], f"exact_{field}"

    title = (ref.get("title") or "").lower().strip()
    if title and title in lookup:
        return lookup[title], "exact_title"

    # Fuzzy title fallback (simple word-overlap)
    if title:
        title_words = set(w for w in title.split() if len(w) > 3)
        best_score  = 0
        best_pid    = None
        for candidate_title, candidate_pid in lookup.items():
            cand_words = set(w for w in candidate_title.split() if len(w) > 3)
            if not cand_words:
                continue
            overlap = len(title_words & cand_words) / max(len(title_words), 1)
            if overlap > 0.6 and overlap > best_score:
                best_score = overlap
                best_pid   = candidate_pid
        if best_pid:
            return best_pid, f"fuzzy_title_{best_score:.2f}"

    return None, "unresolved"


def extract_reference_rows(corpus: dict, id_map: dict, lookup: dict) -> list[dict]:
    """
    For each paper that has a 'references' list, build citation edge rows.
    corpus keys are used as citing paper IDs after lookup.
    """
    rows = []
    for key, paper in corpus.items():
        citing_id = id_map.get(key)
        if not citing_id:
            continue
        refs = paper.get("references", [])
        if not refs:
            continue
        for ref in refs:
            cited_id, method = resolve_reference(ref, lookup)
            rows.append({
                "citing_paper_id": citing_id,
                "cited_paper_id":  cited_id or "",
                "citing_title":    (paper.get("title") or "").replace("\n", " ")[:120],
                "cited_title":     (ref.get("title") or "").replace("\n", " ")[:120],
                "citing_year":     paper.get("year", ""),
                "cited_year":      ref.get("year", ""),
                "resolution_method": method,
            })
    return rows


# ── CSV writers ───────────────────────────────────────────────────────────────

def write_csv(path: Path, columns: list, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info(f"Wrote {len(rows):>5} rows → {path}")


# ── QA summary ────────────────────────────────────────────────────────────────

def print_qa_summary(paper_rows: list[dict], ref_rows: list[dict]):
    total         = len(paper_rows)
    with_pdf      = sum(1 for r in paper_rows if r["has_pdf"] == "yes")
    with_doi      = sum(1 for r in paper_rows if r["doi"])
    with_abstract = sum(1 for r in paper_rows if r["abstract_snippet"])
    resolved      = sum(1 for r in ref_rows if r["cited_paper_id"])
    unresolved    = len(ref_rows) - resolved

    print("\n── Corpus QA Summary ──────────────────────────────")
    print(f"  Total papers      : {total}")
    print(f"  With PDF          : {with_pdf} ({100*with_pdf//max(total,1)}%)")
    print(f"  With DOI          : {with_doi} ({100*with_doi//max(total,1)}%)")
    print(f"  With abstract     : {with_abstract} ({100*with_abstract//max(total,1)}%)")
    print(f"  Citation edges    : {len(ref_rows)}")
    print(f"    Resolved        : {resolved} ({100*resolved//max(len(ref_rows),1)}%)")
    print(f"    Unresolved      : {unresolved}")
    print("────────────────────────────────────────────────────\n")


# ── Public API (called from collect_data.py) ──────────────────────────────────

def store_metadata(corpus: dict,
                   papers_path: Path = METADATA_CSV,
                   references_path: Path = REFERENCES_CSV):
    """
    Generate both CSV files from a corpus dict.
    Can be called programmatically or via __main__.
    """
    # Build ID map: corpus key → stable paper_id
    id_map = {key: make_paper_id(paper) for key, paper in corpus.items()}

    # Build lookup table for reference resolution
    lookup = build_id_lookup(corpus)

    # Paper rows
    paper_rows = [
        paper_to_row(id_map[key], paper)
        for key, paper in corpus.items()
    ]
    write_csv(papers_path, PAPERS_COLUMNS, paper_rows)

    # Reference rows
    ref_rows = extract_reference_rows(corpus, id_map, lookup)
    write_csv(references_path, REFERENCES_COLUMNS, ref_rows)

    return paper_rows, ref_rows


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s")

    parser = argparse.ArgumentParser(
        description="Generate papers_metadata.csv and all_references.csv from corpus.json"
    )
    parser.add_argument("--corpus",   default=str(CORPUS_JSON),
                        help="Path to corpus.json (default: data/metadata/corpus.json)")
    parser.add_argument("--validate", action="store_true",
                        help="Print QA summary after writing CSVs")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        log.error(f"Corpus file not found: {corpus_path}")
        return

    with open(corpus_path) as f:
        corpus = json.load(f)
    log.info(f"Loaded corpus: {len(corpus)} papers from {corpus_path}")

    paper_rows, ref_rows = store_metadata(corpus)

    if args.validate:
        print_qa_summary(paper_rows, ref_rows)


if __name__ == "__main__":
    main()
