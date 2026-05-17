"""Standards management page for the Compliance Gap Analyser.

Renders a full CRUD interface for managing compliance standards — both
built-in (from ``sources.yaml``) and custom (from ``data/custom_standards.yaml``).

Supports:
- Listing all standards in a styled table
- Adding new custom standards
- Editing custom standards inline
- Deleting custom standards (with confirmation)
- Replacing built-in standards with custom entries
- Refreshing the standards list

Session state keys used:
    sm_add_form: bool — show/hide add form
    sm_edit_name: str | None — which standard is being edited
    sm_delete_confirm: str | None — which standard is pending deletion
    sm_replace_name: str | None — which built-in standard is being replaced
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

import streamlit as st
import yaml

from standards_ingestion.custom_loader import load_custom_standards

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Paths
# ------------------------------------------------------------------

_CUSTOM_STANDARDS_PATH = Path(__file__).resolve().parent.parent / "data" / "custom_standards.yaml"

# ------------------------------------------------------------------
# Category badge colours
# ------------------------------------------------------------------

_CATEGORY_COLORS: dict[str, dict[str, str]] = {
    "APRA": {"bg": "#1a3a4a", "fg": "#64b5f6"},
    "AASB": {"bg": "#1b3a2a", "fg": "#81c784"},
    "IFRS": {"bg": "#3e2c1a", "fg": "#ffb74d"},
}

_TYPE_BADGES = {
    "built-in": {"bg": "#37474f", "fg": "#b0bec5", "label": "Built-in"},
    "custom": {"bg": "#004d40", "fg": "#4db6ac", "label": "Custom"},
}

# ------------------------------------------------------------------
# Data helpers
# ------------------------------------------------------------------


def _load_builtin_sources() -> list[dict[str, Any]]:
    """Load built-in standards from ``sources.yaml``."""
    _sources_path = Path(__file__).resolve().parent.parent / "standards_ingestion" / "sources.yaml"
    if not _sources_path.exists():
        return []
    try:
        with open(_sources_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return cast("list[dict[str, Any]]", data.get("sources", []) or [])
    except Exception as exc:
        logger.warning("Failed to load sources.yaml: %s", exc)
        return []


def _load_all_standards() -> list[dict[str, Any]]:
    """Load and merge built-in + custom standards.

    Built-in sources appear first, then custom. If a custom source shares
    the same name as a built-in, the custom entry overrides it.

    Returns:
        Merged list of source dicts. Each dict has a ``_type`` key added
        to indicate whether it is ``"built-in"`` or ``"custom"``.
    """
    builtin = _load_builtin_sources()
    custom = load_custom_standards()

    # Tag built-in
    for src in builtin:
        src["_type"] = "built-in"

    # Tag custom
    for src in custom:
        src["_type"] = "custom"

    # Merge: built-in first, custom overrides on name conflict
    seen: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for src in builtin:
        name = src.get("name")
        if name and name not in seen:
            seen[name] = src
            order.append(name)

    for src in custom:
        name = src.get("name")
        if name:
            if name not in seen:
                order.append(name)
            seen[name] = src

    return [seen[n] for n in order]


def _save_custom_standards(standards: list[dict[str, Any]]) -> bool:
    """Write custom standards to ``data/custom_standards.yaml``.

    Only writes the custom entries (those with ``_type == "custom"``),
    stripping the internal ``_type`` key from the output.

    Returns:
        ``True`` on success, ``False`` on failure.
    """
    try:
        # Only write custom entries, strip internal keys
        clean: list[dict[str, Any]] = []
        for src in standards:
            if src.get("_type") != "custom":
                continue
            entry = {k: v for k, v in src.items() if not k.startswith("_")}
            clean.append(entry)

        _CUSTOM_STANDARDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_CUSTOM_STANDARDS_PATH, "w", encoding="utf-8") as fh:
            yaml.dump({"sources": clean}, fh, default_flow_style=False, sort_keys=False)
        return True
    except Exception as exc:
        logger.error("Failed to save custom_standards.yaml: %s", exc)
        st.error(f"Failed to save: {exc}")
        return False


def _category_badge_html(category: str) -> str:
    """Return an HTML span badge for a category value."""
    colors = _CATEGORY_COLORS.get(category, {"bg": "#37474f", "fg": "#b0bec5"})
    return (
        f"<span style='background:{colors['bg']};color:{colors['fg']};"
        f"padding:2px 10px;border-radius:10px;font-size:0.75em;font-weight:600;"
        f"letter-spacing:0.03em;'>{category}</span>"
    )


def _type_badge_html(stype: str) -> str:
    """Return an HTML span badge for a source type."""
    info = _TYPE_BADGES.get(stype, _TYPE_BADGES["custom"])
    return (
        f"<span style='background:{info['bg']};color:{info['fg']};"
        f"padding:2px 10px;border-radius:10px;font-size:0.75em;font-weight:600;"
        f"letter-spacing:0.03em;'>{info['label']}</span>"
    )


# ------------------------------------------------------------------
# Form helpers
# ------------------------------------------------------------------


def _render_source_form(
    title: str,
    initial: dict[str, Any] | None = None,
    on_save: Any | None = None,
    on_cancel: Any | None = None,
) -> None:
    """Render a compact source form inside an expander.

    Args:
        title: Expander title.
        initial: Pre-filled values dict with ``name``, ``url``, ``category``, ``summary``.
        on_save: Callable invoked when Save is clicked.
        on_cancel: Callable invoked when Cancel is clicked.
    """
    data = initial or {}

    with st.expander(title, expanded=True):
        name = st.text_input("Name", value=data.get("name", ""), key="sm_form_name")
        url = st.text_input("URL", value=data.get("url", ""), key="sm_form_url")
        category = st.text_input("Category", value=data.get("category", ""), key="sm_form_category")
        summary = st.text_area(
            "Summary",
            value=data.get("summary", ""),
            height=80,
            key="sm_form_summary",
        )

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("Save", type="primary", use_container_width=True):
                if on_save:
                    on_save(name, url, category, summary)
        with col2:
            if st.button("Cancel", use_container_width=True):
                if on_cancel:
                    on_cancel()


def _render_add_form() -> None:
    """Render the Add Standard form."""
    if st.session_state.get("sm_add_form"):

        def on_save(name: str, url: str, category: str, summary: str) -> None:
            if not name.strip():
                st.error("Name is required.")
                return
            new_entry: dict[str, Any] = {
                "name": name.strip(),
                "url": url.strip(),
                "category": category.strip() or "Other",
                "summary": summary.strip(),
                "_type": "custom",
            }
            all_standards = _load_all_standards()
            all_standards.append(new_entry)
            if _save_custom_standards(all_standards):
                st.success(f"Standard '{name.strip()}' added successfully.")
                st.session_state.sm_add_form = False
                st.rerun()

        def on_cancel() -> None:
            st.session_state.sm_add_form = False
            st.rerun()

        _render_source_form(
            "\u2795  Add New Standard",
            on_save=on_save,
            on_cancel=on_cancel,
        )


def _render_edit_form(standard: dict[str, Any]) -> None:
    """Render the inline edit form for a custom standard."""
    edit_name = st.session_state.sm_edit_name

    def on_save(name: str, url: str, category: str, summary: str) -> None:
        if not name.strip():
            st.error("Name is required.")
            return
        all_standards = _load_all_standards()
        for src in all_standards:
            if src.get("name") == edit_name and src.get("_type") == "custom":
                src["name"] = name.strip()
                src["url"] = url.strip()
                src["category"] = category.strip() or "Other"
                src["summary"] = summary.strip()
                break
        if _save_custom_standards(all_standards):
            st.success(f"Standard '{edit_name}' updated successfully.")
            st.session_state.sm_edit_name = None
            st.rerun()

    def on_cancel() -> None:
        st.session_state.sm_edit_name = None
        st.rerun()

    _render_source_form(
        f"\u270E  Edit: {edit_name}",
        initial={
            "name": standard.get("name", ""),
            "url": standard.get("url", ""),
            "category": standard.get("category", ""),
            "summary": standard.get("summary", ""),
        },
        on_save=on_save,
        on_cancel=on_cancel,
    )


def _render_replace_form(standard: dict[str, Any]) -> None:
    """Render the replace form — replaces a built-in standard with a custom entry."""
    rep_name = st.session_state.sm_replace_name

    def on_save(name: str, url: str, category: str, summary: str) -> None:
        if not name.strip():
            st.error("Name is required.")
            return
        new_entry: dict[str, Any] = {
            "name": name.strip(),
            "url": url.strip(),
            "category": category.strip() or "Other",
            "summary": summary.strip(),
            "_type": "custom",
        }
        all_standards = _load_all_standards()
        # Remove the old built-in entry with this name
        all_standards = [s for s in all_standards if s.get("name") != rep_name]
        # Insert custom entry at the same position
        all_standards.append(new_entry)
        if _save_custom_standards(all_standards):
            st.success(f"Built-in standard '{rep_name}' replaced with custom entry.")
            st.session_state.sm_replace_name = None
            st.rerun()

    def on_cancel() -> None:
        st.session_state.sm_replace_name = None
        st.rerun()

    _render_source_form(
        f"\u267b\ufe0f  Replace: {rep_name}",
        initial={
            "name": standard.get("name", ""),
            "url": standard.get("url", ""),
            "category": standard.get("category", ""),
            "summary": standard.get("summary", ""),
        },
        on_save=on_save,
        on_cancel=on_cancel,
    )


# ------------------------------------------------------------------
# Row action buttons
# ------------------------------------------------------------------


def _render_row_actions(standard: dict[str, Any]) -> None:
    """Render action buttons for a single standard row."""
    stype = standard.get("_type", "built-in")
    name = standard.get("name", "")

    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    # Edit — custom only
    with col1:
        if stype == "custom":
            if st.button("\u270E", key=f"edit_{name}", type="secondary", help="Edit"):
                st.session_state.sm_edit_name = name
                st.rerun()

    # Delete — custom only
    with col2:
        if stype == "custom":
            if st.button("\U0001f5d1\ufe0f", key=f"del_{name}", type="secondary", help="Delete"):
                st.session_state.sm_delete_confirm = name
                st.rerun()

    # Replace — built-in only
    with col3:
        if stype == "built-in":
            if st.button("\u267b\ufe0f", key=f"rep_{name}", type="secondary", help="Replace with custom entry"):
                st.session_state.sm_replace_name = name
                st.rerun()

    # Source link — popover (like questionnaire_ui.py pattern)
    with col4:
        url = standard.get("url", "")
        if url:
            with st.popover(f"\U0001f517 Link"):
                st.caption("**Source URL**")
                st.code(url, language=None)
        else:
            st.caption("\u2014")


# ------------------------------------------------------------------
# Main render function
# ------------------------------------------------------------------


def render_standards_manager() -> None:
    """Render the Standards Management page.

    Displays all standards (built-in + custom) in a styled table with
    action buttons for adding, editing, deleting, and replacing standards.
    """
    # -- Initialise session state -------------------------------------------
    if "sm_add_form" not in st.session_state:
        st.session_state.sm_add_form = False
    if "sm_edit_name" not in st.session_state:
        st.session_state.sm_edit_name = None
    if "sm_delete_confirm" not in st.session_state:
        st.session_state.sm_delete_confirm = None
    if "sm_replace_name" not in st.session_state:
        st.session_state.sm_replace_name = None

    # -- Page header --------------------------------------------------------
    st.markdown(
        """
        <div style='padding:20px 24px;background:linear-gradient(135deg,#0d1b2a 0%,#1b2a4a 100%);
        border-radius:12px;margin-bottom:24px;border:1px solid #1e3a5f;'>
        <h2 style='margin:0 0 4px 0;color:#e0e0e0;font-weight:700;'>
        \U0001f4c2  Standards Library
        </h2>
        <p style='margin:0;color:#78909c;font-size:0.9em;'>
        Manage built-in and custom compliance standards. Custom standards are
        stored in <code style='background:#263238;padding:2px 6px;border-radius:4px;'>data/custom_standards.yaml</code>.
        </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -- ChromaDB status message --------------------------------------------
    if "sm_chromadb_status" in st.session_state and st.session_state.sm_chromadb_status:
        msg = st.session_state.sm_chromadb_status
        if msg.get("type") == "success":
            st.success(msg.get("text", ""))
        else:
            st.error(msg.get("text", ""))
        del st.session_state.sm_chromadb_status

    # -- Top bar: Add + Populate ChromaDB + Refresh -------------------------
    col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
    with col1:
        if st.button("\u2795  Add Standard", type="primary", use_container_width=True):
            st.session_state.sm_add_form = True
            st.rerun()
    with col2:
        if st.button("\U0001f4be  Populate ChromaDB", type="secondary", use_container_width=True):
            success, msg = _populate_chromadb()
            st.session_state.sm_chromadb_status = {
                "type": "success" if success else "error",
                "text": msg,
            }
            st.rerun()
    with col3:
        if st.button("\U0001f504  Refresh", use_container_width=True):
            st.session_state.sm_add_form = False
            st.session_state.sm_edit_name = None
            st.session_state.sm_delete_confirm = None
            st.session_state.sm_replace_name = None
            st.rerun()

    # -- Active forms (rendered before table) -------------------------------
    # Add form
    if st.session_state.sm_add_form:
        _render_add_form()

    # Edit form
    if st.session_state.sm_edit_name:
        all_standards = _load_all_standards()
        for src in all_standards:
            if src.get("name") == st.session_state.sm_edit_name:
                _render_edit_form(src)
                break

    # Delete confirmation
    if st.session_state.sm_delete_confirm:
        del_name = st.session_state.sm_delete_confirm
        st.warning(f"Are you sure you want to delete **{del_name}**?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes, Delete", type="primary", use_container_width=True):
                all_standards = _load_all_standards()
                filtered = [
                    s for s in all_standards
                    if s.get("name") != del_name or s.get("_type") != "custom"
                ]
                if _save_custom_standards(filtered):
                    st.success(f"Standard '{del_name}' deleted.")
                    st.session_state.sm_delete_confirm = None
                    st.rerun()
        with col2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.sm_delete_confirm = None
                st.rerun()

    # Replace form
    if st.session_state.sm_replace_name:
        all_standards = _load_all_standards()
        for src in all_standards:
            if src.get("name") == st.session_state.sm_replace_name:
                _render_replace_form(src)
                break

    # -- Load standards -----------------------------------------------------
    all_standards = _load_all_standards()

    if not all_standards:
        st.info("\U0001f4d6 No standards found. Add a custom standard to get started.")
        return

    # -- Summary stats ------------------------------------------------------
    builtin_count = sum(1 for s in all_standards if s.get("_type") == "built-in")
    custom_count = sum(1 for s in all_standards if s.get("_type") == "custom")

    stats_col1, stats_col2, stats_col3 = st.columns(3)
    with stats_col1:
        st.metric("\U0001f4c2 Total Standards", len(all_standards))
    with stats_col2:
        st.metric("\U0001f517 Built-in", builtin_count)
    with stats_col3:
        st.metric("\u2728 Custom", custom_count)

    st.divider()

    # -- Standards table ----------------------------------------------------
    st.subheader("\U0001f4da  All Standards")

    for idx, standard in enumerate(all_standards):
        name = standard.get("name", "Unnamed")
        category = standard.get("category", "Other")
        summary = standard.get("summary", "")
        stype = standard.get("_type", "built-in")

        # Row background: subtle alternating
        bg = "#0d1b2a" if idx % 2 == 0 else "#112240"
        border = "1px solid #1e3a5f"

        # Row header
        st.markdown(
            f"""
            <div style='background:{bg};border:{border};border-radius:8px;
            padding:12px 16px;margin-bottom:6px;'>
            <div style='display:flex;align-items:center;gap:12px;flex-wrap:wrap;'>
            <span style='flex:1;min-width:200px;font-weight:600;color:#e0e0e0;
            font-size:0.9em;'>{name}</span>
            {_category_badge_html(category)}
            {_type_badge_html(stype)}
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Summary line (full text, no truncation)
        if summary:
            st.markdown(
                "<div style='padding:0 16px 8px 16px;'><span style='color:#78909c;font-size:0.82em;'>"
                + _escape_html(summary)
                + "</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='padding:0 16px 8px 16px;'><span style='color:#546e7a;font-size:0.82em;font-style:italic;'>No summary</span></div>",
                unsafe_allow_html=True,
            )

        # Action buttons row
        st.markdown("</div>", unsafe_allow_html=True)  # close row div
        _render_row_actions(standard)

        # Row separator
        if idx < len(all_standards) - 1:
            st.divider()

    # -- Refresh button at bottom -------------------------------------------
    st.divider()
    if st.button("\U0001f504  Refresh Standards List", type="secondary", use_container_width=True):
        st.session_state.sm_add_form = False
        st.session_state.sm_edit_name = None
        st.session_state.sm_delete_confirm = None
        st.session_state.sm_replace_name = None
        st.rerun()


def _escape_html(text: str) -> str:
    """Minimal HTML escaping for summary text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _populate_chromadb() -> tuple[bool, str]:
    """Embed all standards (built-in + custom) into ChromaDB.

    Reads sources.yaml and custom_standards.yaml, then upserts each
    standard's summary as a document into the ChromaDB collection.

    Returns:
        Tuple of (success, message).
    """
    try:
        import yaml as _yaml

        from standards_ingestion.embedder import (
            init_chroma_client,
            get_or_create_collection,
        )

        # Load built-in sources
        _sources_path = Path(__file__).resolve().parent.parent / "standards_ingestion" / "sources.yaml"
        if _sources_path.exists():
            with open(_sources_path, "r", encoding="utf-8") as fh:
                _data = _yaml.safe_load(fh)
            sources = _data.get("sources", []) or []
        else:
            sources = []

        # Load custom sources
        custom = load_custom_standards()
        sources.extend(custom)

        if not sources:
            return (False, "No standards found to embed.")

        # Initialize ChromaDB
        client = init_chroma_client()
        collection = get_or_create_collection(client)

        # Upsert each standard as a single document
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, str]] = []

        for src in sources:
            name = src.get("name", "Unknown")
            summary = src.get("summary", "")
            url = src.get("url", "")
            category = src.get("category", "Unknown")

            if not summary:
                continue

            ids.append(f"standard:{name}")
            documents.append(summary)
            metadatas.append({
                "standard_name": name,
                "source_url": url,
                "source_type": "standard",
                "standard_category": category,
            })

        if not ids:
            return (False, "No standards with summaries found to embed.")

        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)  # type: ignore[arg-type]
        return (True, f"Embedded {len(ids)} standards into ChromaDB.")

    except Exception as exc:
        logger.error("Failed to populate ChromaDB: %s", exc)
        return (False, f"Error: {exc}")
