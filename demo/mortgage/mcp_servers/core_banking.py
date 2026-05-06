"""MCP server for Core Banking system.

Provides tool: disburse_loan(loan_amount, customer_name, property_address)
Calls stub API: POST /core-banking/disburse
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

MCP_PORT = int(os.environ.get("MCP_PORT", "8083"))
mcp = FastMCP("core-banking", host="0.0.0.0", port=MCP_PORT)
STUB_URL = os.environ.get("STUB_API_URL", "http://stub-apis:6000")


@mcp.tool()
async def disburse_loan(
    loan_amount: float,
    customer_name: str,
    property_address: str,
) -> str:
    """Disburse an approved mortgage loan through the Core Banking system."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/core-banking/disburse",
            json={
                "loan_amount": loan_amount,
                "customer_name": customer_name,
                "property_address": property_address,
            },
            timeout=10.0,
        )
        return resp.text


if __name__ == "__main__":
    mcp.run(transport="sse")
