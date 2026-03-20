"""Pytest configuration and fixtures."""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator, Generator

# Set before any musehub imports so the Settings lru_cache picks up the value.
# This is a test-only secret; in CI/Docker the real secret comes from the environment.
os.environ.setdefault("ACCESS_TOKEN_SECRET", "test-secret-for-unit-tests-do-not-use-in-prod")
os.environ.setdefault("MUSE_ENV", "test")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from musehub.db import database
from musehub.db.database import Base, get_db
from musehub.db.models import User
from musehub.main import app


def pytest_configure(config: pytest.Config) -> None:
    """Ensure asyncio_mode is auto so async fixtures work (e.g. in Docker when pyproject not in cwd)."""
    if hasattr(config.option, "asyncio_mode") and config.option.asyncio_mode is None:
        config.option.asyncio_mode = "auto"
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_variation_store() -> Generator[None, None, None]:
    """Reset the singleton VariationStore between tests to prevent cross-test pollution.

    Gracefully no-ops if the variation module has been removed (MuseHub extraction).
    """
    yield
    try:
        from musehub.variation.storage.variation_store import reset_variation_store
        reset_variation_store()
    except ModuleNotFoundError:
        pass


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create an in-memory test database session."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    old_engine = database._engine
    old_factory = database._async_session_factory
    database._engine = engine
    database._async_session_factory = async_session_factory
    try:
        async with async_session_factory() as session:
            async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
                yield session
            app.dependency_overrides[get_db] = override_get_db
            yield session
            app.dependency_overrides.clear()
    finally:
        database._engine = old_engine
        database._async_session_factory = old_factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:

    """Create an async test client. Depends on db_session so auth revocation check uses test DB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# -----------------------------------------------------------------------------
# Auth fixtures for API contract and integration tests
# -----------------------------------------------------------------------------

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:

    """Create a test user (for authenticated route tests)."""
    user = User(
        id="550e8400-e29b-41d4-a716-446655440000",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User) -> str:

    """JWT for test_user (1 hour)."""
    from musehub.auth.tokens import create_access_token
    return create_access_token(user_id=test_user.id, expires_hours=1)


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:

    """Headers with Bearer token and JSON content type."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }
