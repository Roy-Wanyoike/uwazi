"""External MCP server integration — Uwazi uses an MCP server it did not write.

The challenge brief requires: *"One MCP server you did not write.
Community, official, or vendor. One line on why it beats writing it
yourself."*

Uwazi integrates the official MCP fetch server
(`mcp` Python package's `mcp.server.fetch` — see
https://github.com/modelcontextprotocol/servers/tree/main/src/fetch)
to pull tender notices from public procurement-portal URLs. The
agent calls the external `fetch_url` MCP tool, then passes the
content to its own `ingest_tender` tool.

Why this beats writing it ourselves: the official fetch server handles
HTTP redirects, gzip, charset detection, HTML stripping, robots.txt
respect, and SSRF protection. We would have to write ~500 LOC to
reproduce it; we get it for free, and any improvement lands in our
agent without a single PR on our side.

If the external fetch server is unavailable (e.g., offline demo), the
tool degrades gracefully — the agent reads from the local file path
instead and notes the fallback in the audit trail.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any

# ---------------------------------------------------------------------------
# The official MCP fetch server — Python implementation
# ---------------------------------------------------------------------------

FETCH_SERVER_PACKAGE = "mcp-server-fetch"  # pip install mcp-server-fetch
FETCH_SERVER_MODULE = "mcp_server_fetch"


def is_fetch_server_available() -> bool:
    """True if the official mcp-server-fetch is importable."""
    try:
        import importlib

        importlib.import_module(FETCH_SERVER_MODULE)
        return True
    except ImportError:
        return False


async def fetch_url_via_external_mcp(url: str, max_length: int = 5000) -> dict[str, Any]:
    """Call the official MCP fetch server to retrieve a URL.

    Starts the fetch server as a subprocess (stdio transport), connects
    as an MCP client, calls the `fetch` tool, returns the content.

    If the server isn't installed or the URL fetch fails, returns a
    fallback dict with `error` set — the caller handles it.
    """
    if not is_fetch_server_available():
        return {
            "error": (
                f"{FETCH_SERVER_PACKAGE} not installed — install with "
                f"`pip install {FETCH_SERVER_PACKAGE}`. Falling back to local files."
            ),
            "fallback": True,
        }

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", FETCH_SERVER_MODULE],
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "fetch",
                    {"url": url, "max_length": max_length},
                )
                # The result.content is a list of content blocks
                if result.content:
                    text_blocks = [b for b in result.content if hasattr(b, "text")]
                    text = text_blocks[0].text if text_blocks else ""
                    return {
                        "url": url,
                        "content": text,
                        "fetched_via": "external_mcp_fetch_server",
                    }
                return {"url": url, "content": "", "fetched_via": "external_mcp_fetch_server"}
    except Exception as exc:
        return {
            "error": f"external fetch server call failed: {exc}",
            "fallback": True,
        }


# ---------------------------------------------------------------------------
# Install helper for the demo script
# ---------------------------------------------------------------------------


def ensure_fetch_server_installed() -> bool:
    """If fetch server isn't installed, try to install it. Returns True on success."""
    if is_fetch_server_available():
        return True
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", FETCH_SERVER_PACKAGE],
            check=True,
            timeout=60,
        )
        return is_fetch_server_available()
    except Exception:
        return False
