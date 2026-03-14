# 🔬 DS3294 Citation Graph Builder

An interactive Streamlit dashboard for extracting, visualizing, and analyzing citation networks from scientific literature. This project transforms static PDF papers and bibliographic data into a dynamic, Gestalt-optimized network graph.

## 📊 1. Data Source Plan
The application is designed to ingest data from multiple flexible streams:
* **Primary Source (Automated):** Open-access scientific PDFs (e.g., from arXiv, PubMed, or local collections).
* **Secondary Source (Manual/Batch):** Direct manual data entry via the UI or bulk ingestion using structured JSON files containing metadata (Title, Authors, Year, References).
* **Future Integration:** Direct API calls to the Semantic Scholar or arXiv APIs to pull reference graphs dynamically.

## ⚙️ 2. Pre-Processing & Data Extraction Plan
Raw scientific papers are messy. Our pre-processing pipeline handles the conversion of unstructured text into a structured network dataset:
1. **Text Extraction:** Utilize `PyPDF2` (or `pdfminer.six` for higher fidelity) to strip raw text from uploaded PDF binaries.
2. **Metadata Parsing:** Apply Regular Expressions (Regex) and heuristic rules to identify the Title, Authors, and Publication Year from the first few pages of the document.
3. **Reference Resolution:** * Locate the "References" section at the tail of the document.
   * Parse individual citation strings.
   * Use **Fuzzy String Matching** (`fuzzywuzzy`) to map parsed reference strings to existing nodes (papers) within our local corpus database.

## 🏗️ 3. Code Structure & Architecture Plan
The project is built on a modular architecture using Python, Streamlit, and NetworkX:

* `app.py`: The core application and routing logic. Handles the Streamlit UI, page navigation, and state management.
* **Data Layer:** `st.session_state` manages an in-memory dictionary of paper metadata and the active `nx.DiGraph` (Directed Graph) object.
* **Analysis Engine:** Utilizes `NetworkX` to compute graph metrics such as PageRank, Betweenness Centrality, and In/Out-degree distributions.
* **Visualization Engine:** Integrates `pyvis` (with customized Gestalt design principles) to render an interactive HTML/JS physics-based graph directly inside the Streamlit dashboard.

## 🐛 4. Testing and Debugging Plan
To ensure the integrity of the citation network and the stability of the UI, the following testing protocols are planned:
* **Unit Testing (Extraction):** Isolate the `extract_metadata_from_text` function and test it against a suite of known, manually annotated PDF text dumps to verify regex accuracy.
* **Graph Validation:** Implement checks to ensure no duplicate nodes are created and that edges (citations) accurately point from a newer paper to an older paper.
* **Graceful Degradation:** Test the application environment with missing dependencies (e.g., simulating a lack of `PyPDF2` or `pyvis`) to ensure the dashboard falls back to standard NetworkX/Matplotlib rendering or provides clear warning UI alerts.
* **Activity Logging:** Maintain a continuous `st.session_state["log"]` to trace user actions (uploads, parsing errors, edge creations) for real-time debugging within the dashboard.
