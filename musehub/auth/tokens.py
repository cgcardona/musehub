"""
Access Token Generation and Validation

Provides cryptographically signed JWT tokens for time-limited access control.
Tokens are self-contained and don't require database storage.
"""
from __future__ import annotations


import hashlib
import jwt
from datetime import datetime, timedelta, timezone

from typing import Required, TypedDict

from musehub.config import settings


class AccessCodeError(Exception):
    """Raised when access code validation fails."""
    pass


class TokenClaims(TypedDict, total=False):
    """Decoded JWT payload returned by validate_access_code.

    ``type``, ``iat``, and ``exp`` are always present.
    ``sub`` is the user ID — omitted for anonymous/machine tokens.
    ``role`` is set to ``"admin"`` for tokens issued with ``is_admin=True``.
    ``token_type`` is ``"agent"`` for AI agent tokens, ``"human"`` otherwise.
    ``agent_name`` is an optional display identifier for the agent.
    """

    type: Required[str]
    iat: Required[int]
    exp: Required[int]
    sub: str
    role: str
    token_type: str   # "human" | "agent"
    agent_name: str   # e.g. "my-coding-agent/1.0"


def _get_secret() -> str:
    """Get the token signing secret, raising if not configured."""
    if not settings.access_token_secret:
        raise AccessCodeError(
            "ACCESS_TOKEN_SECRET not configured. "
            "Generate one with: openssl rand -hex 32"
        )
    return settings.access_token_secret


def hash_token(token: str) -> str:
    """
    Generate a SHA256 hash of a token for storage.
    
    This allows us to track tokens without storing the actual token value.
    
    Args:
        token: The JWT token string
        
    Returns:
        SHA256 hex digest of the token
    """
    return hashlib.sha256(token.encode()).hexdigest()


def generate_agent_token(
    user_id: str | None = None,
    agent_name: str | None = None,
    duration_days: int = 365,
    is_admin: bool = False,
) -> str:
    """Generate a long-lived JWT token marked as an AI agent token.

    Agent tokens receive higher rate limits and appear with an "agent" badge
    in the MuseHub activity feed. The ``token_type`` claim is set to ``"agent"``.

    Args:
        user_id: MuseHub user ID the agent acts on behalf of.
        agent_name: Optional human-readable agent identifier (e.g. "my-bot/1.0").
        duration_days: Token validity in days (default 365).
        is_admin: If True, adds admin role to the token.

    Returns:
        Signed JWT token string with ``token_type: "agent"`` claim.
    """
    secret = _get_secret()
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(days=duration_days)

    payload: dict[str, object] = {
        "type": "access",
        "token_type": "agent",
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
    }
    if user_id:
        payload["sub"] = user_id
    if agent_name:
        payload["agent_name"] = agent_name
    if is_admin:
        payload["role"] = "admin"

    return str(jwt.encode(payload, secret, algorithm=settings.access_token_algorithm))


def generate_access_code(
    user_id: str | None = None,
    duration_hours: int | None = None,
    duration_days: int | None = None,
    duration_minutes: int | None = None,
    is_admin: bool = False,
) -> str:
    """
    Generate a signed access code (JWT) with the specified duration.
    
    Args:
        user_id: User UUID to associate with this token (required for budget tracking)
        duration_hours: Token validity in hours
        duration_days: Token validity in days 
        duration_minutes: Token validity in minutes (for testing)
        is_admin: If True, adds admin role to the token
        
    Returns:
        Signed JWT token string
        
    Raises:
        AccessCodeError: If no duration specified or secret not configured
    """
    secret = _get_secret()
    
    # Calculate total duration
    total_hours: float = 0.0
    if duration_hours:
        total_hours += duration_hours
    if duration_days:
        total_hours += duration_days * 24
    if duration_minutes:
        total_hours += duration_minutes / 60
        
    if total_hours <= 0:
        raise AccessCodeError(
            "Must specify at least one of: duration_hours, duration_days, duration_minutes"
        )
    
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(hours=total_hours)
    
    payload = {
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
    }
    
    # Add user ID if provided (for budget tracking)
    if user_id:
        payload["sub"] = user_id
    
    # Add admin role if specified
    if is_admin:
        payload["role"] = "admin"
    
    token = jwt.encode(
        payload,
        secret,
        algorithm=settings.access_token_algorithm,
    )
    return str(token)


