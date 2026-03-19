"""Typed structures for the MCP protocol layer.

Defines every entity used across tool definitions, the MCP server,
and the HTTP/WebSocket route layer. No ``dict[str, object]`` is used
here — all shapes are named TypedDicts or Pydantic wire models.

## TypedDicts (internal use — JSON-RPC, stdio server, tool registry)

Use these in non-Pydantic code (tool definitions, the stdio JSON-RPC server,
the MCP server's internal ``list_tools()`` result). They are standard
``TypedDict`` with ``typing_extensions`` — fully mypy-checked but not
suitable as FastAPI response types because some contain recursive fields.

  Tool definitions → ``MCPPropertyDef``, ``MCPInputSchema``, ``MCPToolDef``
  Content → ``MCPContentBlock``
  Server capabilities → ``MCPToolsCapability``, ``MCPResourcesCapability``,
                        ``MCPCapabilities``, ``MCPServerInfo``
  JSON-RPC params → ``MCPToolCallParams``, ``MCPInitializeParams``
  JSON-RPC messages → ``MCPRequest``, ``MCPSuccessResponse``,
                        ``MCPErrorDetail``, ``MCPErrorResponse``, ``MCPResponse``
  Method results → ``MCPCapabilitiesResult``, ``MCPInitializeResult``,
                        ``MCPToolsListResult``, ``MCPCallResult``
  Full responses → ``MCPInitializeResponse``, ``MCPToolsListResponse``,
                        ``MCPCallResponse``, ``MCPMethodResponse``
  DAW channel → ``DAWToolCallMessage``, ``DAWToolResponse``
  Elicitation (2025-11-25) → ``ElicitationAction``, ``ElicitationRequest``,
                              ``ElicitationResponse``, ``SessionInfo``

## Pydantic wire models (API route responses)

``MCPPropertyDef`` is self-referential (``properties: dict[str, "MCPPropertyDef"]``)
and also contains ``JSONValue`` fields. Pydantic v2 cannot generate a finite
schema for either — both cause ``RecursionError`` at route registration time.

These three Pydantic ``BaseModel`` subclasses mirror their TypedDict counterparts
and are the correct return types for FastAPI route handlers:

  ``MCPPropertyDefWire`` — mirrors ``MCPPropertyDef``, resolves self-reference via
                            ``model_rebuild()``, uses ``PydanticJson`` for ``default``
                            and ``items`` fields.
  ``MCPInputSchemaWire`` — mirrors ``MCPInputSchema``, uses ``MCPPropertyDefWire``.
  ``MCPToolDefWire`` — mirrors ``MCPToolDef``, uses ``MCPInputSchemaWire``.
                            Use ``MCPToolDefWire.model_validate(tool_dict)`` to convert
                            from the TypedDict returned by ``server.list_tools()``.

Rule: FastAPI route handlers that return tool definitions must return
``MCPToolDefWire`` (not ``MCPToolDef``). Internal tool registration and the
stdio JSON-RPC server continue to use the TypedDict variants.
"""
from __future__ import annotations


from typing import Literal, NotRequired, Required, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from musehub.contracts.json_types import JSONValue, JSONObject
from musehub.contracts.pydantic_types import PydanticJson


# ── Tool schema shapes ────────────────────────────────────────────────────────


class MCPPropertyDef(TypedDict, total=False):
    """JSON Schema definition for a single MCP tool property.

    Covers the subset of JSON Schema used in MCP tool definitions.
    All constraint fields (``enum``, ``minimum``, etc.) are optional.
    """

    type: Required[str] # "string", "number", "integer", "boolean", "array", "object"
    description: str
    enum: list[str | int | float]
    minimum: float
    maximum: float
    default: JSONValue
    items: dict[str, JSONValue] # array item schema (simplified)
    properties: dict[str, "MCPPropertyDef"] # nested object property schemas


class MCPInputSchema(TypedDict, total=False):
    """JSON Schema describing an MCP tool's accepted arguments."""

    type: Required[str]
    properties: Required[dict[str, MCPPropertyDef]]
    required: list[str]


class MCPToolDef(TypedDict, total=False):
    """Definition of a single MCP tool exposed to LLM clients."""

    name: Required[str]
    description: Required[str]
    inputSchema: Required[MCPInputSchema]
    server_side: bool


