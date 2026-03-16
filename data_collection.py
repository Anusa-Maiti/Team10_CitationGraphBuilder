#!/usr/bin/env python3
"""
Enhanced script to query web APIs for human evolution papers and build a corpus
with GROBID processing for reference extraction

Sources:
- Europe PMC (REST API): PDFs, metadata
- arXiv (q-bio): Preprint PDFs
- bioRxiv: Preprint PDFs

Output structure:
- data/raw/          # PDF files
- data/processed/     # GROBID TEI XML files
- data/metadata/      # corpus.json
"""

import os
import json
import time
import hashlib
import re
import requests
import argparse
import xml.etree.ElementTree as ET
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


class EnhancedCorpusBuilder:
    """Build corpus by querying APIs AND processing PDFs with GROBID"""
    
    def __init__(self, output_dir: str = "./data", grobid_url: str = "http://localhost:8070"):
        """
        Initialize the corpus builder
        
        Args:
            output_dir: Base output directory
            grobid_url: URL of GROBID service
        """
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"           # PDFs stored here
        self.processed_dir = self.output_dir / "processed"  # GROBID XML stored here
        self.metadata_dir = self.output_dir / "metadata"  # corpus.json stored here
        
        # Create directories
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # GROBID settings
        self.grobid_url = grobid_url
        self.grobid_available = self.check_grobid()
        
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
        
        # Rate limiting per source (requests per second)
        self.rate_limits = {
            'europe_pmc': 0.5,    # 2 requests/second (be respectful)
            'arxiv': 1/3.0,       # 1 request/3 seconds
            'biorxiv': 0.5        # 2 requests/second
        }
        
        self.last_request_time = {
            'europe_pmc': 0,
            'arxiv': 0,
            'biorxiv': 0
        }
        
        # User agent
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Academic Research Bot; mailto:your-email@example.com)'
        }
        
        logger.info(f"📁 Output directory: {self.output_dir}")
        logger.info(f"📁 PDFs will be stored in: {self.raw_dir}")
        logger.info(f"📁 GROBID XML will be stored in: {self.processed_dir}")
        logger.info(f"📁 Metadata will be stored in: {self.metadata_dir}")
        logger.info(f"📄 Corpus file: {self.corpus_file}")
        
        if self.grobid_available:
            logger.info("✅ GROBID is available - will extract references")
        else:
            logger.warning("⚠️ GROBID not detected - run: docker run -t --rm -p 8070:8070 grobid/grobid:0.8.0")
    
    def check_grobid(self) -> bool:
        """Check if GROBID is running"""
        try:
            response = requests.get(f"{self.grobid_url}/api/isalive", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def load_corpus(self) -> List[Dict[str, Any]]:
        """Load existing corpus if available"""
        if self.corpus_file.exists():
            with open(self.corpus_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    def save_corpus(self):
        """Save corpus to JSON file"""
        with open(self.corpus_file, 'w', encoding='utf-8') as f:
            json.dump(self.corpus, f, indent=2, ensure_ascii=False)
        logger.info(f"✅ Saved {len(self.corpus)} papers to {self.corpus_file}")
    
    def rate_limit(self, source: str):
        """Apply rate limiting for specific source"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time[source]
        required_interval = self.rate_limits[source]
        
        if time_since_last < required_interval:
            sleep_time = required_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time[source] = time.time()
    
    def generate_readable_filename(self, metadata: Dict[str, Any]) -> str:
        """
        Generate a readable filename from paper metadata
        
        Format: FirstAuthor_Year_FirstFiveWordsOfTitle.pdf
        """
        # Get first author's last name
        authors = metadata.get('authors', [])
        if authors and isinstance(authors, list) and len(authors) > 0:
            first_author = authors[0]
            if isinstance(first_author, str):
                # Extract last name (simplified)
                name_parts = first_author.split()
                first_author = name_parts[-1] if name_parts else "Unknown"
            else:
                first_author = "Unknown"
        else:
            first_author = "Unknown"
        
        # Clean author name
        first_author = re.sub(r'[^\w]', '', first_author)
        if not first_author:
            first_author = "Unknown"
        
        # Get year
        year = metadata.get('year', 'XXXX')
        if not year or year == '':
            year = 'XXXX'
        
        # Get title slug (first 5 words, cleaned)
        title = metadata.get('title', '')
        if title:
            # Extract words, remove punctuation
            words = re.findall(r'\b[a-zA-Z]+\b', title)
            title_words = words[:5]
            title_slug = '_'.join(title_words) if title_words else 'paper'
        else:
            title_slug = 'paper'
        
        # Clean title slug
        title_slug = re.sub(r'[^\w]', '', title_slug)
        
        # Combine
        filename = f"{first_author}_{year}_{title_slug}.pdf"
        
        return filename
    
    def is_duplicate(self, doi: Optional[str], title: Optional[str]) -> bool:
        """Check if paper already exists in corpus"""
        if doi and doi in self.seen_dois:
            return True
        if title and title.lower() in self.seen_titles:
            return True
        return False
    
    # ==================== EUROPE PMC API ====================
    
    def query_europe_pmc(self, query: str, max_results: int = 15) -> List[Dict]:
        """
        Query Europe PMC REST API
        Source: Europe PMC
        Access: REST API
        Content: PDFs, metadata
        Rate Limit: Be respectful (2 requests/second)
        """
        logger.info(f"🔍 Querying Europe PMC for: '{query}'")
        
        base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
        params = {
            'query': query,
            'format': 'json',
            'pageSize': max_results,
            'resultType': 'core'
        }
        
        self.rate_limit('europe_pmc')
        
        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            papers = []
            if 'resultList' in data and 'result' in data['resultList']:
                for result in data['resultList']['result']:
                    # Only include open access papers
                    if result.get('isOpenAccess', 'N') != 'Y':
                        continue
                    
                    # Parse authors
                    author_string = result.get('authorString', '')
                    authors = [a.strip() for a in author_string.split(';')] if author_string else []
                    
                    paper = {
                        'id': hashlib.md5(f"{result.get('title', '')}_{author_string}_{result.get('pubYear', '')}".encode()).hexdigest()[:12],
                        'title': result.get('title', ''),
                        'authors': authors,
                        'year': result.get('pubYear', ''),
                        'journal': result.get('journalTitle', ''),
                        'doi': result.get('doi', ''),
                        'pmcid': result.get('pmcid', ''),
                        'pmid': result.get('pmid', ''),
                        'source': 'EuropePMC',
                        'abstract': result.get('abstractText', ''),
                        'date_added': datetime.now().isoformat()
                    }
                    
                    # Get PDF URL for open access papers
                    if result.get('hasPDF', 'N') == 'Y' and result.get('pmcid'):
                        paper['pdf_url'] = f"https://europepmc.org/articles/{result['pmcid']}/pdf"
                    
                    papers.append(paper)
            
            logger.info(f"✅ Found {len(papers)} open-access papers from Europe PMC")
            return papers
            
        except Exception as e:
            logger.error(f"❌ Error querying Europe PMC: {e}")
            return []
    
    # ==================== ARXIV API ====================
    
    def query_arxiv(self, query: str, max_results: int = 15) -> List[Dict]:
        """
        Query arXiv API
        Source: arXiv
        Access: API
        Content: Preprint PDFs
        Rate Limit: 1 request/3 seconds
        """
        logger.info(f"🔍 Querying arXiv for: '{query}'")
        
        base_url = "http://export.arxiv.org/api/query"
        params = {
            'search_query': f'all:{query}',
            'start': 0,
            'max_results': max_results,
            'sortBy': 'relevance'
        }
        
        self.rate_limit('arxiv')
        
        try:
            response = requests.get(base_url, params=params, timeout=30)
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
                
                # Get categories (to filter for q-bio)
                categories = []
                for cat in entry.findall('atom:category', ns):
                    categories.append(cat.get('term', ''))
                
                # Only include q-bio papers
                if not any('q-bio' in cat for cat in categories):
                    continue
                
                # Get title
                title_elem = entry.find('atom:title', ns)
                title = title_elem.text.replace('\n', ' ').strip() if title_elem is not None else ''
                
                # Get DOI
                doi = None
                doi_elem = entry.find('arxiv:doi', ns)
                if doi_elem is not None:
                    doi = doi_elem.text
                
                paper = {
                    'id': hashlib.md5(f"{title}_{', '.join(authors)}_{year}".encode()).hexdigest()[:12],
                    'title': title,
                    'authors': authors,
                    'year': year,
                    'journal': 'arXiv (q-bio)',
                    'doi': doi,
                    'arxiv_id': entry.find('atom:id', ns).text.split('/abs/')[-1],
                    'pdf_url': pdf_url,
                    'source': 'arXiv',
                    'categories': categories,
                    'abstract': entry.find('atom:summary', ns).text.replace('\n', ' ').strip(),
                    'date_added': datetime.now().isoformat()
                }
                papers.append(paper)
            
            logger.info(f"✅ Found {len(papers)} papers from arXiv q-bio")
            return papers
            
        except Exception as e:
            logger.error(f"❌ Error querying arXiv: {e}")
            return []
    
    # ==================== BIORXIV API ====================
    
    def query_biorxiv(self, query: str, max_results: int = 15) -> List[Dict]:
        """
        Query bioRxiv API
        Source: bioRxiv
        Access: API
        Content: Preprint PDFs
        Rate Limit: 2 requests/second
        """
        logger.info(f"🔍 Querying bioRxiv for: '{query}'")
        
        self.rate_limit('biorxiv')
        
        try:
            # Get recent papers (last 30 days, 100 papers)
            url = f"https://api.biorxiv.org/details/biorxiv/2000-01-01/{datetime.now().strftime('%Y-%m-%d')}/{max_results}"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            papers = []
            if 'collection' in data:
                for item in data['collection']:
                    # Check if title or abstract matches query
                    title = item.get('title', '')
                    abstract = item.get('abstract', '')
                    
                    query_clean = query.lower().replace('"', '')
                    
                    if query_clean in title.lower() or query_clean in abstract.lower():
                        # Parse authors
                        author_string = item.get('authors', '')
                        authors = [a.strip() for a in author_string.split(';')] if author_string else []
                        
                        paper = {
                            'id': hashlib.md5(f"{title}_{author_string}_{item.get('date', '')[:4]}".encode()).hexdigest()[:12],
                            'title': title,
                            'authors': authors,
                            'year': item.get('date', '')[:4],
                            'journal': 'bioRxiv',
                            'doi': item.get('doi', ''),
                            'biorxiv_id': item.get('doi', '').split('10.1101/')[-1],
                            'pdf_url': f"https://www.biorxiv.org/content/{item.get('doi')}.full.pdf",
                            'source': 'bioRxiv',
                            'abstract': abstract,
                            'date_added': datetime.now().isoformat()
                        }
                        papers.append(paper)
            
            logger.info(f"✅ Found {len(papers)} papers from bioRxiv")
            return papers
            
        except Exception as e:
            logger.error(f"❌ Error querying bioRxiv: {e}")
            return []
    
    # ==================== GROBID PROCESSING ====================
    
    def process_with_grobid(self, pdf_path: Path) -> Optional[Dict]:
        """
        Process PDF with GROBID to extract rich metadata and references
        Saves TEI XML to data/processed/
        """
        if not self.grobid_available:
            return None
        
        logger.info(f"🔬 Processing with GROBID: {pdf_path.name}")
        
        try:
            with open(pdf_path, 'rb') as f:
                files = {'input': f}
                response = requests.post(
                    f"{self.grobid_url}/api/processFulltextDocument",
                    files=files,
                    timeout=120
                )
                
                if response.status_code == 200:
                    grobid_xml = response.text
                    
                    # Save GROBID XML to processed directory
                    xml_filename = pdf_path.stem + ".tei.xml"
                    xml_path = self.processed_dir / xml_filename
                    
                    with open(xml_path, 'w', encoding='utf-8') as f:
                        f.write(grobid_xml)
                    
                    # Parse XML to extract structured data
                    paper_data = self.parse_grobid_xml(grobid_xml)
                    paper_data['grobid_xml'] = str(xml_path)
                    
                    logger.info(f"   ✅ Extracted {paper_data.get('reference_count', 0)} references")
                    return paper_data
                else:
                    logger.warning(f"   GROBID returned status {response.status_code}")
                    return None
                    
        except requests.exceptions.ConnectionError:
            logger.error("   ❌ Cannot connect to GROBID")
            return None
        except Exception as e:
            logger.error(f"   ❌ GROBID processing failed: {e}")
            return None
    
    def parse_grobid_xml(self, xml_string: str) -> Dict:
        """
        Parse GROBID XML to extract structured metadata and references
        """
        try:
            root = ET.fromstring(xml_string)
            ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
            
            # Extract title
            title_elem = root.find('.//tei:titleStmt/tei:title', ns)
            title = title_elem.text if title_elem is not None else ""
            
            # Extract authors
            authors = []
            for author in root.findall('.//tei:sourceDesc//tei:author/tei:persName', ns):
                surname = author.find('tei:surname', ns)
                forename = author.find('tei:forename', ns)
                if surname is not None:
                    author_name = surname.text
                    if forename is not None and forename.text:
                        author_name = f"{forename.text} {author_name}"
                    authors.append(author_name)
            
            # Extract year
            date_elem = root.find('.//tei:date[@type="published"]', ns)
            year = date_elem.get('when', '')[:4] if date_elem is not None else ""
            
            # Extract references
            references = []
            for ref in root.findall('.//tei:listBibl/tei:biblStruct', ns):
                ref_data = {
                    'raw': '',
                    'title': ref.findtext('.//tei:title', '', ns),
                    'authors': [],
                    'year': None,
                    'doi': None,
                    'journal': None
                }
                
                # Get raw reference text (simplified)
                ref_text_parts = []
                for elem in ref.iter():
                    if elem.text and elem.text.strip():
                        ref_text_parts.append(elem.text.strip())
                ref_data['raw'] = ' '.join(ref_text_parts)[:200]  # Truncate
                
                # Extract authors
                for author in ref.findall('.//tei:author/tei:persName', ns):
                    surname = author.find('tei:surname', ns)
                    if surname is not None and surname.text:
                        ref_data['authors'].append(surname.text)
                
                # Extract year
                ref_date = ref.find('.//tei:date', ns)
                if ref_date is not None:
                    ref_data['year'] = ref_date.get('when', '')[:4]
                
                # Extract DOI
                idno = ref.find('.//tei:idno[@type="DOI"]', ns)
                if idno is not None and idno.text:
                    ref_data['doi'] = idno.text
                
                # Extract journal
                journal = ref.find('.//tei:monogr/tei:title', ns)
                if journal is not None and journal.text:
                    ref_data['journal'] = journal.text
                
                references.append(ref_data)
            
            return {
                'title': title,
                'authors': authors,
                'year': year,
                'references': references,
                'reference_count': len(references)
            }
            
        except Exception as e:
            logger.error(f"Error parsing GROBID XML: {e}")
            return {
                'title': '',
                'authors': [],
                'year': '',
                'references': [],
                'reference_count': 0
            }
    
    # ==================== PDF DOWNLOAD ====================
    
    def download_pdf(self, metadata: Dict[str, Any]) -> bool:
        """
        Download PDF for a paper and process with GROBID
        
        PDFs stored in: data/raw/
        GROBID XML stored in: data/processed/
        """
        if not metadata.get('pdf_url'):
            logger.debug(f"No PDF URL for {metadata.get('title', 'Unknown')[:50]}...")
            return False
        
        # Generate readable filename
        filename = self.generate_readable_filename(metadata)
        pdf_path = self.raw_dir / filename
        
        # Check if already downloaded (by checking if any file with same DOI exists)
        if metadata.get('doi'):
            for existing in self.corpus:
                if existing.get('doi') == metadata.get('doi') and existing.get('local_pdf'):
                    if Path(existing['local_pdf']).exists():
                        logger.info(f"📄 Paper already in corpus: {filename}")
                        metadata['local_pdf'] = existing['local_pdf']
                        return True
        
        # Skip if file already exists
        if pdf_path.exists():
            logger.info(f"📄 PDF already exists: {filename}")
            metadata['local_pdf'] = str(pdf_path)
            
            # If not processed with GROBID yet, process now
            if self.grobid_available and not metadata.get('grobid_processed'):
                grobid_data = self.process_with_grobid(pdf_path)
                if grobid_data:
                    metadata['grobid_processed'] = True
                    metadata['extracted_title'] = grobid_data.get('title')
                    metadata['extracted_authors'] = grobid_data.get('authors')
                    metadata['extracted_year'] = grobid_data.get('year')
                    metadata['references'] = grobid_data.get('references', [])
                    metadata['reference_count'] = grobid_data.get('reference_count', 0)
                    metadata['grobid_xml'] = grobid_data.get('grobid_xml')
            
            return True
        
        # Apply rate limiting based on source
        source = metadata.get('source', '').lower()
        if 'arxiv' in source:
            self.rate_limit('arxiv')
        elif 'pmc' in source or 'europe' in source:
            self.rate_limit('europe_pmc')
        elif 'biorxiv' in source:
            self.rate_limit('biorxiv')
        
        # Download PDF
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Academic Research Bot)'
            }
            response = requests.get(
                metadata['pdf_url'], 
                headers=headers, 
                stream=True, 
                timeout=60,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Save PDF
            with open(pdf_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logger.info(f"✅ Downloaded: {filename}")
            metadata['local_pdf'] = str(pdf_path)
            metadata['file_size'] = pdf_path.stat().st_size
            
            # Process with GROBID
            if self.grobid_available:
                grobid_data = self.process_with_grobid(pdf_path)
                if grobid_data:
                    metadata['grobid_processed'] = True
                    metadata['extracted_title'] = grobid_data.get('title')
                    metadata['extracted_authors'] = grobid_data.get('authors')
                    metadata['extracted_year'] = grobid_data.get('year')
                    metadata['references'] = grobid_data.get('references', [])
                    metadata['reference_count'] = grobid_data.get('reference_count', 0)
                    metadata['grobid_xml'] = grobid_data.get('grobid_xml')
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to download PDF: {e}")
            # Remove partial download if it exists
            if pdf_path.exists():
                pdf_path.unlink()
            return False
    
    # ==================== MAIN BUILD FUNCTION ====================
    
    def build_corpus(self, search_terms: List[str], target_count: int = 30):
        """
        Main function: Query web APIs with search terms and build corpus
        
        Args:
            search_terms: List of search queries
            target_count: Target number of papers to collect
        """
        logger.info("="*70)
        logger.info(f"🎯 Starting corpus build - Target: {target_count} papers")
        logger.info(f"🔎 Search terms: {search_terms}")
        logger.info("="*70)
        
        papers_found = []
        
        for term in search_terms:
            if len(self.corpus) + len(papers_found) >= target_count:
                break
            
            logger.info(f"\n{'='*60}")
            logger.info(f"SEARCHING FOR: '{term}'")
            logger.info(f"{'='*60}")
            
            # Try Europe PMC
            logger.info("\n📡 Source: Europe PMC")
            pmc_papers = self.query_europe_pmc(term, max_results=10)
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
            logger.info("\n📡 Source: arXiv (q-bio)")
            arxiv_papers = self.query_arxiv(term, max_results=10)
            for paper in arxiv_papers:
                if len(self.corpus) + len(papers_found) >= target_count:
                    break
                if not self.is_duplicate(paper.get('doi'), paper.get('title')):
                    papers_found.append(paper)
                    if paper.get('title'):
                        self.seen_titles.add(paper['title'].lower())
            
            # Try bioRxiv
            logger.info("\n📡 Source: bioRxiv")
            biorxiv_papers = self.query_biorxiv(term, max_results=10)
            for paper in biorxiv_papers:
                if len(self.corpus) + len(papers_found) >= target_count:
                    break
                if not self.is_duplicate(paper.get('doi'), paper.get('title')):
                    papers_found.append(paper)
                    if paper.get('doi'):
                        self.seen_dois.add(paper['doi'])
                    if paper.get('title'):
                        self.seen_titles.add(paper['title'].lower())
        
        # Add to corpus
        logger.info(f"\n{'='*60}")
        logger.info(f"Found {len(papers_found)} new papers")
        logger.info(f"{'='*60}")
        
        added_count = 0
        for paper in papers_found[:target_count - len(self.corpus)]:
            added_count += 1
            logger.info(f"\n📄 Processing paper {added_count}/{len(papers_found[:target_count - len(self.corpus)])}")
            
            # Try to download PDF and process with GROBID
            self.download_pdf(paper)
            
            # Add to corpus
            self.corpus.append(paper)
            logger.info(f"➕ Added to corpus: {paper.get('title', '')[:80]}...")
        
        # Save final corpus
        self.save_corpus()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print summary of downloaded papers"""
        print("\n" + "="*70)
        print("✅ CORPUS BUILD COMPLETE")
        print("="*70)
        print(f"Total papers in corpus: {len(self.corpus)}")
        
        # Count by source
        sources = {}
        for paper in self.corpus:
            src = paper.get('source', 'Unknown')
            sources[src] = sources.get(src, 0) + 1
        
        print("\n📊 Papers by source:")
        for src, count in sources.items():
            print(f"  • {src}: {count}")
        
        # Count successful downloads
        downloaded = sum(1 for p in self.corpus if 'local_pdf' in p)
        print(f"\n📄 PDFs successfully downloaded: {downloaded}")
        print(f"   Location: {self.raw_dir}")
        
        # Count GROBID processed
        grobid_processed = sum(1 for p in self.corpus if p.get('grobid_processed'))
        print(f"🔬 Papers processed with GROBID: {grobid_processed}")
        print(f"   Location: {self.processed_dir}")
        
        # Total references extracted
        total_refs = sum(p.get('reference_count', 0) for p in self.corpus)
        print(f"📚 Total references extracted: {total_refs}")
        
        # File sizes
        total_size_mb = sum(p.get('file_size', 0) for p in self.corpus) / (1024 * 1024)
        print(f"💾 Total PDF size: {total_size_mb:.2f} MB")
        
        # Show sample
        if self.corpus:
            print("\n📝 Sample paper (first in corpus):")
            sample = self.corpus[0]
            print(f"  Title: {sample.get('title', 'N/A')[:100]}...")
            print(f"  Authors: {', '.join(sample.get('authors', [])[:3])}")
            print(f"  Year: {sample.get('year', 'N/A')}")
            print(f"  Source: {sample.get('source', 'N/A')}")
            print(f"  References: {sample.get('reference_count', 0)}")
            if 'local_pdf' in sample:
                print(f"  PDF: {Path(sample['local_pdf']).name}")
        
        print(f"\n💾 Corpus metadata saved to: {self.corpus_file}")
        print(f"📁 PDFs saved to: {self.raw_dir}")
        print(f"📁 GROBID XML saved to: {self.processed_dir}")


def main():
    parser = argparse.ArgumentParser(description='Build human evolution paper corpus with GROBID reference extraction')
    parser.add_argument('--output-dir', type=str, default='./data',
                       help='Output directory for data (default: ./data)')
    parser.add_argument('--count', type=int, default=30,
                       help='Number of papers to collect (default: 30)')
    parser.add_argument('--grobid-url', type=str, default='http://localhost:8070',
                       help='GROBID API URL (default: http://localhost:8070)')
    parser.add_argument('--no-grobid', action='store_true',
                       help='Skip GROBID processing even if available')
    
    args = parser.parse_args()
    
    # Define search terms - THESE ARE ACTUALLY QUERIED
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
        '"lucy" australopithecus',
        '"hominin fossil"',
        '"homo erectus"'
    ]
    
    # Build corpus
    builder = EnhancedCorpusBuilder(
        output_dir=args.output_dir, 
        grobid_url=args.grobid_url
    )
    
    # Override GROBID availability if --no-grobid flag is set
    if args.no_grobid:
        builder.grobid_available = False
        logger.info("🚫 GROBID processing disabled by --no-grobid flag")
    
    builder.build_corpus(search_terms, target_count=args.count)


if __name__ == "__main__":
    main()