def create_access_token(
    user_id: str | None = None,
    expires_hours: int | None = None,
    expires_days: int | None = None,
    is_admin: bool = False,
) -> str:
    """
    Alias for generate_access_code for test/API compatibility.
    Generates a signed JWT for the given user and duration.
    """
    return generate_access_code(
        user_id=user_id,
        duration_hours=expires_hours,
        duration_days=expires_days,
        is_admin=is_admin,
    )


def validate_access_code(token: str) -> TokenClaims:
    """
    Validate an access code and return its claims.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded token payload dict with keys: type, iat, exp, and optionally sub (user_id)
        
    Raises:
        AccessCodeError: If token is invalid, expired, or malformed
    """
    secret = _get_secret()
    
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[settings.access_token_algorithm],
        )
        
        # Validate and narrow each claim at the jwt.decode() boundary.
        # jwt.decode() returns dict[str, Any]; we validate types explicitly
        # rather than coercing so malformed tokens raise clear errors.
        raw_type = payload.get("type")
        if not isinstance(raw_type, str) or raw_type != "access":
            raise AccessCodeError("Invalid token type")

        raw_iat = payload.get("iat", 0)
        raw_exp = payload.get("exp", 0)
        if not isinstance(raw_iat, int) or not isinstance(raw_exp, int):
            raise AccessCodeError("Malformed token: iat/exp must be integers")

        claims = TokenClaims(type=raw_type, iat=raw_iat, exp=raw_exp)

        raw_sub = payload.get("sub")
        if raw_sub is not None:
            if not isinstance(raw_sub, str):
                raise AccessCodeError("Malformed token: sub must be a string")
            claims["sub"] = raw_sub

        raw_role = payload.get("role")
        if raw_role is not None:
            if not isinstance(raw_role, str):
                raise AccessCodeError("Malformed token: role must be a string")
            claims["role"] = raw_role

        raw_token_type = payload.get("token_type")
        if raw_token_type is not None:
            if not isinstance(raw_token_type, str):
                raise AccessCodeError("Malformed token: token_type must be a string")
            claims["token_type"] = raw_token_type

        raw_agent_name = payload.get("agent_name")
        if raw_agent_name is not None:
            if not isinstance(raw_agent_name, str):
                raise AccessCodeError("Malformed token: agent_name must be a string")
            claims["agent_name"] = raw_agent_name

        return claims
        
    except jwt.ExpiredSignatureError:
        raise AccessCodeError("Access code has expired")
    except jwt.InvalidTokenError as e:
        raise AccessCodeError(f"Invalid access code: {e}")


def get_user_id_from_token(token: str) -> str | None:
    """
    Extract the user ID from a token without full validation.

    SECURITY: Do not use for authorization. This decodes without verifying
    the signature. Use claims from validate_access_code() or require_valid_token
    for any access decisions.

    Args:
        token: JWT token string

    Returns:
        User ID if present, None otherwise
    """
    try:
        payload = jwt.decode(
            token,
            options={"verify_signature": False},
        )
        sub = payload.get("sub")
        return str(sub) if sub is not None else None
    except jwt.InvalidTokenError:
        return None


def get_token_expiration(token: str) -> datetime:
    """
    Get the expiration datetime for a token without fully validating it.
    Useful for displaying expiration info to users.
    
    Args:
        token: JWT token string
        
    Returns:
        Expiration datetime (UTC)
        
    Raises:
        AccessCodeError: If token is malformed
    """
    try:
        # Decode without verification to read expiration
        payload = jwt.decode(
            token,
            options={"verify_signature": False},
        )
        exp_timestamp = payload.get("exp")
        if not exp_timestamp:
            raise AccessCodeError("Token has no expiration")
        return datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    except jwt.InvalidTokenError as e:
        raise AccessCodeError(f"Invalid token format: {e}")
