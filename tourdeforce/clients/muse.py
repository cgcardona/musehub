"""Muse VCS client stub for TourDeForce.

The full MuseClient was extracted to cgcardona/muse.
This stub preserves the type signatures so tourdeforce/runner.py can import
without errors. All MuseClient methods raise NotImplementedError at runtime.

TODO(muse-extraction): re-integrate MuseClient once Muse exposes a
standalone service API.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


class MuseError(Exception):
    pass


class CheckoutResult:
    """Structured checkout result."""

    def __init__(
        self,
        success: bool,
        blocked: bool = False,
        target: str = "",
        head_moved: bool = False,
        executed: int = 0,
        failed: int = 0,
        plan_hash: str = "",
        drift_severity: str = "",
        drift_total_changes: int = 0,
        status_code: int = 200,
    ) -> None:
        self.success = success
        self.blocked = blocked
        self.target = target
        self.head_moved = head_moved
        self.executed = executed
        self.failed = failed
        self.plan_hash = plan_hash
        self.drift_severity = drift_severity
        self.drift_total_changes = drift_total_changes
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "blocked": self.blocked,
            "target": self.target,
            "head_moved": self.head_moved,
            "executed": self.executed,
            "plan_hash": self.plan_hash[:12] if self.plan_hash else "",
            "drift_severity": self.drift_severity,
            "drift_total_changes": self.drift_total_changes,
        }


class MergeResult:
    """Structured merge result."""

    def __init__(
        self,
        success: bool,
        merge_variation_id: str = "",
        conflicts: list[dict[str, Any]] | None = None,
        executed: int = 0,
        status_code: int = 200,
    ) -> None:
        self.success = success
        self.merge_variation_id = merge_variation_id
        self.conflicts: list[dict[str, Any]] = conflicts or []
        self.executed = executed
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "merge_variation_id": self.merge_variation_id,
            "conflict_count": len(self.conflicts),
            "conflicts": self.conflicts,
            "executed": self.executed,
        }


class MuseClient:
    """Stub — the real client was extracted to cgcardona/muse.

    TODO(muse-extraction): re-integrate once Muse exposes a standalone HTTP API.
    """

    def __init__(self, config: Any, *args: Any, **kwargs: Any) -> None:
        self._config = config

    async def close(self) -> None:
        pass

    async def save_variation(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError("MuseClient: extracted to cgcardona/muse — re-integrate via service API")

    async def set_head(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("MuseClient: extracted to cgcardona/muse — re-integrate via service API")

    async def get_log(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("MuseClient: extracted to cgcardona/muse — re-integrate via service API")

    async def checkout(self, *args: Any, **kwargs: Any) -> CheckoutResult:
        raise NotImplementedError("MuseClient: extracted to cgcardona/muse — re-integrate via service API")

    async def merge(self, *args: Any, **kwargs: Any) -> MergeResult:
        raise NotImplementedError("MuseClient: extracted to cgcardona/muse — re-integrate via service API")
