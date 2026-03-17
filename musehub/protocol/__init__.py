"""Maestro Protocol — single source of truth for the FE ↔ BE wire contract.

Public re-exports for convenience:

    from musehub.protocol import (
        MAESTRO_VERSION,
        MaestroEvent,
        emit,
        parse_event,
        ProtocolSerializationError,
    )
"""
from __future__ import annotations

from musehub.protocol.version import MAESTRO_VERSION
from musehub.protocol.events import MaestroEvent
from musehub.protocol.emitter import emit, parse_event, ProtocolSerializationError

__all__ = [
    "MAESTRO_VERSION",
    "MaestroEvent",
    "emit",
    "parse_event",
    "ProtocolSerializationError",
]