class MCPContentBlock(TypedDict):
    """A content block in an MCP tool result (currently always text)."""

    type: str
    text: str


# ── Server capability shapes ──────────────────────────────────────────────────


class MCPToolsCapability(TypedDict, total=False):
    """The ``tools`` entry in ``MCPCapabilities``.

    Currently always ``{}`` — reserved for future tool metadata.
    """


class MCPResourcesCapability(TypedDict, total=False):
    """The ``resources`` entry in ``MCPCapabilities``.

    Currently always ``{}`` — reserved for future resource metadata.
    """


class MCPCapabilities(TypedDict, total=False):
    """MCP server capabilities advertised during the ``initialize`` handshake."""

    tools: MCPToolsCapability
    resources: MCPResourcesCapability


class MCPServerInfo(TypedDict):
    """MCP server info returned in ``initialize`` responses and ``get_server_info()``."""

    name: str
    version: str
    protocolVersion: str # noqa: N815
    capabilities: MCPCapabilities


# ── JSON-RPC 2.0 method-specific param shapes ─────────────────────────────────


class MCPToolCallParams(TypedDict):
    """Params for the ``tools/call`` JSON-RPC method."""

    name: str
    arguments: JSONObject


class MCPInitializeParams(TypedDict, total=False):
    """Params for the ``initialize`` JSON-RPC method."""

    protocolVersion: Required[str] # noqa: N815
    clientInfo: dict[str, str] # noqa: N815 {name, version}
    capabilities: dict[str, JSONValue]


# ── JSON-RPC 2.0 message shapes ───────────────────────────────────────────────


class MCPRequest(TypedDict, total=False):
    """An incoming JSON-RPC 2.0 message from an MCP client.

    ``jsonrpc`` and ``method`` are always present.
    ``id`` is absent for notifications.
    ``params`` is absent when the method takes no parameters.

    ``params`` is typed as ``JSONObject`` because the specific shape depends on
    the method. Callers must narrow using ``isinstance`` before accessing keys,
    or use the method-specific param TypedDicts (``MCPToolCallParams`` etc.).
    """

    jsonrpc: Required[str]
    method: Required[str]
    id: str | int | None
    params: JSONObject


class MCPSuccessResponse(TypedDict):
    """A JSON-RPC 2.0 success response."""

    jsonrpc: str
    id: str | int | None
    result: JSONObject


class MCPErrorDetail(TypedDict, total=False):
    """The ``error`` object inside a JSON-RPC 2.0 error response."""

    code: Required[int]
    message: Required[str]
    data: JSONValue


class MCPErrorResponse(TypedDict):
    """A JSON-RPC 2.0 error response."""

    jsonrpc: str
    id: str | int | None
    error: MCPErrorDetail


MCPResponse = MCPSuccessResponse | MCPErrorResponse
"""Discriminated union of all JSON-RPC 2.0 response shapes."""


# ── Method-specific result TypedDicts (contents of ``result`` in success responses) ──


class MCPCapabilitiesResult(TypedDict):
    """Result body for ``initialize`` — capability block."""

    tools: MCPToolsCapability


class MCPInitializeResult(TypedDict):
    """Result body for the ``initialize`` JSON-RPC method."""

    protocolVersion: str # noqa: N815
    serverInfo: MCPServerInfo
    capabilities: MCPCapabilitiesResult


class MCPToolsListResult(TypedDict):
    """Result body for the ``tools/list`` JSON-RPC method."""

    tools: list[MCPToolDef]


class MCPCallResult(TypedDict, total=False):
    """Result body for the ``tools/call`` JSON-RPC method."""

    content: Required[list[MCPContentBlock]]
    isError: bool # noqa: N815


class MCPInitializeResponse(TypedDict):
    """Full JSON-RPC response for the ``initialize`` method."""

    jsonrpc: str
    id: str | int | None
    result: MCPInitializeResult


class MCPToolsListResponse(TypedDict):
    """Full JSON-RPC response for the ``tools/list`` method."""

    jsonrpc: str
    id: str | int | None
    result: MCPToolsListResult


class MCPCallResponse(TypedDict):
    """Full JSON-RPC response for the ``tools/call`` method."""

    jsonrpc: str
    id: str | int | None
    result: MCPCallResult


