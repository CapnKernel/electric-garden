"""Tests for the barcode scanning views and lookup logic."""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.formats import date_format
from pytest_django.asserts import assertContains, assertNotContains

from app.models import Container, Packet, Plant, Planting, PlantingEvent
from app.scan import BarcodeNotFound, lookup_barcode, scan_and_mark


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


class TestScanAction:
    """Scanning is an action: it marks the object and navigates to its page."""

    @staticmethod
    def _scan(client, q):
        return client.post(reverse('app:scan'), {'q': q}, HTTP_HX_REQUEST='true')

    def test_get_renders_prefocused_input(self, authed_client):
        response = authed_client.get(reverse('app:scan'))

        assert response.status_code == 200
        assertContains(response, 'name="q"')
        assertContains(response, 'autofocus')

    def test_navbar_input_posts_to_the_scan_action(self, authed_client):
        response = authed_client.get(reverse('app:scan'))

        assertContains(response, f'hx-post="{reverse("app:scan")}"')

    def test_breadcrumb_is_scan(self, authed_client):
        response = authed_client.get(reverse('app:scan'))

        assertContains(response, '<li class="breadcrumb-item active" aria-current="page">Scan</li>', html=True)

    def test_barcode_query_redirects_to_detail_page(self, authed_client, plant):
        response = authed_client.get(reverse('app:scan'), {'q': plant.barcode})

        assert response.status_code == 302
        assert response['Location'] == reverse('app:plant_detail', kwargs={'pk': plant.pk})

    def test_unknown_barcode_query_redirects_to_search(self, authed_client, db):
        response = authed_client.get(reverse('app:scan'), {'q': 'P=999'})

        assert response.status_code == 302
        assert response['Location'] == f'{reverse("app:search")}?q=P%3D999'

    def test_htmx_scan_redirects_to_plant_detail(self, authed_client, plant):
        response = self._scan(authed_client, 'P=1')

        assert response.headers['HX-Redirect'] == reverse('app:plant_detail', kwargs={'pk': plant.pk})

    def test_htmx_scan_redirects_to_packet_detail(self, authed_client, packet):
        response = self._scan(authed_client, 'P=101')

        assert response.headers['HX-Redirect'] == reverse('app:packet_detail', kwargs={'pk': packet.pk})

    def test_htmx_scan_redirects_to_planting_detail(self, authed_client, planting):
        response = self._scan(authed_client, 'P=1001')

        assert response.headers['HX-Redirect'] == reverse('app:planting_detail', kwargs={'pk': planting.pk})

    def test_htmx_scan_redirects_to_container_detail(self, authed_client, container):
        response = self._scan(authed_client, 'PC=1')

        assert response.headers['HX-Redirect'] == reverse('app:container_detail', kwargs={'pk': container.pk})

    def test_htmx_unknown_barcode_goes_to_search(self, authed_client, db):
        response = self._scan(authed_client, 'P=999')

        assert response.headers['HX-Redirect'] == f'{reverse("app:search")}?q=P%3D999'

    def test_does_not_create_objects(self, authed_client, plant):
        self._scan(authed_client, 'P=1')

        assert Plant.objects.count() == 1


class TestSearchPage:
    """Search is a view, so an unmatched scan term gets its own readable URL."""

    def test_shows_matching_groups(self, authed_client, plant):
        response = authed_client.get(reverse('app:search'), {'q': 'Dwarf'})

        assert [group['title'] for group in response.context['search_results']] == ['Plants']
        assertContains(response, 'Plants')

    def test_no_match_shows_an_alert(self, authed_client, db):
        response = authed_client.get(reverse('app:search'), {'q': 'zucchini'})

        assert response.context['error'] == 'No match for zucchini.'
        assertContains(response, 'No match for zucchini.')

    def test_no_term_prompts_for_one(self, authed_client, db):
        response = authed_client.get(reverse('app:search'))

        assertContains(response, 'type a search term')


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

    def test_scan_action_updates_timestamp(self, authed_client, plant):
        assert plant.last_scanned_at is None

        authed_client.post(
            reverse('app:scan'),
            {'q': 'P=1'},
            HTTP_HX_REQUEST='true',
        )

        plant.refresh_from_db()
        assert plant.last_scanned_at is not None

    def test_scan_page_updates_timestamp(self, authed_client, plant):
        assert plant.last_scanned_at is None

        authed_client.get(reverse('app:scan'), {'q': 'P=1'})

        plant.refresh_from_db()
        assert plant.last_scanned_at is not None


