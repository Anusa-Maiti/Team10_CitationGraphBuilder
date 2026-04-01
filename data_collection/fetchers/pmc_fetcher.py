"""
fetchers/pmc_fetcher.py
-----------------------
Fetches papers from PubMed Central (PMC) using the NCBI E-utilities API.
PDF download uses the PMC Open Access FTP service to get real PDF URLs,
avoiding the redirect/login page that the direct /pdf/ URL hits.

API docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
OA service: https://www.ncbi.nlm.nih.gov/pmc/tools/oa-service/
"""

import os
import logging
import xml.etree.ElementTree as ET
from urllib.parse import quote

from .base_fetcher import BaseFetcher

log = logging.getLogger(__name__)

ESEARCH_URL  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL   = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
OA_SERVICE   = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


class PMCFetcher(BaseFetcher):

    def __init__(self, output_dir="data/raw", rate_limit=3):
        api_key = os.getenv("NCBI_API_KEY")
        super().__init__(output_dir=output_dir, rate_limit=10 if api_key else rate_limit)
        self.api_key = api_key
        self._base_params = {"api_key": api_key} if api_key else {}

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: dict) -> list:
        term = self._build_term(query)
        params = {**self._base_params, "db": "pmc", "term": term,
                  "retmax": 5, "retmode": "json"}
        resp = self._get(ESEARCH_URL, params=params)
        if resp is None:
            return []
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        log.debug(f"PMC ESearch '{term}' → {len(ids)} results")
        return [{"pmcid": f"PMC{i}"} for i in ids]

    def _build_term(self, query: dict) -> str:
        if query.get("pmid"):  return f"{query['pmid']}[uid]"
        if query.get("doi"):   return f"{query['doi']}[doi]"
        parts = [f'"{query["title"]}"[Title]']
        if query.get("author"):
            parts.append(f"{query['author'].split()[0]}[Author]")
        if query.get("year"):
            y = query["year"]
            parts.append(f"{y}:{y}[pdat]")
        return " AND ".join(parts)

    # ── Metadata ──────────────────────────────────────────────────────────────

    def fetch_metadata(self, candidate: dict) -> dict | None:
        pmcid = candidate.get("pmcid", "")
        numeric_id = pmcid.replace("PMC", "")
        params = {**self._base_params, "db": "pmc", "id": numeric_id,
                  "retmode": "xml", "rettype": "full"}
        resp = self._get(EFETCH_URL, params=params)
        if resp is None:
            return None
        return self._parse_pmc_xml(resp.text, pmcid)

    def _parse_pmc_xml(self, xml_text: str, pmcid: str) -> dict:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            log.warning(f"PMC XML parse error for {pmcid}: {e}")
            return {"pmcid": pmcid}

        title_el = root.find(".//article-title")
        title = "".join(title_el.itertext()).strip() if title_el is not None else None

        authors = []
        for contrib in root.findall(".//contrib[@contrib-type='author']"):
            surname = contrib.findtext(".//surname", "")
            given   = contrib.findtext(".//given-names", "")
            name    = f"{surname}, {given}".strip(", ")
            if name:
                authors.append(name)

        year    = root.findtext(".//pub-date/year") or root.findtext(".//history/date/year")
        journal = root.findtext(".//journal-title")

        doi = None
        for aid in root.findall(".//article-id"):
            if aid.get("pub-id-type") == "doi":
                doi = aid.text
                break

        abstract_parts = ["".join(p.itertext()).strip() for p in root.findall(".//abstract//p")]
        abstract = " ".join(abstract_parts) or None

        return {"pmcid": pmcid, "doi": doi, "title": title, "authors": authors,
                "year": year, "venue": journal, "abstract": abstract, "source": "PMC"}

    # ── PDF Download via OA service ───────────────────────────────────────────

    def download_pdf(self, metadata: dict) -> str | None:
        pmcid = metadata.get("pmcid")
        if not pmcid:
            return None

        title    = metadata.get("title") or pmcid
        filename = self._safe_filename(title)

        # Step 1: ask OA service for the real download link
        pdf_url = self._resolve_oa_pdf_url(pmcid)

        # Step 2: fallback chain if OA service returns nothing
        if not pdf_url:
            # Europe PMC direct PDF
            pmcid_lower = pmcid.lower()
            pdf_url = f"https://europepmc.org/articles/{pmcid_lower}/pdf/{pmcid_lower}.pdf"
            log.debug(f"OA service gave no URL, trying Europe PMC: {pdf_url}")

        result = self._download_pdf(pdf_url, filename)

        # Step 3: last resort — PubMed Central HTML-to-PDF via unpaywall-style URL
        if result is None:
            alt = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf"
            result = self._download_pdf(alt, filename + "_alt")

        return result

    def _resolve_oa_pdf_url(self, pmcid: str) -> str | None:
        """
        Query the PMC OA service to get a real FTP/HTTPS PDF download URL.
        Returns URL string or None.
        """
        resp = self._get(OA_SERVICE, params={"id": pmcid, "format": "pdf"})
        if resp is None:
            return None
        try:
            root = ET.fromstring(resp.text)
        except ET.ParseError:
            return None

        # OA service returns <OA><records><record>...<link format="pdf" href="..."/>
        for link in root.findall(".//link"):
            fmt  = link.get("format", "")
            href = link.get("href", "")
            if fmt == "pdf" and href:
                # Convert FTP to HTTPS
                if href.startswith("ftp://"):
                    href = href.replace("ftp://", "https://", 1)
                log.debug(f"OA service PDF URL: {href}")
                return href

        # Some records only offer tgz; extract PDF URL from that
        for link in root.findall(".//link"):
            href = link.get("href", "")
            if href.endswith(".tar.gz") or "tgz" in href:
                log.debug(f"OA service only offers tgz for {pmcid}, skipping")
                break

        return None
