"""Tests for the barcode / id mapping."""

import pytest

from garden.models import Container, Packet, Plant, Planting


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='豆D', name='Dwarf bean')


@pytest.fixture
def packet(db, plant):
    return Packet.objects.create(id=1, plant=plant)


@pytest.fixture
def planting(db, packet):
    return Planting.objects.create(id=1, packet=packet, planted='2026-01-01')


@pytest.fixture
def container(db):
    return Container.objects.create(id=1, name='Blue ribbon 1')


def test_barcode_is_prefix_plus_id(plant, packet, planting, container):
    assert plant.barcode == f'P={plant.id}'
    assert packet.barcode == f'P={packet.id}'
    assert planting.barcode == f'P={planting.id}'
    assert container.barcode == f'PC={container.id}'


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
    assert plant.barcode == 'P=7'


def test_create_rejects_id_and_barcode_together(db):
    with pytest.raises(ValueError):
        Plant.objects.create(id=7, barcode='P=7', code='BR', name='Beetroot')
