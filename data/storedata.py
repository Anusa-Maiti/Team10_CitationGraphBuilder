#!/usr/bin/env python3
"""
Script to create CSV files from corpus.json metadata
Stores files as:
- data/metadata/papers_metadata.csv
- data/metadata/all_references.csv
"""

import json
import csv
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def create_papers_csv(corpus_path: str):
    """
    Create papers_metadata.csv with paper metadata from corpus.json
    
    Args:
        corpus_path: Path to corpus.json file
    """
    corpus_path = Path(corpus_path)
    
    # Check if file exists
    if not corpus_path.exists():
        print(f"❌ Error: {corpus_path} not found!")
        return None
    
    # Load corpus
    with open(corpus_path, 'r', encoding='utf-8') as f:
        corpus = json.load(f)
    
    print(f"✅ Loaded {len(corpus)} papers from {corpus_path}")
    
    # Set output path to same directory as corpus.json
    output_path = corpus_path.parent / "papers_metadata.csv"
    
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
    
    print(f"✅ Created papers CSV: {output_path}")
    print(f"   Columns: {', '.join(columns)}")
    print(f"   Total papers: {len(rows)}")
    
    return output_path


def create_references_csv(corpus_path: str):
    """
    Create all_references.csv with all references from all papers
    """
    corpus_path = Path(corpus_path)
    
    if not corpus_path.exists():
        print(f"❌ Error: {corpus_path} not found!")
        return None
    
    with open(corpus_path, 'r', encoding='utf-8') as f:
        corpus = json.load(f)
    
    # Set output path to same directory as corpus.json
    output_path = corpus_path.parent / "all_references.csv"
    
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
    total_refs = 0
    
    for paper in corpus:
        citing_id = paper.get('id', '')
        citing_title = paper.get('title', '')
        citing_year = paper.get('year', '')
        citing_source = paper.get('source', '')
        
        references = paper.get('references', [])
        total_refs += len(references)
        
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
    
    print(f"✅ Created references CSV: {output_path}")
    print(f"   Total reference entries: {len(ref_rows)}")
    print(f"   Average references per paper: {total_refs/len(corpus):.1f}" if corpus else "   No papers")
    
    return output_path


def print_summary(corpus_path: Path, papers_csv: Path, refs_csv: Path = None):
    """Print summary of all files"""
    print("\n" + "="*60)
    print("📊 SUMMARY")
    print("="*60)
    
    # Load corpus for stats
    with open(corpus_path, 'r', encoding='utf-8') as f:
        corpus = json.load(f)
    
    print(f"\n📁 Input file: {corpus_path}")
    print(f"   Total papers: {len(corpus)}")
    
    print(f"\n📁 Output files:")
    print(f"   • {papers_csv.name} - Paper metadata")
    print(f"   • {refs_csv.name} - All references") if refs_csv else None
    
    print(f"\n📊 Statistics:")
    
    # Count by source
    sources = {}
    for paper in corpus:
        src = paper.get('source', 'Unknown')
        sources[src] = sources.get(src, 0) + 1
    
    print("   Papers by source:")
    for src, count in sources.items():
        print(f"     • {src}: {count}")
    
    # GROBID stats
    grobid_count = sum(1 for p in corpus if p.get('grobid_processed'))
    print(f"   Papers with GROBID: {grobid_count} ({grobid_count/len(corpus)*100:.1f}%)")
    
    # References
    total_refs = sum(p.get('reference_count', 0) for p in corpus)
    print(f"   Total references: {total_refs}")
    
    # PDFs
    pdf_count = sum(1 for p in corpus if p.get('local_pdf') and Path(p.get('local_pdf', '')).exists())
    print(f"   PDFs downloaded: {pdf_count}")
    
    print(f"\n✅ All files saved in: {corpus_path.parent}")


def main():
    parser = argparse.ArgumentParser(description='Create CSV files from corpus.json metadata')
    parser.add_argument('--corpus', type=str, default='data/metadata/corpus.json',
                       help='Path to corpus.json file (default: data/metadata/corpus.json)')
    parser.add_argument('--no-references', action='store_true',
                       help='Skip creating references CSV')
    
    args = parser.parse_args()
    
    print("="*60)
    print("📊 CORPUS TO CSV CONVERTER")
    print("="*60)
    
    corpus_path = Path(args.corpus)
    
    # Check if corpus exists
    if not corpus_path.exists():
        print(f"\n❌ Error: {corpus_path} not found!")
        print("\nLooking in current directory:")
        print(f"   Current directory: {Path.cwd()}")
        print(f"   Files in current directory:")
        for f in Path.cwd().glob("*"):
            print(f"     {f}")
        return
    
    # Create papers CSV (always)
    papers_csv = create_papers_csv(args.corpus)
    
    # Create references CSV unless skipped
    refs_csv = None
    if not args.no_references:
        refs_csv = create_references_csv(args.corpus)
    
    # Print summary
    if papers_csv:
        print_summary(corpus_path, papers_csv, refs_csv)
    
    print("\n" + "="*60)
    print("✅ Done!")


if __name__ == "__main__":
    main()
