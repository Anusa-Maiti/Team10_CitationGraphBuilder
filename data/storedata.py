#!/usr/bin/env python3
"""
Script to create a CSV file with metadata from corpus.json
"""

import json
import csv
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def create_papers_csv(corpus_path: str, output_path: str = None):
    """
    Create a CSV file with paper metadata from corpus.json
    
    Args:
        corpus_path: Path to corpus.json file
        output_path: Path for output CSV (optional)
    """
    corpus_path = Path(corpus_path)
    
    # Check if file exists
    if not corpus_path.exists():
        print(f"❌ Error: {corpus_path} not found!")
        return
    
    # Load corpus
    with open(corpus_path, 'r', encoding='utf-8') as f:
        corpus = json.load(f)
    
    print(f"✅ Loaded {len(corpus)} papers from {corpus_path}")
    
    # Generate output filename if not provided
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = corpus_path.parent / f"papers_metadata_{timestamp}.csv"
    else:
        output_path = Path(output_path)
    
    # Define CSV columns (based on metadata in corpus.json)
    columns = [
        'paper_id',
        'title',
        'authors',
        'year',
        'journal',
        'source',
        'doi',
        'pmcid',
        'pmid',
        'arxiv_id',
        'biorxiv_id',
        'url',
        'has_pdf',
        'pdf_url',
        'reference_count',
        'grobid_processed',
        'file_size_mb',
        'local_pdf_path',
        'grobid_xml_path',
        'date_added'
    ]
    
    # Prepare data for CSV
    rows = []
    for paper in corpus:
        # Format authors list as semicolon-separated string
        authors = paper.get('authors', [])
        if isinstance(authors, list):
            authors_str = '; '.join(authors)
        else:
            authors_str = str(authors) if authors else ''
        
        # Get URL (prioritize DOI URL)
        doi = paper.get('doi', '')
        url = f"https://doi.org/{doi}" if doi else paper.get('pdf_url', '')
        
        # Check if PDF exists
        local_pdf = paper.get('local_pdf', '')
        has_pdf = Path(local_pdf).exists() if local_pdf else False
        
        row = {
            'paper_id': paper.get('id', ''),
            'title': paper.get('title', ''),
            'authors': authors_str,
            'year': paper.get('year', ''),
            'journal': paper.get('journal', ''),
            'source': paper.get('source', ''),
            'doi': doi,
            'pmcid': paper.get('pmcid', ''),
            'pmid': paper.get('pmid', ''),
            'arxiv_id': paper.get('arxiv_id', ''),
            'biorxiv_id': paper.get('biorxiv_id', ''),
            'url': url,
            'has_pdf': has_pdf,
            'pdf_url': paper.get('pdf_url', ''),
            'reference_count': paper.get('reference_count', 0),
            'grobid_processed': paper.get('grobid_processed', False),
            'file_size_mb': round(paper.get('file_size', 0) / (1024 * 1024), 2) if paper.get('file_size') else 0,
            'local_pdf_path': local_pdf,
            'grobid_xml_path': paper.get('grobid_xml', ''),
            'date_added': paper.get('date_added', '')
        }
        rows.append(row)
    
    # Write to CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"✅ Created CSV file: {output_path}")
    print(f"   Columns: {', '.join(columns)}")
    print(f"   Total papers: {len(rows)}")
    
    # Print summary statistics
    print("\n📊 Summary Statistics:")
    
    # Count by source
    sources = {}
    for paper in corpus:
        src = paper.get('source', 'Unknown')
        sources[src] = sources.get(src, 0) + 1
    
    print("  Papers by source:")
    for src, count in sources.items():
        print(f"    • {src}: {count}")
    
    # Count GROBID processed
    grobid_count = sum(1 for p in corpus if p.get('grobid_processed'))
    print(f"  Papers with GROBID processing: {grobid_count}")
    
    # Total references
    total_refs = sum(p.get('reference_count', 0) for p in corpus)
    print(f"  Total references extracted: {total_refs}")
    
    # PDF download stats
    pdf_count = sum(1 for p in corpus if p.get('local_pdf') and Path(p.get('local_pdf', '')).exists())
    print(f"  PDFs downloaded: {pdf_count}")
    
    return output_path


def create_references_csv(corpus_path: str, output_path: str = None):
    """
    Create a separate CSV file with all references from all papers
    """
    corpus_path = Path(corpus_path)
    
    if not corpus_path.exists():
        print(f"❌ Error: {corpus_path} not found!")
        return
    
    with open(corpus_path, 'r', encoding='utf-8') as f:
        corpus = json.load(f)
    
    # Generate output filename
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = corpus_path.parent / f"all_references_{timestamp}.csv"
    else:
        output_path = Path(output_path)
    
    # Define columns for references CSV
    ref_columns = [
        'citing_paper_id',
        'citing_title',
        'citing_year',
        'citing_source',
        'ref_raw',
        'ref_title',
        'ref_authors',
        'ref_year',
        'ref_journal',
        'ref_doi'
    ]
    
    ref_rows = []
    
    for paper in corpus:
        citing_id = paper.get('id', '')
        citing_title = paper.get('title', '')
        citing_year = paper.get('year', '')
        citing_source = paper.get('source', '')
        
        references = paper.get('references', [])
        for ref in references:
            # Format reference authors
            ref_authors = ref.get('authors', [])
            if isinstance(ref_authors, list):
                ref_authors_str = '; '.join(ref_authors)
            else:
                ref_authors_str = str(ref_authors) if ref_authors else ''
            
            row = {
                'citing_paper_id': citing_id,
                'citing_title': citing_title,
                'citing_year': citing_year,
                'citing_source': citing_source,
                'ref_raw': ref.get('raw', ''),
                'ref_title': ref.get('title', ''),
                'ref_authors': ref_authors_str,
                'ref_year': ref.get('year', ''),
                'ref_journal': ref.get('journal', ''),
                'ref_doi': ref.get('doi', '')
            }
            ref_rows.append(row)
    
    # Write references CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=ref_columns)
        writer.writeheader()
        writer.writerows(ref_rows)
    
    print(f"\n✅ Created references CSV: {output_path}")
    print(f"   Total reference entries: {len(ref_rows)}")
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Create CSV files from corpus.json metadata')
    parser.add_argument('--corpus', type=str, default='data/metadata/corpus.json',
                       help='Path to corpus.json file (default: data/metadata/corpus.json)')
    parser.add_argument('--output', type=str, help='Output CSV file path (optional)')
    parser.add_argument('--references', action='store_true', 
                       help='Also create a separate CSV with all references')
    
    args = parser.parse_args()
    
    print("="*60)
    print("📊 CORPUS TO CSV CONVERTER")
    print("="*60)
    
    # Create main papers CSV
    papers_csv = create_papers_csv(args.corpus, args.output)
    
    # Create references CSV if requested
    if args.references:
        create_references_csv(args.corpus)
    
    print("\n" + "="*60)
    print("✅ Done!")


if __name__ == "__main__":
    main()
