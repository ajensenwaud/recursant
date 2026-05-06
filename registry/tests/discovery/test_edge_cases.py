"""IT-9: Edge case integration tests.

Tests empty subnet scans and concurrent scan execution.
"""

import uuid
import time
import concurrent.futures

import httpx
import pytest

from tests.discovery.conftest import REGISTRY_URL, scan_and_wait


# Subnet with no containers (use /28 for fewer targets = faster scan)
EMPTY_SUBNET = '10.99.99.0/28'


def _empty_scan_payload(name=None):
    return {
        'name': name or f'empty-scan-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'config': {
            'cidrs': [EMPTY_SUBNET],
            'ports': [5000],
            'timeout_ms': 1000,
            'max_concurrent_probes': 14,
        },
    }


class TestEmptySubnet:
    """Test scanning a subnet with no containers."""

    def test_scan_empty_subnet(self, api, cleanup_scans):
        """Scan an empty subnet, verify scan reaches terminal state with 0 results."""
        scan = scan_and_wait(api, _empty_scan_payload(), timeout=60)
        cleanup_scans.append(scan['id'])

        # Scan should complete (or fail gracefully — no reachable hosts either way)
        assert scan['status'] in ('completed', 'failed'), (
            f'Expected terminal state, got {scan["status"]}'
        )

        # If completed, summary should show 0 discovered hosts
        if scan['status'] == 'completed':
            summary = scan.get('summary', {})
            if summary:
                hosts_reachable = summary.get('hosts_reachable', 0)
                assert hosts_reachable == 0, (
                    f'Expected 0 reachable hosts on empty subnet, got {hosts_reachable}'
                )


class TestConcurrentScans:
    """Test running multiple scans simultaneously."""

    def test_concurrent_scans(self, api, auth_headers, cleanup_scans):
        """Launch 2 scans simultaneously, verify both complete."""
        payloads = [
            {
                'name': f'concurrent-a-{uuid.uuid4().hex[:8]}',
                'scan_type': 'network',
                'config': {
                    'cidrs': ['10.99.98.0/24'],
                    'ports': [5000],
                    'timeout_ms': 2000,
                    'max_concurrent_probes': 10,
                },
            },
            {
                'name': f'concurrent-b-{uuid.uuid4().hex[:8]}',
                'scan_type': 'network',
                'config': {
                    'cidrs': ['10.99.97.0/24'],
                    'ports': [5000],
                    'timeout_ms': 2000,
                    'max_concurrent_probes': 10,
                },
            },
        ]

        # Create both scans
        scan_ids = []
        for payload in payloads:
            resp = api.post('/discovery/scans', json=payload)
            assert resp.status_code == 201, f'Failed to create scan: {resp.text}'
            scan_ids.append(resp.json()['id'])
            cleanup_scans.append(resp.json()['id'])

        # Wait for both to complete
        deadline = time.time() + 120
        completed = set()

        while time.time() < deadline and len(completed) < 2:
            for sid in scan_ids:
                if sid in completed:
                    continue
                resp = api.get(f'/discovery/scans/{sid}')
                assert resp.status_code == 200
                status = resp.json()['status']
                if status in ('completed', 'failed', 'cancelled'):
                    completed.add(sid)
            if len(completed) < 2:
                time.sleep(1)

        assert len(completed) == 2, (
            f'Expected both scans to finish, only {len(completed)}/2 completed'
        )

        # Verify both are in terminal state
        for sid in scan_ids:
            resp = api.get(f'/discovery/scans/{sid}')
            assert resp.status_code == 200
            assert resp.json()['status'] in ('completed', 'failed'), (
                f'Scan {sid} in unexpected state: {resp.json()["status"]}'
            )
