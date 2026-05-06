"""MCP server for Credit Engine.

Provides tools:
  - assess_credit_capacity(annual_salary)
  - make_credit_decision(loan_amount, property_value)
Calls stub API: POST /credit/assess-capacity, POST /credit/decide
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

MCP_PORT = int(os.environ.get("MCP_PORT", "8082"))
mcp = FastMCP("credit-engine", host="0.0.0.0", port=MCP_PORT)
STUB_URL = os.environ.get("STUB_API_URL", "http://stub-apis:6000")


@mcp.tool()
async def assess_credit_capacity(annual_salary: float) -> str:
    """Calculate the maximum mortgage loan amount based on annual salary."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/credit/assess-capacity",
            json={"annual_salary": annual_salary},
            timeout=10.0,
        )
        return resp.text


@mcp.tool()
async def make_credit_decision(loan_amount: float, property_value: float) -> str:
    """Make a credit decision based on loan amount and property value (LTV check)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/credit/decide",
            json={"loan_amount": loan_amount, "property_value": property_value},
            timeout=10.0,
        )
        return resp.text


if __name__ == "__main__":
    mcp.run(transport="sse")
