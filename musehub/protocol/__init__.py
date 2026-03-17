"""Muse Hub Protocol — single source of truth for the wire contract.

Public re-exports:

    from musehub.protocol import MUSE_VERSION, MuseEvent
"""
from __future__ import annotations

from musehub.protocol.version import MUSE_VERSION
from musehub.protocol.events import MuseEvent

__all__ = [
    "MUSE_VERSION",
    "MuseEvent",
]
