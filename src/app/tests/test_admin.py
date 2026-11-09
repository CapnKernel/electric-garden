"""Tests for barcode-aware admin behaviour."""

from django.urls import reverse
from pytest_django.asserts import assertContains

from app.models import Plant

# The plant change form carries an empty planting-schedule inline, so a form post
# must include its management form.
EMPTY_SCHEDULE_FORMSET = {
    'planting_schedules-TOTAL_FORMS': '0',
    'planting_schedules-INITIAL_FORMS': '0',
    'planting_schedules-MIN_NUM_FORMS': '0',
    'planting_schedules-MAX_NUM_FORMS': '1000',
}


def test_admin_creates_object_with_preassigned_id(admin_client, db):
    url = reverse('admin:app_plant_add') + '?id=42'

    response = admin_client.post(url, {**EMPTY_SCHEDULE_FORMSET, 'code': 'ZZ', 'name': 'Preassigned plant'})

    assert response.status_code == 302
    assert Plant.objects.filter(pk=42).exists()


def test_admin_keeps_preassigned_id_for_add_another(admin_client, db):
    url = reverse('admin:app_plant_add') + '?id=42'

    response = admin_client.post(
        url,
        {**EMPTY_SCHEDULE_FORMSET, 'code': 'ZZ', 'name': 'Preassigned plant', '_addanother': 'Save and add another'},
    )

    assert response.status_code == 302
    assert response['Location'] == reverse('admin:app_plant_add') + '?id=42'


def test_admin_changelist_links_to_scan_page(admin_client, db):
    plant = Plant.objects.create(id=1, code='ZZ', name='Scan me')

    response = admin_client.get(reverse('admin:app_plant_changelist'))

    assertContains(response, plant.scan_url)
