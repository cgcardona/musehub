"""Snapshot and commit ID hashing — MuseHub-side implementation.

This module provides the canonical server-side ID computation functions used
by MuseHub services and test fixtures.  It intentionally mirrors the hashing
logic in ``muse.core.snapshot`` (the Muse CLI) so that IDs generated on the
server can be cross-verified against IDs sent by the CLI.

CONTRACT: The separator constant ``_SEP`` and the hash construction algorithm
MUST remain identical to ``muse.core.snapshot._SEP`` and
``muse.core.snapshot.compute_snapshot_id``.  Any change to either side must
be applied to both simultaneously.  A mismatch is a silent data-integrity bug.
"""

import hashlib

# Must match muse.core.snapshot._SEP exactly.
_SEP = "\x00"


def compute_snapshot_id(manifest: dict[str, str]) -> str:
    """Return sha256 of the sorted ``path NUL object_id`` pairs.

    Uses a null-byte separator to prevent collision attacks via filenames or
    object IDs that contain the previous ``|``/``:`` separators.
    """
    parts = sorted(f"{path}{_SEP}{oid}" for path, oid in manifest.items())
    payload = _SEP.join(parts).encode()
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
