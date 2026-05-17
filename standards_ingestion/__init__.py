"""Standards ingestion pipeline for the Compliance Gap Analyser.

Public API:
    - download_source (from downloader)
    - extract_text_from_pdf, chunk_text (from parser)
    - upsert_documents, init_chroma_client (from embedder)
"""

from standards_ingestion.downloader import download_source
from standards_ingestion.parser import chunk_text, extract_text_from_pdf
from standards_ingestion.embedder import init_chroma_client, upsert_documents

__all__ = [
    "download_source",
    "extract_text_from_pdf",
    "chunk_text",
    "init_chroma_client",
    "upsert_documents",
]
