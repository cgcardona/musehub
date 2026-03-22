"""Jinja2 server-side filter functions for MuseHub templates.

Registers filters on a Jinja2 Environment so every MuseHub page template
can call them without duplicating JavaScript utility functions:

    {{ issue.created_at | fmtdate }}        → "Jan 15, 2025"
    {{ commit.timestamp | fmtrelative }}    → "3 hours ago"
    {{ commit.commit_id | shortsha }}       → "a1b2c3d4"
    {{ label.color | label_text_color }}    → "#000" or "#fff"
    {{ issue.body | markdown }}             → safe HTML (bold, italic, code, links)

Filters are registered exactly once via the shared ``_templates`` module:

    # musehub/api/routes/musehub/_templates.py — do not call this directly
    register_musehub_filters(templates.env)

Route handlers import the ready-to-use instance:

    from musehub.api.routes.musehub._templates import templates
"""

from datetime import datetime, timezone
from typing import Callable

from jinja2 import Environment


def _fmtdate(value: datetime | str | None) -> str:
    """Format a datetime or ISO-8601 string as 'Jan 15, 2025'.

    Returns an empty string for None so templates can write
    ``{{ x | fmtdate }}`` without an explicit null check.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.strftime("%b %-d, %Y")


def _fmtrelative(value: datetime | str | None) -> str:
    """Format a datetime as a human-relative string: '3 hours ago'.

    Computes the delta from UTC now.  Returns an empty string for None.
    Timezone-naive datetimes are assumed to be UTC.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = now - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = seconds // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


def _shortsha(value: str | None) -> str:
    """Return the first 8 characters of a commit SHA.

    Returns an empty string for None or empty input so templates never
    render ``None`` in place of a commit hash.
    """
    if not value:
        return ""
    return value[:8]


_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _note_name(midi: int | None) -> str:
    """Convert a MIDI pitch value (0–127) to a note name string, e.g. 60 → 'C4'.

    Returns '—' for None so templates never render 'None' in place of a note name.
    """
    if midi is None:
        return "—"
    octave = midi // 12 - 1
    name = _NOTE_NAMES[midi % 12]
    return f"{name}{octave}"



