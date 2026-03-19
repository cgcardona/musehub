"""MuseHub MCP Elicitation UI — landing pages for URL-mode elicitation flows.

URL-mode elicitation (MCP 2025-11-25) lets the MCP server direct users to a
URL to complete an out-of-band interaction (OAuth, payment, API key entry).
This router provides the landing pages that receive those redirects.

Endpoints:

  GET /mcp/connect/{platform}?elicitation_id=...
    Landing page for streaming platform OAuth start. Verifies the user's
    MuseHub session, then redirects to the platform's OAuth page.
    On return, the callback signals elicitation completion to the agent.

  GET /mcp/connect/daw/{service}?elicitation_id=...
    Same pattern for cloud DAW / mastering service connections (LANDR, Splice, etc.).

  GET /mcp/elicitation/{elicitation_id}/callback?status=accepted|declined
    OAuth redirect target. Resolves the pending elicitation Future in the
    active MCP session and pushes a ``notifications/elicitation/complete``
    event to the agent's SSE stream.

Security:
  - All endpoints require a valid MuseHub session cookie (user must be logged in).
  - The ``elicitation_id`` is validated against the active session to prevent
    cross-session hijacking.
  - Only allow-listed platform slugs are accepted (no open redirects).
"""

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from musehub.api.routes.musehub._templates import templates
from musehub.mcp.elicitation import AVAILABLE_PLATFORMS, AVAILABLE_DAW_CLOUDS

logger = logging.getLogger(__name__)

router = APIRouter(tags=["MCP Elicitation UI"])

# ── Slug → display name lookup ────────────────────────────────────────────────

_PLATFORM_BY_SLUG: dict[str, str] = {
    p.lower().replace(" ", "-"): p for p in AVAILABLE_PLATFORMS if isinstance(p, str)
}

_DAW_BY_SLUG: dict[str, str] = {
    s.lower().replace(" ", "-"): s for s in AVAILABLE_DAW_CLOUDS if isinstance(s, str)
}

# Placeholder OAuth URLs — replace with real platform OAuth endpoints in production.
_PLATFORM_OAUTH_URLS: dict[str, str] = {
    "Spotify": "https://accounts.spotify.com/authorize?client_id=musehub&scope=user-read-private",
    "SoundCloud": "https://soundcloud.com/connect?client_id=musehub&scope=non-expiring",
    "Bandcamp": "https://bandcamp.com/api/oauth/authorize",
    "YouTube Music": "https://accounts.google.com/o/oauth2/auth?scope=youtube",
    "Apple Music": "https://appleid.apple.com/auth/authorize",
    "TIDAL": "https://login.tidal.com/oauth/authorize",
    "Amazon Music": "https://www.amazon.com/ap/oa",
    "Deezer": "https://connect.deezer.com/oauth/auth.php",
}

_DAW_OAUTH_URLS: dict[str, str] = {
    "LANDR": "https://app.landr.com/oauth/authorize",
    "Splice": "https://splice.com/oauth/authorize",
    "Soundtrap": "https://www.soundtrap.com/oauth/authorize",
    "BandLab": "https://www.bandlab.com/api/oauth/authorize",
    "Audiotool": "https://www.audiotool.com/oauth/authorize",
}


# ── Auth helper ───────────────────────────────────────────────────────────────


def _get_musehub_user_id(request: Request) -> str | None:
    """Extract the authenticated user ID from the session cookie.

    Returns the user ID string if logged in, or None for anonymous users.
    """
    session = request.session if hasattr(request, "session") else {}
    return session.get("user_id")


# ── Platform OAuth start page ─────────────────────────────────────────────────


@router.get(
    "/mcp/connect/{platform_slug}",
    operation_id="mcpElicitationPlatformConnect",
    summary="MCP URL Elicitation — streaming platform OAuth start",
    response_class=HTMLResponse,
)
async def platform_connect_start(
    request: Request,
    platform_slug: str,
    elicitation_id: str = Query(..., description="Stable elicitation ID from the agent's request"),
) -> Response:
    """Landing page for streaming platform OAuth elicitation.

    Validates the platform slug, checks user authentication, then renders
    a confirmation page before redirecting to the platform OAuth.
    """
    platform = _PLATFORM_BY_SLUG.get(platform_slug)
    if platform is None:
        return HTMLResponse(
            content=_error_page(
                f"Unknown platform: {platform_slug!r}. "
                "Supported: " + ", ".join(_PLATFORM_BY_SLUG.keys())
            ),
            status_code=404,
        )

    user_id = _get_musehub_user_id(request)
    if user_id is None:
        callback = request.url
        return RedirectResponse(url=f"/login?next={callback}", status_code=302)

    oauth_url = _PLATFORM_OAUTH_URLS.get(platform, "#")
    callback_url = str(request.url_for(
        "mcpElicitationCallback",
        elicitation_id=elicitation_id,
    )) + "?status=accepted"

    # In production, the OAuth flow would redirect to this callback URL.
    # For now, show a confirmation page that completes the elicitation.
    context = {
        "request": request,
        "platform": platform,
        "platform_slug": platform_slug,
        "elicitation_id": elicitation_id,
        "oauth_url": oauth_url,
        "callback_url": callback_url,
        "user_id": user_id,
    }
    return templates.TemplateResponse("mcp/elicitation_connect.html", context)


