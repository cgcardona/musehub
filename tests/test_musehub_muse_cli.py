"""Unit tests for muse_cli snapshot hashing utilities.

muse_cli/snapshot.py provides deterministic ID functions used by test
fixtures across the suite — yet it had no tests of its own.  These
tests lock down the hashing contract so that any accidental change to
the algorithm is immediately caught.
"""
from __future__ import annotations

import hashlib

import pytest

from musehub.muse_cli.snapshot import compute_commit_id, compute_snapshot_id


class TestComputeSnapshotId:
    def test_empty_manifest_is_deterministic(self) -> None:
        result = compute_snapshot_id({})
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 hex

    def test_single_entry(self) -> None:
        result = compute_snapshot_id({"tracks/bass.mid": "sha256:abc"})
        assert len(result) == 64

    def test_same_manifest_same_id(self) -> None:
        manifest = {"a": "1", "b": "2"}
        assert compute_snapshot_id(manifest) == compute_snapshot_id(manifest)

    def test_insertion_order_does_not_matter(self) -> None:
        m1 = {"a": "1", "b": "2"}
        m2 = {"b": "2", "a": "1"}
        assert compute_snapshot_id(m1) == compute_snapshot_id(m2)

    def test_different_manifests_different_ids(self) -> None:
        assert compute_snapshot_id({"a": "1"}) != compute_snapshot_id({"a": "2"})
        assert compute_snapshot_id({"a": "1"}) != compute_snapshot_id({"b": "1"})

    def test_known_value(self) -> None:
        """Regression: algorithm must not change without updating this test.

        Uses the null-byte separator (\\x00) introduced when the CLI migrated
        from the old ``|``/``:`` scheme to prevent separator-injection attacks.
        """
        _SEP = "\x00"
        manifest = {"tracks/piano.mid": "sha256:deadbeef"}
        parts = sorted(f"{k}{_SEP}{v}" for k, v in manifest.items())
        payload = _SEP.join(parts).encode()
        expected = hashlib.sha256(payload).hexdigest()
        assert compute_snapshot_id(manifest) == expected

    def test_multiple_entries_sorted(self) -> None:
        _SEP = "\x00"
        m = {"z/file": "oid-z", "a/file": "oid-a", "m/file": "oid-m"}
        result = compute_snapshot_id(m)
        # Manually compute expected value using null-byte separator
        parts = sorted(f"{k}{_SEP}{v}" for k, v in m.items())
        expected = hashlib.sha256(_SEP.join(parts).encode()).hexdigest()
        assert result == expected


class TestComputeCommitId:
    def test_returns_sha256_hex(self) -> None:
        cid = compute_commit_id([], "snap-id", "init", "2026-01-01T00:00:00+00:00")
        assert len(cid) == 64

    def test_deterministic(self) -> None:
        kwargs = dict(
            parent_ids=["p1", "p2"],
            snapshot_id="snap-abc",
            message="feat: add piano",
            committed_at_iso="2026-03-01T12:00:00+00:00",
        )
        assert compute_commit_id(**kwargs) == compute_commit_id(**kwargs)

    def test_parent_order_does_not_matter(self) -> None:
        base = dict(snapshot_id="s", message="m", committed_at_iso="2026-01-01T00:00:00")
        id1 = compute_commit_id(parent_ids=["a", "b"], **base)
        id2 = compute_commit_id(parent_ids=["b", "a"], **base)
        assert id1 == id2

    def test_different_messages_different_ids(self) -> None:
        base = dict(parent_ids=[], snapshot_id="s", committed_at_iso="2026-01-01T00:00:00")
        assert compute_commit_id(message="msg-1", **base) != compute_commit_id(message="msg-2", **base)

    def test_different_timestamps_different_ids(self) -> None:
        base = dict(parent_ids=[], snapshot_id="s", message="m")
        t1 = compute_commit_id(committed_at_iso="2026-01-01T00:00:00", **base)
        t2 = compute_commit_id(committed_at_iso="2026-01-02T00:00:00", **base)
        assert t1 != t2

    def test_different_snapshots_different_ids(self) -> None:
        base = dict(parent_ids=[], message="m", committed_at_iso="2026-01-01T00:00:00")
        assert compute_commit_id(snapshot_id="s1", **base) != compute_commit_id(snapshot_id="s2", **base)

    def test_known_value(self) -> None:
        """Regression: algorithm must not change without updating this test."""
        parents = ["parent-a", "parent-b"]
        snap = "snapshot-xyz"
        msg = "feat: add groove"
        ts = "2026-01-01T00:00:00+00:00"
        parts = ["|".join(sorted(parents)), snap, msg, ts]
        expected = hashlib.sha256("|".join(parts).encode()).hexdigest()
        assert compute_commit_id(parent_ids=parents, snapshot_id=snap, message=msg, committed_at_iso=ts) == expected
