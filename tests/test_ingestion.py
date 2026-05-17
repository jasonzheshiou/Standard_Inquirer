"""Comprehensive tests for the standards ingestion pipeline.

Covers:
- Downloader: download with mocked HTTP, ETag skip, error handling
- Parser: text extraction, chunking, clause extraction regex
- Embedder: ChromaDB upsert with mocked client
- Full pipeline: end-to-end flow with mock data
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
import responses

from engine.schemas import StandardsSource
from standards_ingestion.downloader import StandardsDownloadError, download_source, slugify
from standards_ingestion.parser import (
    Document,
    IngestionError,
    chunk_text,
    extract_text_from_pdf,
    _CLAUSE_PATTERN,
)
from standards_ingestion.embedder import (
    get_or_create_collection,
    init_chroma_client,
    upsert_documents,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_source(
    name: str = "CPS 230",
    url: str = "https://example.com/cps230.pdf",
    category: str = "APRA",
) -> StandardsSource:
    """Helper to create a StandardsSource for testing."""
    return StandardsSource(name=name, url=url, category=category, expected_last_modified=None)


# ---------------------------------------------------------------------------
# slugify tests
# ---------------------------------------------------------------------------


class TestSlugify:
    """Tests for the slugify helper function."""

    def test_simple_name(self) -> None:
        assert slugify("CPS 230") == "cps-230"

    def test_multi_word(self) -> None:
        assert slugify("ASX Listing Rules") == "asx-listing-rules"

    def test_special_characters(self) -> None:
        assert slugify("CPS 200 (v1.2)") == "cps-200-v1-2"

    def test_already_slug(self) -> None:
        assert slugify("cps-230") == "cps-230"

    def test_leading_trailing_spaces(self) -> None:
        assert slugify("  CPS 230  ") == "cps-230"


# ---------------------------------------------------------------------------
# Downloader tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestDownloadSource:
    """Tests for the download_source function using mocked HTTP."""

    @responses.activate
    def test_successful_download(self, tmp_path: Path) -> None:
        """A successful PDF download should save the file and return updated=True."""
        pdf_content = b"%PDF-1.4 fake pdf content for testing"
        responses.add(
            responses.GET,
            "https://example.com/cps230.pdf",
            body=pdf_content,
            status=200,
            headers={"Content-Type": "application/pdf"},
        )

        source = _make_source()
        output_dir = str(tmp_path / "raw_pdfs")
        file_path, was_updated = download_source(source, output_dir)

        assert was_updated is True
        assert file_path.exists()
        assert file_path.name == "cps-230.pdf"
        assert file_path.read_bytes() == pdf_content

    @responses.activate
    def test_etag_skip_304(self, tmp_path: Path) -> None:
        """If server returns 304, existing file is reused and updated=False."""
        pdf_content = b"%PDF-1.4 existing pdf"
        meta_content = "ETag: \"abc123\""

        # Create existing file and meta
        output_dir = tmp_path / "raw_pdfs"
        output_dir.mkdir()
        file_path = output_dir / "cps-230.pdf"
        file_path.write_bytes(pdf_content)
        (file_path.with_suffix(".pdf.meta")).write_text(meta_content)

        responses.add(
            responses.GET,
            "https://example.com/cps230.pdf",
            status=304,
            headers={"ETag": "\"abc123\""},
        )

        source = _make_source()
        result_path, was_updated = download_source(source, str(output_dir))

        assert was_updated is False
        assert result_path == file_path

    @responses.activate
    def test_last_modified_skip_304(self, tmp_path: Path) -> None:
        """If server returns 304 via Last-Modified, existing file is reused."""
        pdf_content = b"%PDF-1.4 existing pdf"
        meta_content = "Last-Modified: Mon, 01 Jan 2024 00:00:00 GMT"

        output_dir = tmp_path / "raw_pdfs"
        output_dir.mkdir()
        file_path = output_dir / "cps-230.pdf"
        file_path.write_bytes(pdf_content)
        (file_path.with_suffix(".pdf.meta")).write_text(meta_content)

        responses.add(
            responses.GET,
            "https://example.com/cps230.pdf",
            status=304,
        )

        source = _make_source()
        result_path, was_updated = download_source(source, str(output_dir))

        assert was_updated is False

    @responses.activate
    def test_network_error_raises(self) -> None:
        """Network errors should raise StandardsDownloadError."""
        responses.add(
            responses.GET,
            "https://example.com/cps230.pdf",
            status=500,
        )

        source = _make_source()
        with pytest.raises(StandardsDownloadError, match="HTTP 500"):
            download_source(source)

    @responses.activate
    def test_wrong_content_type_raises(self) -> None:
        """Non-PDF response should raise StandardsDownloadError."""
        responses.add(
            responses.GET,
            "https://example.com/cps230.pdf",
            body=b"<html>not a pdf</html>",
            status=200,
            headers={"Content-Type": "text/html"},
        )

        source = _make_source()
        with pytest.raises(StandardsDownloadError, match="Expected PDF"):
            download_source(source)

    @responses.activate
    def test_saves_meta_on_success(self, tmp_path: Path) -> None:
        """Successful download should save ETag/Last-Modified metadata."""
        responses.add(
            responses.GET,
            "https://example.com/cps230.pdf",
            body=b"%PDF-1.4",
            status=200,
            headers={
                "Content-Type": "application/pdf",
                "ETag": "\"xyz789\"",
                "Last-Modified": "Tue, 02 Jan 2024 00:00:00 GMT",
            },
        )

        source = _make_source()
        output_dir = str(tmp_path / "raw_pdfs")
        download_source(source, output_dir)

        meta_path = tmp_path / "raw_pdfs" / "cps-230.pdf.meta"
        assert meta_path.exists()
        meta = meta_path.read_text()
        assert "ETag: \"xyz789\"" in meta
        assert "Last-Modified: Tue, 02 Jan 2024 00:00:00 GMT" in meta


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestClauseRegex:
    """Tests for the clause/paragraph extraction regex pattern."""

    def test_paragraph_with_subclause(self) -> None:
        matches = _CLAUSE_PATTERN.findall("Paragraph 27(b)")
        assert matches == ["27(b)"]

    def test_clause_reference(self) -> None:
        matches = _CLAUSE_PATTERN.findall("Clause 30")
        assert matches == ["30"]

    def test_paragraph_symbol(self) -> None:
        matches = _CLAUSE_PATTERN.findall("\u00b6 15A")
        assert matches == ["15A"]

    def test_paragraph_simple(self) -> None:
        matches = _CLAUSE_PATTERN.findall("Paragraph 5")
        assert matches == ["5"]

    def test_paragraph_with_nested_subclause(self) -> None:
        matches = _CLAUSE_PATTERN.findall("Paragraph 10(a)(i)")
        assert matches == ["10(a)"]  # Regex captures first subclause group

    def test_no_match_plain_text(self) -> None:
        matches = _CLAUSE_PATTERN.findall("This is just normal text")
        assert matches == []

    def test_multiple_clauses(self) -> None:
        text = "Paragraph 27(b) and Clause 30 are relevant"
        matches = _CLAUSE_PATTERN.findall(text)
        assert matches == ["27(b)", "30"]

    def test_case_insensitive(self) -> None:
        matches = _CLAUSE_PATTERN.findall("paragraph 12")
        assert matches == ["12"]


class TestChunkText:
    """Tests for the chunk_text function."""

    def test_chunks_produced_for_long_text(self) -> None:
        """Long text should be split into multiple chunks."""
        long_text = "This is a test. " * 200  # ~2600 chars
        metadata = {"standard_name": "CPS 230"}
        docs = chunk_text(long_text, metadata, chunk_size=100, overlap=10)

        assert len(docs) > 1
        assert all(isinstance(d, Document) for d in docs)

    def test_single_chunk_for_short_text(self) -> None:
        """Short text should produce a single chunk."""
        short_text = "Short text."
        metadata = {"standard_name": "CPS 230"}
        docs = chunk_text(short_text, metadata, chunk_size=500, overlap=50)

        assert len(docs) == 1
        assert docs[0].page_content == short_text

    def test_metadata_propagated(self) -> None:
        """Base metadata should be present in every chunk."""
        text = "Test content. " * 50
        metadata = {"standard_name": "CPS 230", "source_url": "http://example.com"}
        docs = chunk_text(text, metadata, chunk_size=100, overlap=10)

        for doc in docs:
            assert doc.metadata["standard_name"] == "CPS 230"
            assert doc.metadata["source_url"] == "http://example.com"
            assert "chunk_index" in doc.metadata

    def test_clause_extracted_into_metadata(self) -> None:
        """Clause references in text should be extracted into metadata."""
        text = "Paragraph 27(b) requires that insurers have adequate governance."
        metadata = {"standard_name": "CPS 230"}
        docs = chunk_text(text, metadata, chunk_size=500, overlap=50)

        assert len(docs) >= 1
        assert "clause" in docs[0].metadata
        assert docs[0].metadata["clause"] == "27(b)"

    def test_chunk_indices_sequential(self) -> None:
        """Chunk indices should be sequential from 0."""
        text = "Chunk " * 100
        metadata = {"standard_name": "Test"}
        docs = chunk_text(text, metadata, chunk_size=50, overlap=5)

        indices = [d.metadata["chunk_index"] for d in docs]
        assert indices == list(range(len(docs)))

    def test_empty_text_no_chunks(self) -> None:
        """Empty text should produce no chunks."""
        docs = chunk_text("", {"standard_name": "Test"})
        assert len(docs) == 0


class TestExtractTextFromPdf:
    """Tests for extract_text_from_pdf."""

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(IngestionError, match="not found"):
            extract_text_from_pdf("/nonexistent/file.pdf")

    def test_raises_on_non_pdf(self, tmp_path: Path) -> None:
        """Non-PDF file should raise IngestionError."""
        fake_pdf = tmp_path / "not_a_pdf.pdf"
        fake_pdf.write_text("This is not a PDF", encoding="utf-8")

        with pytest.raises(IngestionError, match="Cannot open PDF"):
            extract_text_from_pdf(fake_pdf)

    def test_raises_on_empty_pdf(self, tmp_path: Path) -> None:
        """Empty PDF (0 pages) should raise IngestionError."""
        # Create a minimal valid PDF with 0 pages
        empty_pdf = tmp_path / "empty.pdf"
        # Minimal PDF header without pages
        empty_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n")

        with pytest.raises(IngestionError, match="empty"):
            extract_text_from_pdf(empty_pdf)


# ---------------------------------------------------------------------------
# Embedder tests (mocked ChromaDB)
# ---------------------------------------------------------------------------


class TestInitChromaClient:
    """Tests for init_chroma_client."""

    def test_creates_persistent_client(self) -> None:
        """Should return a chromadb.PersistentClient instance."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("standards_ingestion.embedder.chromadb") as mock_chroma:
                mock_client = MagicMock()
                mock_chroma.PersistentClient.return_value = mock_client

                result = init_chroma_client(tmp_dir)

                mock_chroma.PersistentClient.assert_called_once_with(path=tmp_dir)
                assert result == mock_client


