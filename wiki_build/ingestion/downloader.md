# Downloader

The `standards_ingestion.downloader` module provides PDF document downloading with ETag / Last-Modified conditional GET support.

## Function

### `download_source(source: StandardsSource, output_dir: str = "data/raw_pdfs/") -> tuple[Path, bool]`

Download a standards PDF with ETag / Last-Modified support.

**Parameters:**
- `source` — The `StandardsSource` configuration object
- `output_dir` — Directory to save the downloaded PDF (default: `data/raw_pdfs/`)

**Returns:** A tuple of `(file_path, was_updated)` where `was_updated` indicates whether a new download occurred.

**Raises:** `StandardsDownloadError` if the download fails or the response is not a successful PDF download.

## How It Works

1. **Slug generation** — Converts the source name to a file-safe slug (e.g., "CPS 230" → "cps-230")
2. **Conditional GET** — If a `.pdf.meta` companion file exists, reads stored ETag or Last-Modified header and sends `If-None-Match` or `If-Modified-Since`
3. **304 handling** — If the server returns 304 Not Modified, the existing file is reused
4. **Validation** — Checks that the response Content-Type contains "pdf"
5. **Streaming save** — Downloads in 8KB chunks to handle large PDFs
6. **Metadata storage** — Saves ETag and Last-Modified headers to `.pdf.meta` for future conditional requests

## Slug Generation

The `slugify()` function converts source names to file-safe slugs:

```python
from standards_ingestion.downloader import slugify

slugify("CPS 230")        # → "cps-230"
slugify("ASX Listing Rules")  # → "asx-listing-rules"
slugify("AI PS 400")      # → "ai-ps-400"
```

## Error Handling

```python
from standards_ingestion.downloader import StandardsDownloadError, download_source

try:
    path, updated = download_source(source)
except StandardsDownloadError as exc:
    logger.error(f"Download failed: {exc}")
```

## File Output

For a source named "CPS 230", the following files are created:

| File | Purpose |
|------|---------|
| `data/raw_pdfs/cps-230.pdf` | Downloaded PDF document |
| `data/raw_pdfs/cps-230.pdf.meta` | ETag/Last-Modified metadata for conditional GET |
