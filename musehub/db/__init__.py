"""
Database module for MuseHub.

Provides async SQLAlchemy support with PostgreSQL and SQLite.
"""

from musehub.db.database import (
    get_db,
    init_db,
    close_db,
    AsyncSessionLocal,
)
from musehub.db.models import User, AccessToken
from musehub.db import muse_cli_models as muse_cli_models  # noqa: F401 — register CLI commit tables with Base
from musehub.db import musehub_models as musehub_models  # noqa: F401 — register with Base
from musehub.db import musehub_label_models as musehub_label_models  # noqa: F401 — register with Base
from musehub.db import musehub_collaborator_models as musehub_collaborator_models  # noqa: F401 — register with Base
from musehub.db import musehub_stash_models as musehub_stash_models  # noqa: F401 — register with Base

__all__ = [
    "get_db",
    "init_db",
    "close_db",
    "AsyncSessionLocal",
    "User",
    "AccessToken",
]
