"""IT-8: Scheduled scan integration tests.

Tests the scan schedule CRUD endpoints.
"""

import uuid

import pytest


def _schedule_payload(name=None):
    return {
        'name': name or f'schedule-{uuid.uuid4().hex[:8]}',
        'scan_type': 'network',
        'scan_config': {
            'cidrs': ['10.99.99.0/24'],
            'ports': [5000],
            'timeout_ms': 2000,
            'max_concurrent_probes': 10,
        },
        'cron_expression': '0 */6 * * *',
        'enabled': True,
    }


class TestCreateSchedule:
    """Tests for POST /discovery/schedules."""

    def test_create_schedule(self, api):
        """Create a schedule with valid cron + config."""
        payload = _schedule_payload()
        resp = api.post('/discovery/schedules', json=payload)
        assert resp.status_code == 201, f'Create schedule failed: {resp.text}'

        data = resp.json()
        assert 'id' in data
        assert data['name'] == payload['name']
        assert data['cron_expression'] == payload['cron_expression']
        assert data['enabled'] is True

        # Cleanup
        api.delete(f'/discovery/schedules/{data["id"]}')


class TestListSchedules:
    """Tests for GET /discovery/schedules."""

    def test_list_schedules(self, api):
        """Create a schedule and verify it appears in the list."""
        payload = _schedule_payload()
        resp = api.post('/discovery/schedules', json=payload)
        assert resp.status_code == 201
        schedule_id = resp.json()['id']

        try:
            resp = api.get('/discovery/schedules')
            assert resp.status_code == 200
            body = resp.json()
            assert 'schedules' in body
            assert isinstance(body['schedules'], list)

            # Find our schedule in the list
            found = [s for s in body['schedules'] if s['id'] == schedule_id]
            assert len(found) == 1, f'Expected to find schedule {schedule_id} in list'
        finally:
            api.delete(f'/discovery/schedules/{schedule_id}')


class TestUpdateSchedule:
    """Tests for PUT /discovery/schedules/<id>."""

    def test_update_schedule(self, api):
        """Update the enabled flag on a schedule."""
        payload = _schedule_payload()
        resp = api.post('/discovery/schedules', json=payload)
        assert resp.status_code == 201
        schedule_id = resp.json()['id']

        try:
            # Disable the schedule
            resp = api.put(f'/discovery/schedules/{schedule_id}', json={
                'enabled': False,
            })
            assert resp.status_code == 200, f'Update failed: {resp.text}'
            assert resp.json()['enabled'] is False

            # Verify via list
            resp = api.get('/discovery/schedules')
            assert resp.status_code == 200
            found = [s for s in resp.json()['schedules'] if s['id'] == schedule_id]
            assert len(found) == 1
            assert found[0]['enabled'] is False
        finally:
            api.delete(f'/discovery/schedules/{schedule_id}')


class TestDeleteSchedule:
    """Tests for DELETE /discovery/schedules/<id>."""

    def test_delete_schedule(self, api):
        """Delete a schedule and verify 404 on subsequent access."""
        payload = _schedule_payload()
        resp = api.post('/discovery/schedules', json=payload)
        assert resp.status_code == 201
        schedule_id = resp.json()['id']

        # Delete
        resp = api.delete(f'/discovery/schedules/{schedule_id}')
        assert resp.status_code == 204, f'Delete failed: {resp.status_code}: {resp.text}'

        # Verify gone from list
        resp = api.get('/discovery/schedules')
        assert resp.status_code == 200
        found = [s for s in resp.json()['schedules'] if s['id'] == schedule_id]
        assert len(found) == 0, f'Schedule {schedule_id} should not appear after deletion'
