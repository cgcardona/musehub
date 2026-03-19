"""Event registry — canonical mapping of event type strings to model classes.

Invariants:
  - Every event the server can emit has an entry here.
  - Registry is frozen at import time; no runtime mutation.
"""
from __future__ import annotations



from musehub.protocol.events import MCPMessageEvent, MCPPingEvent, MuseEvent

EVENT_REGISTRY: dict[str, type[MuseEvent]] = {
    "mcp.message": MCPMessageEvent,
    "mcp.ping": MCPPingEvent,
}

ALL_EVENT_TYPES: frozenset[str] = frozenset(EVENT_REGISTRY.keys())


def get_event_class(event_type: str) -> type[MuseEvent]:
    """Look up the model class for an event type. Raises KeyError for unknown types."""
    return EVENT_REGISTRY[event_type]


def is_known_event(event_type: str) -> bool:
    """Return ``True`` when ``event_type`` is a registered event type string."""
    return event_type in EVENT_REGISTRY
