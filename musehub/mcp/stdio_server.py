"""MuseHub MCP stdio transport — local dev and Cursor integration.

Entry point: ``python -m musehub.mcp.stdio_server``

Protocol:
  - Reads newline-delimited JSON-RPC 2.0 messages from ``stdin``
  - Writes JSON-RPC 2.0 responses to ``stdout`` (one per line)
  - Logs diagnostic messages to ``stderr``
  - Processes messages sequentially (no concurrency concerns)
  - Notifications (no ``id``) produce no output (202-equivalent silence)

Auth:
  - No JWT authentication — stdio is a trusted local process.
  - All tools including write tools are available.
  - ``user_id`` defaults to ``"stdio-user"`` so write tools can record an author.

Usage:
  # Direct:
  python -m musehub.mcp.stdio_server

  # Via Cursor (.cursor/mcp.json):
  {
    "mcpServers": {
      "musehub": {
        "command": "python",
        "args": ["-m", "musehub.mcp.stdio_server"],
        "env": {"DATABASE_URL": "postgresql+asyncpg://..."}
      }
    }
  }
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys

logger = logging.getLogger("musehub.mcp.stdio")


async def _run() -> None:
    """Main async stdio loop."""
    from musehub.db import init_db
    from musehub.mcp.dispatcher import handle_request

    # Initialise DB before handling any requests.
    try:
        await init_db()
        logger.info("MuseHub MCP stdio server started")
    except Exception as exc:
        logger.warning("DB init failed (tools requiring DB will return db_unavailable): %s", exc)

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    stdout_transport, stdout_protocol = await loop.connect_write_pipe(
        asyncio.BaseProtocol, sys.stdout
    )

    while True:
        try:
            line_bytes = await reader.readline()
        except asyncio.IncompleteReadError:
            break
        if not line_bytes:
            break

        line = line_bytes.decode("utf-8").strip()
        if not line:
            continue

        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            error_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            }
            _write_json(stdout_transport, error_resp)
            continue

        try:
            resp = await handle_request(raw, user_id="stdio-user")
        except Exception as exc:
            logger.exception("Dispatcher error: %s", exc)
            resp = {
                "jsonrpc": "2.0",
                "id": raw.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {exc}"},
            }

        if resp is not None:
            _write_json(stdout_transport, resp)


def _write_json(transport: asyncio.BaseTransport, obj: object) -> None:
    """Serialise ``obj`` to JSON and write it as a single newline-terminated line."""
    line = json.dumps(obj, default=str) + "\n"
    if isinstance(transport, asyncio.WriteTransport):
        transport.write(line.encode("utf-8"))


def main() -> None:
    """Stdio server entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
