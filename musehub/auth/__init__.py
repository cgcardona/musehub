"""
Muse Authentication Module

Provides JWT-based access token generation and validation.
"""

from musehub.auth.tokens import (
    generate_access_code,
    validate_access_code,
    get_user_id_from_token,
    hash_token,
    AccessCodeError,
)
from musehub.auth.dependencies import optional_token, require_valid_token, require_device_id

__all__ = [
    "generate_access_code",
    "validate_access_code",
    "get_user_id_from_token",
    "hash_token",
    "AccessCodeError",
    "optional_token",
    "require_valid_token",
    "require_device_id",
]
