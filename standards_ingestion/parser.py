"""Text extraction, chunking, and clause-number extraction for PDF and HTML sources.

Provides functions to extract text from PDF documents (PyMuPDF) and HTML
pages (regex-based), clean up headers/footers, split into overlapping chunks,
and extract regulatory clause/paragraph references.

Usage::

    from standards_ingestion.parser import (
        extract_text_from_pdf,
        extract_text_from_html,
        chunk_text,
    )

    text = extract_text_from_pdf("data/raw_pdfs/cps-230.pdf")
    chunks = chunk_text(text, metadata={"standard_name": "CPS 230"})

    html_text = extract_text_from_html("<html>...</html>")
    chunks = chunk_text(html_text, metadata={"standard_name": "AASB 17"})
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any

import fitz
from langchain_text_splitters import RecursiveCharacterTextSplitter


class IngestionError(Exception):
    """Raised when document ingestion (parsing/chunking) fails."""


@dataclasses.dataclass
class Document:
    """A single text document with metadata.

    Attributes:
        page_content: The text content of the document chunk.
        metadata: A dictionary of metadata associated with this chunk.
    """

    page_content: str
    metadata: dict[str, Any]


# Common header/footer patterns to strip from extracted PDF text
_HEADER_FOOTER_PATTERNS: list[str] = [
    r"Page\s+\d+\s+of\s+\d+",  # "Page 1 of 5"
    r"^\s*Page\s+\d+\s*$",  # standalone "Page X"
    r"^\s*\d+\s*$",  # standalone page numbers
    r"Confidential\s+—\s+Not\s+for\s+Distribution",
    r"Copyright\s+[\d\-]+",
    r"APRA\s+.*?\s+20\d{2}",  # "APRA CPS 230 2019"
]

# Combined regex for clause/paragraph references
_CLAUSE_PATTERN = re.compile(
    r"(?:Paragraph|Clause|\u00b6)\s*(\d+[A-Z]?(?:\([a-z]+\))?)",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    """Remove common header/footer patterns from extracted text.

    Args:
        text: Raw text extracted from a PDF page.

    Returns:
        Cleaned text with headers and footers removed.
    """
    cleaned = text
    for pattern in _HEADER_FOOTER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.MULTILINE)
    # Collapse excessive whitespace
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def extract_text_from_html(html: str) -> str:
    """Extract clean text from an HTML document.

    Strips HTML tags using regex, collapses whitespace, and returns
    a plain-text representation suitable for chunking and embedding.

    Args:
        html: Raw HTML string content.

    Returns:
        Cleaned text with tags removed and whitespace normalised.
    """
    # Remove script and style blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Replace common tag-based whitespace with spaces
    text = re.sub(r"<br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "\n  - ", text, flags=re.IGNORECASE)
    text = re.sub(r"<td[^>]*>", "\t", text, flags=re.IGNORECASE)
    text = re.sub(r"<th[^>]*>", "\t", text, flags=re.IGNORECASE)

    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode common HTML entities
    entities = {
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
        "&apos;": "'",
        "&nbsp;": " ",
        "&ndash;": "-",
        "&mdash;": "—",
        "&lsquo;": "'",
        "&rsquo;": "'",
        "&ldquo;": '"',
        "&rdquo;": '"',
        "&bull;": "•",
        "&hellip;": "…",
    }
    for entity, replacement in entities.items():
        text = text.replace(entity, replacement)

    # Decode numeric HTML entities (e.g. &#x20; or &#32;)
    def _replace_numeric(m: re.Match[str]) -> str:
        try:
            if m.group(1):  # hex
                return chr(int(m.group(1), 16))
            return chr(int(m.group(1)))
        except (ValueError, OverflowError):
            return ""

    text = re.sub(r"&#(x?)([0-9a-fA-F]+);", _replace_numeric, text)

    # Clean up whitespace
    text = re.sub(r"[ \t]+", " ", text)       # collapse spaces/tabs
    text = re.sub(r"\n{3,}", "\n\n", text)     # collapse excessive newlines
    text = re.sub(r"^\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+$", "", text, flags=re.MULTILINE)

    return text.strip()


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract text from all pages of a PDF document.

    Uses PyMuPDF (fitz) to open and read the PDF.  Extracted text is
    cleaned of common headers and footers.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Cleaned text from all pages joined by double newlines.

    Raises:
        IngestionError: If the file cannot be opened or is not a valid PDF.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise IngestionError(f"PDF file not found: {pdf_path}")

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise IngestionError(f"Cannot open PDF file: {pdf_path} ({exc})") from exc

    if doc.page_count == 0:
        doc.close()
        raise IngestionError(f"PDF file is empty: {pdf_path}")

    pages: list[str] = []
    try:
        for page in doc:
            text = page.get_text()
            pages.append(_clean_text(str(text)))
    finally:
        doc.close()

    return "\n\n".join(pages)


def chunk_text(
    text: str,
    metadata: dict[str, Any],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[Document]:
    """Split text into overlapping chunks with clause metadata.

    Uses ``langchain_text_splitter.RecursiveCharacterTextSplitter`` to
    split the input text into chunks of approximately ``chunk_size``
    characters with ``overlap`` characters of overlap between adjacent
    chunks.

    Clause numbers (e.g. "Paragraph 27(b)", "Clause 30", "\u00b6 15A")
    are extracted from each chunk and stored in metadata.

    Args:
        text: The full text to chunk.
        metadata: Base metadata dict to attach to every chunk.
        chunk_size: Target size of each chunk in characters.
        overlap: Number of overlapping characters between chunks.

    Returns:
        List of :class:`Document` objects with ``page_content`` and
        enriched ``metadata``.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        length_function=len,
        separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""],
    )

    raw_chunks = splitter.split_text(text)

    documents: list[Document] = []
    for idx, chunk in enumerate(raw_chunks):
        # Extract clause/paragraph references
        clause_refs = _CLAUSE_PATTERN.findall(chunk)
        chunk_meta: dict[str, Any] = {**metadata, "chunk_index": idx}
        if clause_refs:
            chunk_meta["clause"] = clause_refs[0]  # Primary clause ref

        documents.append(Document(page_content=chunk, metadata=chunk_meta))

    return documents
