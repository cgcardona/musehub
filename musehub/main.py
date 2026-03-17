"""
MuseHub API

Standalone FastAPI application for the music composition version control platform.
GitHub for music — push commits, open pull requests, track issues, publish releases.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Awaitable, Callable, cast

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
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
    ui_similarity as musehub_ui_similarity_routes,
    ui_topics as musehub_ui_topics_routes,
    ui_forks as musehub_ui_forks_routes,
    ui_emotion_diff as musehub_ui_emotion_diff_routes,
    ui_user_profile as musehub_ui_profile_routes,
    ui_new_repo as musehub_ui_new_repo_routes,
    discover as musehub_discover_routes,
    users as musehub_user_routes,
    oembed as musehub_oembed_routes,
    raw as musehub_raw_routes,
    sitemap as musehub_sitemap_routes,
)
from musehub.api.routes import musehub as musehub_router_pkg
from musehub.db import init_db, close_db


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
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
        return response


logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


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
        if not pw or pw == "changeme123":
            raise RuntimeError(
                "Production requires DB_PASSWORD set to a strong value. "
                "Generate with: openssl rand -hex 16"
            )

    yield

    logger.info("Shutting down MuseHub...")
    await close_db()


app = FastAPI(
    title="MuseHub API",
    version=settings.app_version,
    description=(
        "**MuseHub** — the music composition version control platform powered by Muse VCS.\n\n"
        "MuseHub gives AI agents and human composers a GitHub-style workflow for music:\n"
        "push commits, open pull requests, track issues, and browse public repos via a "
        "machine-readable OpenAPI spec.\n\n"
        "## Authentication\n\n"
        "All write endpoints and private-repo reads require a **Bearer JWT** in the "
        "`Authorization` header:\n\n"
        "```\nAuthorization: Bearer <your-jwt>\n```\n\n"
        "Public repo read endpoints accept unauthenticated requests.\n\n"
        "## URL Scheme\n\n"
        "Repos are addressed as `/{owner}/{slug}` (e.g. `/gabriel/neo-soul-experiment`).\n"
        "Clone URL format: `musehub://{owner}/{slug}`\n"
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
    openapi_url="/api/v1/openapi.json",
    # Docs are served via custom routes below that use locally-bundled assets,
    # so we disable the default CDN-dependent auto-generated routes.
    docs_url=None,
    redoc_url=None,
)


def _handle_rate_limit(request: Request, exc: Exception) -> Response:
    if isinstance(exc, RateLimitExceeded):
        return cast(Response, _rate_limit_exceeded_handler(request, exc))
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

# Fixed-prefix subrouters registered BEFORE the main musehub router
# so their concrete paths are matched first, not shadowed by /{owner}/{repo_slug}.
app.include_router(musehub_user_routes.router, prefix="/api/v1/musehub", tags=["Users"])
app.include_router(musehub_discover_routes.router, prefix="/api/v1", tags=["Discover"])
app.include_router(musehub_discover_routes.star_router, prefix="/api/v1", tags=["Social"])
app.include_router(musehub_router_pkg.router, prefix="/api/v1")
app.include_router(musehub_ui_notifications_routes.router, tags=["musehub-ui-notifications"])
app.include_router(musehub_ui_topics_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_profile_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_new_repo_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_routes.fixed_router, tags=["musehub-ui"])
app.include_router(musehub_ui_milestones_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_stash_routes.router, tags=["musehub-ui-stash"])
app.include_router(musehub_ui_forks_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_collab_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_labels_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_blame_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_settings_routes.router, tags=["musehub-ui-settings"])
app.include_router(musehub_ui_similarity_routes.router, tags=["musehub-ui"])
app.include_router(musehub_ui_emotion_diff_routes.router, tags=["musehub-ui"])
app.include_router(musehub_oembed_routes.router, tags=["musehub-oembed"])
app.include_router(musehub_raw_routes.router, prefix="/api/v1", tags=["musehub-raw"])
app.include_router(musehub_sitemap_routes.router, tags=["musehub-sitemap"])

_STATIC_DIR = Path(__file__).parent / "templates" / "musehub" / "static"
app.mount(
    "/musehub/static",
    StaticFiles(directory=str(_STATIC_DIR)),
    name="musehub-static",
)

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
    return RedirectResponse(url="/musehub/ui/explore")
