"""MCP server mode — real FastMCP SSE server with @mcp.tool() definitions."""

import os

from mcp.server.fastmcp import FastMCP


def create_mcp_server():
    """Create a FastMCP server with tools from MCP_TOOLS env var."""
    server_name = os.environ.get('AGENT_NAME', 'mcp-server')
    port = int(os.environ.get('AGENT_PORT', '8080'))
    tools_csv = os.environ.get('MCP_TOOLS', '')

    mcp = FastMCP(server_name, host='0.0.0.0', port=port)

    # Dynamically register tools from comma-separated list
    tool_names = [t.strip() for t in tools_csv.split(',') if t.strip()]

    for tool_name in tool_names:
        # Create a closure to capture the tool name
        def _make_tool(name):
            async def tool_func(input: str) -> str:
                """Process input and return a result."""
                return f"Result from {name}: {input}"
            tool_func.__name__ = name
            tool_func.__qualname__ = name
            tool_func.__doc__ = f"Execute the {name} tool"
            return tool_func

        mcp.tool()(_make_tool(tool_name))

    return mcp


def run():
    mcp = create_mcp_server()
    mcp.run(transport='sse')
