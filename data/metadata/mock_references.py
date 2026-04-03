import json
import csv
import random
import os

def create_mock_data():
    current_folder = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(current_folder, 'corpus.json')
    csv_path = os.path.join(current_folder, 'all_references.csv')

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            papers = json.load(f)
    except FileNotFoundError:
        print(f"Error: Still can't find {json_path}. Check if corpus.json is named correctly.")
        return

    paper_ids = [paper['id'] for paper in papers]
    
    mock_citations = []
    for source in paper_ids:
        num_citations = random.randint(1, 4)
        targets = random.sample([p for p in paper_ids if p != source], min(num_citations, len(paper_ids)-1))
        
        for target in targets:
            mock_citations.append({'source_id': source, 'target_id': target})

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['source_id', 'target_id'])
        writer.writeheader()
        writer.writerows(mock_citations)
        
    print(f"Success! Created all_references.csv with {len(mock_citations)} fake citations.")
    print(f"Saved to: {csv_path}")

if __name__ == "__main__":
    create_mock_data()