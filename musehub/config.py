"""
Muse Configuration

Environment-based configuration for the Muse service.
"""

import logging
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _app_version_from_package() -> str:
    """Read version from the single source of truth (pyproject.toml via protocol.version)."""
    from musehub.protocol.version import MUSE_VERSION
    return MUSE_VERSION


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service Info
    app_name: str = "Muse"
    app_version: str = _app_version_from_package()
    debug: bool = False
    muse_env: str = "production"  # "test" | "development" | "production"

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 10001

    # Database Configuration
    # PostgreSQL: postgresql+asyncpg://user:pass@localhost:5432/muse
    # SQLite (dev): sqlite+aiosqlite:///./muse.db
    database_url: str | None = None
    db_password: str | None = None

    # CORS Settings (fail closed: no default origins)
    # Set CORS_ORIGINS (JSON array) in .env. Local dev: ["http://localhost:10003", "muse://"].
    # Production: exact origins only. Never use "*" in production.
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def _warn_cors_wildcard_in_production(self) -> "Settings":
        """Warn when CORS allows all origins in non-debug (production) mode."""
        if not self.debug and self.cors_origins and "*" in self.cors_origins:
            logging.getLogger(__name__).warning(
                "CORS allows all origins (*) with DEBUG=false. "
                "Set CORS_ORIGINS to exact origins in production."
            )
        return self

    # Access Token Settings
    # Generate secret with: openssl rand -hex 32
    access_token_secret: str | None = None
    access_token_algorithm: str = "HS256"
    # In-memory revocation cache TTL (seconds). Reduces DB hits; revocation visible within this window.
    token_revocation_cache_ttl_seconds: int = 60

    # AWS S3 Asset Delivery (drum kits, GM soundfont)
    # Region MUST match the bucket's region (S3 returns 301 if URL uses wrong region).
    aws_region: str = "eu-west-1"
    aws_s3_asset_bucket: str | None = None
    aws_cloudfront_domain: str | None = None
    presign_expiry_seconds: int = 1800  # 30-min default for presigned download URLs

    # Asset endpoint rate limits (UUID-only auth, no JWT)
    asset_rate_limit_per_device: str = "30/minute"
    asset_rate_limit_per_ip: str = "120/minute"

    # MCP rate limits — agents get a higher tier than anonymous/human callers.
    # Agent tokens carry `token_type: "agent"` in their JWT claims.
    mcp_rate_limit_human: str = "60/minute"
    mcp_rate_limit_agent: str = "600/minute"
    mcp_rate_limit_anonymous: str = "20/minute"

    # Stdio MCP server: proxy DAW tools to Muse backend
    muse_mcp_url: str | None = None
    mcp_token: str | None = None

    # MuseHub object storage — binary artifacts (MIDI, MP3, WebP) stored as flat files
    # under <musehub_objects_dir>/<repo_id>/<object_id>. Mount on a persistent volume in prod.
    musehub_objects_dir: str = "/data/musehub/objects"

    # Webhook secret encryption key — AES-256 (Fernet) key for encrypting webhook signing
    # secrets at rest. Generate with:
    # python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    webhook_secret_key: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently discard unknown env vars (e.g. OPENROUTER_API_KEY from other tools)
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience access
settings = get_settings()