class TestContainerContentsOrdering:
    """A container's planting events are grouped by planting, then ordered by date."""

    @staticmethod
    def _events(container):
        return list(container.planting_events)

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
        # A germinated event carries no location details, so it inherits none of
        # the interleaved dates above; it still sorts last for its planting.
        e3 = PlantingEvent.objects.create(planting=first, event_type='germinated', date='2026-03-01')

        assert self._events(container) == [e1, e3, e2]


class TestContainerContentsRows:
    """One row per planting, listing all of that planting's events."""

    def test_planting_row_lists_all_events(self, authed_client, container, planting):
        # The ``planting`` fixture already recorded the (single) planted event;
        # give it the container so the planting is located there.
        planting.events.filter(event_type=PlantingEvent.EventType.PLANTED).update(planted_in=container)
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.GERMINATED,
            date='2026-01-10',
        )

        response = authed_client.get(container.detail_url)

        assertContains(response, 'Planted')
        assertContains(response, 'Germinated')
        # Both events share the planting's single row, so its barcode appears once.
        assert response.content.decode().count(planting.barcode) == 1


class TestContainerContentsTransplant:
    """A transplanted planting is shown in the container it was transplanted to."""

    @staticmethod
    def _events(container):
        return list(container.planting_events)

    def test_shown_in_latest_container_with_all_events(self, container, packet):
        destination = Container.objects.create(id=2, name='Destination')
        planting = Planting.objects.create(id=1001, packet=packet)
        planted = PlantingEvent.objects.create(
            planting=planting, event_type='planted', date='2026-01-01', planted_in=container
        )
        germinated = PlantingEvent.objects.create(planting=planting, event_type='germinated', date='2026-01-05')
        transplanted = PlantingEvent.objects.create(
            planting=planting, event_type='transplanted', date='2026-02-01', planted_in=destination
        )

        # Not in the container it was transplanted out of...
        assert self._events(container) == []
        # ...but in the destination, with its full history.
        assert self._events(destination) == [planted, germinated, transplanted]

    def test_transplant_to_free_text_location_leaves_container(self, container, packet):
        """``planted_in`` and ``location`` are one location, so a free-text
        transplant moves the planting out of its former container."""
        planting = Planting.objects.create(id=1001, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type='planted', date='2026-01-01', planted_in=container)
        PlantingEvent.objects.create(
            planting=planting, event_type='transplanted', date='2026-02-01', location='B4 4.9-5.45'
        )

        assert not container.plantings.exists()
        assert self._events(container) == []
        assert planting.placement.text == 'B4 4.9-5.45'


class TestContainerDetailQueries:
    """Rendering a container does not query once per contained row."""

    @staticmethod
    def _query_count(client, container):
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(container.detail_url)
        assert response.status_code == 200
        return len(ctx.captured_queries)

    def test_query_count_does_not_grow_with_plantings(self, authed_client, container, packet):
        first = Planting.objects.create(id=1001, packet=packet)
        PlantingEvent.objects.create(
            planting=first,
            event_type=PlantingEvent.EventType.PLANTED,
            date='2026-01-01',
            planted_in=container,
        )
        one_planting_qc = self._query_count(authed_client, container)

        for pk in (1002, 1003, 1004):
            planting = Planting.objects.create(id=pk, packet=packet)
            PlantingEvent.objects.create(
                planting=planting,
                event_type=PlantingEvent.EventType.PLANTED,
                date='2026-01-01',
                planted_in=container,
            )
        four_plantings_qc = self._query_count(authed_client, container)

        assert four_plantings_qc == one_planting_qc


