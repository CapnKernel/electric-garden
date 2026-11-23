"""Tests for the ``Placement`` value object and the models' placement accessors."""

import pytest
from django.core.exceptions import ValidationError

from app.models import Container, Packet, Plant, Planting, PlantingEvent
from app.placement import EMPTY, Placement


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='豆D', name='Dwarf bean')


@pytest.fixture
def packet(db, plant):
    return Packet.objects.create(id=101, plant=plant)


@pytest.fixture
def container(db):
    return Container.objects.create(id=1, name='Blue ribbon 1')


class TestPlacementValue:
    """A placement is a container, free text, both, or neither."""

    def test_empty(self):
        assert EMPTY.is_empty
        assert EMPTY.display == ''
        assert str(EMPTY) == ''

    def test_text_only(self):
        placement = Placement(text='Front garden')

        assert not placement.is_empty
        assert placement.display == 'Front garden'

    def test_container_only(self, container):
        assert Placement(container=container).display == str(container)

    def test_both_halves_are_displayed_together(self, container):
        placement = Placement(container=container, text='Front garden')

        assert placement.display == f'{container} · Front garden'

    def test_whitespace_only_text_is_empty(self):
        assert Placement(text='   ') == EMPTY

    def test_is_in(self, container):
        other = Container.objects.create(id=2, name='Other')

        assert Placement(container=container).is_in(container)
        assert not Placement(container=container).is_in(other)
        assert not EMPTY.is_in(container)


class TestEventPlacement:
    """Events read and write both halves of a location through ``placement``."""

    def test_set_and_read(self, packet, container):
        planting = Planting.objects.create(id=1001, packet=packet)
        event = PlantingEvent(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')

        event.set_placement(Placement(container=container, text='Front garden'))
        event.save()

        assert event.planted_in == container
        assert event.location == 'Front garden'
        assert event.placement == Placement(container=container, text='Front garden')
        assert event.has_location

    def test_germinated_event_rejects_a_placement(self, packet, container):
        planting = Planting.objects.create(id=1001, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')
        event = PlantingEvent(planting=planting, event_type=PlantingEvent.EventType.GERMINATED, date='2026-01-05')
        event.set_placement(Placement(container=container))

        with pytest.raises(ValidationError):
            event.save()

    def test_last_placement_is_empty_without_placements(self, packet):
        planting = Planting.objects.create(id=1001, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')

        assert PlantingEvent.last_placement() == EMPTY


class TestPlantingPlacement:
    """A planting's placement is the one on its most recent located event."""

    def test_comes_from_the_latest_located_event(self, packet, container):
        first = container
        second = Container.objects.create(id=2, name='Second pot')
        planting = Planting.objects.create(id=1001, packet=packet)
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.PLANTED,
            date='2026-01-01',
            planted_in=first,
            location='Old spot',
        )
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.TRANSPLANTED,
            date='2026-02-01',
            planted_in=second,
            location='New spot',
        )

        assert planting.placement == Placement(container=second, text='New spot')
        assert planting.is_in(second)
        assert not planting.is_in(first)

    def test_germinated_events_are_ignored(self, packet, container):
        planting = Planting.objects.create(id=1001, packet=packet)
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.PLANTED,
            date='2026-01-01',
            planted_in=container,
        )
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.GERMINATED,
            date='2026-01-05',
        )

        assert planting.placement.container == container

    def test_is_empty_without_events(self, packet):
        planting = Planting.objects.create(id=1001, packet=packet)

        assert planting.placement == EMPTY
        assert not planting.is_in(Container(id=1))


class TestPacketPlacement:
    """A packet's placement is the container it is stored in."""

    def test_is_the_container(self, packet, container):
        packet.container = container

        assert packet.placement == Placement(container=container)

    def test_is_empty_without_a_container(self, packet):
        assert packet.placement == EMPTY
