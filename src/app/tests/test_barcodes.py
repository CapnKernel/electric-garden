"""Tests for the barcode / id mapping."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from app.models import Container, Packet, Plant, Planting, PlantingEvent


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='豆D', name='Dwarf bean')


@pytest.fixture
def packet(db, plant):
    return Packet.objects.create(id=101, plant=plant)


@pytest.fixture
def planting(db, packet):
    planting = Planting.objects.create(id=1001, packet=packet)
    PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')
    return planting


@pytest.fixture
def container(db):
    return Container.objects.create(id=1, name='Blue ribbon 1')


def test_barcode_is_prefix_plus_padded_id(plant, packet, planting, container):
    # Ids are zero-padded: Plant/Container to 3 digits, Packet to 3, Planting to 4.
    assert plant.barcode == 'P=001'
    assert packet.barcode == 'P=101'
    assert planting.barcode == 'P=1001'
    assert container.barcode == 'PC=001'


def test_barcode_pads_to_model_width(db):
    assert Plant(id=7).barcode == 'P=007'
    assert Packet(id=107).barcode == 'P=107'
    assert Planting(id=1007).barcode == 'P=1007'
    assert Container(id=7).barcode == 'PC=007'
    # Values wider than the pad width are not truncated.
    assert Packet(id=1234).barcode == 'P=1234'
    assert Planting(id=12345).barcode == 'P=12345'


def test_barcode_is_read_only(plant):
    with pytest.raises(AttributeError):
        plant.barcode = 'P=1'


def test_pk_from_barcode_round_trips_each_model(plant, packet, planting, container):
    assert Plant.pk_from_barcode(plant.barcode) == plant.id
    assert Packet.pk_from_barcode(packet.barcode) == packet.id
    assert Planting.pk_from_barcode(planting.barcode) == planting.id
    assert Container.pk_from_barcode(container.barcode) == container.id


def test_pk_from_barcode_uses_each_models_prefix(plant, packet, planting, container):
    # The number in the barcode is the primary key.
    assert Plant.pk_from_barcode('P=7') == 7
    assert Packet.pk_from_barcode('P=107') == 107
    assert Planting.pk_from_barcode('P=1007') == 1007
    assert Container.pk_from_barcode('PC=7') == 7


def test_create_accepts_barcode(db):
    plant = Plant.objects.create(barcode='P=7', code='BR', name='Beetroot')
    assert plant.id == 7
    assert plant.barcode == 'P=007'


def test_create_rejects_id_and_barcode_together(db):
    with pytest.raises(ValueError):
        Plant.objects.create(id=7, barcode='P=7', code='BR', name='Beetroot')


class TestPlantedDate:
    """Tests for ``Planting.planted_date``."""

    def test_returns_planted_event(self, db, packet):
        planting = Planting.objects.create(id=2, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-02-01')
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.OTHER, date='2026-02-15')

        assert planting.planted_date == date(2026, 2, 1)

    def test_ignores_other_event_types(self, db, packet):
        planting = Planting.objects.create(id=3, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')
        PlantingEvent.objects.create(
            planting=planting, event_type=PlantingEvent.EventType.GERMINATED, date='2026-01-05'
        )

        assert planting.planted_date == date(2026, 1, 1)

    def test_returns_none_without_events(self, db, packet):
        planting = Planting.objects.create(id=4, packet=packet)

        assert planting.planted_date is None


class TestEventOrdering:
    """The planted event comes first, in creation order and in date."""

    def test_first_event_must_be_planted(self, db, packet):
        planting = Planting.objects.create(id=5, packet=packet)

        with pytest.raises(ValidationError):
            PlantingEvent.objects.create(
                planting=planting,
                event_type=PlantingEvent.EventType.GERMINATED,
                date='2026-01-05',
            )

    def test_planted_event_rejected_once_another_event_exists(self, db, packet):
        planting = Planting.objects.create(id=6, packet=packet)
        # A non-planted event can only exist here if it bypassed validation.
        PlantingEvent.objects.bulk_create(
            [
                PlantingEvent(
                    planting=planting,
                    event_type=PlantingEvent.EventType.OTHER,
                    date='2026-01-05',
                )
            ]
        )

        with pytest.raises(ValidationError):
            PlantingEvent.objects.create(
                planting=planting,
                event_type=PlantingEvent.EventType.PLANTED,
                date='2026-01-02',
            )

    def test_event_not_dated_before_planted(self, db, packet):
        planting = Planting.objects.create(id=7, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-02-01')

        with pytest.raises(ValidationError):
            PlantingEvent.objects.create(
                planting=planting,
                event_type=PlantingEvent.EventType.TRANSPLANTED,
                date='2026-01-15',
            )

    def test_planted_not_dated_after_an_existing_event(self, db, packet):
        planting = Planting.objects.create(id=8, packet=packet)
        planted = PlantingEvent.objects.create(
            planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01'
        )
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.GERMINATED,
            date='2026-01-20',
        )

        planted.date = date(2026, 1, 25)
        with pytest.raises(ValidationError):
            planted.save()


class TestLabel:
    """``label`` is the short name shown after a barcode (e.g. in breadcrumbs)."""

    def test_container_uses_name(self, container):
        assert container.label == 'Blue ribbon 1'

    def test_plant_uses_name(self, plant):
        assert plant.label == 'Dwarf bean'

    def test_planting_uses_plant_name(self, planting):
        assert planting.label == 'Dwarf bean'

    def test_packet_label_without_full_name(self, packet):
        assert packet.label == 'Dwarf bean'

    def test_packet_label_includes_full_name_in_parentheses(self, packet):
        packet.full_name = 'Marketmore'

        assert packet.label == 'Dwarf bean (Marketmore)'


class TestModelLabel:
    """``model_label`` names the model for templates, e.g. in breadcrumbs."""

    def test_values(self, plant, packet, planting, container):
        assert plant.model_label == 'plant'
        assert packet.model_label == 'packet'
        assert planting.model_label == 'planting'
        assert container.model_label == 'container'


class TestDetailTemplate:
    """Each barcoded model names the partial that renders it."""

    def test_values(self, plant, packet, planting, container):
        assert plant.detail_template == 'app/partials/detail/plant.html'
        assert packet.detail_template == 'app/partials/detail/packet.html'
        assert planting.detail_template == 'app/partials/detail/planting.html'
        assert container.detail_template == 'app/partials/detail/container.html'


class TestPacketStr:
    """``str(packet)`` is the barcode and label, e.g. for form selects and admin."""

    def test_without_full_name(self, packet):
        assert str(packet) == 'P=101: Dwarf bean'

    def test_with_full_name(self, packet):
        packet.full_name = 'Marketmore'

        assert str(packet) == 'P=101: Dwarf bean (Marketmore)'


class TestPlantingStr:
    """``str(planting)`` names the barcode, plant and planting date."""

    def test_includes_planted_date(self, planting):
        assert str(planting) == 'P=1001: Dwarf bean planted 01-Jan-2026'

    def test_without_a_planted_event(self, db, packet):
        planting = Planting.objects.create(id=1002, packet=packet)

        assert str(planting) == 'P=1002: Dwarf bean'


class TestSinglePlantedEvent:
    """A planting has at most one ``planted`` event (see the model constraint)."""

    def test_second_planted_event_rejected(self, db, packet):
        planting = Planting.objects.create(id=5, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')

        with pytest.raises(ValidationError):
            PlantingEvent.objects.create(
                planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-02-01'
            )

    def test_transplant_event_allowed(self, db, packet):
        planting = Planting.objects.create(id=6, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')
        PlantingEvent.objects.create(
            planting=planting, event_type=PlantingEvent.EventType.TRANSPLANTED, date='2026-02-01'
        )

        assert planting.events.count() == 2
