"""Pure snapshot hashing utilities retained for MuseHub tests.

The full snapshot module was extracted to cgcardona/muse.
Only compute_snapshot_id and compute_commit_id are retained here
because MuseHub test fixtures use them to generate deterministic IDs.

IMPORTANT: the separator must stay in sync with muse.core.snapshot._SEP.
The CLI migrated from ``|``/``:`` to a null-byte separator to prevent
separator-injection collisions (filenames cannot contain \\x00 on POSIX).
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