class TestContainerDisplayExcludesMovedItems:
    """Rendered container view omits items that have since moved elsewhere."""

    def test_moved_planting_and_packet_not_shown_in_former_container(self, authed_client, container, packet):
        destination = Container.objects.create(id=2, name='Destination')
        planting = Planting.objects.create(id=1002, packet=packet)
        PlantingEvent.objects.create(planting=planting, event_type='planted', date='2026-01-01', planted_in=container)
        PlantingEvent.objects.create(
            planting=planting, event_type='transplanted', date='2026-02-01', planted_in=destination
        )
        # The packet itself has been moved to the destination container.
        packet.container = destination
        packet.save(update_fields=['container'])

        former = authed_client.get(container.detail_url)

        assertNotContains(former, planting.barcode)
        assertNotContains(former, packet.barcode)
        assertContains(former, 'This container is empty.')

        moved_to = authed_client.get(destination.detail_url)

        assertContains(moved_to, planting.barcode)
        assertContains(moved_to, packet.barcode)


class TestGetAbsoluteUrl:
    """The canonical model URL is the object's detail page."""

    def test_plant_detail(self, plant):
        assert plant.get_absolute_url() == reverse('app:plant_detail', kwargs={'pk': plant.pk})

    def test_packet_detail(self, packet):
        assert packet.get_absolute_url() == reverse('app:packet_detail', kwargs={'pk': packet.pk})

    def test_planting_detail(self, planting):
        assert planting.get_absolute_url() == reverse('app:planting_detail', kwargs={'pk': planting.pk})

    def test_container_detail(self, container):
        assert container.get_absolute_url() == reverse('app:container_detail', kwargs={'pk': container.pk})

    def test_detail_url_differs_from_scan_url(self, plant):
        assert plant.detail_url != plant.scan_redirect_url

    def test_admin_url_points_to_admin_change_page(self, plant):
        assert plant.admin_url == reverse('admin:app_plant_change', args=[plant.pk])


