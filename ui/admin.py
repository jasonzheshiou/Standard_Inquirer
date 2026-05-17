"""Admin panel for the Compliance Gap Analyser.

Provides standards ingestion controls, ChromaDB chunk count display,
and last update timestamp information.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import streamlit as st

from ui.home import _render_llm_status

logger = logging.getLogger(__name__)


def _get_last_update() -> str | None:
    """Read the last update timestamp from data/last_update.json.

    Returns:
        ISO-8601 timestamp string, or ``None`` if the file does not exist.
    """
    try:
        meta_path = Path("data/last_update.json")
        if meta_path.exists():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return data.get("last_update", data.get("timestamp", "Unknown"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read last_update.json: %s", exc)
    return None


def _get_chunk_count() -> int | None:
    """Query ChromaDB for the current document chunk count.

    Returns:
        Number of documents in the ChromaDB collection, or ``None``
        if ChromaDB is not yet initialized or an error occurs.
    """
    try:
        from standards_ingestion.embedder import init_chroma_client, get_or_create_collection

        client = init_chroma_client()
        collection = get_or_create_collection(client)
        return collection.count()
    except Exception as exc:
        logger.warning("Could not query ChromaDB chunk count: %s", exc)
    return None


def _run_ingestion_pipeline() -> list[str]:
    """Run the full ingestion pipeline: download â†’ parse â†’ chunk â†’ embed.

    Returns:
        List of log messages from the pipeline execution.
    """
    messages: list[str] = []

    try:
        from standards_ingestion.downloader import download_source
        from standards_ingestion.parser import extract_text_from_pdf, chunk_text
        from standards_ingestion.embedder import init_chroma_client, upsert_documents, get_or_create_collection
    except ImportError as exc:
        messages.append(f"Pipeline import error: {exc}")
        return messages

    # Load sources from YAML
    try:
        import yaml
        sources_file = Path("standards_ingestion/sources.yaml")
        if sources_file.exists():
            raw = sources_file.read_text(encoding="utf-8")
            sources_data = yaml.safe_load(raw)
            sources = sources_data.get("sources", [])
        else:
            messages.append("sources.yaml not found â€” nothing to ingest.")
            return messages
    except Exception as exc:
        messages.append(f"Failed to load sources: {exc}")
        return messages

    if not sources:
        messages.append("No sources configured in sources.yaml.")
        return messages

    # Initialize ChromaDB
    try:
        client = init_chroma_client()
        collection = get_or_create_collection(client)
    except Exception as exc:
        messages.append(f"Failed to initialize ChromaDB: {exc}")
        return messages

    total_chunks = 0

    # --- Built-in sources (sources.yaml) ---
    for source in sources:
        from engine.schemas import StandardsSource

        src = StandardsSource(
            name=source.get("name", "Unknown"),
            url=source.get("url", ""),
            category=source.get("category", "Unknown"),
            expected_last_modified=source.get("expected_last_modified"),
        )

        try:
            messages.append(f"Downloading {src.name}...")
            st.write(f"- Downloading {src.name}...")

            pdf_path, was_updated = download_source(src)
            messages.append(f"Downloaded: {pdf_path} (updated={was_updated})")
            st.write(f"  â†’ {pdf_path} (updated={was_updated})")
        except Exception as exc:
            messages.append(f"Download error for {src.name}: {exc}")
            st.write(f"  âš  {exc}")
            continue

        try:
            messages.append(f"Extracting text from {src.name}...")
            st.write(f"- Extracting text from {src.name}...")
            # Route to the correct text extractor based on file type
            if pdf_path.suffix.lower() == ".pdf":
                text = extract_text_from_pdf(pdf_path)
            else:
                # HTML — extract text from the HTML page
                from standards_ingestion.parser import extract_text_from_html

                html_text = pdf_path.read_text(encoding="utf-8")
                text = extract_text_from_html(html_text)
            messages.append(f"Extracted {len(text)} characters from {src.name}")
            st.write(f"  â†’ {len(text)} characters extracted")
        except Exception as exc:
            messages.append(f"Parse error for {src.name}: {exc}")
            st.write(f"  âš  {exc}")
            continue

        try:
            messages.append(f"Chunking {src.name}...")
            st.write(f"- Chunking {src.name}...")
            docs = chunk_text(
                text,
                metadata={
                    "standard_name": src.name,
                    "source_url": src.url,
                },
            )
            messages.append(f"Created {len(docs)} chunks for {src.name}")
            st.write(f"  â†’ {len(docs)} chunks created")
        except Exception as exc:
            messages.append(f"Chunking error for {src.name}: {exc}")
            st.write(f"  âš  {exc}")
            continue

        try:
            messages.append(f"Embedding {len(docs)} documents for {src.name}...")
            st.write(f"- Embedding {len(docs)} documents for {src.name}...")
            count = upsert_documents(docs, collection)
            total_chunks += count
            messages.append(f"Upserted {count} documents for {src.name}")
            st.write(f"  â†’ {count} documents upserted")
        except Exception as exc:
            messages.append(f"Embedding error for {src.name}: {exc}")
            st.write(f"  âš  {exc}")
            continue

    # --- Custom standards (custom_standards.yaml) ---
    try:
        from standards_ingestion.custom_loader import load_custom_standards
        from standards_ingestion.parser import Document

        custom_sources = load_custom_standards()
        if custom_sources:
            messages.append("=== Custom Standards ===")
            st.write("=== Custom Standards ===")
            custom_count = 0
            for cs in custom_sources:
                cs_name = cs.get("name", "Unknown")
                cs_url = cs.get("url", "")
                cs_category = cs.get("category", "Unknown")
                cs_summary = cs.get("summary", "")

                if not cs_summary:
                    messages.append(f"  Custom [{cs_name}]: no summary — skipped")
                    continue

                doc = Document(
                    page_content=cs_summary,
                    metadata={
                        "standard_name": cs_name,
                        "source_url": cs_url,
                        "source_type": "custom",
                        "standard_category": cs_category,
                    },
                )
                try:
                    count = upsert_documents([doc], collection)
                    total_chunks += count
                    custom_count += 1
                    messages.append(f"  Custom [{cs_name}]: upserted {count} document(s)")
                    st.write(f"  - Custom [{cs_name}]: upserted {count} document(s)")
                except Exception as exc:
                    messages.append(f"  Custom [{cs_name}]: embedding error — {exc}")
                    st.write(f"  - Custom [{cs_name}]: ⚠ {exc}")
            if custom_count:
                messages.append(f"Custom standards processed: {custom_count}/{len(custom_sources)}")
                st.write(f"Custom standards processed: {custom_count}/{len(custom_sources)}")
    except Exception as exc:
        messages.append(f"Failed to process custom standards: {exc}")
        st.write(f"⚠ Failed to process custom standards: {exc}")

    # Save last update timestamp
    try:
        meta_path = Path("data/last_update.json")
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps({"last_update": time.strftime("%Y-%m-%dT%H:%M:%S")}),
            encoding="utf-8",
        )
        messages.append(f"Last update saved: {meta_path}")
    except OSError as exc:
        messages.append(f"Failed to save last_update.json: {exc}")

    return messages


def render_admin() -> None:
    """Render the admin panel with ingestion controls and status.

    Displays:
        - Last update timestamp
        - ChromaDB chunk count
        - "Update Standards Now" button that runs the ingestion pipeline
        - Ingestion log messages
    """
    st.title("Admin Panel")

    # LLM Status
    _render_llm_status()
    st.divider()

    # Last update timestamp
    last_update = _get_last_update()
    if last_update:
        st.info(f"Last standards update: {last_update}")
    else:
        st.info("No previous update recorded.")

    # Chunk count
    chunk_count = _get_chunk_count()
    if chunk_count is not None:
        st.metric("ChromaDB Chunks", chunk_count)
    else:
        st.info("ChromaDB not yet initialized.")

    st.divider()

    # Ingestion controls
    st.subheader("Standards Ingestion")

    if st.button("Update Standards Now", type="primary"):
        with st.spinner("Running ingestion pipeline..."):
            status = st.status("In Progress", expanded=True)
            with status:
                messages = _run_ingestion_pipeline()
                for msg in messages:
                    st.write(msg)
            status.update(label="Complete", state="complete")

    st.divider()

    # Ingestion logs
    log_path = Path("data/ingestion.log")
    if log_path.exists():
        st.subheader("Ingestion Log")
        try:
            log_content = log_path.read_text(encoding="utf-8")
            st.code(log_content, language="text")
        except OSError:
            st.warning("Could not read ingestion log.")
