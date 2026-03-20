"""JSON alternate response helpers for MuseHub HTML page handlers.

Every MuseHub HTML page is a shell that loads its data client-side via JS.
This module adds machine-readable JSON access to those same URLs so AI agents
and bots can consume the same endpoints without a browser.

Two audiences, one URL:
- Browsers get the rich HTML shell (default).
- Agents send ``Accept: application/json`` and get structured JSON.

Bot detection adds ``X-MuseHub-JSON-Available`` to responses for known bot
User-Agents so they know content negotiation is supported.
"""

import logging
import re
from typing import Any, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Matches bot/AI agent User-Agent strings (case-insensitive).
_BOT_UA_PATTERN = re.compile(r"bot|agent|claude|gpt|cursor", re.IGNORECASE)


def is_bot_user_agent(request: Request) -> bool:
    """Return True when the request originates from a known bot or AI agent.

    Checks the User-Agent header for patterns common to crawlers and AI agents.
    Used to conditionally add ``X-MuseHub-JSON-Available`` so bots discover
    that content negotiation is supported without setting Accept explicitly.
    """
    ua = request.headers.get("user-agent", "")
    return bool(_BOT_UA_PATTERN.search(ua))


def json_or_html(
    request: Request,
    template_fn: Callable[[], Response],
    json_data: dict[str, Any],
) -> Response:
    """Return JSON or HTML based on the caller's Accept header or ?format param.

    Inspects ``Accept: application/json`` or ``?format=json`` and dispatches:
    - JSON callers receive ``{"data": <json_data>, "meta": {"url": <url>}}``.
    - All other callers receive the HTML shell from ``template_fn()``.

    Both ``Accept: application/json`` and ``?format=json`` are honoured so that
    agents without header control (e.g. browser-initiated ``<a>`` links, plain
    ``curl``) can still access structured data — consistent with
    ``negotiate_response()`` in ``negotiate.py``.

    The ``meta.url`` field lets agents reconstruct canonical URLs from
    relative links without additional parsing. The ``meta.api`` field links to
    the canonical REST endpoint when the URL differs from the UI route.

    Args:
        request: The incoming FastAPI request.
        template_fn: Zero-argument callable that renders and returns the HTML
            response. Called lazily — only when the caller wants HTML.
        json_data: Serialisable dict to embed under the ``data`` key.

    Returns:
        ``JSONResponse`` for JSON callers; ``template_fn()`` result otherwise.
    """
    wants_json = (
        request.query_params.get("format") == "json"
        or "application/json" in request.headers.get("accept", "")
    )
    if wants_json:
        logger.debug("✅ json_or_html: JSON path — %s", str(request.url))
        # Build canonical REST API URL: replace /api/v1 prefix if already an API
        # URL, or expose the api_link header hint if set by the handler.
        api_link = request.headers.get("X-MuseHub-API-Link", str(request.url))
        return JSONResponse(
            content={
                "data": json_data,
                "meta": {"url": str(request.url), "api": api_link},
            }
        )
    logger.debug("✅ json_or_html: HTML path — %s", str(request.url))
    return add_json_available_header(template_fn(), request)


def add_json_available_header(
    response: Response,
    request: Request,
    *,
    api_link: str | None = None,
) -> Response:
    """Attach agent-discovery headers to HTML responses.

    Two headers are emitted for known bot/agent User-Agents:

    ``X-MuseHub-JSON-Available: true``
        Signals that content negotiation is supported — the agent can
        re-request with ``Accept: application/json`` or ``?format=json``
        to get structured JSON from this same URL.

    ``X-MuseHub-API: <url>``
        When ``api_link`` is supplied, points directly to the canonical
        REST endpoint for this resource (e.g. ``/api/v1/domains/@a/b``).
        Agents that need raw JSON without an HTML wrapper should use
        this URL, or the ``muse://`` MCP resources.

    ``Link: <url>; rel="alternate"; type="application/json"``
        Standard RFC 5988 link relation that browsers and well-behaved
        crawlers understand. Always added when ``api_link`` is provided.

    Args:
        response: The response to annotate (mutated in-place).
        request: The originating request used for User-Agent inspection.
        api_link: Optional canonical REST API URL for this resource.

    Returns:
        The same response object (mutated).
    """
    if api_link:
        # Always add the standard Link header — readable by any HTTP client.
        existing = response.headers.get("Link", "")
        new_link = f'<{api_link}>; rel="alternate"; type="application/json"'
        response.headers["Link"] = f"{existing}, {new_link}".lstrip(", ")

    if is_bot_user_agent(request):
        response.headers["X-MuseHub-JSON-Available"] = "true"
        if api_link:
            response.headers["X-MuseHub-API"] = api_link

    return response
