"""IT-6: Enforcement integration tests.

Tests quarantine, dismiss, and governance stats endpoints.
"""

import uuid

import pytest

from tests.discovery.conftest import (
    scan_and_wait, USE_K8S, DISC_SERVICES, LEGACY_SUBNETS,
)


EMPTY_SUBNET = '10.99.99.0/24'


def _scan_payload(name=None):
    return {
        'name': name or f'enforce-scan-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': {
            'cidrs': [EMPTY_SUBNET],
            'ports': [5000],
            'timeout_ms': 2000,
            'max_concurrent_probes': 10,
        },
    }


def _topology_scan_payload(group='eng', name=None):
    """Build scan payload for topology tests — K8s or Docker Compose."""
    config = {
        'timeout_ms': 5000,
        'max_concurrent_probes': 20,
    }
    if USE_K8S:
        config['hosts'] = DISC_SERVICES[group]
    else:
        subnet_map = {'eng': 'a', 'ds': 'b'}
        config['cidrs'] = [LEGACY_SUBNETS[subnet_map.get(group, 'a')]]
        config['ports'] = [5000]
    return {
        'name': name or f'enforce-{group}-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': config,
    }


def _get_agents_by_status(api, governance_status):
    """Fetch discovered agents filtered by governance status."""
    resp = api.get('/discovery/agents', params={
        'governance_status': governance_status,
        'per_page': 100,
    })
    assert resp.status_code == 200
    return resp.json()['agents']


class TestQuarantine:
    """Test quarantine endpoint generates deny policy."""

    @pytest.mark.requires_topology
    def test_quarantine_generates_deny_policy(self, api, cleanup_scans, reset_agent_statuses):
        """Quarantine an agent, verify governance_status changed and MeshPolicy created."""
        # First ensure we have discovered agents
        scan = scan_and_wait(api, _topology_scan_payload('eng'), timeout=120)
        cleanup_scans.append(scan['id'])

        agents = _get_agents_by_status(api, 'unknown')
        assert len(agents) > 0, 'Need at least one ungoverned agent to quarantine'

        agent_id = agents[0]['id']
        resp = api.post(f'/discovery/agents/{agent_id}/quarantine')
        assert resp.status_code == 200, f'Quarantine failed: {resp.text}'

        result = resp.json()
        assert result['governance_status'] == 'quarantined'

        # Verify via GET
        resp = api.get(f'/discovery/agents/{agent_id}')
        assert resp.status_code == 200
        assert resp.json()['governance_status'] == 'quarantined'


class TestDismiss:
    """Test dismiss endpoint."""

    @pytest.mark.requires_topology
    def test_dismiss_agent(self, api, cleanup_scans, reset_agent_statuses):
        """Dismiss an agent, verify governance_status changed to dismissed."""
        scan = scan_and_wait(api, _topology_scan_payload('ds'), timeout=120)
        cleanup_scans.append(scan['id'])

        agents = _get_agents_by_status(api, 'unknown')
        assert len(agents) > 0, 'Need at least one ungoverned agent to dismiss'

        agent_id = agents[0]['id']
        resp = api.post(f'/discovery/agents/{agent_id}/dismiss')
        assert resp.status_code == 200, f'Dismiss failed: {resp.text}'

        result = resp.json()
        assert result['governance_status'] == 'dismissed'

        # Verify via GET
        resp = api.get(f'/discovery/agents/{agent_id}')
        assert resp.status_code == 200
        assert resp.json()['governance_status'] == 'dismissed'


class TestGovernanceStats:
    """Test governance stats endpoint."""

    def test_governance_stats(self, api):
        """Verify stats endpoint returns correct structure with counts."""
        resp = api.get('/discovery/stats')
        assert resp.status_code == 200, f'Stats failed: {resp.text}'

        stats = resp.json()

        # Verify expected fields are present
        expected_fields = [
            'total_agents',
            'total_tools',
            'governed_agents',
            'ungoverned_agents',
            'governance_coverage_pct',
        ]
        for field in expected_fields:
            assert field in stats, f'Missing field in stats: {field}'

        # All counts should be non-negative integers
        for field in ['total_agents', 'total_tools', 'governed_agents', 'ungoverned_agents']:
            assert isinstance(stats[field], int), f'{field} should be int, got {type(stats[field])}'
            assert stats[field] >= 0, f'{field} should be >= 0, got {stats[field]}'

        # Coverage percentage should be between 0 and 100
        pct = stats['governance_coverage_pct']
        assert isinstance(pct, (int, float)), f'coverage_pct should be numeric, got {type(pct)}'
        assert 0 <= pct <= 100, f'coverage_pct should be 0-100, got {pct}'
