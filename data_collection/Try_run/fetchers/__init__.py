"""
fetchers/__init__.py
Exposes all fetcher classes for convenient import.
"""

from .base_fetcher      import BaseFetcher
from .pmc_fetcher       import PMCFetcher
from .europepmc_fetcher import EuropePMCFetcher
from .arxiv_fetcher     import ArXivFetcher
from .biorxiv_fetcher   import BioRxivFetcher

__all__ = [
    "BaseFetcher",
    "PMCFetcher",
    "EuropePMCFetcher",
    "ArXivFetcher",
    "BioRxivFetcher",
]
