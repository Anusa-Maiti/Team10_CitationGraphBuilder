"""
fetchers/biorxiv_fetcher.py
----------------------------
Fetches preprints from bioRxiv using the official REST API.

API docs: https://api.biorxiv.org/
Rate limit: 2 requests/second recommended
Focuses on evolutionary biology, genomics, and palaeontology collections.
"""

import logging
from datetime import datetime, timedelta

from .base_fetcher import BaseFetcher

log = logging.getLogger(__name__)

BIORXIV_DETAIL_URL  = "https://api.biorxiv.org/details/biorxiv/{doi}/na/json"
BIORXIV_SEARCH_URL  = "https://api.biorxiv.org/details/biorxiv"
BIORXIV_PDF_PATTERN = "https://www.biorxiv.org/content/{doi}.full.pdf"

# bioRxiv subject categories relevant to human evolution
RELEVANT_COLLECTIONS = {
    "evolutionary biology",
    "genomics",
    "genetics",
    "paleontology",
    "bioinformatics",
    "ecology",
}


class BioRxivFetcher(BaseFetcher):
    """
    Fetches bioRxiv preprints.
    Supports DOI-based lookup and date-range search filtered by category.
    """

    def __init__(self, output_dir="data/raw", rate_limit=2):
        super().__init__(output_dir=output_dir, rate_limit=rate_limit)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: dict) -> list:
        """
        If DOI provided, use direct lookup.
        Otherwise, search recent papers in relevant categories
        and filter by title similarity.
        """
        if query.get("doi") and "biorxiv" in query["doi"].lower():
            return self._search_by_doi(query["doi"])

        return self._search_by_title(query)

    def _search_by_doi(self, doi: str) -> list:
        url = BIORXIV_DETAIL_URL.format(doi=doi)
        resp = self._get(url)
        if resp is None:
            return []
        data = resp.json()
        collection = data.get("collection", [])
        return collection[:1] if collection else []

    def _search_by_title(self, query: dict) -> list:
        """
        bioRxiv's public API doesn't support full-text search by title.
        We fetch recent papers in a date range around the paper's year
        and filter by collection + simple title match.
        """
        year = query.get("year")
        if not year:
            year = datetime.now().year

        try:
            year = int(year)
        except (ValueError, TypeError):
            year = datetime.now().year

        # Search ±1 year window
        start = f"{max(year-1, 2013)}-01-01"
        end   = f"{year+1}-12-31"

        url = f"{BIORXIV_SEARCH_URL}/{start}/{end}/0/json"
        resp = self._get(url)
        if resp is None:
            return []

        data = resp.json()
        all_papers = data.get("collection", [])

        # Filter by relevant collection and title keyword match
        title_words = set(query.get("title", "").lower().split())
        matches = []
        for paper in all_papers:
            category = paper.get("category", "").lower()
            if not any(cat in category for cat in RELEVANT_COLLECTIONS):
                continue
            paper_title_words = set(paper.get("title", "").lower().split())
            overlap = title_words & paper_title_words
            # Require at least 3 content words to match
            content_overlap = {w for w in overlap if len(w) > 3}
            if len(content_overlap) >= 3:
                matches.append(paper)

        log.debug(f"bioRxiv '{query.get('title', '')[:50]}' → {len(matches)} matches")
        return matches[:5]

    # ── Metadata ──────────────────────────────────────────────────────────────

    def fetch_metadata(self, candidate: dict) -> dict | None:
        """Normalise bioRxiv API response to internal schema."""
        if not candidate:
            return None

        doi    = candidate.get("doi", "")
        authors_raw = candidate.get("authors", "")

        # Authors: bioRxiv returns semicolon-separated string
        authors = [a.strip() for a in authors_raw.split(";") if a.strip()]

        # Year from date string "YYYY-MM-DD"
        date_str = candidate.get("date", "")
        year = date_str[:4] if date_str else None

        return {
            "doi":       doi,
            "title":     candidate.get("title"),
            "authors":   authors,
            "year":      year,
            "venue":     f"bioRxiv ({candidate.get('category', '')})",
            "abstract":  candidate.get("abstract"),
            "version":   candidate.get("version"),
            "server":    candidate.get("server", "biorxiv"),
            "_doi":      doi,  # internal – for PDF URL construction
            "source":    "bioRxiv",
        }

    # ── PDF Download ──────────────────────────────────────────────────────────

    def download_pdf(self, metadata: dict) -> str | None:
        doi = metadata.get("_doi") or metadata.get("doi")
        if not doi:
            return None

        # bioRxiv PDF URL uses the DOI path
        doi_path = doi.replace("10.1101/", "")
        pdf_url = f"https://www.biorxiv.org/content/10.1101/{doi_path}.full.pdf"

        title = metadata.get("title") or doi
        filename = f"biorxiv_{self._safe_filename(title)}"
        return self._download_pdf(pdf_url, filename)
