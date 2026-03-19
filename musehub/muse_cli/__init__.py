"""Minimal muse_cli stub retained for MuseHub compatibility.

The full Muse CLI was extracted to cgcardona/muse.
This package provides only the ORM models and DB helpers that MuseHub
reads directly from the muse_commits / muse_snapshots tables.

TODO(musehub-extraction): remove this package when MuseHub is extracted.
"""

from musehub.db import muse_cli_models as models  # noqa: F401 — register tables

__all__ = ["models"]
