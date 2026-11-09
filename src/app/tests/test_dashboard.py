"""Tests for the dashboard view."""

from urllib.parse import urlencode

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects, assertTemplateUsed

from app.models import Container, Packet, Plant, Planting


@pytest.fixture
def garden_data(db):
    plant = Plant.objects.create(id=1, code='BR', name='Beetroot')
    Plant.objects.create(id=2, code='CA', name='Carrot')
    Plant.objects.create(id=3, code='XX', name='Deleted plant', deleted=True)

    packet = Packet.objects.create(id=101, plant=plant, brand='Brand A')
    Packet.objects.create(id=102, plant=plant, brand='Brand B')
    Packet.objects.create(id=103, plant=plant, brand='Brand C')
    Packet.objects.create(id=104, plant=plant, brand='Deleted packet', deleted=True)

    Planting.objects.create(id=1001, packet=packet)
    Planting.objects.create(id=1002, packet=packet, deleted=True)

    Container.objects.create(id=1, name='Blue ribbon 1')
    Container.objects.create(id=2, name='Blue ribbon 2')


def test_requires_login(client, db):
    """The dashboard is inaccessible without authentication."""
    top = reverse('app:top')

    response = client.get(top)

    assertRedirects(response, f'{reverse("login")}?{urlencode({"next": top})}')


def test_renders_headings(authed_client, garden_data):
    response = authed_client.get(reverse('app:top'))

    assertTemplateUsed(response, 'app/top.html')
    assertTemplateUsed(response, 'app/base.html')
    assertContains(response, 'Plants')
    assertContains(response, 'Packets')
    assertContains(response, 'Plantings')
    assertContains(response, 'Containers')


def test_base_template_includes_toast_support(authed_client, db):
    """The shared base template provides the toast container and helper."""
    response = authed_client.get(reverse('app:top'))

    assertContains(response, 'id="toastContainer"')
    assertContains(response, 'function showToast')


def test_loads_stats_partial_via_htmx(authed_client, garden_data):
    """The dashboard fetches its statistics from the dash_stats partial."""
    response = authed_client.get(reverse('app:top'))

    assertContains(response, f'hx-get="{reverse("app:dash_stats")}"')
    assertContains(response, 'hx-trigger="load"')


def test_partial_counts_exclude_deleted(authed_client, garden_data):
    """The view passes the active counts in its context."""
    response = authed_client.get(reverse('app:dash_stats'))

    assert response.status_code == 200
    assert response.context['plant_count'] == 2
    assert response.context['packet_count'] == 3
    assert response.context['planting_count'] == 1
    assert response.context['container_count'] == 2


def test_partial_renders_counts(authed_client, garden_data):
    """The partial renders each count in its own card."""
    response = authed_client.get(reverse('app:dash_stats'))

    content = response.content.decode()
    assert '<!DOCTYPE html>' not in content
    assertContains(response, '<p class="card-text display-6">2</p>', html=True)  # plants
    assertContains(response, '<p class="card-text display-6">3</p>', html=True)  # packets
    assertContains(response, '<p class="card-text display-6">1</p>', html=True)  # plantings
    assertContains(response, '<p class="card-text display-6">2</p>', html=True)  # containers


def test_cards_link_to_admin_changelists(authed_client, garden_data):
    """Each dashboard card links to the matching admin changelist."""
    response = authed_client.get(reverse('app:dash_stats'))

    for url_name in (
        'admin:app_plant_changelist',
        'admin:app_packet_changelist',
        'admin:app_planting_changelist',
        'admin:app_container_changelist',
    ):
        assertContains(response, f'href="{reverse(url_name)}"')
