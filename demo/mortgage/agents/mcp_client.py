"""MCPToolClient and SidecarToolClient — tool call wrappers.

MCPToolClient: starts an MCP server as a subprocess and communicates via stdio.
SidecarToolClient: routes tool calls through the sidecar for governance + audit.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Optional

import httpx


class MCPToolClient:
    """Client that manages an MCP server subprocess and calls its tools."""

    def __init__(self, server_script: str, env: Optional[dict] = None):
        self._server_script = server_script
        self._env = env or dict(os.environ)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command="python",
            args=[self._server_script],
            env=self._env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=arguments)
                return result.content[0].text

    def call_tool_sync(self, name: str, arguments: dict[str, Any]) -> str:
        """Synchronous wrapper for call_tool."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, self.call_tool(name, arguments)).result()
            else:
                return loop.run_until_complete(self.call_tool(name, arguments))
        except RuntimeError:
            return asyncio.run(self.call_tool(name, arguments))


class SidecarToolClient:
    """Routes tool calls through the sidecar for governance and audit.

    Drop-in replacement for MCPToolClient — same call_tool_sync() interface.
    POSTs to {sidecar_url}/tools/call instead of spawning MCP subprocesses.
    """

    def __init__(self, sidecar_url: str):
        self._sidecar_url = sidecar_url.rstrip("/")

    def call_tool_sync(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool through the sidecar gateway."""
        resp = httpx.post(
            f"{self._sidecar_url}/tools/call",
            json={"tool_name": name, "arguments": arguments},
            timeout=30.0,
        )

        if resp.status_code == 200:
            data = resp.json()
            result = data.get("result", data)
            return json.dumps(result) if isinstance(result, dict) else str(result)

        # Error — return error JSON for the agent to handle
        try:
            error_data = resp.json()
        except Exception:
            error_data = {"error": resp.text}

        return json.dumps({"status": "error", "message": error_data.get("error", str(resp.status_code))})
