"""Sync wrapper around the MCP SSE client.

Calls a tool on a remote MCP server via SSE transport and returns the
text result synchronously.
"""

from __future__ import annotations

import asyncio

from mcp.client.sse import sse_client
from mcp import ClientSession


def call_mcp_tool(mcp_server_url: str, tool_name: str, arguments: dict) -> str:
    """Call a tool on an MCP server via SSE transport.

    Args:
        mcp_server_url: SSE endpoint URL (e.g. ``http://mcp-credit-engine:8082/sse``).
        tool_name: Name of the tool to invoke.
        arguments: Tool arguments dict.

    Returns:
        The text content from the first content block, or empty string.
    """
    return asyncio.run(_call_mcp_tool(mcp_server_url, tool_name, arguments))


async def _call_mcp_tool(mcp_server_url: str, tool_name: str, arguments: dict) -> str:
    async with sse_client(url=mcp_server_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return result.content[0].text if result.content else ""
