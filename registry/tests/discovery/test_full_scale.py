"""IT-10: Full-scale integration tests.

Tests scanning all groups and verifying performance.
Supports both K8s (hosts-based) and Docker Compose (CIDR-based) topologies.
"""

import time
import uuid

import pytest

from tests.discovery.conftest import (
    scan_and_wait, USE_K8S, DISC_SERVICES, LEGACY_SUBNETS,
)


pytestmark = [pytest.mark.requires_topology, pytest.mark.slow]


# Legacy Docker Compose subnets
ALL_SUBNETS = [
    LEGACY_SUBNETS['a'],
    LEGACY_SUBNETS['b'],
    LEGACY_SUBNETS['c'],
    LEGACY_SUBNETS['d'],
    LEGACY_SUBNETS['e'],
]


def _full_scan_payload(name=None):
    config = {
        'timeout_ms': 3000,
        'max_concurrent_probes': 100,
    }
    if USE_K8S:
        config['hosts'] = DISC_SERVICES['all']
    else:
        config['cidrs'] = ALL_SUBNETS
        config['ports'] = [5000, 9999, 12345]
    return {
        'name': name or f'full-scan-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': config,
    }


class TestFullScale:
    """Full-scale scan across all groups."""

    def test_full_scan_all_groups(self, api, cleanup_scans):
        """Scan all groups, verify all hosts found."""
        scan = scan_and_wait(api, _full_scan_payload(), timeout=300)
        cleanup_scans.append(scan['id'])

        assert scan['status'] == 'completed', f'Full scan status: {scan["status"]}'

        # Check summary for discovered hosts
        summary = scan.get('summary', {})
        hosts_reachable = summary.get('hosts_reachable', 0)
        assert hosts_reachable > 0, f'Expected reachable hosts, got {hosts_reachable}'

        # Check that agents were discovered
        resp = api.get('/discovery/agents', params={'per_page': 100})
        assert resp.status_code == 200
        agents = resp.json()
        assert agents['total'] > 0, 'Expected discovered agents from full scan'

        # Check that tools were discovered
        resp = api.get('/discovery/tools', params={'per_page': 100})
        assert resp.status_code == 200
        tools = resp.json()
        assert tools['total'] > 0, 'Expected discovered tools from full scan'

    def test_performance_under_120s(self, api, cleanup_scans):
        """Verify full scan completes under 120 seconds."""
        payload = _full_scan_payload(name=f'perf-scan-{uuid.uuid4().hex[:8]}')

        start = time.time()
        resp = api.post('/discovery/scans', json=payload)
        assert resp.status_code == 201, f'Failed to create scan: {resp.text}'
        scan_id = resp.json()['id']
        cleanup_scans.append(scan_id)

        # Poll for completion
        deadline = time.time() + 300  # allow up to 300s for the test itself
        while time.time() < deadline:
            resp = api.get(f'/discovery/scans/{scan_id}')
            assert resp.status_code == 200
            status = resp.json()['status']
            if status in ('completed', 'failed', 'cancelled'):
                break
            time.sleep(1)

        elapsed = time.time() - start
        scan_data = resp.json()

        assert scan_data['status'] == 'completed', (
            f'Scan did not complete successfully: {scan_data["status"]}'
        )
        assert elapsed < 120, (
            f'Full scan took {elapsed:.1f}s, expected under 120s'
        )
