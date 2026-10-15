"""Tests for the barcode / id mapping."""

import pytest

from garden.models import Container, Packet, Plant, Planting, PlantingEvent


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='豆D', name='Dwarf bean')


@pytest.fixture
def packet(db, plant):
    return Packet.objects.create(id=1, plant=plant)


@pytest.fixture
def planting(db, packet):
    planting = Planting.objects.create(id=1, packet=packet)
    PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')
    return planting


@pytest.fixture
def container(db):
    return Container.objects.create(id=1, name='Blue ribbon 1')


def test_barcode_is_prefix_plus_padded_id(plant, packet, planting, container):
    # Ids are zero-padded: Plant/Container to 3 digits, Packet to 3, Planting to 4.
    assert plant.barcode == 'P=001'
    assert packet.barcode == 'P=001'
    assert planting.barcode == 'P=0001'
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
