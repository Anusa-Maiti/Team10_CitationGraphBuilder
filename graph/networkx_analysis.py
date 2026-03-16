import pandas as pd
import networkx as nx
import os
import glob

def build_and_analyze():
    # this script is now in graph/
    graph_folder = os.path.dirname(os.path.abspath(__file__))
    root_folder = os.path.dirname(graph_folder)
    meta_folder = os.path.join(root_folder, 'data', 'metadata')
    
    meta_files = glob.glob(os.path.join(meta_folder, "papers_metadata*.csv"))
    if not meta_files:
        print("Error: No metadata csv found.")
        return
        
    meta_file = max(meta_files, key=os.path.getctime)
    ref_file = os.path.join(meta_folder, 'all_references.csv')
    
    p_df = pd.read_csv(meta_file)
    r_df = pd.read_csv(ref_file)
    
    G = nx.DiGraph()
    id_col = [c for c in p_df.columns if 'id' in c.lower()][0]
    
    for i, row in p_df.iterrows():
        G.add_node(row[id_col], title=row.get('title', 'na'), year=row.get('year', 0))
        
    for i, row in r_df.iterrows():
        G.add_edge(row['source_id'], row['target_id'])
        
    nx.set_node_attributes(G, dict(G.in_degree()), 'citations_count')
    nx.set_node_attributes(G, dict(G.out_degree()), 'cites_count')
    
    print("\n--- RESULTS ---")
    print(f"Nodes: {G.number_of_nodes()}")
    print(f"Edges: {G.number_of_edges()}")
    print(f"Density: {nx.density(G):.4f}")
    
    print("\nwriting output files to graph folder...")
    nodes_out = pd.DataFrame.from_dict(dict(G.nodes(data=True)), orient='index')
    nodes_out.index.name = 'paper_id'
    nodes_out.reset_index(inplace=True)
    nodes_out.to_csv(os.path.join(graph_folder, 'nodes_list.csv'), index=False)
    
    nx.to_pandas_edgelist(G).to_csv(os.path.join(graph_folder, 'edges_list.csv'), index=False)
    nx.write_gexf(G, os.path.join(graph_folder, 'network_map.gexf'))
    
    print("Done.")

if __name__ == "__main__":
    build_and_analyze()