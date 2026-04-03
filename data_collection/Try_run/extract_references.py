"""
extract_references.py
---------------------
Fetches reference lists for every paper in corpus.json using:
  1. Europe PMC /references API  (primary)
  2. Semantic Scholar /references API (fallback)

Writes data/metadata/all_references.csv and updates corpus.json.

Usage:
    python extract_references.py
    python extract_references.py --limit 10
    python extract_references.py --force
"""

import sys, re, csv, json, time, hashlib, logging, argparse
import requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))

Path("data/metadata").mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("data/collection.log")],
)
log = logging.getLogger(__name__)

CORPUS_JSON    = Path("data/metadata/corpus.json")
REFERENCES_CSV = Path("data/metadata/all_references.csv")
HEADERS        = {"User-Agent": "CitationGraphBuilder/1.0 (academic-research)"}

CSV_COLUMNS = [
    "citing_paper_id", "cited_paper_id", "citing_title",
    "raw_reference", "parsed_authors", "parsed_year",
    "parsed_title", "parsed_venue", "parsed_doi", "resolution_method",
]

# ── HTTP ──────────────────────────────────────────────────────────────────────

def get(url, params=None, pause=0.4):
    time.sleep(pause)
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        log.debug(f"HTTP error {url}: {e}")
        return None

# ── Europe PMC ────────────────────────────────────────────────────────────────

EPMC_REFS   = "https://www.ebi.ac.uk/europepmc/webservices/rest/{src}/{id}/references"
EPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

def epmc_src_id(paper):
    """Resolve paper to (source, id) for EPMC API."""
    if paper.get("pmcid"):
        return "PMC", str(paper["pmcid"]).replace("PMC", "")
    if paper.get("pmid"):
        return "MED", str(paper["pmid"])
    if paper.get("doi"):
        resp = get(EPMC_SEARCH, params={
            "query": f'DOI:"{paper["doi"]}"',
            "format": "json", "resultType": "core", "pageSize": 1,
        }, pause=0.4)
        if resp:
            results = (resp.json().get("resultList") or {}).get("result") or []
            if results:
                r = results[0]
                if r.get("pmcid"):
                    return "PMC", str(r["pmcid"]).replace("PMC", "")
                if r.get("pmid"):
                    return "MED", str(r["pmid"])
    return None, None

def fetch_refs_epmc(paper):
    src, pid = epmc_src_id(paper)
    if not src:
        return []
    url  = EPMC_REFS.format(src=src, id=pid)
    resp = get(url, params={"format": "json", "pageSize": 1000}, pause=0.4)
    if not resp:
        return []
    data = resp.json()
    raw  = (data.get("referenceList") or {}).get("reference") or []
    log.debug(f"  EPMC {src}/{pid}: {len(raw)} refs")
    refs = []
    for r in raw:
        auth = r.get("authorString") or ""
        refs.append({
            "raw":     f"{auth} ({r.get('pubYear','')}) {r.get('title','')}".strip(),
            "authors": auth,
            "year":    str(r.get("pubYear") or ""),
            "title":   r.get("title"),
            "venue":   r.get("journalAbbreviation") or r.get("journal"),
            "doi":     r.get("doi"),
            "pmid":    str(r.get("id", "")) if r.get("source") == "MED" else None,
            "pmcid":   r.get("pmcid"),
        })
    return refs

# ── Semantic Scholar ──────────────────────────────────────────────────────────

S2_REFS   = "https://api.semanticscholar.org/graph/v1/paper/{pid}/references"
S2_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,authors,year,externalIds,venue"

def s2_paper_id(paper):
    """Get a Semantic Scholar resolvable ID, trying title search if needed."""
    if paper.get("doi"):
        return paper["doi"]
    if paper.get("pmid"):
        return f"PMID:{paper['pmid']}"
    if paper.get("arxiv_id"):
        return f"ARXIV:{paper['arxiv_id']}"
    # No structured ID — search by title
    title = paper.get("title", "")
    if not title:
        return None
    resp = get(S2_SEARCH, params={
        "query": title, "fields": "paperId,title,year", "limit": 5,
    }, pause=1.2)
    if not resp:
        return None
    data  = resp.json()
    items = data.get("data") if isinstance(data, dict) else None
    if not items:
        return None
    year = str(paper.get("year", ""))
    # Prefer exact year match
    for item in items:
        if year and str(item.get("year", "")) == year:
            return item.get("paperId")
    return items[0].get("paperId")

def fetch_refs_s2(paper):
    pid = s2_paper_id(paper)
    if not pid:
        return []
    url  = S2_REFS.format(pid=requests.utils.quote(str(pid), safe=":/"))
    resp = get(url, params={"fields": S2_FIELDS, "limit": 500}, pause=1.2)
    if not resp:
        return []
    data  = resp.json()
    if not isinstance(data, dict):
        return []
    items = data.get("data") or []
    log.debug(f"  S2 {pid}: {len(items)} refs")
    refs = []
    for item in items:
        # citedPaper can be null — always guard with "or {}"
        p   = item.get("citedPaper") or {}
        if not p:
            continue
        ext     = p.get("externalIds") or {}
        authors = " | ".join(
            (a.get("name") or "") for a in (p.get("authors") or [])
        )
        refs.append({
            "raw":     f"{authors} ({p.get('year','')}) {p.get('title','')}".strip(),
            "authors": authors,
            "year":    str(p.get("year") or ""),
            "title":   p.get("title"),
            "venue":   p.get("venue"),
            "doi":     ext.get("DOI"),
            "pmid":    str(ext.get("PubMed") or "") or None,
            "pmcid":   None,
        })
    return refs

