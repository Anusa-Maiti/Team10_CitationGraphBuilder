"""
fetchers/europepmc_fetcher.py
------------------------------
Fetches papers from Europe PMC REST API.

API docs: https://europepmc.org/RestfulWebService
No documented rate limit – use 5 req/s conservatively.
"""

import logging
from .base_fetcher import BaseFetcher

log = logging.getLogger(__name__)

SEARCH_URL   = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
ARTICLE_URL  = "https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{id}/fullTextXML"
PDF_URL      = "https://europepmc.org/articles/{pmcid}/pdf/{pmcid}.pdf"


class EuropePMCFetcher(BaseFetcher):
    """
    Queries Europe PMC for open-access papers.
    Returns metadata and downloads PDF where available.
    """

    def __init__(self, output_dir="data/raw", rate_limit=5):
        super().__init__(output_dir=output_dir, rate_limit=rate_limit)

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: dict) -> list:
        q = self._build_query(query)
        params = {
            "query":       q,
            "format":      "json",
            "resultType":  "core",
            "pageSize":    5,
            "synonym":     "TRUE",
        }
        resp = self._get(SEARCH_URL, params=params)
        if resp is None:
            return []

        data = resp.json()
        results = data.get("resultList", {}).get("result", [])
        log.debug(f"Europe PMC '{q}' → {len(results)} results")
        return results  # Each result is already a metadata dict

    def _build_query(self, query: dict) -> str:
        if query.get("doi"):
            return f'DOI:"{query["doi"]}"'
        if query.get("pmid"):
            return f'EXT_ID:{query["pmid"]} AND SRC:MED'
        parts = [f'TITLE:"{query["title"]}"']
        if query.get("author"):
            surname = query["author"].split()[0]
            parts.append(f'AUTH:{surname}')
        return " AND ".join(parts)

    # ── Metadata ──────────────────────────────────────────────────────────────

    def fetch_metadata(self, candidate: dict) -> dict | None:
        """Map Europe PMC response fields to our internal schema."""
        if not candidate:
            return None

        # Authors list
        author_list = candidate.get("authorList", {})
        authors = []
        if isinstance(author_list, dict):
            for a in author_list.get("author", []):
                name = f"{a.get('lastName', '')}, {a.get('firstName', '')}".strip(", ")
                if name:
                    authors.append(name)

        # Journal/venue
        journal_info = candidate.get("journalInfo", {})
        venue = (journal_info.get("journal", {}).get("title")
                 or candidate.get("bookOrReportDetails", {}).get("publisher"))

        # PMCID (needed for PDF)
        pmcid = candidate.get("pmcid") or candidate.get("fullTextIdList", {}).get("fullTextId", [None])[0]

        return {
            "pmcid":       pmcid,
            "pmid":        candidate.get("pmid"),
            "doi":         candidate.get("doi"),
            "title":       candidate.get("title"),
            "authors":     authors,
            "year":        str(candidate.get("pubYear", "")),
            "venue":       venue,
            "abstract":    candidate.get("abstractText"),
            "keywords":    candidate.get("keywordList", {}).get("keyword", []),
            "citation_count": candidate.get("citedByCount", 0),
            "is_open_access": candidate.get("isOpenAccess") == "Y",
            "source":      "EuropePMC",
        }

    # ── PDF Download ──────────────────────────────────────────────────────────

    def download_pdf(self, metadata: dict) -> str | None:
        pmcid = metadata.get("pmcid")
        if not pmcid:
            log.debug("EuropePMC: no PMCID, cannot download PDF")
            return None

        # Europe PMC PDF URL pattern
        pmcid_num = pmcid.replace("PMC", "")
        pdf_url = f"https://europepmc.org/articles/{pmcid.lower()}/pdf/{pmcid.lower()}.pdf"

        title = metadata.get("title") or pmcid
        filename = self._safe_filename(title)
        result = self._download_pdf(pdf_url, filename)

        if result is None:
            # Fallback: try direct PMC PDF link
            fallback_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"
            result = self._download_pdf(fallback_url, filename + "_pmc")

        return result
