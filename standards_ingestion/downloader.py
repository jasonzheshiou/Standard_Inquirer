"""PDF standard document downloader with ETag/Last-Modified support.

Downloads prudential standard PDFs from external URLs using ``requests``
with polite headers and conditional GET support (ETag /
Last-Modified) to avoid re-downloading unchanged documents.

Usage::

    from standards_ingestion.downloader import download_source
    from engine.schemas import StandardsSource

    source = StandardsSource(
        name="CPS 230",
        url="https://www.apra.gov.au/...",
        category="APRA",
    )
    path, updated = download_source(source, output_dir="data/raw_pdfs/")
"""

from __future__ import annotations

import re
from pathlib import Path

import requests
from engine.schemas import StandardsSource


class StandardsDownloadError(Exception):
    """Raised when a standards document download fails."""


def slugify(name: str) -> str:
    """Convert a source name to a file-safe slug.

    Examples:
        >>> slugify("CPS 230")
        'cps-230'
        >>> slugify("ASX Listing Rules")
        'asx-listing-rules'

    Args:
        name: Human-readable source name.

    Returns:
        Lowercase slug with hyphens replacing spaces and non-alphanumeric
        characters removed (except hyphens).
    """
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+$", "", slug)
    return slug


def download_source(
    source: StandardsSource,
    output_dir: str = "data/raw_pdfs/",
) -> tuple[Path, bool]:
    """Download a standards PDF with ETag / Last-Modified support.

    Uses a ``requests.Session`` to perform a conditional GET.  If the
    remote server returns ``304 Not Modified`` the existing file is
    reused and ``was_updated`` is ``False``.

    Args:
        source: The standards source configuration.
        output_dir: Directory to save the downloaded PDF.

    Returns:
        A tuple of ``(file_path, was_updated)`` where ``was_updated``
        indicates whether a new download occurred.

    Raises:
        StandardsDownloadError: If the download fails or the response
            is not a successful PDF download.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    slug = slugify(source.name)
    file_path = output_path / f"{slug}.pdf"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "ComplianceGapAnalyser/1.0",
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
    })

    # Build conditional request headers if file already exists
    headers: dict[str, str] = {}
    if file_path.exists():
        # Try to read stored ETag / Last-Modified from a companion file
        meta_path = file_path.with_suffix(".pdf.meta")
        if meta_path.exists():
            try:
                meta = meta_path.read_text(encoding="utf-8").strip()
                if meta.startswith("ETag:"):
                    headers["If-None-Match"] = meta.split(":", 1)[1].strip()
                elif meta.startswith("Last-Modified:"):
                    headers["If-Modified-Since"] = meta.split(":", 1)[1].strip()
            except OSError:
                pass  # Corrupt meta file — start fresh

    try:
        response = session.get(source.url, headers=headers, timeout=120, stream=True)
    except requests.RequestException as exc:
        raise StandardsDownloadError(
            f"Failed to connect to {source.url}: {exc}"
        ) from exc

    # Handle 304 Not Modified
    if response.status_code == 304:
        return (file_path, False)

    # Handle errors
    if response.status_code != 200:
        raise StandardsDownloadError(
            f"Download failed for {source.name}: HTTP {response.status_code}"
        )

    # Validate content type — accept PDF or HTML
    content_type = response.headers.get("Content-Type", "").lower()
    is_pdf = "pdf" in content_type
    is_html = "html" in content_type

    if not is_pdf and not is_html:
        raise StandardsDownloadError(
            f"Expected PDF or HTML but got Content-Type: {content_type}"
        )

    # Save the document
    try:
        if is_pdf:
            ext = ".pdf"
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        else:
            # HTML — save as .html
            html_path = file_path.with_suffix(".html")
            html_path.write_text(response.text, encoding="utf-8")
            return (html_path, True)
    except OSError as exc:
        raise StandardsDownloadError(
            f"Failed to write document to {file_path}: {exc}"
        ) from exc

    # Store metadata for future conditional requests
    meta_path = file_path.with_suffix(".pdf.meta")
    try:
        meta_lines: list[str] = []
        etag = response.headers.get("ETag")
        if etag:
            meta_lines.append(f"ETag: {etag}")
        last_modified = response.headers.get("Last-Modified")
        if last_modified:
            meta_lines.append(f"Last-Modified: {last_modified}")
        if meta_lines:
            meta_path.write_text("\n".join(meta_lines), encoding="utf-8")
    except OSError:
        pass  # Meta file is optional

    return (file_path, True)
