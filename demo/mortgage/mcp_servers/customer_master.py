"""MCP server for Customer Master system.

Provides tool: verify_customer(ban, pin)
Calls stub API: POST /customer-master/verify
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

MCP_PORT = int(os.environ.get("MCP_PORT", "8080"))
mcp = FastMCP("customer-master", host="0.0.0.0", port=MCP_PORT)
STUB_URL = os.environ.get("STUB_API_URL", "http://stub-apis:6000")


@mcp.tool()
async def verify_customer(ban: str, pin: str) -> str:
    """Verify customer BAN and PIN against the Customer Master system."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/customer-master/verify",
            json={"ban": ban, "pin": pin},
            timeout=10.0,
        )
        return resp.text


if __name__ == "__main__":
    mcp.run(transport="sse")
