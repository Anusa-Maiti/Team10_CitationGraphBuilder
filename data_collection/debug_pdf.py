"""
debug_pdf.py
------------
Diagnostic tool — run this first to see exactly what text your PDFs
contain near the end, so we can tune the reference-section detector.

Usage:
    python debug_pdf.py                        # inspect all PDFs in data/raw/
    python debug_pdf.py --pdf data/raw/foo.pdf # inspect one specific PDF
    python debug_pdf.py --tail 200             # show last N lines (default 100)
    python debug_pdf.py --search "References"  # search for a string
"""

import sys
import re
import argparse
from pathlib import Path

def get_text(pdf_path):
    try:
        import fitz
    except ImportError:
        print("Run: pip install pymupdf"); sys.exit(1)
    doc = fitz.open(str(pdf_path))
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return pages

def inspect(pdf_path, tail_lines=100, search=None):
    print(f"\n{'='*70}")
    print(f"PDF: {pdf_path}")
    print(f"{'='*70}")
    pages = get_text(pdf_path)
    full  = "\n".join(pages)
    lines = full.split("\n")

    print(f"Total pages : {len(pages)}")
    print(f"Total chars : {len(full)}")
    print(f"Total lines : {len(lines)}")

    # Show every line that could be a section header (short, possibly bold)
    print(f"\n── Lines that look like section headers (len < 40) ──")
    for i, line in enumerate(lines):
        s = line.strip()
        if 2 < len(s) < 40 and not s[0].isdigit():
            print(f"  [{i:>5}] {repr(s)}")

    # Show last N lines
    print(f"\n── Last {tail_lines} lines of document ──")
    for i, line in enumerate(lines[-tail_lines:]):
        print(f"  {len(lines)-tail_lines+i:>5}: {repr(line)}")

    # Search for a specific string
    if search:
        print(f"\n── Occurrences of {repr(search)} ──")
        for i, line in enumerate(lines):
            if search.lower() in line.lower():
                start = max(0, i-2)
                end   = min(len(lines), i+3)
                print(f"\n  Line {i}:")
                for j in range(start, end):
                    marker = ">>>" if j == i else "   "
                    print(f"  {marker} [{j}] {repr(lines[j])}")

    # Show last page separately
    if pages:
        print(f"\n── Last page text (raw) ──")
        print(pages[-1][:3000])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf",    default=None)
    parser.add_argument("--tail",   type=int, default=100)
    parser.add_argument("--search", default="References")
    args = parser.parse_args()

    if args.pdf:
        pdfs = [Path(args.pdf)]
    else:
        pdfs = list(Path("data/raw").glob("*.pdf"))
        if not pdfs:
            print("No PDFs found in data/raw/")
            sys.exit(1)
        pdfs = pdfs[:3]  # inspect first 3 by default
        print(f"Inspecting first {len(pdfs)} PDFs. Use --pdf to target one.")

    for pdf in pdfs:
        inspect(pdf, tail_lines=args.tail, search=args.search)

if __name__ == "__main__":
    main()
