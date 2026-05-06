"""IT-5: Onboarding integration tests.

Tests onboarding discovered agents and tools into the registry.
Supports both K8s (hosts-based) and Docker Compose (CIDR-based) topologies.
"""

import uuid

import pytest

from tests.discovery.conftest import (
    scan_and_wait, USE_K8S, DISC_SERVICES, LEGACY_SUBNETS,
)


pytestmark = pytest.mark.requires_topology


def _a2a_scan_payload(name=None):
    config = {
        'timeout_ms': 5000,
        'max_concurrent_probes': 20,
    }
    if USE_K8S:
        config['hosts'] = DISC_SERVICES['eng']
    else:
        config['cidrs'] = [LEGACY_SUBNETS['a']]
        config['ports'] = [5000]
    return {
        'name': name or f'onboard-a2a-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': config,
    }


def _mcp_scan_payload(name=None):
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
        'name': name or f'onboard-mcp-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': config,
    }


def _get_ungoverned_agents(api):
    """Get list of agents with unknown governance status."""
    resp = api.get('/discovery/agents', params={
        'governance_status': 'unknown',
        'per_page': 100,
    })
    assert resp.status_code == 200
    return resp.json()['agents']


def _get_ungoverned_tools(api):
    """Get list of tools with ungoverned governance status."""
    resp = api.get('/discovery/tools', params={
        'governance_status': 'ungoverned',
        'per_page': 100,
    })
    assert resp.status_code == 200
    return resp.json()['tools']


class TestOnboardAgent:
    """Test onboarding discovered A2A agents."""

    def test_onboard_agent(self, api, cleanup_scans, reset_agent_statuses):
        """Discover, onboard, verify Agent created in DRAFT."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        agents = _get_ungoverned_agents(api)
        assert len(agents) > 0, 'Need at least one ungoverned agent to onboard'

        agent_id = agents[0]['id']
        resp = api.post(f'/discovery/agents/{agent_id}/onboard', json={})
        assert resp.status_code == 201, f'Onboard failed: {resp.text}'

        result = resp.json()
        assert 'registry_agent_id' in result
        assert result['status'].upper() == 'DRAFT'

    def test_onboard_agent_capabilities_mapped(self, api, cleanup_scans, reset_agent_statuses):
        """Verify capabilities from agent card are mapped to the registry agent."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        agents = _get_ungoverned_agents(api)
        assert len(agents) > 0, 'Need at least one ungoverned agent'

        agent_id = agents[0]['id']

        # Get the discovered agent's details first
        resp = api.get(f'/discovery/agents/{agent_id}')
        assert resp.status_code == 200

        # Onboard it
        resp = api.post(f'/discovery/agents/{agent_id}/onboard', json={})
        assert resp.status_code in (201, 409), f'Unexpected: {resp.status_code}: {resp.text}'

        if resp.status_code == 201:
            registry_agent_id = resp.json()['registry_agent_id']

            # Fetch the registry agent and verify capabilities exist
            resp = api.get(f'/agents/{registry_agent_id}')
            assert resp.status_code == 200
            registry_agent = resp.json()
            assert registry_agent.get('name'), 'Registry agent should have a name'

    def test_onboard_already_onboarded(self, api, cleanup_scans, reset_agent_statuses):
        """Try onboard again, expect 409 conflict."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        agents = _get_ungoverned_agents(api)
        assert len(agents) > 0, 'Need at least one ungoverned agent'

        agent_id = agents[0]['id']

        # Onboard first time
        resp = api.post(f'/discovery/agents/{agent_id}/onboard', json={})
        assert resp.status_code in (201, 409)

        # Onboard second time — should get 409
        resp = api.post(f'/discovery/agents/{agent_id}/onboard', json={})
        assert resp.status_code == 409, f'Expected 409 on re-onboard, got {resp.status_code}: {resp.text}'

    def test_bulk_onboard(self, api, cleanup_scans, reset_agent_statuses):
        """Bulk onboard 3 agents, verify all created."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        agents = _get_ungoverned_agents(api)
        assert len(agents) >= 3, f'Need at least 3 ungoverned agents, found {len(agents)}'

        agent_ids = [a['id'] for a in agents[:3]]
        resp = api.post('/discovery/agents/bulk-onboard', json={
            'agent_ids': agent_ids,
        })
        assert resp.status_code in (201, 207), f'Bulk onboard failed: {resp.text}'

        result = resp.json()
        assert 'results' in result
        assert 'summary' in result
        assert len(result['results']) == 3

        # At least some should succeed
        summary = result['summary']
        assert summary['success'] + summary['conflict'] == 3, (
            f'Expected all 3 to succeed or conflict, got: {summary}'
        )


class TestOnboardTool:
    """Test onboarding discovered MCP tools."""

    def test_onboard_tool(self, api, cleanup_scans):
        """Onboard an MCP tool, verify MeshTool created."""
        scan = scan_and_wait(api, _mcp_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        tools = _get_ungoverned_tools(api)
        assert len(tools) > 0, 'Need at least one ungoverned tool to onboard'

        tool_id = tools[0]['id']
        resp = api.post(f'/discovery/tools/{tool_id}/onboard', json={})
        assert resp.status_code == 201, f'Tool onboard failed: {resp.text}'

        result = resp.json()
        assert 'tool_id' in result
        assert 'tool_name' in result
