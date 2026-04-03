"""
analysis/statistics.py
======================
Compute and export graph statistics for the citation graph.

Outputs reports/statistics.json with:
  - Basic counts (nodes, edges, density)
  - Degree distribution (in-degree, out-degree)
  - Connected components
  - Top-N most cited / most citing papers
  - PageRank, betweenness centrality
  - Placeholder node summary

Usage
-----
    # Default: reads graph/citation_graph.db, writes reports/statistics.json
    python analysis/statistics.py

    # Custom paths
    python analysis/statistics.py --input graph/citation_graph.db --output reports/

    # Also read from CSV files instead of SQLite
    python analysis/statistics.py --nodes graph/nodes_list.csv --edges graph/edges_list.csv

    # Adjust top-N results (default 20)
    python analysis/statistics.py --top-n 10
"""

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

try:
    import networkx as nx
except ImportError:
    sys.exit("networkx is required: pip install networkx")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_from_sqlite(db_path: str):
    """Load nodes and edges from the SQLite citation graph database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    nodes = {}
    for row in conn.execute("SELECT * FROM papers"):
        d = dict(row)
        nodes[d["paper_id"]] = d

    edges = []
    for row in conn.execute("SELECT * FROM citations"):
        edges.append((row["citing_paper_id"], row["cited_paper_id"]))

    conn.close()
    return nodes, edges


def load_from_csv(nodes_csv: str, edges_csv: str):
    """Load nodes and edges from CSV files (nodes_list.csv / edges_list.csv)."""
    nodes = {}
    with open(nodes_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pid = row.get("paper_id") or row.get("id") or row.get("node_id")
            if pid:
                nodes[pid] = row

    edges = []
    with open(edges_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            src = row.get("citing_paper_id") or row.get("source") or row.get("from")
            dst = row.get("cited_paper_id") or row.get("target") or row.get("to")
            if src and dst:
                edges.append((src, dst))

    return nodes, edges


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(nodes: dict, edges: list) -> nx.DiGraph:
    G = nx.DiGraph()
    for pid, attrs in nodes.items():
        G.add_node(pid, **{k: v for k, v in attrs.items() if v is not None})
    for src, dst in edges:
        if src in G and dst in G:
            G.add_edge(src, dst)
    return G


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def degree_distribution(G: nx.DiGraph) -> dict:
    in_degrees = [d for _, d in G.in_degree()]
    out_degrees = [d for _, d in G.out_degree()]
    in_counts = Counter(in_degrees)
    out_counts = Counter(out_degrees)
    return {
        "in_degree": {
            "distribution": {str(k): v for k, v in sorted(in_counts.items())},
            "max": max(in_degrees) if in_degrees else 0,
            "mean": round(sum(in_degrees) / len(in_degrees), 4) if in_degrees else 0,
            "median": sorted(in_degrees)[len(in_degrees) // 2] if in_degrees else 0,
        },
        "out_degree": {
            "distribution": {str(k): v for k, v in sorted(out_counts.items())},
            "max": max(out_degrees) if out_degrees else 0,
            "mean": round(sum(out_degrees) / len(out_degrees), 4) if out_degrees else 0,
            "median": sorted(out_degrees)[len(out_degrees) // 2] if out_degrees else 0,
        },
    }


def component_stats(G: nx.DiGraph) -> dict:
    undirected = G.to_undirected()
    components = list(nx.connected_components(undirected))
    sizes = sorted([len(c) for c in components], reverse=True)
    weakly = list(nx.weakly_connected_components(G))
    strongly = list(nx.strongly_connected_components(G))
    return {
        "weakly_connected_components": {
            "count": len(weakly),
            "largest_size": max(len(c) for c in weakly) if weakly else 0,
            "sizes": sorted([len(c) for c in weakly], reverse=True)[:10],
        },
        "strongly_connected_components": {
            "count": len(strongly),
            "largest_size": max(len(c) for c in strongly) if strongly else 0,
        },
        "undirected_components": {
            "count": len(components),
            "size_distribution": sizes[:10],
        },
    }


def top_papers(G: nx.DiGraph, nodes: dict, top_n: int = 20) -> dict:
    def label(pid):
        n = nodes.get(pid, {})
        title = n.get("title", pid)
        year = n.get("year", "")
        return f"{title[:60]}{'...' if len(title or '') > 60 else ''} ({year})"

    in_deg = sorted(G.in_degree(), key=lambda x: x[1], reverse=True)
    out_deg = sorted(G.out_degree(), key=lambda x: x[1], reverse=True)

    return {
        "most_cited": [
            {"paper_id": pid, "in_degree": d, "label": label(pid)}
            for pid, d in in_deg[:top_n]
        ],
        "most_citing": [
            {"paper_id": pid, "out_degree": d, "label": label(pid)}
            for pid, d in out_deg[:top_n]
        ],
    }


def centrality_stats(G: nx.DiGraph, top_n: int = 20) -> dict:
    print("  Computing PageRank...", flush=True)
    pagerank = nx.pagerank(G, alpha=0.85, max_iter=200)
    top_pr = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:top_n]

    # Betweenness is expensive on large graphs — use a sample if > 5000 nodes
    print("  Computing betweenness centrality...", flush=True)
    if G.number_of_nodes() > 5000:
        sample = list(G.nodes())[:2000]
        bc = nx.betweenness_centrality_subset(G, sources=sample, targets=sample, normalized=True)
        bc_note = "approximated on 2000-node sample (graph > 5000 nodes)"
    else:
        bc = nx.betweenness_centrality(G, normalized=True)
        bc_note = "exact"
    top_bc = sorted(bc.items(), key=lambda x: x[1], reverse=True)[:top_n]

    return {
        "pagerank": {
            "top": [{"paper_id": pid, "score": round(s, 6)} for pid, s in top_pr],
        },
        "betweenness": {
            "note": bc_note,
            "top": [{"paper_id": pid, "score": round(s, 6)} for pid, s in top_bc],
        },
    }


def placeholder_summary(nodes: dict) -> dict:
    placeholders = [
        pid for pid, attrs in nodes.items()
        if str(attrs.get("is_placeholder", "")).lower() in ("1", "true", "yes")
    ]
    real = len(nodes) - len(placeholders)
    return {
        "total_nodes": len(nodes),
        "real_papers": real,
        "placeholder_nodes": len(placeholders),
        "placeholder_fraction": round(len(placeholders) / len(nodes), 4) if nodes else 0,
    }


def resolution_method_summary(edges_csv: str | None = None, all_refs_csv: str | None = None) -> dict:
    """Count resolution_method values from all_references.csv or edges_list.csv."""
    counter: Counter = Counter()
    target = all_refs_csv or edges_csv
    if not target or not os.path.exists(target):
        return {}
    with open(target, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            method = row.get("resolution_method", "unknown") or "unknown"
            counter[method] += 1
    return dict(counter)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def compute_statistics(
    nodes: dict,
    edges: list,
    top_n: int = 20,
    refs_csv: str | None = None,
) -> dict:
    print(f"Building graph ({len(nodes)} nodes, {len(edges)} edges)...", flush=True)
    G = build_graph(nodes, edges)

    stats: dict = {}

    # Basic counts
    stats["summary"] = {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": round(nx.density(G), 6),
        "is_dag": nx.is_directed_acyclic_graph(G),
        "average_clustering": round(nx.average_clustering(G.to_undirected()), 4),
    }

    print("Computing degree distribution...", flush=True)
    stats["degree_distribution"] = degree_distribution(G)

    print("Computing connected components...", flush=True)
    stats["components"] = component_stats(G)

    print(f"Finding top-{top_n} papers...", flush=True)
    stats["top_papers"] = top_papers(G, nodes, top_n)

    print("Computing centrality measures...", flush=True)
    stats["centrality"] = centrality_stats(G, top_n)

    stats["placeholders"] = placeholder_summary(nodes)

    if refs_csv:
        print("Summarising resolution methods...", flush=True)
        stats["resolution_methods"] = resolution_method_summary(all_refs_csv=refs_csv)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Compute citation graph statistics and write reports/statistics.json"
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input", default="graph/citation_graph.db",
                        help="SQLite DB path (default: graph/citation_graph.db)")
    parser.add_argument("--nodes", help="nodes_list.csv path (use instead of --input)")
    parser.add_argument("--edges", help="edges_list.csv path (use instead of --input)")
    parser.add_argument("--refs-csv",
                        default="data/metadata/all_references.csv",
                        help="all_references.csv path for resolution method summary")
    parser.add_argument("--output", default="reports/",
                        help="Output directory (default: reports/)")
    parser.add_argument("--top-n", type=int, default=20,
                        help="Number of top papers to include (default: 20)")
    args = parser.parse_args()

    # Load data
    if args.nodes and args.edges:
        print(f"Loading from CSV: {args.nodes}, {args.edges}")
        nodes, edges = load_from_csv(args.nodes, args.edges)
    elif os.path.exists(args.input):
        print(f"Loading from SQLite: {args.input}")
        nodes, edges = load_from_sqlite(args.input)
    else:
        sys.exit(
            f"Could not find data source.\n"
            f"  Tried SQLite: {args.input}\n"
            f"  Pass --nodes / --edges to use CSV files instead."
        )

    if not nodes:
        sys.exit("No nodes found — is the pipeline complete? Run storedata.py first.")

    refs_csv = args.refs_csv if os.path.exists(args.refs_csv) else None

    t0 = time.time()
    stats = compute_statistics(nodes, edges, top_n=args.top_n, refs_csv=refs_csv)
    elapsed = round(time.time() - t0, 2)
    stats["_meta"] = {"computed_in_seconds": elapsed, "top_n": args.top_n}

    # Write output
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "statistics.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\nDone in {elapsed}s. Statistics written to: {out_path}")
    print(f"  Nodes : {stats['summary']['nodes']}")
    print(f"  Edges : {stats['summary']['edges']}")
    print(f"  Density : {stats['summary']['density']}")
    print(f"  Is DAG : {stats['summary']['is_dag']}")
    wcc = stats["components"]["weakly_connected_components"]
    print(f"  Weakly connected components : {wcc['count']} (largest: {wcc['largest_size']})")
    ph = stats["placeholders"]
    print(f"  Placeholder nodes : {ph['placeholder_nodes']} / {ph['total_nodes']} "
          f"({ph['placeholder_fraction']*100:.1f}%)")


if __name__ == "__main__":
    main()
