import pandas as pd
import networkx as nx
import os
import glob

def build_and_analyze():
    folder = os.path.dirname(os.path.abspath(__file__))
    
    meta_files = glob.glob(os.path.join(folder, "papers_metadata*.csv"))
    
    if not meta_files:
        print("Error: No metadata csv found. check the folder.")
        return
        
    # Get the most recent one if there are multiple
    meta_file = max(meta_files, key=os.path.getctime)
    ref_file = os.path.join(folder, 'all_references.csv')
    
    print(f"using file: {os.path.basename(meta_file)}")
    
    # standard loading
    p_df = pd.read_csv(meta_file)
    r_df = pd.read_csv(ref_file)
    
    G = nx.DiGraph()
    
    # find the paper_id column
    id_col = [c for c in p_df.columns if 'id' in c.lower()][0]
    
    for i, row in p_df.iterrows():
        G.add_node(row[id_col], title=row.get('title', 'na'), year=row.get('year', 0))
        
    for i, row in r_df.iterrows():
        G.add_edge(row['source_id'], row['target_id'])
        
    # add citation counts for the dashboard
    nx.set_node_attributes(G, dict(G.in_degree()), 'citations_count')
    nx.set_node_attributes(G, dict(G.out_degree()), 'cites_count')
    
    print("\n--- RESULTS ---")
    print(f"Nodes: {G.number_of_nodes()}")
    print(f"Edges: {G.number_of_edges()}")
    print(f"Density: {nx.density(G):.4f}")
    
    print("\nwriting output files...")
    
    nodes_out = pd.DataFrame.from_dict(dict(G.nodes(data=True)), orient='index')
    nodes_out.index.name = 'paper_id'
    nodes_out.reset_index(inplace=True)
    nodes_out.to_csv(os.path.join(folder, 'nodes_list.csv'), index=False)
    
    nx.to_pandas_edgelist(G).to_csv(os.path.join(folder, 'edges_list.csv'), index=False)
    nx.write_gexf(G, os.path.join(folder, 'network_map.gexf'))
    
    print("Done")

if __name__ == "__main__":
    build_and_analyze()