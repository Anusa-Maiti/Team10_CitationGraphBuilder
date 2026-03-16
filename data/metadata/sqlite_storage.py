import sqlite3
import pandas as pd
import os

def build_db():
    current_folder = os.path.dirname(os.path.abspath(__file__))
    metadata_csv = os.path.join(current_folder, 'papers_metadata_20260316_204145.csv')
    references_csv = os.path.join(current_folder, 'all_references.csv')
    db_path = os.path.join(current_folder, 'citation_graph.db')

    if not os.path.exists(metadata_csv):
        print(f"Error: Missing {metadata_csv}")
        return

    print("Building SQLite Database...")
    conn = sqlite3.connect(db_path)
    
    # Load Data
    papers_df = pd.read_csv(metadata_csv)
    refs_df = pd.read_csv(references_csv)
    
    # --- AUTO-DETECT ID COLUMN ---
    # Look for common ID names in her CSV columns
    possible_ids = ['id', 'paper_id', 'id_paper', 'ID']
    id_col = next((col for col in papers_df.columns if col in possible_ids), papers_df.columns[0])
    print(f"Using '{id_col}' as the unique identifier.")

    # Save to SQL
    papers_df.to_sql('Papers', conn, if_exists='replace', index=False)
    refs_df.to_sql('Citations', conn, if_exists='replace', index=False)
    
    # Add indexes using the detected column name
    cursor = conn.cursor()
    cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_paper_id ON Papers({id_col})")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_source ON Citations(source_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_target ON Citations(target_id)")
    
    print(f"Done! Saved database to: {db_path}")
    conn.close()

if __name__ == "__main__":
    build_db()