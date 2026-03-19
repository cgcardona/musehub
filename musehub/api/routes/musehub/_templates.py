"""Shared Jinja2 templates instance — single source of truth for MuseHub UI.

Every UI route handler imports from here so that:
- Custom filters (fmtdate, fmtrelative, shortsha, markdown, …) are registered
  exactly once on the shared Jinja2 Environment.
- Global template variables (MUSE_VERSION, now) are available in every template.
- No route module ever constructs its own Jinja2Templates instance.

Usage::

    from musehub.api.routes.musehub._templates import templates

    return templates.TemplateResponse(request, "musehub/pages/foo.html", ctx)

Stack: Jinja2 (server-side rendering) · HTMX 2.x (partial swaps, hx-boost) ·
       Alpine.js 3.x (client-side reactivity). Extensions loaded globally in
       base.html: json-enc, response-targets.
"""

from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates

from musehub.api.routes.musehub.jinja2_filters import register_musehub_filters
from musehub.protocol.version import MUSE_VERSION

_TEMPLATE_DIR = Path(__file__).parent.parent.parent.parent / "templates"

templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))
register_musehub_filters(templates.env)

# ── Global template variables ─────────────────────────────────────────────────
# These are available in every template without passing them in ctx.
templates.env.globals["MUSE_VERSION"] = MUSE_VERSION
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
