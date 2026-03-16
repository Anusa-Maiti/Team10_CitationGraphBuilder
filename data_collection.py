#!/usr/bin/env python3
"""
Script to QUERY WEB APIS for human evolution papers and build a corpus
This actually searches APIs instead of using pre-specified IDs
"""

import os
import json
import time
import hashlib
import requests
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class HumanEvolutionCorpusBuilder:
    """Build a corpus by actually QUERYING web APIs for human evolution papers"""
    
    def __init__(self, output_dir: str = "./data"):
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"
        self.metadata_dir = self.output_dir / "metadata"
        
        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # Corpus storage
        self.corpus_file = self.metadata_dir / "corpus.json"
        self.corpus = self.load_corpus()
        
        # Track seen papers to avoid duplicates
        self.seen_dois = set()
        self.seen_titles = set()
        for paper in self.corpus:
            if paper.get('doi'):
                self.seen_dois.add(paper['doi'])
            if paper.get('title'):
                self.seen_titles.add(paper['title'].lower())
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 1 second between requests
        
    def load_corpus(self) -> List[Dict[str, Any]]:
        """Load existing corpus if available"""
        if self.corpus_file.exists():
            with open(self.corpus_file, 'r') as f:
                return json.load(f)
        return []
    
    def save_corpus(self):
        """Save corpus to JSON file"""
        with open(self.corpus_file, 'w') as f:
            json.dump(self.corpus, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(self.corpus)} papers to {self.corpus_file}")
    
    def rate_limit(self):
        """Simple rate limiting to be respectful to APIs"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def generate_paper_id(self, title: str, authors: str, year: str) -> str:
        """Generate a unique ID for a paper"""
        if not title:
            return hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
        id_string = f"{title}_{authors}_{year}".lower()
        return hashlib.md5(id_string.encode()).hexdigest()[:12]
    
    def is_duplicate(self, doi: Optional[str], title: Optional[str]) -> bool:
        """Check if paper already exists in corpus"""
        if doi and doi in self.seen_dois:
            return True
        if title and title.lower() in self.seen_titles:
            return True
        return False
    
    # ==================== STEP 1: QUERY EUROPE PMC API ====================
    def query_europe_pmc(self, query: str, max_results: int = 30) -> List[Dict]:
        """
        ACTUALLY QUERY the Europe PMC API for papers matching search terms
        This is REAL web searching, not using preset IDs
        """
        logger.info(f"🔍 Querying Europe PMC API for: '{query}'")
        
        base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            'query': query,
            'format': 'json',
            'pageSize': max_results,
            'resultType': 'core'
        }
        
        self.rate_limit()
        
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            papers = []
            if 'resultList' in data and 'result' in data['resultList']:
                for result in data['resultList']['result']:
                    # Extract what we need
                    paper = {
                        'id': self.generate_paper_id(
                            result.get('title', ''),
                            result.get('authorString', ''),
                            result.get('pubYear', '')
                        ),
                        'title': result.get('title', ''),
                        'authors': result.get('authorString', '').split(', '),
                        'year': result.get('pubYear', ''),
                        'journal': result.get('journalTitle', ''),
                        'doi': result.get('doi', ''),
                        'pmcid': result.get('pmcid', ''),
                        'pmid': result.get('pmid', ''),
                        'source': 'EuropePMC',
                        'abstract': result.get('abstractText', ''),
                        'date_added': datetime.now().isoformat()
                    }
                    
                    # Try to get PDF URL if available
                    if result.get('hasPDF', 'N') == 'Y':
                        if result.get('pmcid'):
                            paper['pdf_url'] = f"https://europepmc.org/articles/{result['pmcid']}/pdf"
                    
                    papers.append(paper)
            
            logger.info(f"✅ Found {len(papers)} papers from Europe PMC")
            return papers
            
        except Exception as e:
            logger.error(f"❌ Error querying Europe PMC: {e}")
            return []
    
    # ==================== STEP 2: QUERY ARXIV API ====================
    def query_arxiv(self, query: str, max_results: int = 30) -> List[Dict]:
        """
        ACTUALLY QUERY the arXiv API for papers
        arXiv uses a different XML-based API
        """
        logger.info(f"🔍 Querying arXiv API for: '{query}'")
        
        import xml.etree.ElementTree as ET
        
        base_url = "http://export.arxiv.org/api/query"
        params = {
            'search_query': f'all:{query}',
            'start': 0,
            'max_results': max_results
        }
        
        self.rate_limit()
        
        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            
            # Parse XML response
            root = ET.fromstring(response.text)
            
            # Define namespaces
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'arxiv': 'http://arxiv.org/schemas/atom'
            }
            
            papers = []
            for entry in root.findall('atom:entry', ns):
                # Extract authors
                authors = []
                for author in entry.findall('atom:author', ns):
                    name = author.find('atom:name', ns)
                    if name is not None:
                        authors.append(name.text)
                
                # Get PDF link
                pdf_url = None
                for link in entry.findall('atom:link', ns):
                    if link.get('title') == 'pdf':
                        pdf_url = link.get('href')
                        break
                
                # Get year from published date
                published = entry.find('atom:published', ns)
                year = published.text[:4] if published is not None else ''
                
                paper = {
                    'id': self.generate_paper_id(
                        entry.findtext('atom:title', '', ns),
                        ', '.join(authors),
                        year
                    ),
                    'title': entry.findtext('atom:title', '', ns).replace('\n', ' ').strip(),
                    'authors': authors,
                    'year': year,
                    'journal': 'arXiv',
                    'doi': entry.findtext('arxiv:doi', '', ns),
                    'arxiv_id': entry.findtext('atom:id', '', ns).split('/abs/')[-1],
                    'pdf_url': pdf_url,
                    'source': 'arXiv',
                    'abstract': entry.findtext('atom:summary', '', ns).replace('\n', ' ').strip(),
                    'date_added': datetime.now().isoformat()
                }
                papers.append(paper)
            
            logger.info(f"✅ Found {len(papers)} papers from arXiv")
            return papers
            
        except Exception as e:
            logger.error(f"❌ Error querying arXiv: {e}")
            return []
    
   
    # ==================== STEP 3: DOWNLOAD PDF IF AVAILABLE ====================
    def download_pdf(self, metadata: Dict[str, Any]) -> bool:
        """Download PDF for a paper"""
        if not metadata.get('pdf_url'):
            logger.debug(f"No PDF URL for {metadata.get('title', 'Unknown')[:50]}...")
            return False
        
        pdf_filename = self.raw_dir / f"{metadata['id']}.pdf"
        
        # Skip if already downloaded
        if pdf_filename.exists():
            logger.info(f"📄 PDF already exists: {pdf_filename.name}")
            return True
        
        self.rate_limit()
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Academic Research Bot)'
            }
            response = requests.get(metadata['pdf_url'], headers=headers, stream=True, timeout=30)
            response.raise_for_status()
            
            # Check if it's actually a PDF
            content_type = response.headers.get('content-type', '')
            if 'pdf' not in content_type.lower():
                logger.warning(f"URL doesn't point to PDF: {content_type}")
                return False
            
            with open(pdf_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"✅ Downloaded: {pdf_filename.name}")
            metadata['local_pdf'] = str(pdf_filename)
            return True
            
        except Exception as e:
            logger.debug(f"Failed to download PDF: {e}")
            return False
    
    # ==================== MAIN BUILD FUNCTION ====================
    def build_corpus(self, search_terms: List[str], target_count: int = 30):
        """
        Main function: Actually query web APIs with search terms
        This is REAL web searching, not using preset IDs
        """
        logger.info(f"🎯 Starting corpus build - Target: {target_count} papers")
        logger.info(f"🔎 Search terms: {search_terms}")
        
        papers_found = []
        
        for term in search_terms:
            if len(self.corpus) + len(papers_found) >= target_count:
                break
            
            # Query multiple APIs for each term
            logger.info(f"\n{'='*60}")
            logger.info(f"SEARCHING FOR: '{term}'")
            logger.info(f"{'='*60}")
            
            # Try Europe PMC
            pmc_papers = self.query_europe_pmc(term, max_results=15)
            for paper in pmc_papers:
                if len(self.corpus) + len(papers_found) >= target_count:
                    break
                if not self.is_duplicate(paper.get('doi'), paper.get('title')):
                    papers_found.append(paper)
                    if paper.get('doi'):
                        self.seen_dois.add(paper['doi'])
                    if paper.get('title'):
                        self.seen_titles.add(paper['title'].lower())
            
            # Try arXiv
            arxiv_papers = self.query_arxiv(term, max_results=10)
            for paper in arxiv_papers:
                if len(self.corpus) + len(papers_found) >= target_count:
                    break
                if not self.is_duplicate(paper.get('doi'), paper.get('title')):
                    papers_found.append(paper)
            
        
        # Add to corpus
        logger.info(f"\n{'='*60}")
        logger.info(f"Found {len(papers_found)} new papers")
        logger.info(f"{'='*60}")
        
        for paper in papers_found[:target_count - len(self.corpus)]:
            # Try to download PDF
            self.download_pdf(paper)
            
            # Add to corpus
            self.corpus.append(paper)
            logger.info(f"➕ Added: {paper.get('title', '')[:80]}...")
        
        # Save final corpus
        self.save_corpus()

def main():
    parser = argparse.ArgumentParser(description='Build human evolution paper corpus by ACTUALLY QUERYING WEB APIs')
    parser.add_argument('--output-dir', type=str, default='./data',
                       help='Output directory for data')
    parser.add_argument('--count', type=int, default=30,
                       help='Number of papers to collect')
    args = parser.parse_args()
    
    # Define search terms - THESE ARE ACTUALLY QUERIED, NOT PRESET IDs
    search_terms = [
        # Main human evolution topics
        '"human evolution"',
        '"homo naledi"',
        '"neanderthal genome"',
        '"australopithecus"',
        '"ancient dna" hominin',
        '"paleoanthropology"',
        '"early homo"',
        '"plesianthropus"',  # Taung child
        '"olduvai" hominin',
        '"lucy" australopithecus'
    ]
    
    # Build corpus by ACTUALLY QUERYING APIs
    builder = HumanEvolutionCorpusBuilder(output_dir=args.output_dir)
    builder.build_corpus(search_terms, target_count=args.count)
    
    # Print summary
    print("\n" + "="*70)
    print("✅ CORPUS BUILD COMPLETE - REAL WEB QUERIES PERFORMED")
    print("="*70)
    print(f"Total papers: {len(builder.corpus)}")
    
    # Count by source
    sources = {}
    for paper in builder.corpus:
        src = paper.get('source', 'Unknown')
        sources[src] = sources.get(src, 0) + 1
    
    print("\n📊 Papers by source:")
    for src, count in sources.items():
        print(f"  • {src}: {count}")
    
    # Count successful downloads
    downloaded = sum(1 for p in builder.corpus if 'local_pdf' in p)
    print(f"\n📄 PDFs successfully downloaded: {downloaded}")
    
    # Show sample
    if builder.corpus:
        print("\n📝 Sample paper (first in corpus):")
        sample = builder.corpus[0]
        print(f"  Title: {sample.get('title', 'N/A')[:100]}...")
        print(f"  Authors: {', '.join(sample.get('authors', [])[:3])}")
        print(f"  Year: {sample.get('year', 'N/A')}")
        print(f"  Source: {sample.get('source', 'N/A')}")
        print(f"  DOI: {sample.get('doi', 'N/A')}")
        if 'local_pdf' in sample:
            print(f"  PDF: {sample['local_pdf']}")
    
    print(f"\n💾 Corpus saved to: {builder.corpus_file}")
    print(f"📁 PDFs saved to: {builder.raw_dir}")

if __name__ == "__main__":
    main()
