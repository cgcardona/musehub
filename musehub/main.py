"""
MuseHub API

Standalone FastAPI application for the music composition version control platform.
GitHub for music — push commits, open pull requests, track issues, publish releases.
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Awaitable, Callable

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from musehub.config import settings
from musehub.api.routes.musehub import (
    ui as musehub_ui_routes,
    ui_milestones as musehub_ui_milestones_routes,
    ui_stash as musehub_ui_stash_routes,
    ui_blame as musehub_ui_blame_routes,
    ui_notifications as musehub_ui_notifications_routes,
    ui_collaborators as musehub_ui_collab_routes,
    ui_labels as musehub_ui_labels_routes,
    ui_settings as musehub_ui_settings_routes,
    ui_topics as musehub_ui_topics_routes,
    ui_forks as musehub_ui_forks_routes,
    ui_user_profile as musehub_ui_profile_routes,
    ui_mcp_elicitation as musehub_ui_mcp_elicitation_routes,
    ui_new_repo as musehub_ui_new_repo_routes,
    ui_domains as musehub_ui_domains_routes,
    domains as musehub_domains_routes,
    discover as musehub_discover_routes,
    users as musehub_user_routes,
    oembed as musehub_oembed_routes,
    raw as musehub_raw_routes,
    sitemap as musehub_sitemap_routes,
)
from musehub.api.routes import musehub as musehub_router_pkg
from musehub.api.routes.mcp import router as mcp_router
from musehub.api.routes.musehub.ui_view import insights_router as musehub_ui_insights_router
from musehub.api.routes.musehub.ui_view import redirect_router as musehub_ui_redirect_router
from musehub.api.routes.wire import router as wire_router
from musehub.api.routes.api.repos import router as api_repos_router
from musehub.api.routes.api.identities import router as api_identities_router
from musehub.api.routes.api.search import router as api_search_router
from musehub.db import init_db, close_db


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # No per-request nonces: HTMX swaps the <body>, making per-request
        # nonces incompatible (the browser would block scripts whose nonce no
        # longer matches the current navigation). All inline scripts have been
        # removed; external scripts are served from 'self'. 'unsafe-eval' is
        # still required by Alpine.js v3's expression evaluator.
        request.state.csp_nonce = ""

        response = await call_next(request)

        if "X-Frame-Options" not in response.headers:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), "
            "gyroscope=(), magnetometer=(), microphone=(), "
            "payment=(), usb=()"
        )
        # 'unsafe-eval' is required by Alpine.js v3 (it uses new Function()
        # for expression evaluation). 'unsafe-inline' has been removed from
        # script-src: all JS is in external files served from 'self'.
        # style-src keeps 'unsafe-inline' while server-rendered dynamic inline
        # styles (avatar colours, label colours, etc.) are still present.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline' https://fonts.bunny.net; "
            "font-src 'self' https://fonts.bunny.net; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        if not settings.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        # Prevent fingerprinting — suppress the default "uvicorn" server banner
        response.headers["Server"] = "musehub"
        return response


logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

from musehub.rate_limits import limiter  # noqa: E402 — after logging setup


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    logger.info(f"Starting MuseHub v{settings.app_version}")

    try:
        await init_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database: {e}")
        raise

    if not settings.debug and settings.database_url and "postgres" in settings.database_url:
        pw = (settings.db_password or "").strip()
        weak = {"", "changeme123", "musehub", "password", "postgres", "secret"}
        if not pw or pw in weak:
            raise RuntimeError(
                "Production requires DB_PASSWORD set to a strong value. "
                "Generate with: openssl rand -hex 16"
            )

    # M4: Enforce a minimum 256-bit (32-byte) entropy on the JWT signing secret.
    # A secret shorter than 32 bytes is trivially brute-forced.
    if not settings.debug:
        raw_secret = settings.access_token_secret or ""
        if len(raw_secret.encode()) < 32:
            raise RuntimeError(
                "Production requires ACCESS_TOKEN_SECRET of at least 32 bytes. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )

    yield

    logger.info("Shutting down MuseHub...")
    await close_db()


app = FastAPI(
    title="MuseHub API",
    version=settings.app_version,
    # OpenAPI schema served in debug/dev and test environments.
    # In production (DEBUG=false, MUSE_ENV != "test") it is disabled — agents use /mcp instead.
    openapi_url="/api/v1/openapi.json" if (settings.debug or settings.muse_env == "test") else None,
    description=(
        "**MuseHub** — the version control hub for multidimensional state, powered by Muse.\n\n"
        "Muse is a domain-agnostic version control system. Not just Git — any state space "
        "where a 'change' is a delta across multiple axes simultaneously. "
        "MIDI (21 dimensions), code (symbol graph), genomics, climate simulation, 3D design.\n\n"
        "MuseHub gives AI agents and humans a GitHub-style workflow for any Muse domain: "
        "push commits, open pull requests, track issues, browse domain insights, and "
        "discover registered domain plugins — all via a machine-readable OpenAPI + MCP spec.\n\n"
        "## Authentication\n\n"
        "All write endpoints and private-repo reads require a **Bearer JWT** in the "
        "`Authorization` header:\n\n"
        "```\nAuthorization: Bearer <your-jwt>\n```\n\n"
        "Public repo read endpoints accept unauthenticated requests.\n\n"
        "## MCP (Model Context Protocol)\n\n"
        "Full MCP 2025-11-25 Streamable HTTP at `POST /GET /DELETE /mcp`. "
        "37 tools, 27 resource URIs (`muse://...`), and 11 prompts. "
        "See `/mcp/docs` for the interactive reference.\n\n"
        "## URL Scheme\n\n"
        "Repos: `/{owner}/{slug}` · Domain viewer: `/{owner}/{slug}/view/{ref}` · "
        "Insights: `/{owner}/{slug}/insights/{ref}/{dim}`\n"
        "Clone URL: `musehub://{owner}/{slug}`\n"
    ),
    contact={
        "name": "Muse VCS",
        "url": "https://musehub.app",
        "email": "hello@musehub.app",
    },
    license_info={
        "name": "Proprietary",
        "url": "https://musehub.app/terms",
    },
    lifespan=lifespan,
    # Docs are served via custom routes below that use locally-bundled assets,
    # so we disable the default CDN-dependent auto-generated routes.
    docs_url=None,
    redoc_url=None,
)


def _handle_rate_limit(request: Request, exc: Exception) -> Response:
    if isinstance(exc, RateLimitExceeded):
        result: Response = _rate_limit_exceeded_handler(request, exc)
        return result
    raise exc


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _handle_rate_limit)
app.add_middleware(SecurityHeadersMiddleware)

if "*" in settings.cors_origins:
    logger.warning("SECURITY WARNING: CORS allows all origins. Set CORS_ORIGINS in production.")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files mounted FIRST — must come before the /{owner}/{repo_slug} wildcard
# UI routes, otherwise "static" would be matched as an owner name.
_STATIC_DIR = Path(__file__).parent / "templates" / "musehub" / "static"
app.mount(
    "/static",
    StaticFiles(directory=str(_STATIC_DIR)),
    name="static",
)

# Wire protocol — /wire/repos/{repo_id}/refs|push|fetch
# Must come before /{owner}/{repo_slug} wildcard.
app.include_router(wire_router)

# Clean REST API — /api/repos, /api/identities, /api/search
# Registered before /api/v1 so the concrete prefix is matched first.
app.include_router(api_repos_router)
app.include_router(api_identities_router)
app.include_router(api_search_router)

# Fixed-prefix subrouters registered BEFORE the main musehub router
# so their concrete paths are matched first, not shadowed by /{owner}/{repo_slug}.
app.include_router(musehub_user_routes.router, prefix="/api/v1", tags=["Users"])
app.include_router(musehub_discover_routes.router, prefix="/api/v1", tags=["Discover"])
app.include_router(musehub_discover_routes.star_router, prefix="/api/v1", tags=["Social"])
app.include_router(musehub_domains_routes.router, prefix="/api/v1", tags=["Domains"])
app.include_router(musehub_router_pkg.router, prefix="/api/v1")
app.include_router(musehub_ui_notifications_routes.router, tags=["musehub-ui-notifications"])
app.include_router(musehub_ui_topics_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_mcp_elicitation_routes.router, tags=["musehub-ui-mcp"])
app.include_router(musehub_ui_new_repo_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_domains_routes.router, tags=["musehub-ui-domains"])
app.include_router(musehub_ui_routes.fixed_router, tags=["musehub-ui"])
app.include_router(musehub_ui_milestones_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_stash_routes.router, tags=["musehub-ui-stash"])
app.include_router(musehub_ui_forks_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_collab_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_labels_routes.router, tags=["musehub-ui"])

# Fixed-path routers that must come BEFORE the /{owner}/{repo_slug} wildcard in ui_routes.router.
# Registering them after would cause /oembed, /oembed/commit, /sitemap.xml, /mcp, etc.
# to be shadowed and matched as if "oembed"/"sitemap"/"mcp" were repo owner names.
app.include_router(musehub_oembed_routes.router, tags=["musehub-oembed"])
app.include_router(musehub_raw_routes.router, prefix="/api/v1", tags=["musehub-raw"])
app.include_router(musehub_sitemap_routes.router, tags=["musehub-sitemap"])
app.include_router(mcp_router)

# Wildcard UI routes — /{owner}/{repo_slug} and deeper paths.
# Must come after all fixed-path routers above.
# Redirect router must come before insights_router so /piano-roll, /listen, /arrange
# are caught and 301'd before they'd match as owner names.
app.include_router(musehub_ui_redirect_router, tags=["musehub-ui-redirects"])
app.include_router(musehub_ui_insights_router, tags=["musehub-ui-insights"])
app.include_router(musehub_ui_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_blame_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_settings_routes.router, tags=["musehub-ui-settings"])

# Profile catch-all MUST be last — /{username} is a single-segment wildcard and
# would shadow fixed routes (e.g. /explore, /feed, /topics, /mcp) if registered earlier.
app.include_router(musehub_ui_profile_routes.router, tags=["musehub-ui"])

if settings.debug:
    @app.get("/docs", include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url="/api/v1/openapi.json",
            title="MuseHub API — Swagger UI",
            swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
            swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
        )

    @app.get("/redoc", include_in_schema=False)
    async def redoc_ui() -> HTMLResponse:
        return get_redoc_html(
            openapi_url="/api/v1/openapi.json",
            title="MuseHub API — ReDoc",
        )


@app.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect browsers to the UI; agents should use /api/v1/openapi.json."""
    return RedirectResponse(url="/explore")