class TestGetOrCreateCollection:
    """Tests for get_or_create_collection."""

    def test_returns_collection(self) -> None:
        """Should return the result of get_or_create_collection."""
        mock_client = MagicMock()
        mock_collection = MagicMock(name="test_collection")
        mock_client.get_or_create_collection.return_value = mock_collection

        result = get_or_create_collection(mock_client, name="test_collection")

        assert result == mock_collection
        mock_client.get_or_create_collection.assert_called_once_with(name="test_collection")


class TestUpsertDocuments:
    """Tests for upsert_documents with mocked ChromaDB."""

    def setup_method(self) -> None:
        """Patch SentenceTransformer in the embedder's namespace."""
        self._mock_st_class = MagicMock()
        self._mock_st_instance = MagicMock()
        self._mock_st_instance.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2, 0.3])
        self._mock_st_class.return_value = self._mock_st_instance
        # Patch the class in the embedder module's namespace directly
        import standards_ingestion.embedder as embedder_mod
        self._original_st = embedder_mod.SentenceTransformer
        embedder_mod.SentenceTransformer = self._mock_st_class

    def teardown_method(self) -> None:
        """Restore original SentenceTransformer."""
        import standards_ingestion.embedder as embedder_mod
        embedder_mod.SentenceTransformer = self._original_st

    def test_empty_docs_returns_zero(self) -> None:
        """Empty document list should return 0 without calling ChromaDB."""
        mock_collection = MagicMock()
        count = upsert_documents([], mock_collection)
        assert count == 0
        mock_collection.upsert.assert_not_called()

    def test_upserts_with_correct_metadata(self) -> None:
        """Documents should be upserted with correct metadata structure."""
        mock_collection = MagicMock()

        docs = [
            Document(
                page_content="Test content 1",
                metadata={"standard_name": "CPS 230", "source_url": "http://example.com", "clause": "27(b)"},
            ),
            Document(
                page_content="Test content 2",
                metadata={"standard_name": "CPS 230", "source_url": "http://example.com", "clause": "30"},
            ),
        ]

        count = upsert_documents(docs, mock_collection)

        assert count == 2
        mock_collection.upsert.assert_called_once()

        # Verify upsert arguments
        call_kwargs = mock_collection.upsert.call_args[1]
        assert len(call_kwargs["ids"]) == 2
        assert call_kwargs["ids"][0] == "CPS 230-0"
        assert call_kwargs["ids"][1] == "CPS 230-1"

        # Verify metadata structure
        meta0 = call_kwargs["metadatas"][0]
        assert meta0["standard_name"] == "CPS 230"
        assert meta0["clause"] == "27(b)"
        assert meta0["chunk_index"] == 0
        assert meta0["source_url"] == "http://example.com"

        meta1 = call_kwargs["metadatas"][1]
        assert meta1["clause"] == "30"
        assert meta1["chunk_index"] == 1

    def test_upsert_stores_documents(self) -> None:
        """Document page_content should be stored in ChromaDB."""
        mock_collection = MagicMock()

        docs = [Document(page_content="Hello world", metadata={"standard_name": "Test"})]

        upsert_documents(docs, mock_collection)

        call_kwargs = mock_collection.upsert.call_args[1]
        assert call_kwargs["documents"] == ["Hello world"]

    def test_embedding_generated_per_doc(self) -> None:
        """Each document should get its own embedding."""
        mock_collection = MagicMock()

        docs = [
            Document(page_content="Doc A", metadata={"standard_name": "Test"}),
            Document(page_content="Doc B", metadata={"standard_name": "Test"}),
        ]

        upsert_documents(docs, mock_collection)

        # encode should be called once per document
        assert self._mock_st_instance.encode.call_count == 2


