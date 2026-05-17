# Admin Page

The Admin page (`ui/admin.py`) provides standards ingestion controls, ChromaDB status display, and last update timestamp information.

## Function

### `render_admin() -> None`

Render the admin panel with ingestion controls and status.

## Page Content

### Status Display

#### Last Update Timestamp

```python
last_update = _get_last_update()
if last_update:
    st.info(f"Last standards update: {last_update}")
else:
    st.info("No previous update recorded.")
```

Reads from `data/last_update.json`.

#### ChromaDB Chunk Count

```python
chunk_count = _get_chunk_count()
if chunk_count is not None:
    st.metric("ChromaDB Chunks", chunk_count)
else:
    st.info("ChromaDB not yet initialized.")
```

Queries the ChromaDB collection count via `collection.count()`.

### Ingestion Controls

A button triggers the full ingestion pipeline:

```python
if st.button("Update Standards Now", type="primary"):
    with st.spinner("Running ingestion pipeline..."):
        status = st.status("In Progress", expanded=True)
        with status:
            messages = _run_ingestion_pipeline()
            for msg in messages:
                st.write(msg)
        status.update(label="Complete", state="complete")
```

### Ingestion Log

If `data/ingestion.log` exists, it is displayed as a code block:

```python
log_path = Path("data/ingestion.log")
if log_path.exists():
    st.subheader("Ingestion Log")
    log_content = log_path.read_text(encoding="utf-8")
    st.code(log_content, language="text")
```

## Pipeline Execution

The `_run_ingestion_pipeline()` function runs the full pipeline:

1. **Load sources** — Read `standards_ingestion/sources.yaml`
2. **Initialize ChromaDB** — Create/retrieve collection
3. **For each source:**
   - Download PDF → `download_source()`
   - Extract text → `extract_text_from_pdf()`
   - Chunk → `chunk_text()`
   - Embed → `upsert_documents()`
4. **Save timestamp** → `data/last_update.json`

The pipeline gracefully handles errors at each stage — a failure for one source does not stop processing of subsequent sources.

## Helper Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `_get_last_update()` | Read last update timestamp | `str | None` |
| `_get_chunk_count()` | Query ChromaDB chunk count | `int | None` |
| `_run_ingestion_pipeline()` | Run full pipeline | `list[str]` log messages |

## Error Handling

All pipeline stages are wrapped in try/except blocks. Errors are logged as messages and displayed in the UI without stopping the pipeline:

```python
try:
    pdf_path, was_updated = download_source(src)
except Exception as exc:
    messages.append(f"Download error for {src.name}: {exc}")
    st.write(f"  ⚠ {exc}")
    continue  # Skip to next source
```
