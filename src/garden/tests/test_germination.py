"""Tests for the container germination form."""

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from garden.models import Container, Packet, Plant, Planting, PlantingEvent


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='豆D', name='Dwarf bean')


@pytest.fixture
def packet(db, plant):
    return Packet.objects.create(id=101, plant=plant)


@pytest.fixture
def container(db):
    return Container.objects.create(id=1, name='Blue ribbon 1')


@pytest.fixture
def planting(db, packet, container):
    planting = Planting.objects.create(id=1001, packet=packet)
    PlantingEvent.objects.create(
        planting=planting,
        event_type=PlantingEvent.EventType.PLANTED,
        date='2026-01-01',
        planted_in=container,
    )
    return planting


class TestContainerPlantings:
    """Tests for which plantings are considered to be in a container."""

    def test_lists_planting_planted_in_container(self, container, planting):
        from garden.planting import _container_plantings

        assert _container_plantings(container) == [planting]

    def test_excludes_planting_transplanted_elsewhere(self, container, planting):
        from garden.planting import _container_plantings

        other = Container.objects.create(id=2, name='Other')
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.TRANSPLANTED,
            date='2026-02-01',
            planted_in=other,
        )

        assert _container_plantings(container) == []
        assert _container_plantings(other) == [planting]

    def test_excludes_deleted_planting(self, container, planting):
        from garden.planting import _container_plantings

        planting.deleted = True
        planting.save(update_fields=['deleted'])

        assert _container_plantings(container) == []


class TestContainerGerminationView:
    """Tests for the germination form view."""

    def test_get_renders_form(self, authed_client, container, planting):
        response = authed_client.get(reverse('container_germination', args=[container.pk]))

        assert response.status_code == 200
        assertContains(response, 'Germination')
        assertContains(response, planting.barcode)

    def test_get_is_full_page_titled_with_container_name(self, authed_client, container, planting):
        response = authed_client.get(reverse('container_germination', args=[container.pk]))

        content = response.content.decode()
        assert '<!DOCTYPE html>' in content
        assertContains(response, container.name)
        assertNotContains(response, 'Scan barcode')

    def test_post_sets_germination_and_creates_event(self, authed_client, container, planting):
        response = authed_client.post(
            reverse('container_germination', args=[container.pk]),
            {
                f'{planting.pk}-planting_id': planting.pk,
                f'{planting.pk}-germinated': 'on',
                f'{planting.pk}-score': '3',
            },
        )

        assert response.status_code == 302
        planting.refresh_from_db()
        assert planting.germinated == 3
        event = planting.events.get(event_type=PlantingEvent.EventType.GERMINATED)
        assert event.planted_in == container

    def test_post_via_htmx_redirects_to_scan_page(self, authed_client, container, planting):
        response = authed_client.post(
            reverse('container_germination', args=[container.pk]),
            {
                f'{planting.pk}-planting_id': planting.pk,
                f'{planting.pk}-germinated': 'on',
                f'{planting.pk}-score': '3',
            },
            HTTP_HX_REQUEST='true',
        )

        assert response.status_code == 204
        assert response.headers['HX-Redirect'] == f'{reverse("scan")}?barcode={container.barcode}'

    def test_post_clears_germination_and_removes_event(self, authed_client, container, planting):
        planting.germinated = 3
        planting.save(update_fields=['germinated'])
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.GERMINATED,
            date='2026-02-01',
            planted_in=container,
        )

        authed_client.post(
            reverse('container_germination', args=[container.pk]),
            {f'{planting.pk}-planting_id': planting.pk},
        )

        planting.refresh_from_db()
        assert planting.germinated is None
        assert not planting.events.filter(event_type=PlantingEvent.EventType.GERMINATED).exists()

    def test_post_updates_existing_event(self, authed_client, container, planting):
        event = PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.GERMINATED,
            date='2026-02-01',
            planted_in=container,
        )

        authed_client.post(
            reverse('container_germination', args=[container.pk]),
            {
                f'{planting.pk}-planting_id': planting.pk,
                f'{planting.pk}-germinated': 'on',
                f'{planting.pk}-score': '2',
            },
        )

        assert planting.events.filter(event_type=PlantingEvent.EventType.GERMINATED).count() == 1
        event.refresh_from_db()
        assert event.planted_in == container

    def test_post_germinated_without_score_is_invalid(self, authed_client, container, planting):
        response = authed_client.post(
            reverse('container_germination', args=[container.pk]),
            {
                f'{planting.pk}-planting_id': planting.pk,
                f'{planting.pk}-germinated': 'on',
            },
        )

        assert response.status_code == 200
        assertContains(response, 'Choose a germination score')
        planting.refresh_from_db()
        assert planting.germinated is None

    def test_post_score_above_max_is_invalid(self, authed_client, container, planting):
        response = authed_client.post(
            reverse('container_germination', args=[container.pk]),
            {
                f'{planting.pk}-planting_id': planting.pk,
                f'{planting.pk}-germinated': 'on',
                f'{planting.pk}-score': '4',
            },
        )

        assert response.status_code == 200
        planting.refresh_from_db()
        assert planting.germinated is None

    def test_post_does_not_touch_other_containers(self, authed_client, container, planting):
        other = Container.objects.create(id=2, name='Other')
        other_planting = Planting.objects.create(id=1002, packet=planting.packet)
        PlantingEvent.objects.create(
            planting=other_planting,
            event_type=PlantingEvent.EventType.PLANTED,
            date='2026-01-01',
            planted_in=other,
        )

        authed_client.post(
            reverse('container_germination', args=[container.pk]),
            {
                f'{planting.pk}-planting_id': planting.pk,
                f'{planting.pk}-germinated': 'on',
                f'{planting.pk}-score': '2',
            },
        )

        other_planting.refresh_from_db()
        assert other_planting.germinated is None


