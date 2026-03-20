"""MuseHub storage abstraction layer.

Exposes a single ``StorageBackend`` protocol that all object I/O goes through.
Current backends:

    LocalBackend   — stores blobs under ``<musehub_objects_dir>/<repo_id>/<object_id>``
                     (default for development and single-node production)
    S3Backend      — stores blobs in S3 / S3-compatible storage (e.g. R2)

Usage::

    from musehub.storage import get_backend

    backend = get_backend()
    uri = await backend.put(repo_id, object_id, data)
    data = await backend.get(repo_id, object_id)
"""
from musehub.storage.backends import LocalBackend, S3Backend, StorageBackend, get_backend

__all__ = ["StorageBackend", "LocalBackend", "S3Backend", "get_backend"]
