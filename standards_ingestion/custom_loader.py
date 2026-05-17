"""Load custom standards from a YAML file.

Provides ``load_custom_standards()`` which reads ``data/custom_standards.yaml``
and returns a list of source dicts.  Missing or invalid files are handled
gracefully (empty list is returned).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

CUSTOM_STANDARDS_PATH = Path(__file__).resolve().parent.parent / "data" / "custom_standards.yaml"


def load_custom_standards() -> list[dict[str, Any]]:
    """Load custom standards sources from ``data/custom_standards.yaml``.

    Returns:
        List of source dicts with at least ``name``, ``url``, ``category``,
        and ``summary`` keys.  Returns an empty list if the file is missing
        or contains no sources.
    """
    if not CUSTOM_STANDARDS_PATH.exists():
        return []
    try:
        with open(CUSTOM_STANDARDS_PATH, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data.get("sources", []) or []  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("Failed to load custom_standards.yaml: %s", exc)
        return []
