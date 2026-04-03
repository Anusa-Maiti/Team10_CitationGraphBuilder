"""
redownload_pdfs.py
------------------
Scans data/raw/ for broken PDFs (< 10 KB or containing "Preparing to download")
and re-downloads them using the fixed PMC fetcher (OA service) + Europe PMC fallback.

Also verifies each PDF has extractable text.

Usage:
    python redownload_pdfs.py           # fix all broken PDFs
    python redownload_pdfs.py --check   # report only, no downloading
"""

import sys
import json
import time
import logging
import argparse
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

Path("data/metadata").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("data/collection.log")],
)
log = logging.getLogger(__name__)

CORPUS_JSON = Path("data/metadata/corpus.json")
HEADERS     = {"User-Agent": "CitationGraphBuilder/1.0 (academic-research)"}

# PMC OA service
OA_SERVICE  = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
# Europe PMC PDF pattern
EPMC_PDF    = "https://europepmc.org/articles/{pmcid}/pdf/{pmcid}.pdf"


def is_broken(pdf_path: Path) -> bool:
    """Return True if the PDF is a fake/redirect HTML page or too small."""
    if not pdf_path.exists():
        return True
    if pdf_path.stat().st_size < 10_000:   # < 10 KB → almost certainly fake
        return True
    try:
        snippet = pdf_path.read_bytes()[:500]
        if b"Preparing to download" in snippet or b"<html" in snippet.lower():
            return True
    except OSError:
        return True
    return False


def has_text(pdf_path: Path) -> bool:
    """Check that PyMuPDF can extract real text from the PDF."""
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        text = "".join(p.get_text() for p in doc)
        doc.close()
        return len(text.strip()) > 200
    except Exception:
        return False


def get(url, params=None, pause=0.4, stream=False):
    time.sleep(pause)
    try:
        r = requests.get(url, params=params, headers=HEADERS,
                         timeout=60, stream=stream)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        log.debug(f"  HTTP error {url}: {e}")
        return None


def oa_pdf_url(pmcid: str) -> str | None:
    """Query PMC OA service for a real PDF download URL."""
    import xml.etree.ElementTree as ET
    resp = get(OA_SERVICE, params={"id": pmcid, "format": "pdf"})
    if resp is None:
        return None
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None
    for link in root.findall(".//link"):
        if link.get("format") == "pdf":
            href = link.get("href", "")
            return href.replace("ftp://", "https://", 1) if href else None
    return None


def download(url: str, dest: Path) -> bool:
    """Stream-download url to dest. Returns True on success."""
    log.info(f"  Downloading: {url}")
    resp = get(url, stream=True, pause=0.3)
    if resp is None:
        return False
    content_type = resp.headers.get("Content-Type", "")
    if "html" in content_type:
        log.warning(f"  Got HTML response (not a PDF): {url}")
        return False
    try:
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        size_kb = dest.stat().st_size / 1024
        log.info(f"  Saved {dest.name} ({size_kb:.0f} KB)")
        return not is_broken(dest)
    except OSError as e:
        log.error(f"  Write error: {e}")
        return False


def fix_paper(paper: dict) -> bool:
    """Attempt to download a real PDF for a paper. Returns True if fixed."""
    title   = (paper.get("title") or "unknown")[:60]
    pmcid   = paper.get("pmcid", "")
    doi     = paper.get("doi", "")
    pdf_path = Path(paper.get("pdf_path", ""))

    log.info(f"Fixing: {title}")

    tried = []

    # Strategy 1: PMC OA service (most reliable for PMC papers)
    if pmcid:
        url = oa_pdf_url(pmcid)
        if url:
            if download(url, pdf_path):
                return True
            tried.append(f"OA:{url}")

    # Strategy 2: Europe PMC direct PDF
    if pmcid:
        pmcid_lower = pmcid.lower()
        url = EPMC_PDF.format(pmcid=pmcid_lower)
        if download(url, pdf_path):
            return True
        tried.append(f"EPMC:{url}")

    # Strategy 3: Unpaywall (open access by DOI)
    if doi:
        url = f"https://api.unpaywall.org/v2/{doi}?email=research@example.com"
        resp = get(url, pause=0.5)
        if resp:
            data = resp.json()
            oa_loc = data.get("best_oa_location") or {}
            pdf_url = oa_loc.get("url_for_pdf")
            if pdf_url and download(pdf_url, pdf_path):
                return True
            tried.append(f"Unpaywall:{pdf_url}")

    log.warning(f"  Could not fix (tried: {len(tried)} sources)")
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="Report broken PDFs without re-downloading")
    args = parser.parse_args()

    if not CORPUS_JSON.exists():
        log.error("corpus.json not found. Run collect_data.py first.")
        sys.exit(1)

    with open(CORPUS_JSON) as f:
        corpus = json.load(f)

    broken, good, no_pdf = [], [], []

    for key, paper in corpus.items():
        pdf_path = paper.get("pdf_path")
        if not pdf_path:
            no_pdf.append(key)
            continue
        p = Path(pdf_path)
        if is_broken(p):
            broken.append((key, paper))
        elif not has_text(p):
            log.warning(f"No extractable text: {p.name}")
            broken.append((key, paper))
        else:
            good.append(key)

    log.info(f"\nPDF status: {len(good)} good / {len(broken)} broken / {len(no_pdf)} no PDF")

    if args.check or not broken:
        for key, paper in broken:
            log.info(f"  BROKEN: {paper.get('title','?')[:70]}")
        return

    fixed = 0
    for key, paper in broken:
        if fix_paper(paper):
            fixed += 1

    # Save updated corpus
    with open(CORPUS_JSON, "w") as f:
        json.dump(corpus, f, indent=2, default=str)

    log.info(f"\nFixed {fixed}/{len(broken)} broken PDFs")
    log.info("Now run: python extract_references.py --force")


if __name__ == "__main__":
    main()
