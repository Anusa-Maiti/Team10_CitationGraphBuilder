"""
citation_expander.py
---------------------
Expands the seed corpus by fetching:
  - Backward citations: papers cited BY seed papers (references)
  - Forward citations:  papers that CITE seed papers (citing works)

Uses Europe PMC's citation API which provides both directions,
with fallback to Semantic Scholar's open API.

Usage (called from collect_data.py):
    expander = CitationExpander(corpus, max_papers=200, depth=1)
    expanded_corpus = expander.expand()
"""

import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import time
from datetime import datetime

from fetchers.europepmc_fetcher import EuropePMCFetcher
from fetchers.pmc_fetcher import PMCFetcher

# ── Relevance filter ──────────────────────────────────────────────────────────
# A paper must match at least one INCLUDE term and zero EXCLUDE terms
# (checked against lowercased title + venue string).

INCLUDE_TERMS = {
    # Hominin taxonomy & fossils
    "homo", "hominin", "hominid", "hominini", "australopithecus",
    "paranthropus", "ardipithecus", "sahelanthropus", "orrorin",
    "neanderthal", "neandertal", "denisovan", "erectus", "heidelbergensis",
    "naledi", "floresiensis", "luzonensis", "antecessor",
    # Modern human origins
    "human evolution", "human origins", "modern human", "anatomically modern",
    "out of africa", "multiregional", "archaic human", "early human",
    # Paleoanthropology & archaeology
    "paleoanthropology", "palaeoanthropology", "palaeontology", "paleontology",
    "fossil", "hominin fossil", "skull", "cranium", "mandible", "bipedal",
    "lithic", "acheulean", "oldowan", "mousterian", "stone tool",
    # Ancient & population genomics in human evolution context
    "ancient dna", "ancient genome", "archaic introgression", "introgression",
    "admixture", "population history", "human dispersal", "migration",
    "phylogenetic", "phylogeny", "ancestral population",
    # Specific venues
    "journal of human evolution", "evolutionary anthropology",
    "american journal of physical anthropology", "paleoanthropology",
    "quaternary", "plos genetics", "nature human behaviour",
}

EXCLUDE_TERMS = {
    # Clinical / medical topics unrelated to evolution
    "cancer", "tumor", "tumour", "carcinoma", "leukemia", "lymphoma",
    "diabetes", "cardiovascular", "hypertension", "autoimmune",
    "vaccine", "vaccination", "immunotherapy", "hiv", "covid", "sars",
    "alzheimer", "parkinson", "epilepsy", "asthma", "allergy",
    # Microbiology / virology (unless related to ancient DNA)
    "bacterium", "bacteria", "viral", "virus", "pathogen", "infection",
    "antibiotic", "antimicrobial",
    # Plant / animal biology unrelated to humans
    "plant", "arabidopsis", "drosophila", "zebrafish", "yeast",
    "mouse model", "murine", "bovine", "equine", "avian",
    # Pure methods papers with no human evolution content
    "machine learning classification", "deep learning image",
    "neural network speech", "computer vision",
}


def is_relevant(paper: dict) -> bool:
    """
    Return True if the paper is relevant to human evolution.
    Checks title + venue against INCLUDE_TERMS and EXCLUDE_TERMS.
    """
    text = " ".join([
        (paper.get("title") or ""),
        (paper.get("venue") or ""),
        (paper.get("abstract") or "")[:300],
    ]).lower()

    # Must match at least one include term
    if not any(term in text for term in INCLUDE_TERMS):
        return False

    # Must not match any hard exclude term
    if any(term in text for term in EXCLUDE_TERMS):
        return False

    return True

log = logging.getLogger(__name__)

# Europe PMC citation APIs
EPMC_REFERENCES_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{id}/references"
EPMC_CITATIONS_URL  = "https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{id}/citations"

# Semantic Scholar (open, no key required for modest usage)
S2_PAPER_URL        = "https://api.semanticscholar.org/graph/v1/paper/{paper_id}"
S2_SEARCH_URL       = "https://api.semanticscholar.org/graph/v1/paper/search"


