"""Tests for the free repo scan: the simulation, the share image, and the routes."""
from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from PIL import Image

from musehub.services import musehub_scan as scan
from musehub.services.musehub_scan_card import fmt_tokens, render_card

# ── Unit: parsing ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text,repo", [
    ("pallets/flask", "pallets/flask"),
    ("https://github.com/pallets/flask", "pallets/flask"),
    ("github.com/pallets/flask.git", "pallets/flask"),
    ("  https://www.github.com/a-b/c.d/  ", "a-b/c.d"),
])
def test_parse_repo_accepts_urls_and_slugs(text: str, repo: str) -> None:
    assert scan.parse_repo(text) == repo


@pytest.mark.parametrize("text", ["flask", "https://gitlab.com/a/b/c", "a/b/c", ""])
def test_parse_repo_rejects_everything_else(text: str) -> None:
    with pytest.raises(scan.ScanError):
        scan.parse_repo(text)


def test_changed_symbols_reads_hunk_headers_and_definitions() -> None:
    patch = (
        "@@ -10,6 +10,7 @@ def charge(invoice, amount):\n"
        "-    total = amount\n"
        "+    total = round(amount, 2)\n"
        "@@ -40,3 +41,9 @@ class Ledger:\n"
        "+    def settle(self):\n"
        "+        pass\n"
        "+export const refund = async (id) => {\n"
    )
    assert scan.changed_symbols(patch) == ["charge", "Ledger", "settle", "refund"]


def test_changed_symbols_skips_names_too_common_to_trace() -> None:
    assert scan.changed_symbols("@@ -1 +1 @@ def main():\n+    run()\n") == []


# ── Unit: costing ────────────────────────────────────────────────────────────


_FILLER = "".join(f"\ndef helper_{i}(x):\n    return x + {i}  # unrelated code the agent still reads\n" for i in range(60))


def _snapshot(filler: str = _FILLER) -> scan.Snapshot:
    files = {
        "billing/models.py": "class Invoice:\n    def save(self):\n        db.write(self)\n\ndef charge(inv):\n    inv.save()\n    return total(inv)\n",
        "billing/api.py": "from billing.models import charge\n\ndef create(req):\n    return charge(req.invoice)\n",
        "billing/jobs.py": "from billing.models import charge as bill\n\ndef nightly():\n    for i in todo():\n        bill(i)\n",
        "reports/export.py": "# charge is documented elsewhere\ndef write_row(r):\n    return create(r)\n",
    }
    return scan.Snapshot({path: text + filler for path, text in files.items()})


def test_cost_counts_callers_two_levels_deep_and_false_matches() -> None:
    c = scan.cost_of(_snapshot(), "charge")
    # Level 1: billing/api.py create(). Level 2: reports/export.py calls create().
    assert c.callers == 2
    # The import lines and the comment mention "charge" without calling it.
    assert c.false_matches == 3
    # The aliased import is the caller grep never finds by name.
    assert c.alias_misses == 1
    assert c.muse_tokens == scan.MUSE_TOKENS_ENVELOPE + 2 * scan.MUSE_TOKENS_PER_CALLER
    assert c.grep_tokens > c.muse_tokens


def test_tiny_files_show_no_saving() -> None:
    """When the files are smaller than Muse's answer, the scan says so instead of inventing a gain."""
    r = scan.summarize("acme/tiny", "e" * 40, _snapshot(filler=""), [(1, "t", ["charge"])])
    assert r.task_saving == 0.0


def test_summarize_caps_the_per_task_estimate_at_the_measured_share() -> None:
    r = scan.summarize("acme/pay", "a" * 40, _snapshot(), [(1, "Fix charge", ["charge"]), (2, "Nothing traceable", ["nope"])])
    assert [p.number for p in r.pulls] == [1]
    assert r.ratio == round(r.grep_tokens / r.muse_tokens, 1)
    assert 0 < r.task_saving <= round(scan.EXPLORE_SHARE * scan.MAX_REPLACEABLE, 3)
    assert r.method == "simulated"


