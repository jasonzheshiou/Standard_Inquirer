"""Session persistence for dynamic questionnaires.

Manages saving, loading, listing, and deleting questionnaire sessions
as individual JSON files under ``data/sessions/``.

Session file format::

    {
      "session_id": "uuid",
      "created_at": "ISO timestamp",
      "organization_type": "life_insurer",
      "user_input": "original free-text input",
      "questionnaire": {...},
      "answers": {...},
      "generated_at": "ISO timestamp"
    }

No database is used — each session is a self-contained JSON file.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.schemas import Questionnaire

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path("data/sessions")


# ---------------------------------------------------------------------------
# save_session
# ---------------------------------------------------------------------------

def save_session(
    answers: dict[str, Any],
    questionnaire: Questionnaire,
    session_id: str | None = None,
    organization_type: str | None = None,
    user_input: str | None = None,
) -> str:
    """Persist a questionnaire session to disk.

    Args:
        answers: Mapping of question IDs to user answers.
        questionnaire: Full ``Questionnaire`` model to persist.
        session_id: Optional session identifier (UUID string).
            A new UUID is generated when *None*.
        organization_type: Classification of the organisation
            (e.g. ``"life_insurer"``).
        user_input: Original free-text input used to generate the
            questionnaire.

    Returns:
        The (possibly generated) session ID.
    """
    sid = session_id or str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Serialize questionnaire via Pydantic model_dump_json()
    questionnaire_data = json.loads(questionnaire.model_dump_json())

    session_data: dict[str, Any] = {
        "session_id": sid,
        "created_at": now,
        "organization_type": organization_type,
        "user_input": user_input,
        "questionnaire": questionnaire_data,
        "answers": answers,
        "generated_at": now,
    }

    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{sid}.json"

    path.write_text(json.dumps(session_data, indent=2), encoding="utf-8")
    logger.info("Saved session %s to %s", sid, path)
    return sid


# ---------------------------------------------------------------------------
# load_session
# ---------------------------------------------------------------------------

def load_session(session_id: str) -> dict[str, Any]:
    """Load a questionnaire session from disk.

    Args:
        session_id: The session file identifier (filename without .json).

    Returns:
        Dict with keys ``"answers"`` (dict) and ``"questionnaire"``
        (``Questionnaire`` model).

    Raises:
        FileNotFoundError: When the session file does not exist.
        ValueError: When the file is invalid JSON.
    """
    path = SESSIONS_DIR / f"{session_id}.json"

    if not path.exists():
        raise FileNotFoundError(f"Session not found: {session_id}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid session file: {session_id}") from exc

    # Reconstruct Questionnaire from dict via Pydantic model_validate_json()
    questionnaire = Questionnaire.model_validate_json(
        json.dumps(data["questionnaire"])
    )

    return {
        "answers": data["answers"],
        "questionnaire": questionnaire,
    }


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

def list_sessions() -> list[dict[str, Any]]:
    """Return metadata for every session file in ``data/sessions/``.

    Returns:
        List of dicts with keys:
            ``id`` (str), ``created_at`` (str | None),
            ``organization_type`` (str | None),
            ``user_input`` (str | None).
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    sessions: list[dict[str, Any]] = []

    for file in sorted(SESSIONS_DIR.glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping unreadable session %s: %s", file.name, exc)
            continue

        sessions.append({
            "id": data.get("session_id") or file.stem,
            "created_at": data.get("created_at"),
            "organization_type": data.get("organization_type"),
            "user_input": data.get("user_input"),
        })

    return sessions


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------

def delete_session(session_id: str) -> bool:
    """Delete a session file.

    Args:
        session_id: The session file identifier.

    Returns:
        ``True`` when the file was removed, ``False`` when it did not
        exist.
    """
    path = SESSIONS_DIR / f"{session_id}.json"

    if not path.exists():
        return False

    path.unlink()
    logger.info("Deleted session %s", session_id)
    return True