MCPMethodResponse = MCPInitializeResponse | MCPToolsListResponse | MCPCallResponse | MCPSuccessResponse | MCPErrorResponse
"""Union of all concrete JSON-RPC response types produced by the stdio server."""


# ── DAW channel shapes ────────────────────────────────────────────────────────


class DAWToolCallMessage(TypedDict):
    """Message sent from the MCP server to the connected DAW over WebSocket.

    The DAW executes the tool and replies via ``receive_tool_response``.
    """

    type: Literal["toolCall"]
    requestId: str # noqa: N815
    tool: str
    arguments: dict[str, JSONValue]


class DAWToolResponse(TypedDict, total=False):
    """Response sent from the DAW back to the MCP server after tool execution.

    ``success`` is always present; ``content`` and ``isError`` are optional.
    """

    success: Required[bool]
    content: list[MCPContentBlock]
    isError: bool # noqa: N815


# ── Pydantic wire models for API responses ────────────────────────────────────
#
# ``MCPPropertyDef`` is a recursive TypedDict:
# ``properties: dict[str, "MCPPropertyDef"]`` — self-referential
# ``default: JSONValue`` — recursive type alias
# ``items: dict[str, JSONValue]`` — recursive type alias
#
# Pydantic v2 cannot generate a finite JSON Schema for either recursive
# structure, raising ``RecursionError`` when a FastAPI route handler returns
# any type that transitively contains ``MCPPropertyDef``.
#
# Solution: three Pydantic ``BaseModel`` subclasses that mirror the TypedDicts
# and replace problematic fields with Pydantic-safe equivalents:
# • ``MCPPropertyDefWire`` — self-reference resolved via ``model_rebuild()``,
# ``default`` and ``items`` use ``PydanticJson`` (not ``JSONValue``).
# • ``MCPInputSchemaWire`` — uses ``MCPPropertyDefWire`` for ``properties``.
# • ``MCPToolDefWire`` — uses ``MCPInputSchemaWire`` for ``inputSchema``.
#
# Conversion from TypedDict at the route boundary:
# ``MCPToolDefWire.model_validate(tool_dict)``
#
# The TypedDict variants (``MCPToolDef`` etc.) remain in use everywhere else:
# tool registration, the stdio JSON-RPC server, the MCP server's
# ``list_tools()`` return value.


class MCPPropertyDefWire(BaseModel):
    """Pydantic-safe wire model for a single JSON Schema property definition.

    Mirrors ``MCPPropertyDef`` (TypedDict) for use as a FastAPI response type.

    **Why not ``MCPPropertyDef`` directly?** ``MCPPropertyDef.properties`` is
    self-referential (``dict[str, "MCPPropertyDef"]``) and both ``default`` and
    ``items`` use ``JSONValue`` (a recursive type alias). Pydantic v2 cannot
    generate a finite schema for any of these, causing ``RecursionError`` at
    route registration. This model resolves the self-reference via
    ``MCPPropertyDefWire.model_rebuild()`` (called immediately below) and
    replaces ``JSONValue`` fields with ``PydanticJson``.

    **Conversion:** instantiate via ``MCPToolDefWire.model_validate(tool_dict)``
    — Pydantic recursively converts nested dicts to ``MCPPropertyDefWire``
    instances automatically.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str
    description: str | None = None
    enum: list[str | int | float] | None = None
    minimum: float | None = None
    maximum: float | None = None
    default: PydanticJson | None = None
    items: dict[str, PydanticJson] | None = None
    properties: dict[str, "MCPPropertyDefWire"] | None = None


# Resolve the self-referential ``"MCPPropertyDefWire"`` forward reference.
# Must be called immediately after class definition, before any other model
# that uses this type is defined.
MCPPropertyDefWire.model_rebuild()


class MCPInputSchemaWire(BaseModel):
    """Pydantic-safe wire model for an MCP tool's JSON Schema input descriptor.

    Mirrors ``MCPInputSchema`` (TypedDict) for use as a FastAPI response type.
    ``properties`` uses ``MCPPropertyDefWire`` instead of ``MCPPropertyDef`` to
    avoid the recursive schema generation issue.
    """

    type: str = "object"
    properties: dict[str, MCPPropertyDefWire] = Field(default_factory=dict)
    required: list[str] | None = None


class MCPToolDefWire(BaseModel):
    """Pydantic-safe wire model for a single MCP tool definition.

    Mirrors ``MCPToolDef`` (TypedDict) for use as a FastAPI response type.
    Use this as the return type for any FastAPI route handler that exposes
    tool definitions to API clients.

    **Conversion from TypedDict** (e.g. from ``server.list_tools()``)::

        tools = [MCPToolDefWire.model_validate(t) for t in server.list_tools()]

    Pydantic's ``model_validate`` recurses through the nested dict automatically,
    converting ``inputSchema`` → ``MCPInputSchemaWire`` and each property →
    ``MCPPropertyDefWire`` without manual traversal.

    **Field note:** ``inputSchema`` is spelled in camelCase (matching the MCP
    wire protocol) to allow direct ``model_validate`` from the TypedDict dict
    representation without a remapping step.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str
    inputSchema: MCPInputSchemaWire = Field( # noqa: N815
        default_factory=MCPInputSchemaWire,
        alias="inputSchema",
    )
    server_side: bool | None = None


