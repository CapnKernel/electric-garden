"""Tests for the barcode scanning views and lookup logic."""

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from garden.models import Container, Packet, Plant, Planting, PlantingEvent
from garden.scan import BarcodeNotFound, lookup_barcode, scan_and_mark
from garden.templatetags.garden_extras import friendly_date


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='豆D', name='Dwarf bean')


@pytest.fixture
def packet(db, plant):
    return Packet.objects.create(id=101, plant=plant, brand="Mr Fothergill's")


@pytest.fixture
def planting(db, packet):
    planting = Planting.objects.create(id=1001, packet=packet)
    PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date='2026-01-01')
    return planting


@pytest.fixture
def container(db):
    return Container.objects.create(id=1, name='Blue ribbon 1')


class TestFromBarcode:
    """Tests for the ``from_barcode`` classmethod on the models."""

    def test_plant_from_barcode(self, plant):
        assert Plant.from_barcode('P=1') == plant

    def test_packet_from_barcode(self, packet):
        assert Packet.from_barcode('P=101') == packet

    def test_planting_from_barcode(self, planting):
        assert Planting.from_barcode('P=1001') == planting

    def test_container_from_barcode(self, container):
        assert Container.from_barcode('PC=1') == container

    def test_returns_none_for_unknown_id(self, db):
        assert Plant.from_barcode('P=999') is None

    def test_returns_none_for_wrong_prefix(self, plant):
        assert Plant.from_barcode('PC=1') is None

    def test_returns_none_for_malformed(self, db):
        assert Plant.from_barcode('P=abc') is None
        assert Plant.from_barcode('garbage') is None
        assert Plant.from_barcode('') is None
        assert Plant.from_barcode(None) is None


class TestLookupBarcode:
    """Tests for ``lookup_barcode``."""

    def test_resolves_plant(self, plant):
        assert lookup_barcode('P=1') == plant

    def test_resolves_packet(self, packet):
        assert lookup_barcode('P=101') == packet

    def test_resolves_planting(self, planting):
        assert lookup_barcode('P=1001') == planting

    def test_resolves_container(self, container):
        assert lookup_barcode('PC=1') == container

    def test_strips_whitespace(self, plant):
        assert lookup_barcode('  P=1  ') == plant

    def test_raises_for_empty(self, db):
        with pytest.raises(BarcodeNotFound):
            lookup_barcode('')

    def test_raises_for_unknown(self, db):
        with pytest.raises(BarcodeNotFound):
            lookup_barcode('P=999')

    def test_raises_for_malformed(self, db):
        with pytest.raises(BarcodeNotFound):
            lookup_barcode('garbage')


class TestScanPage:
    """Tests for the full scan page."""

    def test_renders_prefocused_input(self, authed_client):
        response = authed_client.get(reverse('scan'))

        assert response.status_code == 200
        assertContains(response, 'name="barcode"')
        assertContains(response, 'autofocus')

    def test_posts_to_scan_hxpost(self, authed_client):
        response = authed_client.get(reverse('scan'))

        assertContains(response, reverse('scan_hxpost'))


class TestScanHxpost:
    """Tests for the htmx scan handler."""

    def test_shows_plant_info(self, authed_client, plant):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=1'},
            HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 200
        assertContains(response, 'Dwarf bean')
        assertContains(response, 'P=001')

    def test_shows_packet_info(self, authed_client, packet):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=101'},
            HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 200
        assertContains(response, 'Dwarf bean')
        assertContains(response, 'Mr Fothergill&#x27;s')

    def test_shows_planting_info(self, authed_client, planting):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=1001'},
            HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 200
        assertContains(response, 'Planted')
        assertContains(response, friendly_date(planting.events.first().date))

    def test_shows_container_info(self, authed_client, container):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'PC=1'},
            HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 200
        assertContains(response, 'Blue ribbon 1')

    def test_unknown_barcode_shows_error(self, authed_client, db):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=999'},
            HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 200
        assertContains(response, 'No object found')

    def test_malformed_barcode_shows_error(self, authed_client, db):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'garbage'},
            HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 200
        assertContains(response, 'No object found')

    def test_redisplay_input_after_scan(self, authed_client, plant):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=1'},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, 'name="barcode"')
        assertContains(response, 'autofocus')

    def test_redisplay_input_after_error(self, authed_client, db):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=999'},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, 'name="barcode"')
        assertContains(response, 'autofocus')

    def test_is_fragment_only(self, authed_client, plant):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=1'},
            HTTP_HX_REQUEST='true',
        )

        content = response.content.decode()
        assert '<!DOCTYPE html>' not in content
        assert '<html' not in content
        assert '<body' not in content

    def test_get_not_allowed(self, authed_client):
        response = authed_client.get(reverse('scan_hxpost'))

        assert response.status_code == 405

    def test_does_not_modify_data(self, authed_client, plant):
        authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=1'},
            HTTP_HX_REQUEST='true',
        )

        plant.refresh_from_db()
        assert Plant.objects.count() == 1


class TestMarkScanned:
    """Tests that scanning records the scan time on the object."""

    def test_mark_scanned_sets_timestamp(self, plant):
        assert plant.last_scanned_at is None

        plant.mark_scanned()

        plant.refresh_from_db()
        assert plant.last_scanned_at is not None

    def test_scan_and_mark_updates_timestamp(self, plant):
        assert plant.last_scanned_at is None

        scan_and_mark('P=1')

        plant.refresh_from_db()
        assert plant.last_scanned_at is not None

    def test_scan_hxpost_updates_timestamp(self, authed_client, plant):
        assert plant.last_scanned_at is None

        authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': 'P=1'},
            HTTP_HX_REQUEST='true',
        )

        plant.refresh_from_db()
        assert plant.last_scanned_at is not None

    def test_scan_page_updates_timestamp(self, authed_client, plant):
        assert plant.last_scanned_at is None

        authed_client.get(reverse('scan'), {'barcode': 'P=1'})

        plant.refresh_from_db()
        assert plant.last_scanned_at is not None


class TestContainerContentsOrdering:
    """A container's planting events are grouped by planting, then ordered by date."""

    @staticmethod
    def _events(container):
        return [item for item in container.contents if item.verbose_name == 'planting event']

    def test_events_grouped_by_planting_then_date(self, container, packet):
        first = Planting.objects.create(id=1001, packet=packet)
        second = Planting.objects.create(id=1002, packet=packet)
        # The dates interleave across plantings, so ordering by planting first
        # (and date within) gives a different result to ordering by date alone.
        e1 = PlantingEvent.objects.create(
            planting=first, event_type='planted', date='2026-02-01', planted_in=container
        )
        e2 = PlantingEvent.objects.create(
            planting=second, event_type='planted', date='2026-01-15', planted_in=container
        )
        e3 = PlantingEvent.objects.create(
            planting=first, event_type='germinated', date='2026-03-01', planted_in=container
        )

        assert self._events(container) == [e1, e3, e2]


class TestContainerContentsRows:
    """One row per planting, listing all of that planting's events."""

    def test_planting_row_lists_all_events(self, authed_client, container, planting):
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.PLANTED,
            date='2026-01-01',
            planted_in=container,
        )
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.GERMINATED,
            date='2026-01-10',
            planted_in=container,
        )

        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': container.barcode},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, 'Planted')
        assertContains(response, 'Germinated')
        # Both events share the planting's single row, so its barcode appears once.
        assert response.content.decode().count(planting.barcode) == 1