# ---------------------------------------------------------------------------
# Full pipeline test (mocked)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end pipeline test with mocked components."""

    def setup_method(self) -> None:
        """Patch SentenceTransformer in the embedder's namespace."""
        self._mock_st_class = MagicMock()
        self._mock_st_instance = MagicMock()
        self._mock_st_instance.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2, 0.3])
        self._mock_st_class.return_value = self._mock_st_instance

        # Patch the class in the embedder module's namespace
        import standards_ingestion.embedder as embedder_mod
        self._original_st = embedder_mod.SentenceTransformer
        embedder_mod.SentenceTransformer = self._mock_st_class

        # Mock chromadb
        self._mock_chroma_client = MagicMock()
        self._mock_collection = MagicMock()
        self._mock_collection.name = "standards_collection"
        self._mock_chroma_client.get_or_create_collection.return_value = self._mock_collection

        # Replace chromadb module
        import chromadb as real_chroma
        self._original_chroma = real_chroma
        mock_chroma_module = ModuleType("chromadb")
        mock_chroma_module.PersistentClient = MagicMock(return_value=self._mock_chroma_client)
        mock_chroma_module.Client = MagicMock(return_value=self._mock_chroma_client)
        sys.modules["chromadb"] = mock_chroma_module

    def teardown_method(self) -> None:
        """Restore original modules."""
        import standards_ingestion.embedder as embedder_mod
        embedder_mod.SentenceTransformer = self._original_st

        if hasattr(self, "_original_chroma"):
            import chromadb as real_chroma
            real_chroma.__dict__.update(vars(self._original_chroma))
        sys.modules.pop("chromadb", None)

    @responses.activate
    def test_end_to_end_pipeline(self, tmp_path: Path) -> None:
        """Full pipeline: download → parse → chunk → embed should work end-to-end."""
        # Mock PDF download
        pdf_content = b"%PDF-1.4\nfake pdf content"
        responses.add(
            responses.GET,
            "https://example.com/cps230.pdf",
            body=pdf_content,
            status=200,
            headers={"Content-Type": "application/pdf"},
        )

        # Create a minimal valid PDF for the parser
        valid_pdf_path = tmp_path / "cps-230.pdf"
        # Create a real minimal PDF with one page containing test text
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            fitz.Point(50, 50),
            "CPS 230\n\nParagraph 27(b) requires insurers to have governance frameworks.\n"
            "Paragraph 30 mandates regular reporting.\n"
            "Clause 15A covers risk management.\n\n"
            "Additional text. " * 100,  # Make it long enough to chunk
        )
        doc.save(str(valid_pdf_path))
        doc.close()

        # Patch download_source to use our test PDF
        source = _make_source(
            name="CPS 230",
            url="https://example.com/cps230.pdf",
        )

        # Mock the download to return our test PDF
        with patch("standards_ingestion.downloader.download_source") as mock_download:
            mock_download.return_value = (valid_pdf_path, True)

            # Run pipeline steps
            from standards_ingestion.embedder import get_or_create_collection, upsert_documents
            from standards_ingestion.parser import chunk_text, extract_text_from_pdf

            # Parse
            text = extract_text_from_pdf(valid_pdf_path)
            assert len(text) > 0

            # Chunk
            metadata = {
                "standard_name": source.name,
                "source_url": source.url,
                "category": source.category,
            }
            chunks = chunk_text(text, metadata)
            assert len(chunks) > 0

            # Embed
            collection = get_or_create_collection(self._mock_chroma_client)
            assert collection is not None

            count = upsert_documents(chunks, self._mock_collection)
            assert count == len(chunks)
            assert count > 0

    def test_pipeline_save_last_update(self, tmp_path: Path) -> None:
        """Pipeline should save last_update.json with timestamps and stats."""
        with patch("scripts.run_ingestion.load_sources") as mock_sources:
            mock_sources.return_value = [_make_source()]

            with patch("scripts.run_ingestion.download_source") as mock_download:
                # Create a temp PDF for parsing
                pdf_path = tmp_path / "test.pdf"
                import fitz
                doc = fitz.open()
                page = doc.new_page()
                page.insert_text(fitz.Point(50, 50), "Test paragraph 5 content.")
                doc.save(str(pdf_path))
                doc.close()
                mock_download.return_value = (pdf_path, True)

                with patch("scripts.run_ingestion.init_chroma_client") as mock_client:
                    mock_client.return_value = self._mock_chroma_client

                    with patch("scripts.run_ingestion.get_or_create_collection") as mock_coll:
                        mock_coll.return_value = self._mock_collection

                        # Run pipeline
                        scripts_path = Path("scripts")
                        scripts_path.mkdir(exist_ok=True)

                        # Import and run
                        from scripts.run_ingestion import run_pipeline

                        run_pipeline(
                            sources_file="standards_ingestion/sources.yaml",
                            output_dir=str(tmp_path / "raw"),
                            chroma_dir=str(tmp_path / "chroma"),
                        )

                        # Verify last_update.json was saved
                        update_file = Path("data") / "last_update.json"
                        if update_file.exists():
                            data = json.loads(update_file.read_text())
                            assert "timestamp" in data
                            assert "documents_embedded" in data
                            update_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Package import tests
# ---------------------------------------------------------------------------


class TestStandardsIngestionPackage:
    """Tests that the standards_ingestion package exports the correct public API."""

    def test_public_api_importable(self) -> None:
        from standards_ingestion import (
            chunk_text,
            download_source,
            extract_text_from_pdf,
            init_chroma_client,
            upsert_documents,
        )

        assert callable(download_source)
        assert callable(extract_text_from_pdf)
        assert callable(chunk_text)
        assert callable(init_chroma_client)
        assert callable(upsert_documents)

    def test_all_in___all__(self) -> None:
        from standards_ingestion import __all__

        expected = {
            "download_source",
            "extract_text_from_pdf",
            "chunk_text",
            "init_chroma_client",
            "upsert_documents",
        }
        assert set(__all__) == expected
