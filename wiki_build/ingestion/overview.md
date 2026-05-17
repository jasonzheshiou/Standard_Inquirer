# Ingestion Overview

The `standards_ingestion` package implements a four-stage pipeline for ingesting regulatory standard documents (PDFs) into ChromaDB for vector-similarity search.

## Pipeline Stages

```
┌────────────┐    ┌──────────┐    ┌────────┐    ┌──────────┐
│  Download  │ →  │  Parse   │ →  │ Chunk  │ →  │  Embed   │
│  (PDFs)    │    │  (fitz)  │    │(LCTS)  │    │(ChromaDB)│
└────────────┘    └──────────┘    └────────┘    └──────────┘
```

### Stage 1: Download

Downloads PDF documents from external URLs using `requests` with ETag / Last-Modified conditional GET support. If the remote document has not changed, the existing file is reused.

**Module:** `standards_ingestion/downloader.py`
**Key function:** `download_source(source: StandardsSource, output_dir: str) -> tuple[Path, bool]`

### Stage 2: Parse

Extracts text from PDF documents using PyMuPDF (fitz). Common headers and footers are stripped from the extracted text.

**Module:** `standards_ingestion/parser.py`
**Key function:** `extract_text_from_pdf(pdf_path: str | Path) -> str`

### Stage 3: Chunk

Splits the extracted text into overlapping chunks using `langchain_text_splitters.RecursiveCharacterTextSplitter`. Clause/paragraph references are extracted and stored in metadata.

**Module:** `standards_ingestion/parser.py`
**Key function:** `chunk_text(text: str, metadata: dict, chunk_size: int, overlap: int) -> list[Document]`

### Stage 4: Embed

Generates embeddings using `sentence-transformers` and upserts documents to a ChromaDB collection. Each document is stored with metadata including standard name, clause reference, chunk index, and source URL.

**Module:** `standards_ingestion/embedder.py`
**Key functions:** `init_chroma_client()`, `get_or_create_collection()`, `upsert_documents()`

## Configuration

Sources are defined in `standards_ingestion/sources.yaml`:

```yaml
sources:
  - name: "CPS 230"
    url: "https://www.apra.gov.au/prudential-standards/cps-230"
    category: "APRA"
    expected_last_modified: "2025-01-01"
```

## Running the Pipeline

### CLI

```bash
python -m scripts.run_ingestion
```

### Admin Panel

Click "Update Standards Now" in the Admin page of the Streamlit UI.

## Data Flow

```
sources.yaml
    │
    ▼
download_source() → data/raw_pdfs/{slug}.pdf + .pdf.meta
    │
    ▼
extract_text_from_pdf() → cleaned text
    │
    ▼
chunk_text() → list[Document] with clause metadata
    │
    ▼
upsert_documents() → ChromaDB collection
    │
    ▼
data/last_update.json (timestamp + stats)
```

## Error Classes

| Exception | Module | Raised When |
|-----------|--------|-------------|
| `StandardsDownloadError` | `downloader` | Download fails or invalid response |
| `IngestionError` | `parser` | PDF cannot be opened or parsed |