def _label_text_color(hex_bg: str) -> str:
    """Return '#000' or '#fff' for readable contrast against a hex background.

    Uses WCAG relative luminance (W3C simplified formula) to decide whether
    dark or light text produces better contrast.  Falls back to '#000' for
    malformed input.
    """
    hex_bg = hex_bg.lstrip("#")
    if len(hex_bg) != 6:
        return "#000"
    r, g, b = int(hex_bg[0:2], 16), int(hex_bg[2:4], 16), int(hex_bg[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000" if luminance > 0.5 else "#fff"


def _filesizeformat(value: int | float | None) -> str:
    """Format a byte count as a human-readable file size string.

    Examples: 0 → "0 B", 1536 → "1.5 KB", 2097152 → "2.0 MB".
    Returns "0 B" for None or zero.
    """
    if not value or value <= 0:
        return "0 B"
    n = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(n)} B"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"  # unreachable but satisfies mypy


def _markdown(value: str | None) -> str:
    """Convert a Markdown string to safe HTML using mistune.

    Uses mistune's CommonMark-compliant parser with:
    - Images rendered as <img> (badges, screenshots)
    - Fenced code blocks with ``language-*`` class for highlight.js
    - All links marked rel="noopener noreferrer"
    - Headings shifted down one level (h1→h2) to preserve page hierarchy
    - HTML sanitised via mistune's built-in escaping

    Returns an empty string for None.
    """
    if not value:
        return ""

    import re as _re
    import html as _html
    import mistune

    def _esc(s: str) -> str:
        return _html.escape(s, quote=True)

    def _esc_url(s: str) -> str:
        # Allow only safe URL characters; strip everything else.
        import urllib.parse
        return urllib.parse.quote(s, safe=":/?#[]@!$&'()*+,;=%~.-_")

    class _MuseRenderer(mistune.HTMLRenderer):  # type: ignore[misc]
        """HTMLRenderer subclass that customises output for MuseHub."""

        def heading(self, children: str, level: int, **attrs: object) -> str:  # type: ignore[override]
            # Shift h1→h2, h2→h3, etc. so READMEs don't stomp the page <h1>.
            shifted = min(level + 1, 6)
            return f"<h{shifted}>{children}</h{shifted}>\n"

        def link(self, text: str, url: str | None, title: str | None = None) -> str:  # type: ignore[override]
            safe_url = _esc_url(url or "")
            title_attr = f' title="{_esc(title)}"' if title else ""
            return f'<a href="{safe_url}" rel="noopener noreferrer"{title_attr}>{text}</a>'

        def image(self, alt: str, url: str | None, title: str | None = None) -> str:  # type: ignore[override]
            safe_url = _esc_url(url or "")
            title_attr = f' title="{_esc(title)}"' if title else ""
            return f'<img src="{safe_url}" alt="{_esc(alt)}"{title_attr} loading="lazy">'

        def codespan(self, code: str) -> str:  # type: ignore[override]
            return f"<code>{_esc(code)}</code>"

        def block_code(self, code: str, **attrs: object) -> str:  # type: ignore[override]
            info = str(attrs.get("info") or "").strip()
            lang = _re.split(r"\s+", info)[0] if info else ""
            lang_class = f' class="language-{_esc(lang)}"' if lang else ""
            return f'<pre class="code-block"><code{lang_class}>{_esc(code)}</code></pre>\n'

    _md = mistune.create_markdown(renderer=_MuseRenderer(), plugins=["strikethrough", "table", "task_lists"])
    return str(_md(value))


def _auto_code(text: str) -> str:
    """Wrap code-like tokens in plain-text descriptions with <code> tags.

    Each pattern is applied only to text *outside* already-emitted <code>
    blocks, so nesting is impossible regardless of application order.

    Patterns (applied in priority order):
    1. Backtick strings:              `foo`              → <code>foo</code>
    2. musehub_* function calls:      musehub_foo(x='y') → <code>musehub_foo(x='y')</code>
    3. Standalone musehub_* names:    musehub_foo        → <code>musehub_foo</code>
    4. Muse CLI sub-commands:         muse push          → <code>muse push</code>
    5. Short single-quoted literals:  'main', 'v1.0'     → <code>'main'</code>

    Returns str with embedded HTML — use |safe in templates.
    Descriptions are server-controlled strings so there is no XSS risk.
    """
    import re as _re

    _CODE_SPAN = _re.compile(r"<code>.*?</code>", _re.DOTALL)

    def _sub_outside(pattern: str, repl: "str | Callable[..., str]", src: str) -> str:
        """Apply *pattern* → *repl* only to text segments between <code> spans."""
        result: list[str] = []
        last = 0
        for m in _CODE_SPAN.finditer(src):
            chunk = src[last : m.start()]
            result.append(_re.sub(pattern, repl, chunk))
            result.append(m.group(0))  # keep existing code block verbatim
            last = m.end()
        result.append(_re.sub(pattern, repl, src[last:]))
        return "".join(result)

    # 1. Backtick strings
    text = _sub_outside(r"`([^`]+)`", r"<code>\1</code>", text)

    # 2. musehub_xxx(...) — full call, quoting angle brackets in args
    def _wrap_call(m: "_re.Match[str]") -> str:
        name, args = m.group(1), m.group(2)
        safe_args = args.replace("<", "&lt;").replace(">", "&gt;")
        return f"<code>{name}({safe_args})</code>"

    text = _sub_outside(r"\b(musehub_[a-z_]+)\(([^)]*)\)", _wrap_call, text)

    # 3. Standalone musehub_xxx names not followed by (
    text = _sub_outside(r"\b(musehub_[a-z_]+)\b(?!\()", r"<code>\1</code>", text)

    # 4. Muse CLI sub-commands
    text = _sub_outside(
        r"\b(muse\s+(?:push|pull|clone|remote|config|auth|commit|branch|log|diff|init))\b",
        r"<code>\1</code>",
        text,
    )

    # 5. Short single-quoted literals: 'main', 'v1.0', 'final-mix', etc.
    text = _sub_outside(r"'([A-Za-z0-9][A-Za-z0-9_\-\.]{0,28})'", r"<code>'\1'</code>", text)

    # 6. HTML-escape plain-text segments (& outside existing tags/entities)
    def _escape_outside_tags(s: str) -> str:
        parts: list[str] = []
        i = 0
        depth = 0
        while i < len(s):
            ch = s[i]
            if ch == "<":
                depth += 1
                parts.append(ch)
            elif ch == ">":
                depth = max(0, depth - 1)
                parts.append(ch)
            elif depth > 0:
                parts.append(ch)
            elif ch == "&":
                parts.append("&amp;")
            else:
                parts.append(ch)
            i += 1
        return "".join(parts)

    return _escape_outside_tags(text)


def register_musehub_filters(env: Environment) -> None:
    """Register all MuseHub custom Jinja2 filters on *env*.

    Called exactly once by ``musehub.api.routes.musehub._templates`` on the
    shared ``Jinja2Templates`` instance. Do not call this directly.

    Available filters in every template: ``fmtdate``, ``fmtrelative``,
    ``shortsha``, ``label_text_color``, ``filesizeformat``, ``markdown``,
    ``auto_code``.
    """
    env.filters["fmtdate"] = _fmtdate
    env.filters["fmtrelative"] = _fmtrelative
    env.filters["shortsha"] = _shortsha
    env.filters["label_text_color"] = _label_text_color
    env.filters["note_name"] = _note_name
    env.filters["filesizeformat"] = _filesizeformat
    env.filters["markdown"] = _markdown
    env.filters["auto_code"] = _auto_code