def test_remember_and_recent_for_reuse_a_fresh_scan() -> None:
    r = scan.remember(scan.summarize("Acme/Pay", "b" * 40, _snapshot(), [(1, "t", ["charge"])]))
    assert scan.recall(r.id) is r
    assert scan.recent_for("acme/pay") is r


def test_benchmark_prompt_is_the_measured_version() -> None:
    assert "Measure it; don't" in scan.BENCHMARK_PROMPT
    assert "muse code impact" in scan.BENCHMARK_PROMPT


# ── Unit: share image ────────────────────────────────────────────────────────


@pytest.mark.parametrize("n,label", [(2_410_000, "2.41M"), (25_300, "25K"), (1_200, "1.2K"), (900, "900")])
def test_fmt_tokens(n: int, label: str) -> None:
    assert fmt_tokens(n) == label


def test_render_card_is_an_x_sized_png() -> None:
    r = scan.summarize("acme/pay", "c" * 40, _snapshot(), [(1, "t", ["charge"])])
    img = Image.open(io.BytesIO(render_card(r, "musehub.ai/s/abc12")))
    assert img.format == "PNG"
    assert img.size == (1200, 675)


# ── Integration: routes ──────────────────────────────────────────────────────


@pytest.fixture
def fake_scan(monkeypatch: pytest.MonkeyPatch) -> scan.ScanResult:
    result = scan.summarize("acme/pay", "d" * 40, _snapshot(), [(7, "Fix charge", ["charge"])])

    async def _scan(repo_text: str) -> scan.ScanResult:
        return result

    monkeypatch.setattr(scan, "scan", _scan)
    monkeypatch.setattr(scan, "recent_for", lambda repo: None)
    return result


@pytest.mark.anyio
async def test_post_scan_returns_result_with_short_and_image_urls(client: AsyncClient, fake_scan: scan.ScanResult) -> None:
    res = await client.post("/scan", json={"repo": "https://github.com/acme/pay"})
    assert res.status_code == 200
    body = res.json()
    assert body["repo"] == "acme/pay"
    assert body["ratio"] == fake_scan.ratio
    assert body["method"] == "simulated"
    assert body["shortUrl"].endswith(f"/s/{fake_scan.id}")
    assert body["imageUrl"].endswith(f"/s/{fake_scan.id}.png")


@pytest.mark.anyio
async def test_post_scan_explains_bad_input(client: AsyncClient) -> None:
    res = await client.post("/scan", json={"repo": "not a repo"})
    assert res.status_code == 422
    assert "owner/repo" in res.json()["error"]


@pytest.mark.anyio
async def test_result_page_has_og_image_install_button_and_prompt(client: AsyncClient, fake_scan: scan.ScanResult) -> None:
    await client.post("/scan", json={"repo": "acme/pay"})
    res = await client.get(f"/s/{fake_scan.id}")
    assert res.status_code == 200
    html = res.text
    assert f'/s/{fake_scan.id}.png' in html and 'og:image' in html
    assert "Install Muse" in html
    assert "How the scan works" in html and "muse code impact" in html


@pytest.mark.anyio
async def test_share_image_route(client: AsyncClient, fake_scan: scan.ScanResult) -> None:
    await client.post("/scan", json={"repo": "acme/pay"})
    res = await client.get(f"/s/{fake_scan.id}.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"


@pytest.mark.anyio
async def test_unknown_scan_is_404(client: AsyncClient) -> None:
    assert (await client.get("/s/zzzzz")).status_code == 404


@pytest.mark.anyio
async def test_homepage_shows_the_free_scan_card(client: AsyncClient) -> None:
    res = await client.get("/explore")
    assert res.status_code == 200
    html = res.text
    assert 'id="scan-card"' in html
    assert "Free scan" in html
    assert "Your coding agent spends nearly half its tokens looking ahead." in html
    assert 'id="scan-info"' in html
