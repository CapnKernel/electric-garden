"""Tests for the Google Sheets webhook API (Stages 1 and 2)."""

import json

import pytest
from django.test import override_settings
from django.urls import reverse

from garden.models import SheetChangeLog

WEBHOOK_URL = '/garden/api/sheets/webhook/'
API_KEY = 'test-api-key'


def _payload():
    return {
        'sheet_name': 'Sheet1',
        'range': 'B2',
        'column_name': 'Name',
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
    body = response.json()
    assert body['status'] == 'ok'
    assert body['message'] == 'Change received.'
    assert isinstance(body['tracking_id'], int)


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


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_persists_pending_change(client):
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(_payload()),
        content_type='application/json',
        headers={'X-API-Key': API_KEY},
    )
    tracking_id = response.json()['tracking_id']

    change = SheetChangeLog.objects.get(pk=tracking_id)
    assert change.status == SheetChangeLog.Status.PENDING
    assert change.sheet_name == 'Sheet1'
    assert change.range == 'B2'
    assert change.column_name == 'Name'
    assert change.old_values == [['old']]
    assert change.new_values == [['new']]
    assert change.user_email == 'gardener@example.com'
    assert change.edit_timestamp is not None
    assert change.applied_at is None
    assert change.error_message is None


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_stores_row_key(client):
    payload = _payload() | {'key': 'P=42'}
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-API-Key': API_KEY},
    )
    change = SheetChangeLog.objects.get(pk=response.json()['tracking_id'])
    assert change.key == 'P=42'


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_tolerates_unparseable_timestamp(client):
    payload = _payload() | {'timestamp': 'not-a-date'}
    response = client.post(
        WEBHOOK_URL,
        data=json.dumps(payload),
        content_type='application/json',
        headers={'X-API-Key': API_KEY},
    )
    assert response.status_code == 200
    change = SheetChangeLog.objects.get(pk=response.json()['tracking_id'])
    assert change.edit_timestamp is None


@pytest.mark.django_db
@override_settings(SHEETS_WEBHOOK_API_KEY=API_KEY)
def test_webhook_does_not_persist_rejected_request(client):
    client.post(
        WEBHOOK_URL,
        data=json.dumps(_payload()),
        content_type='application/json',
        headers={'X-API-Key': 'wrong'},
    )
    assert SheetChangeLog.objects.count() == 0
