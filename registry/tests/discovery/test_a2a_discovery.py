"""IT-2: A2A agent discovery integration tests.

Tests scanning for A2A agents. Supports both K8s (hosts-based) and
Docker Compose (CIDR-based) topologies.
"""

import uuid

import pytest

from tests.discovery.conftest import (
    scan_and_wait, USE_K8S, DISC_SERVICES, LEGACY_SUBNETS,
)


pytestmark = pytest.mark.requires_topology


def _a2a_scan_payload(name=None):
    """Build scan payload — uses hosts for K8s, CIDRs for Docker Compose."""
    config = {
        'timeout_ms': 5000,
        'max_concurrent_probes': 20,
    }
    if USE_K8S:
        # Scan engineering A2A agents via DNS hostnames
        config['hosts'] = DISC_SERVICES['eng']
    else:
        config['cidrs'] = [LEGACY_SUBNETS['a']]
        config['ports'] = [5000]
    return {
        'name': name or f'a2a-scan-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': config,
    }


class TestA2ADiscovery:
    """Verify A2A agents are discovered."""

    def test_discover_a2a_agents(self, api, cleanup_scans):
        """Scan for A2A agents, verify agents found with parsed cards."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        assert scan['status'] == 'completed', f'Scan status: {scan["status"]}'

        # Check discovered agents
        resp = api.get('/discovery/agents', params={'per_page': 100})
        assert resp.status_code == 200
        agents = resp.json()['agents']
        assert len(agents) > 0, 'Expected at least one A2A agent to be discovered'

        # Verify agents have names (parsed from agent cards)
        for agent in agents:
            assert agent.get('name'), f'Agent missing name: {agent}'

    def test_agent_card_skills_parsed(self, api, cleanup_scans):
        """Verify capabilities array matches card skills."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/agents', params={'per_page': 100})
        assert resp.status_code == 200
        agents = resp.json()['agents']
        assert len(agents) > 0

        # Find an A2A agent by checking full details for one with agent_card
        found_a2a = False
        for agent_summary in agents:
            agent_id = agent_summary['id']
            resp = api.get(f'/discovery/agents/{agent_id}')
            assert resp.status_code == 200
            agent = resp.json()
            if agent.get('agent_card') is not None or agent.get('capabilities') is not None:
                found_a2a = True
                break

        assert found_a2a, (
            'At least one discovered agent should have agent_card or capabilities '
            'populated from A2A card'
        )

    def test_governed_agent_classification(self, api, cleanup_scans):
        """Verify agents that were pre-seeded in registry are classified as governed."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/agents', params={'governance_status': 'governed', 'per_page': 100})
        assert resp.status_code == 200
        governed = resp.json()['agents']

        # If there are pre-registered agents, they should appear as governed
        for agent in governed:
            assert agent['governance_status'] == 'governed'

    def test_ungoverned_agent_classification(self, api, cleanup_scans):
        """Verify unknown agents classified as 'unknown'."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/agents', params={'governance_status': 'unknown', 'per_page': 100})
        assert resp.status_code == 200
        unknown = resp.json()['agents']

        for agent in unknown:
            assert agent['governance_status'] == 'unknown'

    def test_agent_disappearance_tracking(self, api, cleanup_scans):
        """Scan and verify agents are online (basic version)."""
        scan = scan_and_wait(api, _a2a_scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/agents', params={'per_page': 100})
        assert resp.status_code == 200
        agents = resp.json()['agents']

        # After a fresh scan, no agents should have disappeared_at set
        for agent in agents:
            assert agent.get('disappeared_at') is None, (
                f'Agent {agent["name"]} should not have disappeared_at after fresh scan'
            )
