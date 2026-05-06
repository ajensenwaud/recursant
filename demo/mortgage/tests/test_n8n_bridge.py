"""
Tests for the n8n A2A bridge.

Unit tests for the A2A-to-n8n webhook translator.
Uses httpx mock to avoid needing a running n8n instance.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
import sys
import os

# Add bridge directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'agents', 'n8n_bridge'))

from bridge import app  # noqa: E402


@pytest.fixture
def client():
    """Flask test client for the bridge."""
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


class TestA2AHandler:
    """Tests for POST /a2a endpoint."""

    def test_parse_error_on_empty_body(self, client):
        """Should return JSON-RPC parse error when body is empty."""
        response = client.post('/a2a', data='not json', content_type='text/plain')
        assert response.status_code == 400
        data = response.get_json()
        assert data['error']['code'] == -32700

    def test_method_not_found(self, client):
        """Should return method not found for unknown methods."""
        response = client.post('/a2a', json={
            'jsonrpc': '2.0',
            'id': '1',
            'method': 'unknown/method',
            'params': {},
        })
        assert response.status_code == 404
        data = response.get_json()
        assert data['error']['code'] == -32601

    @patch('bridge.httpx.post')
    def test_message_send_with_text(self, mock_post, client):
        """Should forward text message to n8n webhook."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({'status': 'verified', 'name': 'Jane Smith'})
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        payload = {
            'jsonrpc': '2.0',
            'id': 'req-1',
            'method': 'message/send',
            'params': {
                'message': {
                    'parts': [
                        {'kind': 'text', 'text': json.dumps({
                            'customer_name': 'Jane Smith',
                            'document_type': 'passport',
                        })}
                    ]
                }
            }
        }

        response = client.post('/a2a', json=payload)
        assert response.status_code == 200

        data = response.get_json()
        assert data['jsonrpc'] == '2.0'
        assert data['id'] == 'req-1'
        assert data['result']['status'] == 'completed'
        assert len(data['result']['artifacts']) == 1

        # Verify webhook was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert 'kyc-verification' in call_args[0][0]

    @patch('bridge.httpx.post')
    def test_message_send_with_image(self, mock_post, client):
        """Should forward text + image to n8n webhook."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({'status': 'verified'})
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        payload = {
            'jsonrpc': '2.0',
            'id': 'req-2',
            'method': 'message/send',
            'params': {
                'message': {
                    'parts': [
                        {'kind': 'text', 'text': json.dumps({
                            'customer_name': 'John Doe',
                        })},
                        {'kind': 'file', 'file': {
                            'bytes': 'base64encodedimage==',
                            'mimeType': 'image/jpeg',
                        }}
                    ]
                }
            }
        }

        response = client.post('/a2a', json=payload)
        assert response.status_code == 200

        # Verify the webhook payload includes the image
        call_args = mock_post.call_args
        webhook_payload = call_args[1]['json']
        assert webhook_payload['passport_image'] == 'base64encodedimage=='
        assert webhook_payload['media_type'] == 'image/jpeg'

    def test_message_send_with_no_content(self, client):
        """Should return failure when message has no content."""
        payload = {
            'jsonrpc': '2.0',
            'id': 'req-3',
            'method': 'message/send',
            'params': {
                'message': {
                    'parts': []
                }
            }
        }

        response = client.post('/a2a', json=payload)
        assert response.status_code == 200

        data = response.get_json()
        assert data['result']['status'] == 'failed'

    @patch('bridge.httpx.post')
    def test_message_send_n8n_error(self, mock_post, client):
        """Should return error artifact when n8n webhook fails."""
        mock_post.side_effect = Exception("Connection refused")

        payload = {
            'jsonrpc': '2.0',
            'id': 'req-4',
            'method': 'message/send',
            'params': {
                'message': {
                    'parts': [
                        {'kind': 'text', 'text': 'test message'}
                    ]
                }
            }
        }

        response = client.post('/a2a', json=payload)
        assert response.status_code == 200

        data = response.get_json()
        result = data['result']
        assert result['status'] == 'completed'
        artifact_text = result['artifacts'][0]['text']
        error_data = json.loads(artifact_text)
        assert error_data['status'] == 'error'
        assert 'Connection refused' in error_data['message']

    @patch('bridge.httpx.post')
    def test_message_send_non_json_text(self, mock_post, client):
        """Should handle non-JSON text content gracefully."""
        mock_response = MagicMock()
        mock_response.text = json.dumps({'status': 'verified'})
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        payload = {
            'jsonrpc': '2.0',
            'id': 'req-5',
            'method': 'message/send',
            'params': {
                'message': {
                    'parts': [
                        {'kind': 'text', 'text': 'Just a plain text message'}
                    ]
                }
            }
        }

        response = client.post('/a2a', json=payload)
        assert response.status_code == 200

        # The non-JSON text should be wrapped in a 'message' key
        call_args = mock_post.call_args
        webhook_payload = call_args[1]['json']
        assert webhook_payload['message'] == 'Just a plain text message'


class TestHealthCheck:
    """Tests for GET /health endpoint."""

    @patch('bridge.httpx.get')
    def test_health_ok_when_n8n_reachable(self, mock_get, client):
        """Should return 'ok' when n8n is reachable."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        response = client.get('/health')
        assert response.status_code == 200

        data = response.get_json()
        assert data['status'] == 'ok'
        assert data['n8n_reachable'] is True
        assert data['agent'] == 'n8n-kyc-bridge'

    @patch('bridge.httpx.get')
    def test_health_degraded_when_n8n_unreachable(self, mock_get, client):
        """Should return 'degraded' when n8n is unreachable."""
        mock_get.side_effect = Exception("Connection refused")

        response = client.get('/health')
        assert response.status_code == 200

        data = response.get_json()
        assert data['status'] == 'degraded'
        assert data['n8n_reachable'] is False

    @patch('bridge.httpx.get')
    def test_health_degraded_on_non_200(self, mock_get, client):
        """Should return 'degraded' when n8n returns non-200."""
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_get.return_value = mock_response

        response = client.get('/health')
        assert response.status_code == 200

        data = response.get_json()
        assert data['status'] == 'degraded'
        assert data['n8n_reachable'] is False