class TestGerminationButton:
    """Tests that the container scan result offers the germination button."""

    def test_button_shown_when_container_has_plantings(self, authed_client, container, planting):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': container.barcode},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, reverse('container_germination', args=[container.pk]))

    def test_button_not_shown_when_container_empty(self, authed_client, container):
        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': container.barcode},
            HTTP_HX_REQUEST='true',
        )

        assertNotContains(response, reverse('container_germination', args=[container.pk]))

    def test_button_not_shown_when_container_has_no_plantings(self, authed_client, container, packet):
        packet.container = container
        packet.save(update_fields=['container'])

        response = authed_client.post(
            reverse('scan_hxpost'),
            {'barcode': container.barcode},
            HTTP_HX_REQUEST='true',
        )

        assertNotContains(response, reverse('container_germination', args=[container.pk]))


class TestLastScannedUpdated:
    """last_scanned_at is bumped only when a planting or event actually changes."""

    @staticmethod
    def _germination_data(planting, score):
        return {
            f'{planting.pk}-planting_id': planting.pk,
            f'{planting.pk}-germinated': 'on',
            f'{planting.pk}-score': str(score),
        }

    def test_changed_germination_updates_last_scanned(self, authed_client, container, planting):
        Planting.objects.filter(pk=planting.pk).update(last_scanned_at=None)

        authed_client.post(
            reverse('container_germination', args=[container.pk]),
            self._germination_data(planting, 2),
        )

        planting.refresh_from_db()
        assert planting.last_scanned_at is not None

    def test_identical_germination_does_not_update_last_scanned(self, authed_client, container, planting):
        data = self._germination_data(planting, 2)
        authed_client.post(reverse('container_germination', args=[container.pk]), data)
        planting.refresh_from_db()
        before = planting.last_scanned_at

        authed_client.post(reverse('container_germination', args=[container.pk]), data)

        planting.refresh_from_db()
        assert planting.last_scanned_at == before

    def test_creating_event_updates_last_scanned(self, authed_client, planting):
        Planting.objects.filter(pk=planting.pk).update(last_scanned_at=None)

        authed_client.post(
            reverse('planting_event_create', args=[planting.pk]),
            {'event_type': PlantingEvent.EventType.TRANSPLANTED, 'date': '2026-03-01'},
        )

        planting.refresh_from_db()
        assert planting.last_scanned_at is not None

    def test_editing_event_updates_last_scanned(self, authed_client, planting):
        event = PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.TRANSPLANTED,
            date='2026-03-01',
        )
        Planting.objects.filter(pk=planting.pk).update(last_scanned_at=None)

        authed_client.post(
            reverse('planting_event_edit', args=[event.pk]),
            {'event_type': event.event_type, 'date': '2026-03-02', 'location': 'New spot', 'notes': ''},
        )

        planting.refresh_from_db()
        assert planting.last_scanned_at is not None
