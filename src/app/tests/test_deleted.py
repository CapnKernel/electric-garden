"""Tests for the soft-deletion rule shared by the deletable models."""

import pytest
from django.core.exceptions import ValidationError
from pytest_django.asserts import assertContains

from app.models import Container, Packet, Plant, Planting, PlantingEvent

MODEL_NAMES = ('container', 'plant', 'packet', 'planting')


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='BR', name='Beetroot')


@pytest.fixture
def packet(plant):
    return Packet.objects.create(id=101, plant=plant)


def make_unsaved(model_name, plant, packet):
    """Return an unsaved instance of the named deletable model."""
    factories = {
        'container': lambda: Container(id=1, name='Blue ribbon 1'),
        'plant': lambda: Plant(id=2, code='XX', name='Gone'),
        'packet': lambda: Packet(id=102, plant=plant),
        'planting': lambda: Planting(id=1001, packet=packet),
    }
    return factories[model_name]()


@pytest.mark.parametrize('model_name', MODEL_NAMES)
def test_reason_on_a_live_item_is_an_error(model_name, plant, packet):
    """A deleted reason only makes sense on a deleted item, so saving it is refused."""
    obj = make_unsaved(model_name, plant, packet)
    obj.deleted_reason = 'no longer wanted'

    with pytest.raises(ValidationError) as excinfo:
        obj.save()

    assert 'deleted_reason' in excinfo.value.message_dict
    assert not type(obj).objects.filter(pk=obj.pk).exists()


@pytest.mark.parametrize('model_name', MODEL_NAMES)
def test_reason_on_a_deleted_item_saves(model_name, plant, packet):
    """A deleted item may record why it went."""
    obj = make_unsaved(model_name, plant, packet)
    obj.deleted = True
    obj.deleted_reason = 'no longer wanted'

    obj.save()

    assert type(obj).objects.filter(deleted=True, deleted_reason='no longer wanted').exists()


@pytest.mark.parametrize('model_name', MODEL_NAMES)
def test_undeleted_item_must_lose_its_reason_first(model_name, plant, packet):
    """Un-deleting an item without clearing the reason is an error."""
    obj = make_unsaved(model_name, plant, packet)
    obj.deleted = True
    obj.deleted_reason = 'no longer wanted'
    obj.save()

    obj.deleted = False

    with pytest.raises(ValidationError):
        obj.save()


def test_deleted_detail_page_marks_the_object(authed_client, plant):
    """A deleted object's detail card is struck through and names the reason."""
    plant.deleted = True
    plant.deleted_reason = 'wrong variety'
    plant.save()

    response = authed_client.get(plant.detail_url)

    assertContains(response, f'<s>{plant}</s>')
    assertContains(response, '>Deleted</span>')
    assertContains(response, 'wrong variety')


def test_container_card_shows_deleted_planting_struck_through(authed_client, plant):
    """A container's planting list keeps deleted plantings, struck through."""
    container = Container.objects.create(id=1, name='Blue ribbon 1')
    packet = Packet.objects.create(id=101, plant=plant, container=container)
    planting = Planting.objects.create(id=1001, packet=packet, deleted=True)
    PlantingEvent.objects.create(
        planting=planting,
        event_type=PlantingEvent.EventType.PLANTED,
        date='2026-01-01',
        planted_in=container,
    )

    response = authed_client.get(container.detail_url)

    assertContains(response, planting.barcode)
    assertContains(response, '<tr class="text-decoration-line-through">')