# ── ID + resolution ───────────────────────────────────────────────────────────

def make_paper_id(paper):
    if paper.get("doi"):
        return re.sub(r"[^\w.-]", "_", paper["doi"].strip())
    if paper.get("pmid"):
        return f"pmid_{paper['pmid']}"
    if paper.get("pmcid"):
        return re.sub(r"[^\w.-]", "_", str(paper["pmcid"]).strip())
    if paper.get("arxiv_id"):
        return f"arxiv_{paper['arxiv_id']}"
    title = (paper.get("title") or "unknown").lower().strip()
    return "hash_" + hashlib.md5(title.encode()).hexdigest()[:12]

def build_lookup(corpus):
    lookup = {}
    for paper in corpus.values():
        pid = make_paper_id(paper)
        for field in ("doi", "pmid", "pmcid", "arxiv_id"):
            val = (paper.get(field) or "").strip().lower()
            if val:
                lookup[val] = pid
        title = (paper.get("title") or "").lower().strip()
        if title:
            lookup[title] = pid
    return lookup

def resolve(ref, lookup):
    for field, method in [("doi","exact_doi"),("pmid","exact_pmid"),("pmcid","exact_pmcid")]:
        val = (ref.get(field) or "").strip().lower()
        if val and val in lookup:
            return lookup[val], method
    title = (ref.get("title") or "").lower().strip()
    if title and title in lookup:
        return lookup[title], "exact_title"
    if title:
        qw = {w for w in title.split() if len(w) > 3}
        best_score, best_pid = 0.0, None
        for cand, cpid in lookup.items():
            cw = {w for w in cand.split() if len(w) > 3}
            if not cw:
                continue
            j = len(qw & cw) / len(qw | cw)
            if j > best_score:
                best_score, best_pid = j, cpid
        if best_score >= 0.55:
            return best_pid, f"fuzzy_{best_score:.2f}"
    return None, "unresolved"

# ── Pipeline ──────────────────────────────────────────────────────────────────

def make_edge(paper, ref, cited_id, method):
    return {
        "citing_paper_id":   make_paper_id(paper),
        "cited_paper_id":    cited_id or "",
        "citing_title":      (paper.get("title") or "")[:120],
        "raw_reference":     (ref.get("raw") or "")[:300],
        "parsed_authors":    (ref.get("authors") or "")[:150],
        "parsed_year":       str(ref.get("year") or ""),
        "parsed_title":      (ref.get("title") or "")[:200],
        "parsed_venue":      (ref.get("venue") or "")[:120],
        "parsed_doi":        ref.get("doi") or "",
        "resolution_method": method,
    }

def process(corpus, force=False, limit=None):
    lookup    = build_lookup(corpus)
    all_edges = []
    done      = 0

    for key, paper in corpus.items():
        if limit and done >= limit:
            break

        label = (paper.get("title") or key)[:65]

        if not force and paper.get("references_extracted"):
            log.info(f"[cached] {label}")
            for ref in paper.get("references") or []:
                cited_id, method = resolve(ref, lookup)
                all_edges.append(make_edge(paper, ref, cited_id, method))
            continue

        log.info(f"Fetching: {label}")

        refs = fetch_refs_epmc(paper)
        src  = "epmc"
        if not refs:
            log.info(f"  EPMC empty → Semantic Scholar")
            refs = fetch_refs_s2(paper)
            src  = "s2"

        if refs:
            log.info(f"  {len(refs)} refs via {src}")
        else:
            log.warning(f"  No references found")

        paper["references"]           = refs
        paper["references_extracted"] = datetime.now().isoformat()

        for ref in refs:
            cited_id, method = resolve(ref, lookup)
            all_edges.append(make_edge(paper, ref, cited_id, method))

        done += 1

    return all_edges

def write_csv(edges):
    REFERENCES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(REFERENCES_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(edges)
    log.info(f"Wrote {len(edges)} rows -> {REFERENCES_CSV}")

def print_summary(edges):
    total    = len(edges)
    resolved = sum(1 for e in edges if e["cited_paper_id"])
    print("\n── Reference Extraction Summary ─────────────────────")
    print(f"  Total edges       : {total}")
    print(f"  Resolved to corpus: {resolved}  ({100*resolved//max(total,1)}%)")
    print(f"  Unresolved        : {total - resolved}")
    for method in ("exact_doi","exact_pmid","exact_pmcid","exact_title","fuzzy"):
        n = sum(1 for e in edges if method in e["resolution_method"])
        if n:
            print(f"    {method:<20}: {n}")
    print(f"\n  CSV → {REFERENCES_CSV}")
    print("─────────────────────────────────────────────────────\n")

# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not CORPUS_JSON.exists():
        log.error("corpus.json not found. Run collect_data.py first.")
        sys.exit(1)

    with open(CORPUS_JSON) as f:
        corpus = json.load(f)
    log.info(f"Loaded {len(corpus)} papers")

    edges = process(corpus, force=args.force, limit=args.limit)
    write_csv(edges)

    with open(CORPUS_JSON, "w") as f:
        json.dump(corpus, f, indent=2, default=str)
    log.info("corpus.json updated")

    print_summary(edges)

if __name__ == "__main__":
    main()
