"""IT-1: Scan CRUD API integration tests.

Tests the discovery scan lifecycle — create, list, get, cancel, rerun.
All tests make real HTTP calls to the running registry API.
"""

import uuid

import pytest

from tests.discovery.conftest import scan_and_wait


def _make_scan_payload(name=None, scan_type='network', cidrs=None, ports=None):
    """Helper to build a valid scan creation payload."""
    return {
        'name': name or f'test-scan-{uuid.uuid4().hex[:8]}',
        'scan_type': scan_type,
        'config': {
            'cidrs': cidrs or ['10.99.99.0/24'],
            'ports': ports or [5000],
            'timeout_ms': 2000,
            'max_concurrent_probes': 10,
        },
    }


class TestCreateScan:
    """Tests for POST /discovery/scans."""

    def test_create_scan_valid(self, api, cleanup_scans):
        """Create a scan with valid config, expect 201."""
        payload = _make_scan_payload()
        resp = api.post('/discovery/scans', json=payload)

        assert resp.status_code == 201, f'Expected 201, got {resp.status_code}: {resp.text}'
        data = resp.json()
        assert 'id' in data
        assert data['name'] == payload['name']
        assert data['scan_type'] == 'network'
        assert data['status'] in ('pending', 'running', 'completed', 'failed')
        cleanup_scans.append(data['id'])

    def test_create_scan_missing_fields(self, api):
        """Omit scan_type, expect 400 validation error."""
        payload = {
            'name': f'test-scan-{uuid.uuid4().hex[:8]}',
            'config': {
                'cidrs': ['10.99.99.0/24'],
                'ports': [5000],
            },
        }
        resp = api.post('/discovery/scans', json=payload)

        assert resp.status_code == 400
        body = resp.json()
        assert 'error' in body or 'messages' in body

    def test_create_scan_invalid_cidr(self, api):
        """Invalid CIDR notation, expect 400."""
        payload = _make_scan_payload(cidrs=['not-a-cidr'])
        resp = api.post('/discovery/scans', json=payload)

        assert resp.status_code == 400
        body = resp.json()
        assert 'error' in body or 'messages' in body

    def test_create_scan_invalid_port(self, api):
        """Port 99999 is out of range, expect 400."""
        payload = _make_scan_payload(ports=[99999])
        resp = api.post('/discovery/scans', json=payload)

        assert resp.status_code == 400
        body = resp.json()
        assert 'error' in body or 'messages' in body


class TestListScans:
    """Tests for GET /discovery/scans."""

    def test_list_scans_paginated(self, api, cleanup_scans):
        """Create 3 scans, list with per_page=2, verify pagination."""
        created_ids = []
        for i in range(3):
            payload = _make_scan_payload(name=f'paginate-test-{i}-{uuid.uuid4().hex[:6]}')
            resp = api.post('/discovery/scans', json=payload)
            assert resp.status_code == 201, f'Failed to create scan {i}: {resp.text}'
            created_ids.append(resp.json()['id'])
            cleanup_scans.append(resp.json()['id'])

        # Fetch page 1
        resp = api.get('/discovery/scans', params={'per_page': 2, 'page': 1})
        assert resp.status_code == 200
        body = resp.json()
        assert 'scans' in body
        assert len(body['scans']) <= 2
        assert body['per_page'] == 2
        assert body['total'] >= 3
        assert body['pages'] >= 2

    def test_list_scans_filter_status(self, api, cleanup_scans):
        """Create a scan and filter by its status."""
        payload = _make_scan_payload()
        resp = api.post('/discovery/scans', json=payload)
        assert resp.status_code == 201
        scan = resp.json()
        cleanup_scans.append(scan['id'])

        # Filter by the scan's current status
        status = scan['status']
        resp = api.get('/discovery/scans', params={'status': status})
        assert resp.status_code == 200
        body = resp.json()
        assert 'scans' in body
        # All returned scans should have the requested status
        for s in body['scans']:
            assert s['status'] == status


class TestGetScan:
    """Tests for GET /discovery/scans/<id>."""

    def test_get_scan_by_id(self, api, cleanup_scans):
        """Create and retrieve a scan by ID."""
        payload = _make_scan_payload()
        resp = api.post('/discovery/scans', json=payload)
        assert resp.status_code == 201
        scan_id = resp.json()['id']
        cleanup_scans.append(scan_id)

        resp = api.get(f'/discovery/scans/{scan_id}')
        assert resp.status_code == 200
        data = resp.json()
        assert data['id'] == scan_id
        assert data['name'] == payload['name']

    def test_get_scan_not_found(self, api):
        """Random UUID should return 404."""
        random_id = str(uuid.uuid4())
        resp = api.get(f'/discovery/scans/{random_id}')
        assert resp.status_code == 404


class TestCancelScan:
    """Tests for DELETE /discovery/scans/<id> (cancel)."""

    def test_cancel_running_scan(self, api, cleanup_scans):
        """Start a scan, cancel it, verify it reaches a terminal state."""
        payload = _make_scan_payload()
        resp = api.post('/discovery/scans', json=payload)
        assert resp.status_code == 201
        scan_id = resp.json()['id']
        cleanup_scans.append(scan_id)

        # Cancel the scan
        resp = api.delete(f'/discovery/scans/{scan_id}')
        # Should be 200 if cancelled, or 409 if already completed/failed
        assert resp.status_code in (200, 409), f'Unexpected status: {resp.status_code}: {resp.text}'

        if resp.status_code == 200:
            data = resp.json()
            assert data['status'] == 'cancelled'

        # Verify via GET — scan should be in any terminal state
        resp = api.get(f'/discovery/scans/{scan_id}')
        assert resp.status_code == 200
        assert resp.json()['status'] in ('cancelled', 'completed', 'failed')


class TestRerunScan:
    """Tests for POST /discovery/scans/<id>/rerun."""

    def test_rerun_scan(self, api, cleanup_scans):
        """Complete a scan, rerun it, verify new scan created."""
        # Use a tiny subnet so the scan completes quickly
        payload = _make_scan_payload(cidrs=['10.99.99.0/30'])
        completed = scan_and_wait(api, payload, timeout=60)
        cleanup_scans.append(completed['id'])

        # Rerun
        resp = api.post(f'/discovery/scans/{completed["id"]}/rerun')
        assert resp.status_code == 201, f'Rerun failed: {resp.text}'
        new_scan = resp.json()
        cleanup_scans.append(new_scan['id'])

        # New scan should have a different ID
        assert new_scan['id'] != completed['id']
        assert new_scan['status'] in ('pending', 'running', 'completed', 'failed')
