"""Tests for the dashboard view."""

from datetime import date, timedelta
from urllib.parse import urlencode

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects, assertTemplateUsed

from app.models import Container, Packet, Plant, Planting, PlantingEvent, PlantingSchedule

# A Monday in ISO week 46 of 2026, used to freeze "today" in the view tests.
TODAY = date(2026, 11, 9)


@pytest.fixture
def frozen_today(monkeypatch):
    """Freeze ``timezone.localdate()`` for the view and the model helpers."""
    monkeypatch.setattr('app.models.timezone.localdate', lambda: TODAY)
    return TODAY


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


def test_packet_counts_split_planted_from_unplanted(authed_client, garden_data):
    """A packet counts as planted once any live planting refers to it."""
    response = authed_client.get(reverse('app:dash_stats'))

    assert response.context['planted_packet_count'] == 1
    assert response.context['unplanted_packet_count'] == 2
    assertContains(response, 'Unplanted')


def make_schedule(plant, start_week, end_week, **kwargs):
    """Create a planting schedule that is active unless the test says otherwise."""
    kwargs.setdefault('active', True)
    return PlantingSchedule.objects.create(plant=plant, start_week=start_week, end_week=end_week, **kwargs)


def record_planting(plant, day):
    """Record one ``planted`` event for ``plant`` on ``day``."""
    packet = Packet.objects.create(plant=plant)
    planting = Planting.objects.create(packet=packet)
    return PlantingEvent.objects.create(
        planting=planting,
        event_type=PlantingEvent.EventType.PLANTED,
        date=day,
    )


def test_schedule_counts_split_by_status(authed_client, garden_data, frozen_today):
    """Schedules are counted by status, with anything unplantable as inactive."""
    beetroot = Plant.objects.get(id=1)
    carrot = Plant.objects.get(id=2)
    lettuce = Plant.objects.create(id=4, code='LE', name='Lettuce')
    chard = Plant.objects.create(id=5, code='CH', name='Chard')
    garlic = Plant.objects.create(id=6, code='GA', name='Garlic')
    make_schedule(beetroot, 45, 48)  # never planted, so due
    make_schedule(carrot, 45, 48, repeat_every_weeks=2)
    record_planting(carrot, TODAY - timedelta(weeks=1))  # next planting not yet due
    make_schedule(lettuce, 45, 48, repeat_every_weeks=2)
    record_planting(lettuce, TODAY - timedelta(weeks=5))  # past due
    make_schedule(chard, 40, 44)  # outside the current planting window
    make_schedule(garlic, 45, 48, active=False)

    response = authed_client.get(reverse('app:dash_stats'))

    assert response.context['schedule_counts'] == {
        'due': 1,
        'planted': 1,
        'overdue': 1,
        'inactive': 2,
        'total': 5,
    }


def test_schedule_counts_ignore_deleted_plants(authed_client, garden_data, frozen_today):
    """Schedules for deleted plants are not actionable, so are not counted."""
    deleted = Plant.objects.get(id=3)
    make_schedule(deleted, 45, 48)

    response = authed_client.get(reverse('app:dash_stats'))

    assert response.context['schedule_counts'] == {
        'due': 0,
        'planted': 0,
        'overdue': 0,
        'inactive': 0,
        'total': 0,
    }


def test_cards_ordered_containers_first_schedules_last(authed_client, garden_data):
    """The container card comes first and the schedules card last."""
    response = authed_client.get(reverse('app:dash_stats'))

    content = response.content.decode()
    titles = ['Containers', 'Plants', 'Packets', 'Plantings', 'Schedules']
    positions = [content.index(f'>{title}</h2>') for title in titles]
    assert positions == sorted(positions)


def test_schedules_card_links_to_schedule_page(authed_client, garden_data):
    response = authed_client.get(reverse('app:dash_stats'))

    assertContains(response, f'href="{reverse("app:schedule")}"')


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
