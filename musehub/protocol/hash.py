"""Deterministic protocol fingerprint.

Computes a SHA-256 hash of:
  1. Protocol version string
  2. All registered event JSON schemas (sorted by type name)
  3. All MCP tool schemas (sorted by tool name)

The hash changes if and only if the wire contract changes.
"""


import hashlib
import json

from musehub.protocol.registry import EVENT_REGISTRY
from musehub.protocol.version import MUSE_VERSION


def _event_schemas_canonical() -> list[dict[str, object]]:
    """Extract JSON schemas from all registered event models, sorted by type."""
    schemas: list[dict[str, object]] = []
    for event_type in sorted(EVENT_REGISTRY.keys()):
        model_class = EVENT_REGISTRY[event_type]
        schema: dict[str, object] = model_class.model_json_schema()
        schemas.append({"type": event_type, "schema": schema})
    return schemas


def _tool_schemas_canonical() -> list[dict[str, object]]:
    """Extract canonical tool schemas from the MCP registry, sorted by name."""
    from musehub.mcp.tools import MUSEHUB_TOOLS

    tools: list[dict[str, object]] = []
    for tool in sorted(MUSEHUB_TOOLS, key=lambda t: t["name"]):
        tools.append({
            "name": tool["name"],
            "inputSchema": tool.get("inputSchema", {}),
        })
    return tools


def compute_protocol_hash() -> str:
    """Compute deterministic SHA-256 hash of the protocol surface."""
    payload = {
        "version": MUSE_VERSION,
        "events": _event_schemas_canonical(),
        "tools": _tool_schemas_canonical(),
    }
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def compute_protocol_hash_short() -> str:
    """16-char short hash for display / header use."""
    return compute_protocol_hash()[:16]
