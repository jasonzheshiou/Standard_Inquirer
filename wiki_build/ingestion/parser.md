# Parser

The `standards_ingestion.parser` module provides PDF text extraction, cleaning, and chunking functionality.

## Classes

### Document

A dataclass representing a single text document with metadata.

```python
@dataclasses.dataclass
class Document:
    page_content: str           # The text content of the chunk
    metadata: dict[str, Any]    # Metadata (standard_name, clause, chunk_index, source_url)
```

## Functions

### `extract_text_from_pdf(pdf_path: str | Path) -> str`

Extract text from all pages of a PDF document using PyMuPDF (fitz).

**Parameters:**
- `pdf_path` — Path to the PDF file

**Returns:** Cleaned text from all pages joined by double newlines.

**Raises:** `IngestionError` if the file cannot be opened or is not a valid PDF.

**Processing:**
1. Open PDF with PyMuPDF
2. Extract text from each page
3. Clean headers/footers using `_clean_text()`
4. Join pages with double newlines

```python
from standards_ingestion.parser import extract_text_from_pdf

text = extract_text_from_pdf("data/raw_pdfs/cps-230.pdf")
print(f"Extracted {len(text)} characters")
```

### `chunk_text(text: str, metadata: dict, chunk_size: int = 500, overlap: int = 50) -> list[Document]`

Split text into overlapping chunks with clause metadata.

**Parameters:**
- `text` — The full text to chunk
- `metadata` — Base metadata dict to attach to every chunk
- `chunk_size` — Target size of each chunk in characters (default: 500)
- `overlap` — Number of overlapping characters between chunks (default: 50)

**Returns:** List of `Document` objects with `page_content` and enriched `metadata`.

**Processing:**
1. Split text using `RecursiveCharacterTextSplitter` with separators: `\n\n\n`, `\n\n`, `\n`, `. `, ` `, `""`
2. Extract clause/paragraph references using regex
3. Attach metadata including primary clause reference

## Header/Footer Patterns

The following patterns are stripped from extracted text:

| Pattern | Example |
|---------|---------|
| `Page X of Y` | "Page 1 of 5" |
| Standalone page numbers | "1", "2" |
| Confidential notices | "Confidential — Not for Distribution" |
| Copyright lines | "Copyright 2019-2025" |
| APRA date lines | "APRA CPS 230 2019" |

## Clause Extraction

Clause references are extracted using the regex pattern:

```python
r"(?:Paragraph|Clause|\u00b6)\s*(\d+[A-Z]?(?:\([a-z]+\))?)", re.IGNORECASE
```

This matches patterns like:
- "Paragraph 27"
- "Paragraph 27(b)"
- "Clause 30"
- "¶ 15A"

## Usage

```python
from standards_ingestion.parser import extract_text_from_pdf, chunk_text

# Extract text
text = extract_text_from_pdf("data/raw_pdfs/cps-230.pdf")

# Chunk with metadata
chunks = chunk_text(text, metadata={
    "standard_name": "CPS 230",
    "source_url": "https://www.apra.gov.au/prudential-standards/cps-230",
})

for doc in chunks:
    print(f"Chunk {doc.metadata['chunk_index']}: {doc.page_content[:100]}...")
    if "clause" in doc.metadata:
        print(f"  Clause: {doc.metadata['clause']}")
```
