"""Tests for MuseHub MCP tools.

Covers all acceptance criteria:
  - musehub_list_branches returns all branches with head commit IDs
  - musehub_read_file returns file metadata with MIME type
  - musehub_list_commits returns paginated commit list
  - musehub_search supports path and commit modes
  - musehub_get_context returns full AI context document
  - All tools registered in MCP server with proper schemas
  - Tools handle errors gracefully (not_found, invalid dimension/mode)

Note: execute_browse_repo and execute_get_analysis remain as internal executor
functions, but musehub_browse_repo and musehub_get_analysis are no longer
registered as MCP tools (their capabilities are served by musehub_get_context).

Tests use conftest db_session (in-memory SQLite) and mock the executor's
AsyncSessionLocal to use the test session so no live DB is required.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from musehub.db.musehub_models import (
    MusehubBranch,
    MusehubCommit,
    MusehubObject,
    MusehubRepo,
)
from musehub.mcp.server import MuseMCPServer, ToolCallResult
from musehub.mcp.tools import MCP_TOOLS, MUSEHUB_TOOL_NAMES, TOOL_CATEGORIES
from musehub.mcp.tools.musehub import MUSEHUB_TOOLS
from musehub.services import musehub_mcp_executor as executor
from musehub.services.musehub_mcp_executor import MusehubToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int = 2024, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


async def _seed_repo(session: AsyncSession) -> MusehubRepo:
    """Insert a minimal repo, branch, commit, and object for tests."""
    repo = MusehubRepo(
        repo_id="repo-test-001",
        name="jazz-sessions",
        owner="testuser",
        slug="jazz-sessions",
        visibility="public",
        owner_user_id="user-001",
        created_at=_utc(),
    )
    session.add(repo)

    branch = MusehubBranch(
        branch_id="branch-001",
        repo_id="repo-test-001",
        name="main",
        head_commit_id="commit-001",
    )
    session.add(branch)

    commit = MusehubCommit(
        commit_id="commit-001",
        repo_id="repo-test-001",
        branch="main",
        parent_ids=[],
        message="add bass track",
        author="alice",
        timestamp=_utc(2024, 6, 15),
        snapshot_id="snap-001",
    )
    session.add(commit)

    obj = MusehubObject(
        object_id="sha256:abc123",
        repo_id="repo-test-001",
        path="tracks/bass.mid",
        size_bytes=2048,
        disk_path="/tmp/bass.mid",
        created_at=_utc(),
    )
    session.add(obj)

    await session.commit()
    return repo


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestMusehubToolsRegistered:
    """Verify that all musehub_* tools appear in the combined MCP registry."""

    def test_musehub_tools_in_mcp_tools(self) -> None:
        """All MUSEHUB_TOOLS appear in the combined MCP_TOOLS list."""
        registered_names = {t["name"] for t in MCP_TOOLS}
        for tool in MUSEHUB_TOOLS:
            assert tool["name"] in registered_names, (
                f"MuseHub tool '{tool['name']}' missing from MCP_TOOLS"
            )

    def test_musehub_tool_names_set_correct(self) -> None:
        """MUSEHUB_TOOL_NAMES matches the names declared in MUSEHUB_TOOLS."""
        expected = {t["name"] for t in MUSEHUB_TOOLS}
        assert MUSEHUB_TOOL_NAMES == expected

    def test_musehub_tools_in_categories(self) -> None:
        """Every musehub_* tool has an entry in TOOL_CATEGORIES."""
        from musehub.mcp.tools import MUSEHUB_ELICITATION_TOOL_NAMES, MUSEHUB_WRITE_TOOL_NAMES

        for name in MUSEHUB_TOOL_NAMES:
            assert name in TOOL_CATEGORIES, f"Tool '{name}' missing from TOOL_CATEGORIES"
            if name in MUSEHUB_ELICITATION_TOOL_NAMES:
                expected_category = "musehub-elicitation"
            elif name in MUSEHUB_WRITE_TOOL_NAMES:
                expected_category = "musehub-write"
            else:
                expected_category = "musehub-read"
            assert TOOL_CATEGORIES[name] == expected_category, (
                f"Tool '{name}' has category '{TOOL_CATEGORIES[name]}', expected '{expected_category}'"
            )

    def test_musehub_tools_have_required_fields(self) -> None:
        """Every tool has name, description, and inputSchema. Names start with musehub_ or muse_."""
        for tool in MUSEHUB_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool
            assert tool["name"].startswith("musehub_") or tool["name"].startswith("muse_"), (
                f"Tool name {tool['name']!r} must start with 'musehub_' or 'muse_'"
            )

    def test_musehub_tools_are_server_side(self) -> None:
        """Every musehub_* tool is marked server_side=True."""
        for tool in MUSEHUB_TOOLS:
            assert tool.get("server_side") is True, (
                f"Tool '{tool['name']}' must be server_side=True"
            )

    def test_all_tools_defined(self) -> None:
        """All 41 MuseHub tools (20 read + 16 write + 5 elicitation) are defined."""
        expected_read = {
            # Core repo reads
            "musehub_list_branches",
            "musehub_list_commits",
            "musehub_read_file",
            "musehub_search",
            "musehub_get_context",
            "musehub_get_commit",
            "musehub_compare",
            "musehub_list_issues",
            "musehub_get_issue",
            "musehub_list_prs",
            "musehub_get_pr",
            "musehub_list_releases",
            "musehub_search_repos",
            # Domain tools
            "musehub_get_domain",
            "musehub_get_domain_insights",
            "musehub_get_view",
            "musehub_list_domains",
            # Muse CLI + identity
            "musehub_whoami",
            "muse_pull",
            "muse_remote",
        }
        expected_write = {
            "musehub_create_repo",
            "musehub_fork_repo",
            "musehub_create_issue",
            "musehub_update_issue",
            "musehub_create_issue_comment",
            "musehub_create_pr",
            "musehub_merge_pr",
            "musehub_create_pr_comment",
            "musehub_submit_pr_review",
            "musehub_create_release",
            "musehub_star_repo",
            "musehub_create_label",
            # Auth + push
            "musehub_create_agent_token",
            "muse_push",
            "muse_config",
            # Domain marketplace
            "musehub_publish_domain",
        }
        expected_elicitation = {
            "musehub_create_with_preferences",
            "musehub_review_pr_interactive",
            "musehub_connect_streaming_platform",
            "musehub_connect_daw_cloud",
            "musehub_create_release_interactive",
        }
        assert MUSEHUB_TOOL_NAMES == expected_read | expected_write | expected_elicitation


# ---------------------------------------------------------------------------
# Executor unit tests (using db_session fixture from conftest)
# ---------------------------------------------------------------------------


class TestMusehubExecutors:
    """Unit tests for each executor function using the in-memory test DB."""

    @pytest.mark.anyio
    async def test_browse_repo_returns_db_unavailable_when_not_initialised(self) -> None:
        """_check_db_available returns db_unavailable when session factory is None."""
        from musehub.db import database
        from musehub.services.musehub_mcp_executor import _check_db_available

        original = database._async_session_factory
        database._async_session_factory = None
        try:
            result = _check_db_available()
            assert result is not None
            assert result.ok is False
            assert result.error_code == "db_unavailable"
        finally:
            database._async_session_factory = original

    @pytest.mark.anyio
    async def test_execute_browse_repo_returns_repo_data(
        self, db_session: AsyncSession
    ) -> None:
        """execute_browse_repo (internal executor) returns repo, branches, and commits."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_browse_repo("repo-test-001")

        assert result.ok is True
        # JSONValue union includes list[JSONValue] which rejects str keys — narrow at test boundary.
        assert result.data["repo"]["name"] == "jazz-sessions" # type: ignore[index, call-overload]
        assert result.data["branch_count"] == 1
        assert len(result.data["branches"]) == 1 # type: ignore[arg-type]
        assert len(result.data["recent_commits"]) == 1 # type: ignore[arg-type]
        assert result.data["total_commits"] == 1

    @pytest.mark.anyio
    async def test_execute_browse_repo_not_found(self, db_session: AsyncSession) -> None:
        """execute_browse_repo (internal executor) returns error for unknown repo."""
        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_browse_repo("nonexistent-repo")

        assert result.ok is False
        assert result.error_code == "not_found"

    @pytest.mark.anyio
    async def test_mcp_list_branches_returns_branches(
        self, db_session: AsyncSession
    ) -> None:
        """musehub_list_branches returns all branches with head commit IDs."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_list_branches("repo-test-001")

        assert result.ok is True
        branches = result.data["branches"]
        assert isinstance(branches, list)
        assert len(branches) == 1
        # JSONValue union includes list[JSONValue] which rejects str keys — narrow at test boundary.
        assert branches[0]["name"] == "main" # type: ignore[index, call-overload]
        assert branches[0]["head_commit_id"] == "commit-001" # type: ignore[index, call-overload]

    @pytest.mark.anyio
    async def test_mcp_list_commits_returns_paginated_list(
        self, db_session: AsyncSession
    ) -> None:
        """musehub_list_commits returns commits with total count."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_list_commits(
                "repo-test-001", branch="main", limit=10
            )

        assert result.ok is True
        assert result.data["total"] == 1
        commits = result.data["commits"]
        assert isinstance(commits, list)
        assert len(commits) == 1
        # JSONValue union includes list[JSONValue] which rejects str keys — narrow at test boundary.
        assert commits[0]["message"] == "add bass track" # type: ignore[index, call-overload]
        assert commits[0]["author"] == "alice" # type: ignore[index, call-overload]

    @pytest.mark.anyio
    async def test_mcp_list_commits_limit_clamped(
        self, db_session: AsyncSession
    ) -> None:
        """musehub_list_commits clamps limit to [1, 100]."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            # limit=0 should be clamped to 1
            result = await executor.execute_list_commits("repo-test-001", limit=0)

        assert result.ok is True

    @pytest.mark.anyio
    async def test_mcp_read_file_returns_metadata(
        self, db_session: AsyncSession
    ) -> None:
        """musehub_read_file returns path, size_bytes, and mime_type."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_read_file("repo-test-001", "sha256:abc123")

        assert result.ok is True
        assert result.data["path"] == "tracks/bass.mid"
        assert result.data["size_bytes"] == 2048
        assert result.data["mime_type"] == "audio/midi"
        assert result.data["object_id"] == "sha256:abc123"

    @pytest.mark.anyio
    async def test_mcp_read_file_not_found(self, db_session: AsyncSession) -> None:
        """musehub_read_file returns not_found for unknown object."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_read_file("repo-test-001", "sha256:missing")

        assert result.ok is False
        assert result.error_code == "not_found"

    @pytest.mark.anyio
    async def test_mcp_get_analysis_overview(self, db_session: AsyncSession) -> None:
        """execute_get_analysis (internal executor) overview dimension returns repo stats."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_get_analysis(
                "repo-test-001", dimension="overview"
            )

        assert result.ok is True
        assert result.data["dimension"] == "overview"
        assert result.data["branch_count"] == 1
        assert result.data["commit_count"] == 1
        assert result.data["object_count"] == 1
        assert result.data["midi_analysis"] is None

    @pytest.mark.anyio
    async def test_mcp_get_analysis_commits(self, db_session: AsyncSession) -> None:
        """execute_get_analysis commits dimension returns commit activity summary."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_get_analysis(
                "repo-test-001", dimension="commits"
            )

        assert result.ok is True
        assert result.data["dimension"] == "commits"
        assert result.data["total_commits"] == 1
        by_author = result.data["by_author"]
        assert isinstance(by_author, dict)
        assert by_author.get("alice") == 1

    @pytest.mark.anyio
    async def test_mcp_get_analysis_objects(self, db_session: AsyncSession) -> None:
        """execute_get_analysis objects dimension returns artifact inventory."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_get_analysis(
                "repo-test-001", dimension="objects"
            )

        assert result.ok is True
        assert result.data["dimension"] == "objects"
        assert result.data["total_objects"] == 1
        assert result.data["total_size_bytes"] == 2048

    @pytest.mark.anyio
    async def test_mcp_get_analysis_invalid_dimension(
        self, db_session: AsyncSession
    ) -> None:
        """execute_get_analysis returns error for unknown dimension."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_get_analysis(
                "repo-test-001", dimension="harmonics"
            )

        assert result.ok is False
        assert result.error_code == "invalid_dimension"

    @pytest.mark.anyio
    async def test_mcp_search_by_path(self, db_session: AsyncSession) -> None:
        """musehub_search path mode returns matching artifacts."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_search("repo-test-001", "bass", mode="path")

        assert result.ok is True
        assert result.data["mode"] == "path"
        assert result.data["result_count"] == 1
        results = result.data["results"]
        assert isinstance(results, list)
        # JSONValue union includes list[JSONValue] which rejects str keys — narrow at test boundary.
        assert results[0]["path"] == "tracks/bass.mid" # type: ignore[index, call-overload]

    @pytest.mark.anyio
    async def test_mcp_search_by_path_no_match(
        self, db_session: AsyncSession
    ) -> None:
        """musehub_search returns empty results when nothing matches."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_search(
                "repo-test-001", "drums", mode="path"
            )

        assert result.ok is True
        assert result.data["result_count"] == 0

    @pytest.mark.anyio
    async def test_mcp_search_by_commit(self, db_session: AsyncSession) -> None:
        """musehub_search commit mode searches commit messages."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_search(
                "repo-test-001", "bass", mode="commit"
            )

        assert result.ok is True
        assert result.data["mode"] == "commit"
        assert result.data["result_count"] == 1
        results = result.data["results"]
        assert isinstance(results, list)
        # JSONValue union includes list[JSONValue] which rejects str keys — narrow at test boundary.
        assert results[0]["message"] == "add bass track" # type: ignore[index, call-overload]

    @pytest.mark.anyio
    async def test_mcp_search_invalid_mode(self, db_session: AsyncSession) -> None:
        """musehub_search returns error for unknown mode."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_search(
                "repo-test-001", "bass", mode="fuzzy"
            )

        assert result.ok is False
        assert result.error_code == "invalid_mode"

    @pytest.mark.anyio
    async def test_mcp_search_case_insensitive(self, db_session: AsyncSession) -> None:
        """musehub_search is case-insensitive."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_search(
                "repo-test-001", "BASS", mode="path"
            )

        assert result.ok is True
        assert result.data["result_count"] == 1

    @pytest.mark.anyio
    async def test_mcp_get_context_returns_ai_context(
        self, db_session: AsyncSession
    ) -> None:
        """musehub_get_context returns full AI context document."""
        await _seed_repo(db_session)

        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_get_context("repo-test-001")

        assert result.ok is True
        ctx = result.data["context"]
        assert isinstance(ctx, dict)
        # JSONValue union includes list[JSONValue] which rejects str keys — narrow at test boundary.
        assert ctx["repo"]["name"] == "jazz-sessions" # type: ignore[index, call-overload]
        assert len(ctx["branches"]) == 1 # type: ignore[arg-type]
        assert len(ctx["recent_commits"]) == 1 # type: ignore[arg-type]
        assert ctx["artifacts"]["total_count"] == 1 # type: ignore[index, call-overload]
        assert ctx["musical_analysis"]["key"] is None # type: ignore[index, call-overload]

    @pytest.mark.anyio
    async def test_mcp_get_context_not_found(self, db_session: AsyncSession) -> None:
        """musehub_get_context returns not_found for unknown repo."""
        with patch(
            "musehub.services.musehub_mcp_executor.AsyncSessionLocal",
            return_value=db_session,
        ):
            result = await executor.execute_get_context("ghost-repo")

        assert result.ok is False
        assert result.error_code == "not_found"


