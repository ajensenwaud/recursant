"""MCP server for KYC system.

Provides tool: verify_identity(name, document_type, document_number, date_of_birth)
Calls stub API: POST /kyc/verify-identity
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

MCP_PORT = int(os.environ.get("MCP_PORT", "8081"))
mcp = FastMCP("kyc-system", host="0.0.0.0", port=MCP_PORT)
STUB_URL = os.environ.get("STUB_API_URL", "http://stub-apis:6000")


@mcp.tool()
async def verify_identity(
    name: str,
    document_type: str,
    document_number: str,
    date_of_birth: str,
) -> str:
    """Verify a customer's identity documents against the KYC system."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/kyc/verify-identity",
            json={
                "name": name,
                "document_type": document_type,
                "document_number": document_number,
                "date_of_birth": date_of_birth,
            },
            timeout=10.0,
        )
        return resp.text


if __name__ == "__main__":
    mcp.run(transport="sse")
