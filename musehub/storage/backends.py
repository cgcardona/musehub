"""Storage backend implementations.

All blobs (objects) are content-addressed by ``object_id``.  Backends produce
a ``storage_uri`` string that encodes both backend type and location so that
MuseHub can always reconstruct the full retrieval path from a single string
stored in ``musehub_objects.storage_uri``.

URI schemes:
    ``local://<repo_id>/<object_id>``  — filesystem relative to ``objects_dir``
    ``s3://<bucket>/<key>``             — AWS S3 / S3-compatible (R2, MinIO)
"""
from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Protocol

from musehub.config import settings

logger = logging.getLogger(__name__)


class StorageBackend(Protocol):
    """Content-addressed binary store protocol.

    Backends must be safe to call from async code.  I/O-bound implementations
    should use ``asyncio.to_thread`` internally rather than blocking the event
    loop.
    """

    async def put(self, repo_id: str, object_id: str, data: bytes) -> str:
        """Persist ``data`` and return a ``storage_uri``."""
        ...

    async def get(self, repo_id: str, object_id: str) -> bytes | None:
        """Return raw bytes for the object, or ``None`` if not found."""
        ...

    async def exists(self, repo_id: str, object_id: str) -> bool:
        """Return True if the object is already stored (avoids re-upload)."""
        ...

    async def delete(self, repo_id: str, object_id: str) -> None:
        """Remove an object (used on repo deletion)."""
        ...

    def uri_for(self, repo_id: str, object_id: str) -> str:
        """Return the canonical storage URI without necessarily persisting."""
        ...


class LocalBackend:
    """Filesystem storage backend.

    Objects are stored at:
        ``<objects_dir>/<repo_id>/<object_id>``

    This layout is safe for concurrent writes (each object_id is unique and
    immutable) and trivially rsync-able for backup.
    """

    def __init__(self, objects_dir: str | None = None) -> None:
        self._root = Path(objects_dir or settings.musehub_objects_dir)

    def _path(self, repo_id: str, object_id: str) -> Path:
        # Strip any URI prefix the object_id might carry (e.g. "sha256:")
        safe_id = object_id.replace(":", "_").replace("/", "_")
        return self._root / repo_id / safe_id

    def uri_for(self, repo_id: str, object_id: str) -> str:
        return f"local://{repo_id}/{object_id}"

    async def put(self, repo_id: str, object_id: str, data: bytes) -> str:
        import asyncio
        path = self._path(repo_id, object_id)
        await asyncio.to_thread(self._write, path, data)
        return self.uri_for(repo_id, object_id)

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)

    async def get(self, repo_id: str, object_id: str) -> bytes | None:
        import asyncio
        path = self._path(repo_id, object_id)
        if not path.exists():
            return None
        return await asyncio.to_thread(path.read_bytes)

    async def exists(self, repo_id: str, object_id: str) -> bool:
        return self._path(repo_id, object_id).exists()

    async def delete(self, repo_id: str, object_id: str) -> None:
        import asyncio
        path = self._path(repo_id, object_id)
        if path.exists():
            await asyncio.to_thread(path.unlink)


class S3Backend:
    """AWS S3 (or S3-compatible) storage backend.

    Requires ``boto3`` to be installed and AWS credentials to be configured
    (via environment variables, IAM instance profile, or ``~/.aws/credentials``).

    Objects are stored at:
        ``s3://<bucket>/<repo_id>/<object_id>``

    Uploads are idempotent — ``put`` performs a HeadObject check before
    uploading to avoid unnecessary transfer costs.
    """

    def __init__(self, bucket: str | None = None, region: str | None = None) -> None:
        self._bucket = bucket or settings.aws_s3_asset_bucket or ""
        self._region = region or settings.aws_region
        self._client: object | None = None

    def _get_client(self) -> object:
        if self._client is None:
            import boto3
            self._client = boto3.client("s3", region_name=self._region)
        return self._client

    def _key(self, repo_id: str, object_id: str) -> str:
        safe_id = object_id.replace(":", "_")
        return f"objects/{repo_id}/{safe_id}"

    def uri_for(self, repo_id: str, object_id: str) -> str:
        return f"s3://{self._bucket}/{self._key(repo_id, object_id)}"

    async def put(self, repo_id: str, object_id: str, data: bytes) -> str:
        import asyncio
        key = self._key(repo_id, object_id)
        client = self._get_client()
        await asyncio.to_thread(self._s3_put, client, key, data)
        return self.uri_for(repo_id, object_id)

    def _s3_put(self, client: object, key: str, data: bytes) -> None:
        from typing import Any
        c: Any = client
        try:
            c.head_object(Bucket=self._bucket, Key=key)
            return  # already uploaded
        except Exception:
            pass
        c.put_object(Bucket=self._bucket, Key=key, Body=data)

    async def get(self, repo_id: str, object_id: str) -> bytes | None:
        import asyncio
        from typing import Any
        key = self._key(repo_id, object_id)
        c: Any = self._get_client()
        try:
            def _do_get() -> Any:
                return c.get_object(Bucket=self._bucket, Key=key)
            result = await asyncio.to_thread(_do_get)
            data: bytes = result["Body"].read()
            return data
        except Exception:
            return None

    async def exists(self, repo_id: str, object_id: str) -> bool:
        import asyncio
        from typing import Any
        key = self._key(repo_id, object_id)
        c: Any = self._get_client()
        try:
            def _do_head() -> Any:
                return c.head_object(Bucket=self._bucket, Key=key)
            await asyncio.to_thread(_do_head)
            return True
        except Exception:
            return False

    async def delete(self, repo_id: str, object_id: str) -> None:
        import asyncio
        from typing import Any
        key = self._key(repo_id, object_id)
        c: Any = self._get_client()
        def _do_delete() -> None:
            c.delete_object(Bucket=self._bucket, Key=key)
        await asyncio.to_thread(_do_delete)


def get_backend() -> StorageBackend:
    """Return the configured storage backend (singleton per process).

    Selection logic:
        1.  If ``AWS_S3_ASSET_BUCKET`` is set → ``S3Backend``
        2.  Otherwise → ``LocalBackend`` (safe for dev + single-node prod)
    """
    if settings.aws_s3_asset_bucket:
        return S3Backend()
    return LocalBackend()


def decode_b64(b64_str: str) -> bytes:
    """Decode a base64 string (with or without padding) into bytes."""
    padded = b64_str + "=" * (-len(b64_str) % 4)
    return base64.b64decode(padded)
