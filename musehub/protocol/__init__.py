"""Muse Protocol — single source of truth for the FE ↔ BE wire contract.

Public re-exports for convenience:

    from musehub.protocol import (
        MUSE_VERSION,
        MuseEvent,
        emit,
        parse_event,
        ProtocolSerializationError,
    )
"""
from __future__ import annotations

from musehub.protocol.version import MUSE_VERSION, MAESTRO_VERSION
from musehub.protocol.events import MuseEvent, MaestroEvent
from musehub.protocol.emitter import emit, parse_event, ProtocolSerializationError

__all__ = [
    "MUSE_VERSION",
    "MuseEvent",
    # Back-compat aliases
    "MAESTRO_VERSION",
    "MaestroEvent",
    "emit",
    "parse_event",
    "ProtocolSerializationError",
]
