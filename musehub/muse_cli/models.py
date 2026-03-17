"""Re-exports of Muse CLI ORM models for MuseHub compatibility.

The canonical definitions now live in musehub.db.muse_cli_models.
This module exists only so that MuseHub code and tests can keep importing
from the original path while MuseHub extraction is pending.

TODO(musehub-extraction): remove when MuseHub is extracted to its own repo.
"""
from __future__ import annotations

from musehub.db.muse_cli_models import (
    MuseCliObject,
    MuseCliSnapshot,
    MuseCliCommit,
    MuseCliTag,
)

__all__ = [
    "MuseCliObject",
    "MuseCliSnapshot",
    "MuseCliCommit",
    "MuseCliTag",
]
