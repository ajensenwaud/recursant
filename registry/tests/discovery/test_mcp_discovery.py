"""IT-3: MCP tool discovery integration tests.

Tests scanning for MCP servers and tools. Supports both K8s (hosts-based)
and Docker Compose (CIDR-based) topologies.
"""

import uuid

import pytest

from tests.discovery.conftest import (
    scan_and_wait, USE_K8S, DISC_SERVICES, LEGACY_SUBNETS,
)


pytestmark = pytest.mark.requires_topology


def _mcp_scan_payload(name=None):
    """Build scan payload for MCP servers."""
    config = {
        'timeout_ms': 5000,
        'max_concurrent_probes': 20,
    }
    if USE_K8S:
        config['hosts'] = DISC_SERVICES['mcp']
    else:
        config['cidrs'] = [LEGACY_SUBNETS['c']]
        config['ports'] = [8080, 5000]
    return {
        'name': name or f'mcp-scan-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': config,
    }


class TestMCPDiscovery:
    """Verify MCP servers and tools are discovered."""

    def test_discover_mcp_servers(self, api, cleanup_scans):
        """Verify MCP servers found with tools."""
        scan = scan_and_wait(api, _mcp_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        assert scan['status'] == 'completed', f'Scan status: {scan["status"]}'

        resp = api.get('/discovery/tools', params={'per_page': 100})
        assert resp.status_code == 200
        tools = resp.json()['tools']
        assert len(tools) > 0, 'Expected at least one MCP tool to be discovered'

    def test_tool_list_captured(self, api, cleanup_scans):
        """Verify DiscoveredTool rows created with correct names."""
        scan = scan_and_wait(api, _mcp_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/tools', params={'per_page': 100})
        assert resp.status_code == 200
        tools = resp.json()['tools']
        assert len(tools) > 0

        for tool in tools:
            assert tool.get('tool_name'), f'Tool missing tool_name: {tool}'
            assert isinstance(tool['tool_name'], str)
            assert len(tool['tool_name']) > 0

    def test_tool_input_schemas(self, api, cleanup_scans):
        """Verify input_schema JSON is populated for discovered tools."""
        scan = scan_and_wait(api, _mcp_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/tools', params={'per_page': 100})
        assert resp.status_code == 200
        tools = resp.json()['tools']

        # At least some tools should have input schemas
        tools_with_schema = [t for t in tools if t.get('input_schema')]
        assert len(tools_with_schema) > 0, (
            'Expected at least one tool with input_schema populated'
        )

        for tool in tools_with_schema:
            schema = tool['input_schema']
            assert isinstance(schema, dict), f'input_schema should be a dict, got {type(schema)}'

    def test_mcp_server_url_recorded(self, api, cleanup_scans):
        """Verify mcp_server_url points to host:port."""
        scan = scan_and_wait(api, _mcp_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/tools', params={'per_page': 100})
        assert resp.status_code == 200
        tools = resp.json()['tools']
        assert len(tools) > 0

        for tool in tools:
            url = tool.get('mcp_server_url')
            assert url, f'Tool {tool["tool_name"]} missing mcp_server_url'
            # URL should contain a host and port
            assert ':' in url or '/' in url, (
                f'mcp_server_url should contain host:port, got: {url}'
            )
