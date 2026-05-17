# Embedder

The `standards_ingestion.embedder` module handles ChromaDB client initialization, collection management, and document upsertion with embeddings.

## Functions

### `init_chroma_client(persist_directory: str = "data/chroma_db") -> chromadb.ClientAPI`

Initialise a persistent ChromaDB client.

**Parameters:**
- `persist_directory` — Directory where ChromaDB stores its data (default: `data/chroma_db`)

**Returns:** A configured `chromadb.PersistentClient` instance.

**Raises:** `RuntimeError` if the ChromaDB client cannot be initialised.

```python
from standards_ingestion.embedder import init_chroma_client

client = init_chroma_client()  # Uses default directory
client = init_chroma_client("/custom/chroma/path")  # Custom directory
```

### `get_or_create_collection(client: chromadb.ClientAPI, name: str = "standards_collection") -> chromadb.Collection`

Get an existing collection or create a new one.

**Parameters:**
- `client` — A ChromaDB client instance
- `name` — Name of the collection to get or create (default: `standards_collection`)

**Returns:** A ChromaDB collection object.

```python
from standards_ingestion.embedder import get_or_create_collection

collection = get_or_create_collection(client)
# collection: chromadb.Collection
```

### `upsert_documents(docs: list[Document], collection: chromadb.Collection, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> int`

Generate embeddings and upsert documents to a ChromaDB collection.

**Parameters:**
- `docs` — List of `Document` objects to upsert
- `collection` — Target ChromaDB collection
- `model_name` — HuggingFace model name for embeddings (default: `sentence-transformers/all-MiniLM-L6-v2`)

**Returns:** The number of documents successfully upserted.

**Raises:** `RuntimeError` if embedding generation or ChromaDB upsert fails.

**Processing:**
1. Load the sentence-transformers model
2. For each document:
   - Generate embedding using the model
   - Extract metadata (standard_name, clause, source_url, chunk_index)
   - Create a document ID: `{standard_name}-{idx}`
3. Upsert all documents in a single batch to ChromaDB

```python
from standards_ingestion.embedder import (
    init_chroma_client,
    get_or_create_collection,
    upsert_documents,
)
from standards_ingestion.parser import chunk_text, extract_text_from_pdf

# Setup
client = init_chroma_client()
collection = get_or_create_collection(client)

# Extract and chunk
text = extract_text_from_pdf("data/raw_pdfs/cps-230.pdf")
docs = chunk_text(text, metadata={
    "standard_name": "CPS 230",
    "source_url": "https://www.apra.gov.au/prudential-standards/cps-230",
})

# Embed and upsert
count = upsert_documents(docs, collection)
print(f"Upserted {count} documents")
```

## ChromaDB Collection Metadata

Each upserted document stores the following metadata:

| Field | Source | Example |
|-------|--------|---------|
| `standard_name` | `doc.metadata["standard_name"]` | "CPS 230" |
| `chunk_index` | `doc.metadata["chunk_index"]` | 0, 1, 2... |
| `source_url` | `doc.metadata["source_url"]` | "https://www.apra.gov.au/..." |
| `clause` | `doc.metadata["clause"]` | "27(b)" |

## Embedding Model

The default embedding model is `sentence-transformers/all-MiniLM-L6-v2`, which:

- Produces 384-dimensional embeddings
- Is fast and memory-efficient
- Provides good semantic similarity for regulatory text

To use a different model:

```python
count = upsert_documents(docs, collection, model_name="sentence-transformers/all-mpnet-base-v2")
```

## Error Handling

```python
from standards_ingestion.embedder import upsert_documents, RuntimeError

try:
    count = upsert_documents(docs, collection)
except RuntimeError as exc:
    logger.error(f"Embedding failed: {exc}")
```

## Empty Document Handling

If `docs` is an empty list, `upsert_documents()` returns `0` without attempting any embedding or ChromaDB operations.
