"""Tests for the Google Sheets webhook API (Stage 1)."""

import json

import pytest
from django.test import override_settings
from django.urls import reverse

WEBHOOK_URL = '/garden/api/sheets/webhook/'
API_KEY = 'test-api-key'


def _payload():
    return {
        'sheet_name': 'Sheet1',
        'range': 'B2',
        'old_values': [['old']],
        'new_values': [['new']],
        'timestamp': '2026-09-25T00:00:00Z',
        'user_email': 'gardener@example.com',
    }


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_accepts_valid_request(client):
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(_payload()),
        content_type='application/json',
        headers={'X-API-Key': API_KEY},
    )
    assert response.status_code == 200
    assert response.json() == {'status': 'ok', 'message': 'Change received.'}


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_rejects_missing_key(client):
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(_payload()),
        content_type='application/json',
    )
    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_rejects_wrong_key(client):
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(_payload()),
        content_type='application/json',
        headers={'X-API-Key': 'wrong'},
    )
    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=None)
def test_webhook_fails_closed_without_configured_key(client):
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(_payload()),
        content_type='application/json',
        headers={'X-API-Key': API_KEY},
    )
    assert response.status_code == 401


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_rejects_invalid_payload(client):
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps({'sheet_name': 'only-this'}),
        content_type='application/json',
        headers={'X-API-Key': API_KEY},
    )
    assert response.status_code == 422


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_url_is_reversible():
    assert reverse('garden_api:sheets_webhook') == WEBHOOK_URL