class TestDetailViews:
    """Each scannable object has a detail page reachable by primary key."""

    def test_plant_detail(self, authed_client, plant):
        response = authed_client.get(reverse('app:plant_detail', kwargs={'pk': plant.pk}))

        assert response.status_code == 200
        assertContains(response, 'Dwarf bean')
        assertContains(response, plant.barcode)

    def test_breadcrumbs_name_the_object(self, authed_client, container):
        response = authed_client.get(container.detail_url)

        assertContains(response, '<li class="breadcrumb-item">Container</li>', html=True)
        assertContains(response, f'{container.barcode} Blue ribbon 1')

    def test_packet_breadcrumb_shows_full_name(self, authed_client, packet):
        packet.full_name = 'Marketmore'
        packet.save(update_fields=['full_name'])

        response = authed_client.get(packet.detail_url)

        assertContains(response, '<li class="breadcrumb-item">Packet</li>', html=True)
        assertContains(response, 'P=101 Dwarf bean (Marketmore)')

    def test_planting_detail_shows_packet_full_name(self, authed_client, packet, planting):
        packet.full_name = 'Marketmore'
        packet.save(update_fields=['full_name'])

        response = authed_client.get(planting.detail_url)

        assertContains(response, 'P=101 Dwarf bean (Marketmore)')

    def test_packet_detail(self, authed_client, packet):
        response = authed_client.get(reverse('app:packet_detail', kwargs={'pk': packet.pk}))

        assert response.status_code == 200
        assertContains(response, 'Mr Fothergill&#x27;s')

    def test_planting_detail(self, authed_client, planting):
        response = authed_client.get(reverse('app:planting_detail', kwargs={'pk': planting.pk}))

        assert response.status_code == 200
        assertContains(response, planting.barcode)

    def test_container_detail(self, authed_client, container):
        response = authed_client.get(reverse('app:container_detail', kwargs={'pk': container.pk}))

        assert response.status_code == 200
        assertContains(response, 'Blue ribbon 1')

    def test_is_full_page(self, authed_client, plant):
        response = authed_client.get(reverse('app:plant_detail', kwargs={'pk': plant.pk}))

        assertContains(response, '<!DOCTYPE html>')

    @pytest.mark.parametrize(
        'url_name,admin_url_name',
        [
            ('app:plant_detail', 'admin:app_plant_change'),
            ('app:packet_detail', 'admin:app_packet_change'),
            ('app:planting_detail', 'admin:app_planting_change'),
            ('app:container_detail', 'admin:app_container_change'),
        ],
    )
    def test_admin_link_targets_the_object(
        self, authed_client, plant, packet, planting, container, url_name, admin_url_name
    ):
        obj = {
            'app:plant_detail': plant,
            'app:packet_detail': packet,
            'app:planting_detail': planting,
            'app:container_detail': container,
        }[url_name]

        response = authed_client.get(reverse(url_name, kwargs={'pk': obj.pk}))

        assertContains(response, f'href="{reverse(admin_url_name, args=[obj.pk])}"')

    def test_admin_link_defaults_to_admin_index_without_object(self, authed_client):
        response = authed_client.get(reverse('app:scan'))

        assertContains(response, f'href="{reverse("admin:index")}"')

    @pytest.mark.parametrize(
        'url_name,model',
        [
            ('app:plant_detail', Plant),
            ('app:packet_detail', Packet),
            ('app:planting_detail', Planting),
            ('app:container_detail', Container),
        ],
    )
    def test_unknown_pk_returns_404(self, authed_client, db, url_name, model):
        response = authed_client.get(reverse(url_name, kwargs={'pk': 999}))

        assert response.status_code == 404

    @pytest.mark.parametrize(
        'url_name',
        ['app:plant_detail', 'app:packet_detail', 'app:planting_detail', 'app:container_detail'],
    )
    def test_does_not_mark_scanned(self, authed_client, plant, packet, planting, container, url_name):
        obj = {
            'app:plant_detail': plant,
            'app:packet_detail': packet,
            'app:planting_detail': planting,
            'app:container_detail': container,
        }[url_name]

        authed_client.get(reverse(url_name, kwargs={'pk': obj.pk}))

        obj.refresh_from_db()
        assert obj.last_scanned_at is None


class TestPacketPlantingsPlantedColumn:
    """The packet's plantings table shows when each planting was planted."""

    def test_shows_planted_date(self, authed_client, packet):
        planting = Planting.objects.create(id=1001, packet=packet)
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.PLANTED,
            date='2026-02-01',
        )
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.GERMINATED,
            date='2026-02-05',
        )

        response = authed_client.get(packet.detail_url)

        assertContains(response, date_format(date(2026, 2, 1)))
        assertNotContains(response, date_format(date(2026, 2, 5)))


class TestPlantPackets:
    """The plant detail page lists the plant's packets and their planting counts."""

    def test_lists_packets_with_planting_counts(self, authed_client, plant, packet):
        other_packet = Packet.objects.create(id=102, plant=plant, full_name='Marketmore')
        Planting.objects.create(id=1001, packet=packet)
        Planting.objects.create(id=1002, packet=packet)
        Planting.objects.create(id=1003, packet=other_packet)

        response = authed_client.get(plant.detail_url)

        assertContains(response, 'Packets')
        assertContains(response, packet.barcode)
        assertContains(response, other_packet.barcode)
        assertContains(response, '<td>2</td>', html=True)
        assertContains(response, '<td>1</td>', html=True)

    def test_excludes_deleted_packets(self, authed_client, plant):
        deleted_packet = Packet.objects.create(id=103, plant=plant, deleted=True)

        response = authed_client.get(plant.detail_url)

        assertNotContains(response, deleted_packet.barcode)
