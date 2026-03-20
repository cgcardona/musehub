"""Clean REST API — /api/...

Routes are mounted without a version prefix since MuseHub has one canonical API.
This package replaces the /api/v1 pattern — if the API ever needs to break,
a new package is created and old routes remain until clients migrate.

Routers exported here are mounted in main.py under /api.
"""
from musehub.api.routes.api import repos, identities, search

__all__ = ["repos", "identities", "search"]
