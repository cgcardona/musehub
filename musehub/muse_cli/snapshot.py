"""Pure snapshot hashing utilities retained for MuseHub tests.

The full snapshot module was extracted to cgcardona/muse.
Only compute_snapshot_id and compute_commit_id are retained here
because MuseHub test fixtures use them to generate deterministic IDs.

TODO(musehub-extraction): remove when MuseHub is extracted.
"""
from __future__ import annotations

import hashlib


def compute_snapshot_id(manifest: dict[str, str]) -> str:
    """Return sha256 of the sorted ``path:object_id`` pairs."""
    parts = sorted(f"{path}:{oid}" for path, oid in manifest.items())
    payload = "|".join(parts).encode()
    return hashlib.sha256(payload).hexdigest()


def compute_commit_id(
    parent_ids: list[str],
    snapshot_id: str,
    message: str,
    committed_at_iso: str,
) -> str:
    """Return sha256 of the commit's canonical inputs."""
    parts = [
        "|".join(sorted(parent_ids)),
        snapshot_id,
        message,
        committed_at_iso,
    ]
    payload = "|".join(parts).encode()
    return hashlib.sha256(payload).hexdigest()
