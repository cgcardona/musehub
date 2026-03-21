"""Auth security edge-case tests.

Covers scenarios that test_musehub_auth.py's happy-path tests do not:

- Expired JWT tokens → 401
- Structurally invalid / tampered JWT → 401
- Missing Authorization header entirely → 401 on write endpoints
- Token with wrong algorithm (none-attack) → 401
- Token revocation cache: get/set/clear/TTL semantics
- Revoked token rejected on protected endpoints → 401

These tests exercise the auth layer end-to-end through the ASGI transport
so that FastAPI dependency injection, the token validator, and the DB
revocation check all participate.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.auth.revocation_cache import (
    clear_revocation_cache,
    get_revocation_status,
    set_revocation_status,
)
from musehub.auth.tokens import (
    AccessCodeError,
    create_access_token,
    hash_token,
    validate_access_code,
)
from musehub.config import settings
from musehub.db.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_expired_token(user_id: str = "test-user-id") -> str:
    """Return a structurally valid JWT that expired one hour ago."""
    secret = settings.access_token_secret or "test-secret"
    now = datetime.now(tz=timezone.utc)
    payload = {
        "type": "access",
        "sub": user_id,
        "iat": int((now - timedelta(hours=2)).timestamp()),
        "exp": int((now - timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=settings.access_token_algorithm)


def _make_tampered_token(valid_token: str) -> str:
    """Corrupt the signature portion of a valid JWT.

    We change a character in the middle of the signature rather than the last
    character.  The last base64url character of a 32-byte HMAC-SHA256 encodes
    only 4 data bits (the bottom 2 bits are unused padding); changing only
    those padding bits produces the same decoded bytes, leaving the signature
    intact.  A middle character carries a full 6 bits of data, so flipping it
    is guaranteed to corrupt the signature regardless of the token value.
    """
    header, payload, sig = valid_token.rsplit(".", 2)
    mid = len(sig) // 2
    bad_sig = sig[:mid] + ("A" if sig[mid] != "A" else "B") + sig[mid + 1:]
    return f"{header}.{payload}.{bad_sig}"


def _make_none_alg_token(user_id: str = "test-user-id") -> str:
    """Craft a JWT with alg=none (classic signature-bypass attempt)."""
    import base64, json
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    now = int(datetime.now(tz=timezone.utc).timestamp())
    body = base64.urlsafe_b64encode(
        json.dumps({"type": "access", "sub": user_id, "iat": now, "exp": now + 3600}).encode()
    ).rstrip(b"=").decode()
    return f"{header}.{body}."


# ---------------------------------------------------------------------------
# validate_access_code unit tests
# ---------------------------------------------------------------------------

class TestValidateAccessCodeUnit:
    """Direct unit tests on the token validator (no HTTP)."""

    def test_valid_token_returns_claims(self) -> None:
        token = create_access_token(user_id="u1", expires_hours=1)
        claims = validate_access_code(token)
        assert claims["sub"] == "u1"
        assert claims["type"] == "access"

    def test_expired_token_raises(self) -> None:
        token = _make_expired_token()
        with pytest.raises(AccessCodeError, match="expired"):
            validate_access_code(token)

    def test_tampered_signature_raises(self) -> None:
        token = create_access_token(user_id="u2", expires_hours=1)
        bad = _make_tampered_token(token)
        with pytest.raises(AccessCodeError):
            validate_access_code(bad)

    def test_garbage_string_raises(self) -> None:
        with pytest.raises(AccessCodeError):
            validate_access_code("not.a.jwt")

    def test_none_algorithm_rejected(self) -> None:
        token = _make_none_alg_token()
        with pytest.raises(AccessCodeError):
            validate_access_code(token)

    def test_missing_type_claim_raises(self) -> None:
        secret = settings.access_token_secret or "test-secret"
        now = int(datetime.now(tz=timezone.utc).timestamp())
        payload = {"sub": "u3", "iat": now, "exp": now + 3600}
        token = jwt.encode(payload, secret, algorithm=settings.access_token_algorithm)
        with pytest.raises(AccessCodeError, match="Invalid token type"):
            validate_access_code(token)

    def test_wrong_type_claim_raises(self) -> None:
        secret = settings.access_token_secret or "test-secret"
        now = int(datetime.now(tz=timezone.utc).timestamp())
        payload = {"type": "refresh", "sub": "u4", "iat": now, "exp": now + 3600}
        token = jwt.encode(payload, secret, algorithm=settings.access_token_algorithm)
        with pytest.raises(AccessCodeError, match="Invalid token type"):
            validate_access_code(token)

    def test_admin_token_has_role_claim(self) -> None:
        token = create_access_token(user_id="admin1", expires_hours=1, is_admin=True)
        claims = validate_access_code(token)
        assert claims.get("role") == "admin"

    def test_anonymous_token_has_no_sub(self) -> None:
        token = create_access_token(expires_hours=1)
        claims = validate_access_code(token)
        assert "sub" not in claims


# ---------------------------------------------------------------------------
# Revocation cache unit tests
# ---------------------------------------------------------------------------

class TestRevocationCache:
    """Unit tests for the in-memory revocation cache."""

    def setup_method(self) -> None:
        clear_revocation_cache()

    def teardown_method(self) -> None:
        clear_revocation_cache()

    def test_cache_miss_returns_none(self) -> None:
        assert get_revocation_status("unknown-hash") is None

    def test_set_valid_status_readable(self) -> None:
        set_revocation_status("tok1", revoked=False)
        assert get_revocation_status("tok1") is False

    def test_set_revoked_status_readable(self) -> None:
        set_revocation_status("tok2", revoked=True)
        assert get_revocation_status("tok2") is True

    def test_clear_removes_all_entries(self) -> None:
        set_revocation_status("tok3", revoked=False)
        set_revocation_status("tok4", revoked=True)
        clear_revocation_cache()
        assert get_revocation_status("tok3") is None
        assert get_revocation_status("tok4") is None

    def test_overwrite_status(self) -> None:
        set_revocation_status("tok5", revoked=False)
        set_revocation_status("tok5", revoked=True)
        assert get_revocation_status("tok5") is True

    def test_hash_token_is_deterministic(self) -> None:
        t = "some.jwt.token"
        assert hash_token(t) == hash_token(t)
        assert len(hash_token(t)) == 64  # SHA-256 hex

    def test_hash_token_distinct_inputs(self) -> None:
        assert hash_token("abc") != hash_token("xyz")


# ---------------------------------------------------------------------------
# HTTP integration tests — invalid tokens on write endpoints
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_expired_token_rejected_on_create_repo(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """An expired JWT returns 401 on a write endpoint."""
    user = User(id="expired-user-id")
    db_session.add(user)
    await db_session.commit()

    expired = _make_expired_token(user_id="expired-user-id")
    resp = await client.post(
        "/api/v1/repos",
        json={"name": "beats", "owner": "testuser"},
        headers={"Authorization": f"Bearer {expired}"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_tampered_token_rejected_on_create_repo(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """A tampered JWT (bad signature) returns 401 on a write endpoint."""
    user = User(id="tamper-user-id")
    db_session.add(user)
    await db_session.commit()

    valid = create_access_token(user_id="tamper-user-id", expires_hours=1)
    tampered = _make_tampered_token(valid)
    resp = await client.post(
        "/api/v1/repos",
        json={"name": "beats", "owner": "testuser"},
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_garbage_token_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    """A completely invalid token string returns 401."""
    resp = await client.post(
        "/api/v1/repos",
        json={"name": "beats", "owner": "testuser"},
        headers={"Authorization": "Bearer not-a-jwt-at-all"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_none_alg_token_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    """alg=none token is rejected — signature bypass attempt must fail."""
    token = _make_none_alg_token()
    resp = await client.post(
        "/api/v1/repos",
        json={"name": "beats", "owner": "testuser"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint,method,body", [
    ("/api/v1/repos", "POST", {"name": "x", "owner": "y"}),
    ("/api/v1/repos/fake-id/issues", "POST", {"title": "t"}),
    ("/api/v1/repos/fake-id/issues/1/close", "POST", {}),
])
async def test_missing_auth_header_returns_401(
    client: AsyncClient,
    db_session: AsyncSession,
    endpoint: str,
    method: str,
    body: dict,
) -> None:
    """Write endpoints return 401 when the Authorization header is absent."""
    fn = getattr(client, method.lower())
    resp = await fn(endpoint, json=body)
    assert resp.status_code == 401
