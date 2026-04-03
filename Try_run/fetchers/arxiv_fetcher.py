"""
fetchers/arxiv_fetcher.py
--------------------------
Fetches preprints from arXiv, focusing on the q-bio category
(Quantitative Biology), which covers evolutionary biology,
genomics, and population genetics relevant to human evolution.

API docs: https://arxiv.org/help/api/
Rate limit: 1 request per 3 seconds (enforced here as 0.33 req/s)
"""

import re
import logging
import xml.etree.ElementTree as ET

from .base_fetcher import BaseFetcher

log = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_PDF_URL = "https://arxiv.org/pdf/{arxiv_id}"

# arXiv XML namespaces
NS = {
    "atom":   "http://www.w3.org/2005/Atom",
    "arxiv":  "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

# Human evolution relevant categories
RELEVANT_CATEGORIES = {
    "q-bio.PE",   # Populations and Evolution
    "q-bio.GN",   # Genomics
    "q-bio.CB",   # Cell Behavior
    "q-bio.OT",   # Other Quantitative Biology
    "cs.NE",      # Neural and Evolutionary Computing
}


class ArXivFetcher(BaseFetcher):
    """
    Searches arXiv for preprints on human evolution topics.
    Downloads PDFs directly from arxiv.org (always open access).
    """

    def __init__(self, output_dir="data/raw", rate_limit=0.33):
        super().__init__(output_dir=output_dir, rate_limit=rate_limit)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: dict) -> list:
        search_query = self._build_query(query)
        params = {
            "search_query": search_query,
            "max_results":  5,
            "sortBy":       "relevance",
            "sortOrder":    "descending",
        }
        resp = self._get(ARXIV_API_URL, params=params)
        if resp is None:
            return []

        entries = self._parse_feed(resp.text)
        log.debug(f"arXiv '{search_query}' → {len(entries)} results")
        return entries

    def _build_query(self, query: dict) -> str:
        """
        Build arXiv search query.
        arXiv doesn't support DOI/PMID search, so always use title.
        Restrict to q-bio category for relevance.
        """
        title = query.get("title", "")
        # Use first 6 words of title for reliability
        words = title.split()[:6]
        title_fragment = " ".join(words)
        return f'ti:"{title_fragment}" AND (cat:q-bio.PE OR cat:q-bio.GN)'

    def _parse_feed(self, xml_text: str) -> list:
        """Parse Atom feed returned by arXiv API."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            log.warning(f"arXiv XML parse error: {e}")
            return []

        entries = []
        for entry in root.findall("atom:entry", NS):
            arxiv_id_full = entry.findtext("atom:id", "", NS)
            # Extract just the ID (e.g. 2101.12345v2 → 2101.12345)
            arxiv_id = re.sub(r"v\d+$", "", arxiv_id_full.split("/abs/")[-1])

            # Authors
            authors = []
            for author_el in entry.findall("atom:author", NS):
                name = author_el.findtext("atom:name", "", NS).strip()
                if name:
                    authors.append(name)

            # Categories
            categories = [c.get("term", "") for c in entry.findall("atom:category", NS)]

            # Published year
            published = entry.findtext("atom:published", "", NS)
            year = published[:4] if published else None

            entries.append({
                "arxiv_id":   arxiv_id,
                "title":      "".join(entry.find("atom:title", NS).itertext()).strip()
                              if entry.find("atom:title", NS) is not None else None,
                "authors":    authors,
                "year":       year,
                "abstract":   "".join(entry.find("atom:summary", NS).itertext()).strip()
                              if entry.find("atom:summary", NS) is not None else None,
                "categories": categories,
                "pdf_url":    f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            })

        return entries

    # ── Metadata ──────────────────────────────────────────────────────────────

    def fetch_metadata(self, candidate: dict) -> dict | None:
        """arXiv search results are already metadata-rich – just normalise."""
        if not candidate:
            return None

        return {
            "arxiv_id":  candidate.get("arxiv_id"),
            "doi":       f"10.48550/arXiv.{candidate['arxiv_id']}" if candidate.get("arxiv_id") else None,
            "title":     candidate.get("title"),
            "authors":   candidate.get("authors", []),
            "year":      candidate.get("year"),
            "venue":     "arXiv (" + ", ".join(candidate.get("categories", [])) + ")",
            "abstract":  candidate.get("abstract"),
            "_pdf_url":  candidate.get("pdf_url"),  # internal – used by download_pdf
            "source":    "arXiv",
        }

    # ── PDF Download ──────────────────────────────────────────────────────────

    def download_pdf(self, metadata: dict) -> str | None:
        pdf_url = metadata.get("_pdf_url")
        if not pdf_url:
            arxiv_id = metadata.get("arxiv_id")
            if not arxiv_id:
                return None
            pdf_url = ARXIV_PDF_URL.format(arxiv_id=arxiv_id)

        title = metadata.get("title") or metadata.get("arxiv_id", "arxiv_paper")
        filename = f"arxiv_{self._safe_filename(title)}"
        return self._download_pdf(pdf_url, filename)