class CitationExpander:
    """
    Performs breadth-first citation expansion from the seed corpus.

    Parameters
    ----------
    corpus : dict
        Existing corpus (key → metadata dict).
    max_papers : int
        Hard cap on total papers collected.
    skip_pdf : bool
        If True, only collect metadata (no PDF downloads).
    depth : int
        How many levels deep to expand (1 = direct citations only).
    """

    def __init__(self, corpus: dict, max_papers: int = 200,
                 skip_pdf: bool = False, depth: int = 1):
        self.corpus    = dict(corpus)
        self.max_papers = max_papers
        self.skip_pdf  = skip_pdf
        self.depth     = depth
        self._epmc     = EuropePMCFetcher(rate_limit=5)
        self._seen_ids : set = set(corpus.keys())

    # ── Public ────────────────────────────────────────────────────────────────

    def expand(self) -> dict:
        """Run BFS expansion. Returns updated corpus."""
        frontier = list(self.corpus.values())  # current depth layer

        for d in range(self.depth):
            if len(self.corpus) >= self.max_papers:
                log.info(f"Reached max_papers={self.max_papers} at depth {d}")
                break

            log.info(f"Expansion depth {d+1}: frontier size = {len(frontier)}")
            next_frontier = []

            for paper in frontier:
                if len(self.corpus) >= self.max_papers:
                    break
                new_papers = self._expand_one(paper)
                next_frontier.extend(new_papers)

            frontier = next_frontier

        return self.corpus

    # ── Core expansion ────────────────────────────────────────────────────────

    def _expand_one(self, paper: dict) -> list:
        """
        Expand a single paper: fetch both backward (references) and
        forward (citations) neighbours. Return newly added papers.
        """
        added = []

        # Resolve source / ID for Europe PMC
        epmc_source, epmc_id = self._resolve_epmc_id(paper)
        if epmc_source and epmc_id:
            refs     = self._fetch_references_epmc(epmc_source, epmc_id)
            cit_by   = self._fetch_citations_epmc(epmc_source, epmc_id)
        else:
            log.debug(f"No EPMC ID for: {paper.get('title', '?')[:60]} – trying S2")
            refs   = self._fetch_via_semantic_scholar(paper, direction="references")
            cit_by = self._fetch_via_semantic_scholar(paper, direction="citations")

        for candidate in refs + cit_by:
            new_paper = self._add_to_corpus(candidate)
            if new_paper:
                added.append(new_paper)
                if len(self.corpus) >= self.max_papers:
                    break

        return added

    # ── Europe PMC helpers ────────────────────────────────────────────────────

    def _resolve_epmc_id(self, paper: dict):
        """Return (source, id) tuple for Europe PMC API calls."""
        if paper.get("pmcid"):
            pmcid = paper["pmcid"].replace("PMC", "")
            return "PMC", pmcid
        if paper.get("pmid"):
            return "MED", paper["pmid"]
        if paper.get("doi"):
            return "DOI", paper["doi"]
        return None, None

    def _fetch_references_epmc(self, source: str, paper_id: str) -> list:
        """Fetch papers referenced by this paper (backward)."""
        url = EPMC_REFERENCES_URL.format(source=source, id=paper_id)
        params = {"format": "json", "pageSize": 100}
        resp = self._epmc._get(url, params=params)
        if resp is None:
            return []
        data = resp.json()
        refs = data.get("referenceList", {}).get("reference", [])
        log.debug(f"EPMC references for {source}/{paper_id}: {len(refs)}")
        return [self._normalize_epmc_ref(r) for r in refs]

    def _fetch_citations_epmc(self, source: str, paper_id: str) -> list:
        """Fetch papers that cite this paper (forward)."""
        url = EPMC_CITATIONS_URL.format(source=source, id=paper_id)
        params = {"format": "json", "pageSize": 100}
        resp = self._epmc._get(url, params=params)
        if resp is None:
            return []
        data = resp.json()
        cits = data.get("citationList", {}).get("citation", [])
        log.debug(f"EPMC citations for {source}/{paper_id}: {len(cits)}")
        return [self._normalize_epmc_ref(c) for c in cits]

    def _normalize_epmc_ref(self, ref: dict) -> dict:
        """Normalize a Europe PMC reference/citation record."""
        authors_raw = ref.get("authorString", "")
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]
        return {
            "pmid":    ref.get("id"),
            "pmcid":   ref.get("pmcid"),
            "doi":     ref.get("doi"),
            "title":   ref.get("title"),
            "authors": authors,
            "year":    str(ref.get("pubYear", "")),
            "venue":   ref.get("journalAbbreviation") or ref.get("journal"),
            "source":  "EuropePMC_expansion",
            "collected_at": datetime.now().isoformat(),
        }

    # ── Semantic Scholar fallback ─────────────────────────────────────────────

    def _fetch_via_semantic_scholar(self, paper: dict, direction: str) -> list:
        """
        Use Semantic Scholar to find references or citations.
        direction: "references" | "citations"
        """
        s2_id = self._resolve_s2_id(paper)
        if not s2_id:
            return []

        url = f"{S2_PAPER_URL.format(paper_id=s2_id)}/{direction}"
        params = {
            "fields": "title,authors,year,externalIds,venue",
            "limit":  50,
        }

        # S2 is stricter on rate limits – wait 1 second
        time.sleep(1.0)
        resp = self._epmc._get(url, params=params)
        if resp is None:
            return []

        data = resp.json()
        items = data.get("data", [])
        log.debug(f"S2 {direction} for {s2_id}: {len(items)}")

        normalized = []
        for item in items:
            p = item.get("citedPaper") or item.get("citingPaper") or item
            external = p.get("externalIds", {})
            author_list = p.get("authors", [])
            normalized.append({
                "doi":    external.get("DOI"),
                "pmid":   external.get("PubMed"),
                "title":  p.get("title"),
                "authors": [a.get("name", "") for a in author_list],
                "year":   str(p.get("year", "")),
                "venue":  p.get("venue"),
                "source": f"S2_{direction}",
                "collected_at": datetime.now().isoformat(),
            })
        return normalized

    def _resolve_s2_id(self, paper: dict) -> str | None:
        """Return a Semantic Scholar paper identifier."""
        if paper.get("doi"):
            return paper["doi"]
        if paper.get("pmid"):
            return f"PMID:{paper['pmid']}"
        if paper.get("arxiv_id"):
            return f"ARXIV:{paper['arxiv_id']}"
        return None

    # ── Corpus management ─────────────────────────────────────────────────────

    def _add_to_corpus(self, paper: dict) -> dict | None:
        """
        Add paper to corpus if not already present.
        Filters out pre-1990 papers and papers with no structured identifier,
        since these cannot contribute reference edges to the citation graph.
        Uses DOI > PMID > title as dedup key.
        Returns the paper dict if newly added, else None.
        """
        year   = int(paper.get("year") or 0)
        has_id = bool(paper.get("doi") or paper.get("pmid") or paper.get("pmcid"))

        if year and year < 1990:
            log.debug(f"Skipping pre-1990 paper: {paper.get('title','?')[:60]}")
            return None
        if not has_id:
            log.debug(f"Skipping paper with no DOI/PMID/PMCID: {paper.get('title','?')[:60]}")
            return None
        if not is_relevant(paper):
            log.debug(f"Skipping off-topic paper: {paper.get('title','?')[:60]}")
            return None

        key = (paper.get("doi")
               or paper.get("pmid")
               or paper.get("title", "").lower().strip())

        if not key or key in self._seen_ids:
            return None

        self._seen_ids.add(key)
        self.corpus[key] = paper
        log.info(f"  + Added: {paper.get('title', key)[:70]}")
        return paper