# ── MCP 2025-11-25 Elicitation types ─────────────────────────────────────────


class ElicitationAction(TypedDict, total=False):
    """The action taken by the user in response to an elicitation request.

    Fields:
        action: One of ``"accept"``, ``"decline"``, or ``"cancel"``.
            - ``"accept"`` means the user filled the form / completed the URL flow.
            - ``"decline"`` means the user explicitly declined.
            - ``"cancel"`` means the client cancelled (e.g. timeout or navigation).
        content: Present only when ``action == "accept"``; the form data as a dict
            whose shape matches the ``requestedSchema`` sent with the request.
    """

    action: Required[str]
    content: NotRequired[dict[str, object]]


class ElicitationRequest(TypedDict, total=False):
    """An ``elicitation/create`` request sent from the server to the client.

    Sent as a JSON-RPC 2.0 *request* (has ``id``) over the SSE stream,
    or embedded in the ``POST /mcp`` SSE streaming response.

    Fields:
        mode: ``"form"`` for structured schema-based input, or ``"url"`` for
            out-of-band browser interaction (OAuth, payment, etc.).
        message: Human-readable message displayed to the user.
        requestedSchema: JSON Schema for form mode (restricted subset: flat,
            primitive properties only). Not present for URL mode.
        url: Target URL for URL mode. Not present for form mode.
        elicitationId: Stable ID used to correlate ``notifications/elicitation/complete``.
    """

    mode: Required[str]
    message: Required[str]
    requestedSchema: NotRequired[dict[str, object]]
    url: NotRequired[str]
    elicitationId: NotRequired[str]


class ElicitationResponse(TypedDict, total=False):
    """A JSON-RPC 2.0 response from the client to an ``elicitation/create`` request.

    The client sends this as a normal JSON-RPC success response (``id`` matches
    the server's elicitation request ID) via ``POST /mcp``.

    Fields:
        action: See :class:`ElicitationAction`.
        content: User-provided data (form mode only; absent on decline/cancel).
    """

    action: Required[str]
    content: NotRequired[dict[str, object]]


class SessionInfo(TypedDict, total=False):
    """Summary of an active MCP session — returned in server metadata endpoints.

    Not part of the JSON-RPC wire protocol; used internally for admin/debug.

    Fields:
        session_id: Cryptographically secure session identifier (never log in full).
        user_id: Authenticated user, or ``None`` for anonymous sessions.
        client_capabilities: Capability map from ``initialize`` params.
        pending_count: Number of outstanding elicitation Futures.
        sse_queue_count: Number of active GET /mcp SSE consumers.
        created_at: Unix timestamp of session creation.
        last_active: Unix timestamp of last activity.
        supports_form_elicitation: Whether the client can handle form-mode.
        supports_url_elicitation: Whether the client can handle URL-mode.
    """

    session_id: Required[str]
    user_id: Required[str | None]
    client_capabilities: NotRequired[dict[str, object]]
    pending_count: NotRequired[int]
    sse_queue_count: NotRequired[int]
    created_at: NotRequired[float]
    last_active: NotRequired[float]
    supports_form_elicitation: NotRequired[bool]
    supports_url_elicitation: NotRequired[bool]