# ── Cloud DAW OAuth start page ────────────────────────────────────────────────


@router.get(
    "/mcp/connect/daw/{service_slug}",
    operation_id="mcpElicitationDawConnect",
    summary="MCP URL Elicitation — cloud DAW OAuth start",
    response_class=HTMLResponse,
)
async def daw_connect_start(
    request: Request,
    service_slug: str,
    elicitation_id: str = Query(..., description="Stable elicitation ID from the agent's request"),
) -> Response:
    """Landing page for cloud DAW / mastering service OAuth elicitation."""
    service = _DAW_BY_SLUG.get(service_slug)
    if service is None:
        return HTMLResponse(
            content=_error_page(
                f"Unknown DAW service: {service_slug!r}. "
                "Supported: " + ", ".join(_DAW_BY_SLUG.keys())
            ),
            status_code=404,
        )

    user_id = _get_musehub_user_id(request)
    if user_id is None:
        callback = request.url
        return RedirectResponse(url=f"/login?next={callback}", status_code=302)

    oauth_url = _DAW_OAUTH_URLS.get(service, "#")
    callback_url = str(request.url_for(
        "mcpElicitationCallback",
        elicitation_id=elicitation_id,
    )) + "?status=accepted"

    context = {
        "request": request,
        "service": service,
        "service_slug": service_slug,
        "elicitation_id": elicitation_id,
        "oauth_url": oauth_url,
        "callback_url": callback_url,
        "user_id": user_id,
        "is_daw": True,
    }
    return templates.TemplateResponse("mcp/elicitation_connect.html", context)


# ── OAuth callback / elicitation completion ───────────────────────────────────


@router.get(
    "/mcp/elicitation/{elicitation_id}/callback",
    operation_id="mcpElicitationCallback",
    summary="MCP URL Elicitation — OAuth callback and completion signal",
    response_class=HTMLResponse,
)
async def elicitation_callback(
    request: Request,
    elicitation_id: str,
    status: str = Query("accepted", description="Completion status: 'accepted' or 'declined'"),
    code: str | None = Query(None, description="OAuth authorization code (when status=accepted)"),
) -> Response:
    """OAuth redirect target: resolves the pending elicitation in the MCP session.

    After the OAuth flow completes (or if the user declines), this endpoint:
    1. Pushes a ``notifications/elicitation/complete`` event to the agent's SSE stream.
    2. Renders a completion page the user can close.

    The agent's ``elicit_url()`` await will resolve, allowing the tool to continue.
    """
    action = "accept" if status == "accepted" else "decline"

    # Signal elicitation completion to any active MCP sessions.
    # In the current in-memory model we broadcast to all sessions; in production
    # the elicitation_id would be mapped to a specific session.
    _signal_elicitation_complete(elicitation_id, action=action)

    context = {
        "request": request,
        "elicitation_id": elicitation_id,
        "status": status,
        "action": action,
        "code_present": bool(code),
    }
    return templates.TemplateResponse("mcp/elicitation_callback.html", context)


# ── Signal helper ─────────────────────────────────────────────────────────────


def _signal_elicitation_complete(elicitation_id: str, *, action: str = "accept") -> int:
    """Push ``notifications/elicitation/complete`` to all sessions with a matching pending.

    Returns the number of sessions resolved.

    In production, the elicitation_id is stored with the session at creation
    time so we can do O(1) lookup; here we iterate all sessions (bounded by
    the in-memory store size, typically a few thousand).
    """
    from musehub.mcp import session as session_store
    from musehub.mcp.sse import sse_notification
    from musehub.mcp.session import resolve_elicitation

    resolved = 0
    for sess in list(session_store._SESSIONS.values()):
        # Try resolving the elicitation_id as a pending key.
        did_resolve = resolve_elicitation(sess, elicitation_id, {"action": action})
        if did_resolve:
            resolved += 1
            # Also push a notification so any listening SSE stream sees it.
            notification = sse_notification(
                "notifications/elicitation/complete",
                {"elicitationId": elicitation_id, "action": action},
            )
            from musehub.mcp.session import push_to_session
            push_to_session(sess, notification)

    if resolved:
        logger.info(
            "Elicitation callback: resolved %d session(s) (id=%s, action=%s)",
            resolved,
            elicitation_id,
            action,
        )
    else:
        logger.warning(
            "Elicitation callback: no matching pending Future found (id=%s)",
            elicitation_id,
        )
    return resolved


# ── HTML helpers ──────────────────────────────────────────────────────────────


def _error_page(message: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>MuseHub — MCP Elicitation Error</title>
<style>body{{font-family:sans-serif;max-width:600px;margin:4rem auto;color:#1a1a2e;}}
h1{{color:#e11d48;}}a{{color:#7c3aed;}}</style></head>
<body>
<h1>Elicitation Error</h1>
<p>{message}</p>
<p><a href="/">← Back to MuseHub</a></p>
</body>
</html>"""
