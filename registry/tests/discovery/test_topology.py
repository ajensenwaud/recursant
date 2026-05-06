"""IT-7: Topology integration tests.

Tests the network topology graph endpoint.
Supports both K8s and Docker Compose topologies.
"""

import uuid

import pytest

from tests.discovery.conftest import (
    scan_and_wait, USE_K8S, DISC_SERVICES, LEGACY_SUBNETS,
)


pytestmark = pytest.mark.requires_topology


def _scan_payload(name=None):
    config = {
        'timeout_ms': 5000,
        'max_concurrent_probes': 20,
    }
    if USE_K8S:
        config['hosts'] = DISC_SERVICES['eng']
    else:
        config['cidrs'] = [LEGACY_SUBNETS['a']]
        config['ports'] = [5000, 8080]
    return {
        'name': name or f'topo-scan-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': config,
    }


class TestTopology:
    """Test the topology graph endpoint."""

    def test_topology_returns_graph(self, api, cleanup_scans):
        """Verify topology returns nodes and edges structure."""
        # Ensure at least one scan has run
        scan = scan_and_wait(api, _scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        resp = api.get('/discovery/topology')
        assert resp.status_code == 200, f'Topology failed: {resp.text}'

        topology = resp.json()

        # Verify graph structure
        assert 'nodes' in topology, 'Topology should contain nodes'
        assert 'edges' in topology, 'Topology should contain edges'
        assert isinstance(topology['nodes'], list)
        assert isinstance(topology['edges'], list)

        # Should have at least some nodes after scanning
        assert len(topology['nodes']) > 0, 'Expected at least one node in topology'

        # Verify node structure
        for node in topology['nodes']:
            assert 'id' in node, f'Node missing id: {node}'

    def test_topology_filter_by_subnet(self, api, cleanup_scans):
        """Filter topology by subnet (only applicable for CIDR-based scans)."""
        scan = scan_and_wait(api, _scan_payload(), timeout=120)
        cleanup_scans.append(scan['id'])

        if USE_K8S:
            # K8s uses DNS names, not IPs — just verify topology returns data
            resp = api.get('/discovery/topology')
        else:
            resp = api.get('/discovery/topology', params={'subnet': LEGACY_SUBNETS['a']})
        assert resp.status_code == 200, f'Topology filter failed: {resp.text}'

        topology = resp.json()
        assert 'nodes' in topology
        assert 'edges' in topology
