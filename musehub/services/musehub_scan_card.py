"""Render a scan result as a 1200×675 PNG, the size X shows in a post.

Pure Pillow, no browser. Fonts are bundled in static/fonts/scan (Inter and
JetBrains Mono, both SIL OFL).
"""
from __future__ import annotations

import io
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from musehub.services.musehub_scan import ScanResult

W, H = 1200, 675
_FONTS = Path(__file__).resolve().parent.parent / "templates" / "musehub" / "static" / "fonts" / "scan"
VOID = (7, 7, 15)
TEXT = (226, 232, 240)
SOFT = (168, 184, 204)
DIM = (107, 127, 160)
BLUE = (96, 165, 250)
LINK = (147, 197, 253)
ORANGE = (240, 136, 62)
SPECTRAL = [(96, 165, 250), (129, 140, 248), (167, 139, 250), (192, 132, 252)]


@cache
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    files = {
        "sans": "Inter-Regular.otf", "semi": "Inter-SemiBold.otf", "black": "Inter-ExtraBold.otf",
        "mono": "jetbrains-mono-latin-500-normal.woff", "mono-semi": "jetbrains-mono-latin-600-normal.woff",
    }
    return ImageFont.truetype(str(_FONTS / files[name]), size)


def _spectral(t: float) -> tuple[int, int, int]:
    t = min(max(t, 0.0), 1.0) * (len(SPECTRAL) - 1)
    i = min(int(t), len(SPECTRAL) - 2)
    f = t - i
    a, b = SPECTRAL[i], SPECTRAL[i + 1]
    return (round(a[0] + (b[0] - a[0]) * f), round(a[1] + (b[1] - a[1]) * f), round(a[2] + (b[2] - a[2]) * f))


def fmt_tokens(n: int) -> str:
    """2_410_000 → '2.41M', 25_300 → '25K', 900 → '900'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{round(n / 1000)}K"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def _gradient_text(img: Image.Image, xy: tuple[int, int], text: str, font: ImageFont.FreeTypeFont) -> int:
    """Draw text filled with the spectral gradient; returns its width."""
    box = font.getbbox(text)
    w, h = int(box[2]), int(box[3])
    mask = Image.new("L", (w, h + 8), 0)
    ImageDraw.Draw(mask).text((0, 0), text, font=font, fill=255)
    fill = Image.new("RGB", mask.size)
    fd = ImageDraw.Draw(fill)
    for x in range(w):
        fd.line([(x, 0), (x, mask.size[1])], fill=_spectral(x / max(1, w - 1)))
    img.paste(fill, xy, mask)
    return w


def _wrap(draw: ImageDraw.ImageDraw, words: list[str], font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) > width and cur:
            lines.append(cur); cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def render_card(r: ScanResult, short_url: str) -> bytes:
    """The shareable image for one scan."""
    img = Image.new("RGB", (W, H), VOID)
    glow = Image.new("RGB", (W, H), VOID)
    gd = ImageDraw.Draw(glow)
    for rad in range(420, 0, -6):
        k = (1 - rad / 420) * 0.10
        gd.ellipse([180 - rad, 200 - rad * 0.8, 180 + rad, 200 + rad * 0.8], fill=tuple(round(VOID[i] + (BLUE[i] - VOID[i]) * k) for i in range(3)))
    img = Image.blend(img, glow, 1.0)
    d = ImageDraw.Draw(img)
    for x in range(W):
        d.line([(x, 0), (x, 3)], fill=_spectral(x / (W - 1)))

    # Top row: logo, wordmark, repo pill.
    d.line([(76, 59), (67, 77)], fill=BLUE, width=2); d.line([(76, 59), (85, 77)], fill=BLUE, width=2)
    for cx, cy, rr in ((76, 59, 5), (67, 77, 4.5), (85, 77, 4.5)):
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=BLUE)
    d.text((102, 54), "Muse scan", font=_font("mono-semi", 22), fill=BLUE)
    pill = _font("mono", 20)
    pw = d.textlength(r.repo, font=pill)
    d.rounded_rectangle([W - 60 - pw - 32, 48, W - 60, 86], radius=19, fill=(14, 20, 36), outline=(30, 48, 80))
    d.text((W - 60 - pw - 16, 55), r.repo, font=pill, fill=SOFT)

    # Headline: "Your coding agent could find what breaks with" + gradient "96x fewer tokens".
    head = _font("black", 46)
    lead = _wrap(d, "Your coding agent could find what breaks with".split(), head, 1060)
    y = 128
    for line in lead:
        d.text((60, y), line, font=head, fill=TEXT); y += 56
    _gradient_text(img, (60, y), f"{r.ratio:g}x fewer tokens", head)
    y += 92

    # Bars.
    label, val = _font("semi", 20), _font("mono-semi", 22)
    track = 1200 - 60 - 60 - 150 - 200 - 36
    for name, n, color, frac in (
        ("Without Muse", r.grep_tokens, ORANGE, 1.0),
        ("With Muse", r.muse_tokens, BLUE, r.muse_tokens / r.grep_tokens if r.grep_tokens else 0),
    ):
        d.text((60, y + 4), name, font=label, fill=SOFT)
        x0 = 60 + 150 + 18
        d.rounded_rectangle([x0, y, x0 + max(10, round(track * frac)), y + 34], radius=5, fill=color)
        t = f"{fmt_tokens(n)} tokens"
        d.text((W - 60 - d.textlength(t, font=val), y + 3), t, font=val, fill=color)
        y += 50

    body = _font("sans", 20)
    y += 14
    pct = f"{round(r.task_saving * 100)}%"
    pre = f"Last {len(r.pulls)} merged PRs, replayed. About "
    d.text((60, y), pre, font=body, fill=SOFT)
    bx = 60.0 + d.textlength(pre, font=body)
    bold = f"{pct} fewer tokens per task"
    d.text((bx, y), bold, font=_font("semi", 20), fill=TEXT)
    d.text((bx + d.textlength(bold, font=_font("semi", 20)), y), ", estimated.", font=body, fill=SOFT)

    # Footer: method line and short URL.
    fine = _font("mono", 14)
    lines = _wrap(d, ("Simulated from the repo's structure and history: tokens to find each change's callers "
                      "two levels deep with search and file reads, against one Muse impact query. "
                      "Not a measured agent run.").split(), fine, 740)
    fy = H - 40 - 21 * len(lines)
    for line in lines:
        d.text((60, fy), line, font=fine, fill=DIM); fy += 21
    cta = _font("mono", 20)
    d.text((W - 60 - d.textlength(short_url, font=cta), H - 62), short_url, font=cta, fill=LINK)
    free = "Scan yours free"
    d.text((W - 60 - d.textlength(free, font=_font("semi", 18)), H - 92), free, font=_font("semi", 18), fill=SOFT)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()
