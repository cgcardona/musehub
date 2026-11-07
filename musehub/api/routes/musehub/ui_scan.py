"""Free repo scan: how much Muse would save a coding agent on a public GitHub repo.

Routes:
  POST /scan        — run (or reuse) a scan; JSON body ``{"repo": "owner/repo"}``,
                      returns the result as JSON with its short URL and image URL
  GET  /s/{id}      — the shareable result page, with og:image for X and others
  GET  /s/{id}.png  — the 1200×675 share image

No auth. Rate-limited per IP (``SCAN_LIMIT``). All work is in
``musehub.services.musehub_scan``; the image is drawn by
``musehub.services.musehub_scan_card``.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from musehub.api.routes.musehub._templates import templates as _templates
from musehub.rate_limits import SCAN_LIMIT, limiter
from musehub.services import musehub_scan, musehub_scan_card

logger = logging.getLogger(__name__)
router = APIRouter()


class ScanRequest(BaseModel):
    """Body of POST /scan."""

    repo: str = Field(min_length=3, max_length=200, description="owner/repo or a github.com URL")


def _short_url(request: Request, result_id: str) -> str:
    return str(request.base_url).rstrip("/") + f"/s/{result_id}"


def _payload(request: Request, r: musehub_scan.ScanResult) -> dict[str, str | int | float]:
    short = _short_url(request, r.id)
    return {
        "id": r.id, "repo": r.repo, "sha": r.sha[:7], "pulls": len(r.pulls),
        "grepTokens": r.grep_tokens, "museTokens": r.muse_tokens, "ratio": r.ratio,
        "taskSaving": r.task_saving, "falseMatches": r.false_matches, "aliasMisses": r.alias_misses,
        "files": r.files, "symbols": r.symbols, "method": r.method,
        "shortUrl": short, "imageUrl": short + ".png",
    }


@router.post("/scan", summary="Scan a public GitHub repo")
@limiter.limit(SCAN_LIMIT)
async def scan_repo(request: Request, body: ScanRequest) -> JSONResponse:
    """Run a scan, or return a fresh one of the same repo from the last few hours."""
    try:
        repo = musehub_scan.parse_repo(body.repo)
        result = musehub_scan.recent_for(repo)
        if result is None:
            result = musehub_scan.remember(await asyncio.wait_for(musehub_scan.scan(repo), timeout=110))
            logger.info("✅ scanned %s: %sx over %d PRs", repo, result.ratio, len(result.pulls))
    except musehub_scan.ScanError as exc:
        return JSONResponse({"error": str(exc)}, status_code=422)
    except TimeoutError:
        return JSONResponse({"error": "That repo took too long to scan. Try a smaller one."}, status_code=504)
    if not result.pulls:
        return JSONResponse({"error": "None of the recent pull requests changed functions we could trace."}, status_code=422)
    if result.ratio < 2:
        return JSONResponse({"error": "This repo is small enough that searching it is already cheap. Muse pays off on larger codebases."}, status_code=422)
    return JSONResponse(_payload(request, result))


def _get(result_id: str) -> musehub_scan.ScanResult:
    r = musehub_scan.recall(result_id)
    if r is None:
        raise HTTPException(status_code=404, detail="This scan has expired. Run it again from the homepage.")
    return r


@router.get("/s/{result_id}.png", summary="Share image for a scan")
async def scan_image(request: Request, result_id: str) -> Response:
    """The 1200×675 PNG for a scan result."""
    r = _get(result_id)
    short = _short_url(request, r.id).split("://", 1)[-1]
    png = await asyncio.to_thread(musehub_scan_card.render_card, r, short)
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@router.get("/s/{result_id}", summary="Shareable scan result page")
async def scan_page(request: Request, result_id: str) -> Response:
    """The page a short URL opens: the result, the Install Muse button, and the method."""
    r = _get(result_id)
    return _templates.TemplateResponse(
        request,
        "musehub/pages/scan_result.html",
        {
            "title": f"{r.repo} scan",
            "scan": _payload(request, r),
            "grep_label": musehub_scan_card.fmt_tokens(r.grep_tokens),
            "muse_label": musehub_scan_card.fmt_tokens(r.muse_tokens),
            "muse_pct": max(1.0, round(100 * r.muse_tokens / r.grep_tokens, 1)) if r.grep_tokens else 1.0,
            "scan_prompt": musehub_scan.BENCHMARK_PROMPT,
        },
    )
