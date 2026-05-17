"""CLI orchestration script for the standards ingestion pipeline.

Runs the full pipeline: download → parse → chunk → embed.

Usage::

    python -m scripts.run_ingestion

Or as a module::

    python -m scripts.run_ingestion
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from config import settings
from engine.schemas import StandardsSource
from standards_ingestion.downloader import download_source
from standards_ingestion.embedder import (
    get_or_create_collection,
    init_chroma_client,
    upsert_documents,
)
from standards_ingestion.parser import Document, chunk_text, extract_text_from_html, extract_text_from_pdf, IngestionError

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "PyYAML is required for the ingestion pipeline. "
        "Install it with: pip install pyyaml"
    ) from exc


def load_sources(sources_file: str = "standards_ingestion/sources.yaml") -> list[StandardsSource]:
    """Load standards sources from a YAML configuration file.

    Args:
        sources_file: Path to the YAML sources file.

    Returns:
        List of validated :class:`StandardsSource` objects.
    """
    path = Path(sources_file)
    if not path.exists():
        raise FileNotFoundError(f"Sources file not found: {sources_file}")

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    sources: list[StandardsSource] = []
    for item in data.get("sources", []):
        sources.append(StandardsSource.model_validate(item))

    return sources


def _detect_source_type(url: str, content_type: str | None = None) -> str:
    """Detect the source document type from URL or content-type header.

    Args:
        url: The source URL.
        content_type: Optional Content-Type header from the HTTP response.

    Returns:
        One of 'pdf', 'html', 'markdown', or 'unknown'.
    """
    # Check content-type header first
    if content_type:
        ct = content_type.lower()
        if "pdf" in ct:
            return "pdf"
        if "html" in ct or "text/html" in ct:
            return "html"
        if "plain" in ct or "text/markdown" in ct:
            return "markdown"

    # Fall back to URL extension
    url_lower = url.lower()
    if url_lower.endswith(".pdf"):
        return "pdf"
    if url_lower.endswith(".html") or url_lower.endswith(".htm"):
        return "html"
    if url_lower.endswith(".md") or url_lower.endswith(".markdown"):
        return "markdown"

    return "unknown"


def run_pipeline(
    sources_file: str | None = None,
    output_dir: str = "data/raw_pdfs/",
    chroma_dir: str | None = None,
) -> None:
    """Run the full ingestion pipeline for all configured sources.

    For each source:
    1. Download the PDF (skip if not modified)
    2. Extract text
    3. Chunk into overlapping segments
    4. Generate embeddings and upsert to ChromaDB

    Args:
        sources_file: Path to sources YAML file. Defaults to settings.
        output_dir: Directory for raw PDF downloads.
        chroma_dir: ChromaDB persistence directory. Defaults to settings.
    """
    sources_path = sources_file or settings.standards_sources_file
    persist_dir = chroma_dir or settings.chroma_persist_directory

    logger.info("=" * 60)
    logger.info("Standards Ingestion Pipeline — Starting")
    logger.info("=" * 60)

    # Load sources
    try:
        sources = load_sources(sources_path)
    except Exception as exc:
        logger.error(f"Failed to load sources: {exc}")
        return

    logger.info(f"Loaded {len(sources)} source(s) from {sources_path}")

    # Initialise ChromaDB
    client = init_chroma_client(persist_dir)
    collection = get_or_create_collection(client)
    logger.info(f"ChromaDB collection ready: {collection.name}")

    # Track statistics and per-source status
    stats: dict[str, int] = {
        "sources_downloaded": 0,
        "sources_skipped": 0,
        "pages_parsed": 0,
        "chunks_created": 0,
        "documents_embedded": 0,
    }
    source_statuses: list[dict[str, Any]] = []

    for source in sources:
        logger.info(f"\nProcessing: {source.name} ({source.category})")

        # Initialise per-source status
        source_status: dict[str, Any] = {
            "name": source.name,
            "status": "pending",
            "chunks": 0,
        }

        # Step 1: Download
        try:
            file_path, was_updated = download_source(source, output_dir)
        except Exception as exc:
            source_status["status"] = "failed"
            source_status["error"] = str(exc)
            source_statuses.append(source_status)
            logger.error(f"Download failed for {source.name}: {exc}")
            continue

        if was_updated:
            stats["sources_downloaded"] += 1
            logger.info(f"  Downloaded: {file_path}")
        else:
            stats["sources_skipped"] += 1
            logger.info(f"  Skipped (not modified): {file_path}")
            source_status["status"] = "skipped"
            source_statuses.append(source_status)
            continue

        # Detect source type from URL
        source_type = _detect_source_type(source.url)
        source_status["source_type"] = source_type

        # Step 2: Extract text (route by source type)
        try:
            if source_type == "pdf":
                text = extract_text_from_pdf(file_path)
            elif source_type == "html":
                # Re-download as text for HTML sources
                import requests

                resp = requests.get(source.url, timeout=60)
                resp.raise_for_status()
                text = extract_text_from_html(resp.text)
            else:
                # Try PDF first, fall back to HTML
                try:
                    text = extract_text_from_pdf(file_path)
                    source_type = "pdf"
                except IngestionError:
                    import requests

                    resp = requests.get(source.url, timeout=60)
                    resp.raise_for_status()
                    text = extract_text_from_html(resp.text)
                    source_type = "html"
            source_status["source_type"] = source_type
        except Exception as exc:
            source_status["status"] = "failed"
            source_status["error"] = str(exc)
            source_statuses.append(source_status)
            logger.error(f"Text extraction failed for {source.name}: {exc}")
            continue

        logger.info(f"  Extracted {len(text)} characters of text ({source_type})")

        # Step 3: Chunk
        metadata = {
            "standard_name": source.name,
            "source_url": source.url,
            "category": source.category,
            "source_type": source_type,
            "standard_category": source.category,
        }
        chunks = chunk_text(text, metadata)
        stats["chunks_created"] += len(chunks)
        source_status["chunks"] = len(chunks)
        logger.info(f"  Created {len(chunks)} chunks")

        # Step 4: Embed and upsert
        try:
            count = upsert_documents(chunks, collection)
            stats["documents_embedded"] += count
            source_status["status"] = "success"
            logger.info(f"  Embedded {count} documents into ChromaDB")
        except Exception as exc:
            source_status["status"] = "failed"
            source_status["error"] = str(exc)
            logger.error(f"Embedding failed for {source.name}: {exc}")

        source_statuses.append(source_status)

    # Save update timestamp with per-source status
    last_update = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sources_total": len(sources),
        "sources_downloaded": stats["sources_downloaded"],
        "sources_skipped": stats["sources_skipped"],
        "chunks_created": stats["chunks_created"],
        "documents_embedded": stats["documents_embedded"],
        "sources": source_statuses,
    }

    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    (data_dir / "last_update.json").write_text(
        json.dumps(last_update, indent=2), encoding="utf-8"
    )

    # Print progress report
    logger.info("\n" + "=" * 60)
    logger.info("Pipeline Complete — Summary")
    logger.info("=" * 60)
    logger.info(f"  Sources downloaded:    {stats['sources_downloaded']}")
    logger.info(f"  Sources skipped:       {stats['sources_skipped']}")
    logger.info(f"  Chunks created:        {stats['chunks_created']}")
    logger.info(f"  Documents embedded:    {stats['documents_embedded']}")
    logger.info("  Update record saved:   data/last_update.json")

    # Per-source status report
    logger.info("\n" + "-" * 60)
    logger.info("Per-Source Status")
    logger.info("-" * 60)
    for src in source_statuses:
        status_str = src["status"].upper()
        chunks_str = f", {src['chunks']} chunks" if src.get("chunks") > 0 else ""
        error_str = f" — {src.get('error', 'unknown')}" if src["status"] == "failed" else ""
        logger.info(f"  [{status_str}] {src['name']}{chunks_str}{error_str}")
    logger.info("-" * 60)


if __name__ == "__main__":
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO",
    )
    logger.add("logs/ingestion_{time:YYYY-MM-DD}.log", rotation="1 day", level="DEBUG")

    run_pipeline()
