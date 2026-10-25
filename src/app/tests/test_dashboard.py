"""Tests for the dashboard view."""

from urllib.parse import urlencode

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects, assertTemplateUsed

from app.models import Packet, Plant, Planting


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


def test_requires_login(client, db):
    """The dashboard is inaccessible without authentication."""
    top = reverse('app:top')

    response = client.get(top)

    assertRedirects(response, f'{reverse("login")}?{urlencode({"next": top})}')


def test_renders_counts(authed_client, garden_data):
    response = authed_client.get(reverse('app:top'))

    assertTemplateUsed(response, 'app/top.html')
    assertTemplateUsed(response, 'app/base.html')
    assertContains(response, 'Plants')
    assertContains(response, 'Packets')
    assertContains(response, 'Plantings')


def test_counts_exclude_deleted(authed_client, garden_data):
    response = authed_client.get(reverse('app:top'))

    assert response.context['plant_count'] == 2
    assert response.context['packet_count'] == 3
    assert response.context['planting_count'] == 1
