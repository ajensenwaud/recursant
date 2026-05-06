"""MCP server for Compliance Engine.

Provides tools:
  - check_lending_regulations(loan_amount, property_value, annual_income)
  - verify_document_completeness(document_types_provided)
  - calculate_compliance_score(findings)
Calls stub API: POST /compliance/check-regulations, /compliance/verify-documents, /compliance/calculate-score
"""

import os

import httpx
from mcp.server.fastmcp import FastMCP

MCP_PORT = int(os.environ.get("MCP_PORT", "8084"))
mcp = FastMCP("compliance-engine", host="0.0.0.0", port=MCP_PORT)
STUB_URL = os.environ.get("STUB_API_URL", "http://stub-apis:6000")


@mcp.tool()
async def check_lending_regulations(loan_amount: float, property_value: float, annual_income: float) -> str:
    """Check mortgage lending regulations including LTV and DTI ratio compliance."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/compliance/check-regulations",
            json={"loan_amount": loan_amount, "property_value": property_value, "annual_income": annual_income},
            timeout=10.0,
        )
        return resp.text


@mcp.tool()
async def verify_document_completeness(document_types_provided: str) -> str:
    """Check that all required documents have been provided for the mortgage application."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/compliance/verify-documents",
            json={"document_types_provided": document_types_provided},
            timeout=10.0,
        )
        return resp.text


@mcp.tool()
async def calculate_compliance_score(findings: str) -> str:
    """Calculate a compliance score (0-100) based on review findings."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{STUB_URL}/compliance/calculate-score",
            json={"findings": findings},
            timeout=10.0,
        )
        return resp.text


if __name__ == "__main__":
    mcp.run(transport="sse")
