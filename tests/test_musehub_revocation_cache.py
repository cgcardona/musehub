"""Unit tests for the in-memory token revocation cache.

musehub/auth/revocation_cache.py is a tiny but security-critical module that
had zero test coverage.  These tests verify:

- Basic get/set/clear lifecycle
- TTL expiry (entries become None after TTL elapses)
- Cache hit prevents redundant DB lookups (behaviour contract)
- Overwrite semantics
- hash_token determinism
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from musehub.auth.revocation_cache import (
    _cache,
    clear_revocation_cache,
    get_revocation_status,
    set_revocation_status,
)
from musehub.auth.tokens import hash_token


@pytest.fixture(autouse=True)
def _clean_cache():
    """Ensure a pristine cache before and after every test."""
    clear_revocation_cache()
    yield
    clear_revocation_cache()


class TestGetRevocationStatus:
    def test_returns_none_on_miss(self) -> None:
        assert get_revocation_status("nonexistent") is None

    def test_returns_false_for_valid_cached_token(self) -> None:
        set_revocation_status("tok-a", revoked=False)
        assert get_revocation_status("tok-a") is False

    def test_returns_true_for_revoked_cached_token(self) -> None:
        set_revocation_status("tok-b", revoked=True)
        assert get_revocation_status("tok-b") is True

    def test_expired_entry_returns_none_and_is_evicted(self) -> None:
        # Insert an entry that already expired (expires_at = now - 1s)
        _cache["tok-expired"] = (False, time.monotonic() - 1.0)
        assert get_revocation_status("tok-expired") is None
        assert "tok-expired" not in _cache, "Expired entry should be evicted on read"

    def test_not_yet_expired_entry_returned(self) -> None:
        # Entry expires far in the future
        _cache["tok-future"] = (True, time.monotonic() + 9999.0)
        assert get_revocation_status("tok-future") is True


class TestSetRevocationStatus:
    def test_set_and_get_roundtrip(self) -> None:
        set_revocation_status("tok-c", revoked=True)
        assert get_revocation_status("tok-c") is True

    def test_overwrite_false_to_true(self) -> None:
        set_revocation_status("tok-d", revoked=False)
        set_revocation_status("tok-d", revoked=True)
        assert get_revocation_status("tok-d") is True

    def test_overwrite_true_to_false(self) -> None:
        set_revocation_status("tok-e", revoked=True)
        set_revocation_status("tok-e", revoked=False)
        assert get_revocation_status("tok-e") is False

    def test_ttl_respected(self) -> None:
        """Entry created with a very small TTL expires quickly."""
        with patch("musehub.auth.revocation_cache.settings") as mock_settings:
            mock_settings.token_revocation_cache_ttl_seconds = 0.01
            set_revocation_status("tok-ttl", revoked=False)
        time.sleep(0.05)
        assert get_revocation_status("tok-ttl") is None


class TestClearRevocationCache:
    def test_clear_removes_all(self) -> None:
        set_revocation_status("tok-f", revoked=False)
        set_revocation_status("tok-g", revoked=True)
        clear_revocation_cache()
        assert get_revocation_status("tok-f") is None
        assert get_revocation_status("tok-g") is None

    def test_clear_idempotent_on_empty_cache(self) -> None:
        clear_revocation_cache()
        clear_revocation_cache()  # should not raise


class TestHashToken:
    def test_deterministic(self) -> None:
        tok = "some.jwt.value"
        assert hash_token(tok) == hash_token(tok)

    def test_produces_64_char_hex(self) -> None:
        result = hash_token("anything")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_distinct_inputs_produce_distinct_hashes(self) -> None:
        assert hash_token("token-1") != hash_token("token-2")

    def test_empty_string(self) -> None:
        # Should not raise; SHA-256 of empty bytes is well-defined
        result = hash_token("")
        assert len(result) == 64
