"""
fetchers/base_fetcher.py
------------------------
Abstract base class shared by all source-specific fetchers.
Each fetcher knows how to search for a paper and download its PDF.
"""

import os
import time
import logging
import requests
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "CitationGraphBuilder/1.0 (academic research; contact: your@email.com)"
}


class BaseFetcher(ABC):
    """
    Base class for all paper fetchers.

    Subclasses must implement:
        search(query_dict) -> list[dict]   – search for a paper, return candidates
        fetch_metadata(candidate) -> dict  – enrich a candidate with full metadata
        download_pdf(candidate) -> str|None – download PDF, return local path
    """

    def __init__(self, output_dir: str = "data/raw", rate_limit: float = 1.0):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._min_interval = 1.0 / rate_limit if rate_limit > 0 else 1.0
        self._last_request_time = 0.0

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _wait(self):
        """Enforce rate limit between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _get(self, url: str, params: dict = None, timeout: int = 30, stream: bool = False):
        """Wrapper around requests.get with rate limiting and error handling."""
        self._wait()
        try:
            resp = requests.get(url, params=params, headers=DEFAULT_HEADERS,
                                timeout=timeout, stream=stream)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            log.debug(f"HTTP error [{self.__class__.__name__}] {url}: {e}")
            return None

    # ── PDF download ──────────────────────────────────────────────────────────

    def _download_pdf(self, pdf_url: str, filename: str) -> str | None:
        """
        Download a PDF to self.output_dir/<filename>.pdf.
        Returns local path on success, None on failure.
        """
        dest = self.output_dir / f"{filename}.pdf"
        if dest.exists():
            log.debug(f"PDF already exists: {dest}")
            return str(dest)

        log.info(f"  Downloading PDF: {pdf_url}")
        resp = self._get(pdf_url, timeout=60, stream=True)
        if resp is None:
            return None

        content_type = resp.headers.get("Content-Type", "")
        if "pdf" not in content_type and "octet-stream" not in content_type:
            log.debug(f"  Unexpected Content-Type: {content_type}")
            # Still attempt to save — some servers lie about content type

        try:
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            size_kb = dest.stat().st_size / 1024
            log.info(f"  Saved PDF: {dest} ({size_kb:.1f} KB)")
            return str(dest)
        except OSError as e:
            log.error(f"  Failed to save PDF: {e}")
            return None

    # ── Safe filename helper ──────────────────────────────────────────────────

    @staticmethod
    def _safe_filename(text: str, max_len: int = 60) -> str:
        """Convert arbitrary text to a filesystem-safe filename slug."""
        import re
        slug = re.sub(r"[^\w\s-]", "", text.lower())
        slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
        return slug[:max_len]

    # ── Public interface ──────────────────────────────────────────────────────

    def fetch(self, query: dict, skip_pdf: bool = False) -> dict | None:
        """
        Top-level method called by collect_data.py.
        query keys: title, doi, pmid, year, author

        Returns a metadata dict (with pdf_path if downloaded) or None.
        """
        candidates = self.search(query)
        if not candidates:
            return None

        # Take best candidate (subclasses may rank them)
        candidate = candidates[0]
        metadata = self.fetch_metadata(candidate)
        if metadata is None:
            return None

        if not skip_pdf:
            pdf_path = self.download_pdf(metadata)
            if pdf_path:
                metadata["pdf_path"] = pdf_path

        metadata.setdefault("source", self.__class__.__name__)
        metadata.setdefault("collected_at", datetime.now().isoformat())
        return metadata

    # ── Abstract methods ──────────────────────────────────────────────────────

    @abstractmethod
    def search(self, query: dict) -> list:
        """Search the source for a paper matching `query`. Return list of candidates."""
        ...

    @abstractmethod
    def fetch_metadata(self, candidate: dict) -> dict | None:
        """Given a candidate from search(), return enriched metadata dict."""
        ...

    @abstractmethod
    def download_pdf(self, metadata: dict) -> str | None:
        """Download PDF for this metadata record. Return local path or None."""
        ...
