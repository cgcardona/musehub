"""Unit tests for musehub_release_packager.py.

The packager is a pure URL-builder with no DB access — ideal for fast,
zero-fixture unit tests that run without any test DB setup.
"""
from __future__ import annotations

import pytest

from musehub.services.musehub_release_packager import (
    build_download_urls,
    build_empty_download_urls,
)

REPO_ID = "repo-abc123"
RELEASE_ID = "rel-xyz789"
BASE = f"/api/v1/musehub/repos/{REPO_ID}/releases/{RELEASE_ID}/packages"


class TestBuildDownloadUrls:
    def test_all_false_returns_all_none(self) -> None:
        urls = build_download_urls(REPO_ID, RELEASE_ID)
        assert urls.midi_bundle is None
        assert urls.stems is None
        assert urls.mp3 is None
        assert urls.musicxml is None
        assert urls.metadata is None

    def test_midi_only(self) -> None:
        urls = build_download_urls(REPO_ID, RELEASE_ID, has_midi=True)
        assert urls.midi_bundle == f"{BASE}/midi"
        assert urls.stems is None
        assert urls.mp3 is None
        assert urls.musicxml is None
        assert urls.metadata == f"{BASE}/metadata"

    def test_stems_only(self) -> None:
        urls = build_download_urls(REPO_ID, RELEASE_ID, has_stems=True)
        assert urls.stems == f"{BASE}/stems"
        assert urls.midi_bundle is None
        assert urls.metadata == f"{BASE}/metadata"

    def test_mp3_only(self) -> None:
        urls = build_download_urls(REPO_ID, RELEASE_ID, has_mp3=True)
        assert urls.mp3 == f"{BASE}/mp3"
        assert urls.metadata == f"{BASE}/metadata"

    def test_musicxml_only(self) -> None:
        urls = build_download_urls(REPO_ID, RELEASE_ID, has_musicxml=True)
        assert urls.musicxml == f"{BASE}/musicxml"
        assert urls.metadata == f"{BASE}/metadata"

    def test_all_true_all_urls_present(self) -> None:
        urls = build_download_urls(
            REPO_ID, RELEASE_ID,
            has_midi=True, has_stems=True, has_mp3=True, has_musicxml=True,
        )
        assert urls.midi_bundle == f"{BASE}/midi"
        assert urls.stems == f"{BASE}/stems"
        assert urls.mp3 == f"{BASE}/mp3"
        assert urls.musicxml == f"{BASE}/musicxml"
        assert urls.metadata == f"{BASE}/metadata"

    def test_metadata_absent_when_nothing_available(self) -> None:
        urls = build_download_urls(REPO_ID, RELEASE_ID)
        assert urls.metadata is None

    def test_metadata_present_when_any_flag_true(self) -> None:
        for flag in ("has_midi", "has_stems", "has_mp3", "has_musicxml"):
            urls = build_download_urls(REPO_ID, RELEASE_ID, **{flag: True})
            assert urls.metadata is not None, f"metadata should exist when {flag}=True"

    @pytest.mark.parametrize("flag,attr,suffix", [
        ("has_midi", "midi_bundle", "midi"),
        ("has_stems", "stems", "stems"),
        ("has_mp3", "mp3", "mp3"),
        ("has_musicxml", "musicxml", "musicxml"),
    ])
    def test_url_pattern_matches_expected_suffix(
        self, flag: str, attr: str, suffix: str,
    ) -> None:
        urls = build_download_urls(REPO_ID, RELEASE_ID, **{flag: True})
        url = getattr(urls, attr)
        assert url is not None
        assert url.endswith(f"/{suffix}")
        assert REPO_ID in url
        assert RELEASE_ID in url

    def test_different_repo_and_release_ids(self) -> None:
        other = build_download_urls("repo-other", "rel-other", has_midi=True)
        assert "repo-other" in (other.midi_bundle or "")
        assert "rel-other" in (other.midi_bundle or "")


class TestBuildEmptyDownloadUrls:
    def test_all_fields_none(self) -> None:
        urls = build_empty_download_urls()
        assert urls.midi_bundle is None
        assert urls.stems is None
        assert urls.mp3 is None
        assert urls.musicxml is None
        assert urls.metadata is None
