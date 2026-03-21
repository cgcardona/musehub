"""Shared rate-limiter instance for MuseHub.

Importing ``limiter`` here (rather than from ``main``) breaks the
circular-import chain: ``main`` registers the limiter with the app,
route modules import it from here, and ``main`` imports it from here too.

Limits are read from :class:`~musehub.config.Settings` so they can be
overridden via environment variables without touching code:

  MCP_RATE_LIMIT_HUMAN      (default: 60/minute)
  MCP_RATE_LIMIT_AGENT      (default: 600/minute)
  MCP_RATE_LIMIT_ANONYMOUS  (default: 20/minute)
  ASSET_RATE_LIMIT_PER_IP   (default: 120/minute)

Wire endpoints (push/fetch) use a conservative fixed limit.
Auth endpoints use a fixed per-IP limit to slow credential-stuffing.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from musehub.config import settings

limiter = Limiter(key_func=get_remote_address)

# ── Convenience limit strings (resolved at module load from config) ──────────

# Wire protocol — push is expensive (disk + DB); cap tightly per IP.
WIRE_PUSH_LIMIT: str = "30/minute"
# Fetch/refs are cheaper but can still exhaust DB; moderately capped.
WIRE_FETCH_LIMIT: str = "120/minute"
# MCP POST endpoint — different caps by caller type; use the most
# permissive (agent) as the global cap; per-tool limits added later.
MCP_LIMIT: str = settings.mcp_rate_limit_agent
# Auth endpoints — protect against credential stuffing.
AUTH_LIMIT: str = "20/minute"
# Search — can trigger Qdrant; cap to protect the embedding service.
SEARCH_LIMIT: str = "60/minute"