# ---------------------------------------------------------------------------
# MCP server routing tests
# ---------------------------------------------------------------------------


class TestMusehubMcpServerRouting:
    """Verify that the MCP server correctly routes musehub_* calls."""

    @pytest.fixture
    def server(self) -> MuseMCPServer:
        with patch("musehub.config.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(app_version="0.0.0-test")
            return MuseMCPServer()

    @pytest.mark.anyio
    async def test_musehub_list_branches_routed_to_executor(
        self, server: MuseMCPServer
    ) -> None:
        """call_tool routes musehub_list_branches to the MuseHub executor."""
        mock_result = MusehubToolResult(
            ok=True,
            data={"repo_id": "repo-001", "branches": []},
        )
        with patch(
            "musehub.services.musehub_mcp_executor.execute_list_branches",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await server.call_tool(
                "musehub_list_branches", {"repo_id": "repo-001"}
            )

        assert result.success is True
        assert result.is_error is False

    @pytest.mark.anyio
    async def test_musehub_tool_not_found_returns_error(
        self, server: MuseMCPServer
    ) -> None:
        """musehub_list_branches propagates not_found as an error response."""
        mock_result = MusehubToolResult(
            ok=False,
            error_code="not_found",
            error_message="Repository 'bad-id' not found.",
        )
        with patch(
            "musehub.services.musehub_mcp_executor.execute_list_branches",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await server.call_tool(
                "musehub_list_branches", {"repo_id": "bad-id"}
            )

        assert result.success is False
        assert result.is_error is True

    @pytest.mark.anyio
    async def test_musehub_invalid_mode_is_bad_request(
        self, server: MuseMCPServer
    ) -> None:
        """invalid_mode error is surfaced as bad_request=True."""
        mock_result = MusehubToolResult(
            ok=False,
            error_code="invalid_mode",
            error_message="Unknown mode 'fuzzy'.",
        )
        with patch(
            "musehub.services.musehub_mcp_executor.execute_search",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await server.call_tool(
                "musehub_search", {"repo_id": "r", "query": "bass", "mode": "fuzzy"}
            )

        assert result.bad_request is True

    @pytest.mark.anyio
    async def test_musehub_list_branches_db_unavailable_returns_error(
        self, server: MuseMCPServer
    ) -> None:
        """musehub tools return db_unavailable when session factory is not initialised."""
        mock_result = MusehubToolResult(
            ok=False,
            error_code="db_unavailable",
            error_message="Database session factory is not initialised.",
        )
        with patch(
            "musehub.services.musehub_mcp_executor.execute_list_branches",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await server.call_tool(
                "musehub_list_branches", {"repo_id": "any-id"}
            )

        assert result.success is False
        assert result.is_error is True
        assert "not initialised" in result.content[0]["text"]

    @pytest.mark.anyio
    async def test_musehub_get_context_response_is_json(
        self, server: MuseMCPServer
    ) -> None:
        """musehub_get_context response content is valid JSON."""
        mock_result = MusehubToolResult(
            ok=True,
            data={"repo_id": "r", "context": {"repo": {}, "branches": [], "recent_commits": [], "commit_stats": {"total": 0, "shown": 0}, "artifacts": {"total_count": 0, "by_mime_type": {}, "paths": []}, "musical_analysis": {"key": None, "tempo": None, "time_signature": None, "note": ""}}},
        )
        with patch(
            "musehub.services.musehub_mcp_executor.execute_get_context",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await server.call_tool(
                "musehub_get_context", {"repo_id": "r"}
            )

        assert result.success is True
        # Content must be parseable JSON
        text = result.content[0]["text"]
        parsed = json.loads(text)
        assert "context" in parsed
