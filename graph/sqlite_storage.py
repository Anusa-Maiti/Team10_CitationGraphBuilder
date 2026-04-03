import sqlite3
import pandas as pd
import os
import glob

def build_db():
    # this script is now in graph/
    graph_folder = os.path.dirname(os.path.abspath(__file__))
    
    # go up one level, then into data/metadata to find inputs
    root_folder = os.path.dirname(graph_folder)
    meta_folder = os.path.join(root_folder, 'data', 'metadata')
    
    p_refs = os.path.join(meta_folder, 'all_references.csv')
    db_out = os.path.join(graph_folder, 'citation_graph.db') # save db in graph/

    meta_files = glob.glob(os.path.join(meta_folder, 'papers_metadata*.csv'))
    if not meta_files:
        print("CSV files not found in data/metadata.")
        return
        
    p_meta = max(meta_files, key=os.path.getctime)

    print("Starting DB build...")
    db_conn = sqlite3.connect(db_out)
    
    df_papers = pd.read_csv(p_meta)
    df_refs = pd.read_csv(p_refs)
    
    id_name = [c for c in df_papers.columns if 'id' in c.lower()][0]
    
    df_papers.to_sql('Papers', db_conn, if_exists='replace', index=False)
    df_refs.to_sql('Citations', db_conn, if_exists='replace', index=False)
    
    cur = db_conn.cursor()
    cur.execute(f"CREATE INDEX idx_p ON Papers({id_name})")
    cur.execute("CREATE INDEX idx_s ON Citations(source_id)")
    cur.execute("CREATE INDEX idx_t ON Citations(target_id)")
    
    db_conn.close()
    print("Database built successfully in graph folder.")

if __name__ == "__main__":
    build_db()