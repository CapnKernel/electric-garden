"""Tests for the new planting page."""

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains

from app.models import Container, Packet, Plant, Planting, PlantingEvent


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='豆D', name='Dwarf bean')


@pytest.fixture
def packet(db, plant):
    return Packet.objects.create(id=101, plant=plant, brand="Mr Fothergill's")


@pytest.fixture
def container(db):
    return Container.objects.create(id=1, name='Blue ribbon 1')


@pytest.fixture
def last_location(db, packet, container):
    """An earlier planting whose event supplies the default container and location."""
    planting = Planting.objects.create(packet=packet)
    PlantingEvent.objects.create(
        planting=planting,
        event_type=PlantingEvent.EventType.PLANTED,
        date='2026-02-01',
        planted_in=container,
        location='Front garden parsley box',
    )
    return 'Front garden parsley box'


class TestPlantingCreatePage:
    """GET renders a form for a planting and its initial planted event."""

    def test_renders_form_fields(self, authed_client, db):
        response = authed_client.get(reverse('app:planting_create'))

        assert response.status_code == 200
        form = response.context['form']
        assert list(form.fields) == ['packet', 'date', 'planted_in', 'location', 'notes']

    def test_packet_select_is_enabled_without_a_get_arg(self, authed_client, packet):
        response = authed_client.get(reverse('app:planting_create'))

        assert response.context['form'].fields['packet'].disabled is False
        assertContains(response, packet.barcode)

    def test_packet_select_excludes_deleted_packets(self, authed_client, plant, packet):
        deleted = Packet.objects.create(id=102, plant=plant, deleted=True)

        response = authed_client.get(reverse('app:planting_create'))

        queryset = response.context['form'].fields['packet'].queryset
        assert list(queryset) == [packet]
        assert deleted not in queryset

    def test_packet_get_arg_disables_select(self, authed_client, packet):
        response = authed_client.get(reverse('app:planting_create'), {'packet': packet.pk})

        field = response.context['form'].fields['packet']
        assert field.disabled is True
        assert field.initial == packet.pk
        assertContains(response, f'<option value="{packet.pk}" selected>')

    def test_unknown_packet_get_arg_returns_404(self, authed_client, db):
        response = authed_client.get(reverse('app:planting_create'), {'packet': 999})

        assert response.status_code == 404

    def test_date_starts_empty(self, authed_client, db):
        response = authed_client.get(reverse('app:planting_create'))

        form = response.context['form']
        assert form.fields['date'].initial is None
        assert form['date'].value() is None
        assertContains(response, '>Today</button>')

    def test_location_starts_empty_with_the_default_named_in_the_label(self, authed_client, last_location):
        response = authed_client.get(reverse('app:planting_create'))

        form = response.context['form']
        assert form['location'].value() is None
        assert form.default_placement.text == last_location
        assertContains(response, f'Location last: {last_location}')
        assertContains(response, '>Copy</button>')

    def test_planted_in_starts_empty_with_the_default_named_in_the_label(
        self, authed_client, container, last_location
    ):
        response = authed_client.get(reverse('app:planting_create'))

        form = response.context['form']
        assert form['planted_in'].value() is None
        assert form.default_placement.container == container
        assertContains(response, f'Planted in last: {container}')
        assertContains(response, '>Copy</button>')

    def test_no_defaults_without_prior_events(self, authed_client, packet):
        response = authed_client.get(reverse('app:planting_create'))

        form = response.context['form']
        assert form.default_placement.is_empty
        assert form['planted_in'].label == 'Planted in'
        assert form['location'].label == 'Location'
        assert '>Copy</button>' not in response.content.decode()


class TestLastPlacement:
    """``PlantingEvent.last_placement`` is the whole placement of the latest event that has one."""

    def test_returns_the_most_recent_placement(self, db, packet):
        planting = Planting.objects.create(packet=packet)
        first = Container.objects.create(name='First pot')
        second = Container.objects.create(name='Second pot')
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

        placement = PlantingEvent.last_placement()

        assert placement.container == second
        assert placement.text == 'New spot'

    def test_returns_an_empty_placement_without_one(self, db, packet):
        planting = Planting.objects.create(packet=packet)
        PlantingEvent.objects.create(
            planting=planting,
            event_type=PlantingEvent.EventType.PLANTED,
            date='2026-01-01',
        )

        assert PlantingEvent.last_placement().is_empty


class TestPlantingCreatePost:
    """POST creates a planting plus one planted event and redirects to it."""

    @staticmethod
    def _data(packet, container, **overrides):
        data = {
            'packet': packet.pk,
            'date': '2026-03-01',
            'planted_in': container.pk,
            'location': 'Front garden',
            'notes': 'From seed',
        }
        data.update(overrides)
        return data

    def test_creates_planting_and_planted_event(self, authed_client, packet, container):
        response = authed_client.post(
            reverse('app:planting_create'),
            self._data(packet, container),
        )

        planting = Planting.objects.get()
        assert response.status_code == 302
        assert response['Location'] == planting.detail_url
        assert planting.packet == packet

        event = planting.events.get()
        assert event.event_type == PlantingEvent.EventType.PLANTED
        assert str(event.date) == '2026-03-01'
        assert event.planted_in == container
        assert event.location == 'Front garden'
        assert event.notes == 'From seed'

    def test_packet_get_arg_overrides_posted_packet(self, authed_client, plant, packet):
        other = Packet.objects.create(id=102, plant=plant)
        url = f'{reverse("app:planting_create")}?packet={packet.pk}'

        authed_client.post(
            url,
            {
                'packet': other.pk,
                'date': '2026-03-01',
            },
        )

        assert Planting.objects.get().packet == packet

    def test_packet_get_arg_is_used_when_packet_is_not_posted(self, authed_client, packet):
        url = f'{reverse("app:planting_create")}?packet={packet.pk}'

        authed_client.post(url, {'date': '2026-03-01'})

        assert Planting.objects.get().packet == packet

    def test_unchanged_location_is_confirmed_before_saving(self, authed_client, packet, container, last_location):
        response = authed_client.post(
            reverse('app:planting_create'),
            self._data(packet, container, location=last_location),
        )

        assert response.status_code == 200
        assert response.context['confirm_defaults'] == {
            'Planted in': str(container),
            'Location': last_location,
        }
        assert Planting.objects.count() == 1
        assert PlantingEvent.objects.count() == 1
        assertContains(response, 'Save anyway')

    def test_confirmed_location_is_saved(self, authed_client, packet, container, last_location):
        response = authed_client.post(
            reverse('app:planting_create'),
            self._data(packet, container, location=last_location, confirm_defaults='1'),
        )

        assert response.status_code == 302
        assert PlantingEvent.objects.latest('date').location == last_location

    def test_same_location_in_another_container_saves_without_confirmation(
        self, authed_client, packet, container, last_location
    ):
        other = Container.objects.create(name='Other pot')

        response = authed_client.post(
            reverse('app:planting_create'),
            self._data(packet, other, location=last_location),
        )

        assert response.status_code == 302

    def test_different_location_saves_without_confirmation(self, authed_client, packet, container, last_location):
        response = authed_client.post(
            reverse('app:planting_create'),
            self._data(packet, container, location='Somewhere else'),
        )

        assert response.status_code == 302

    def test_invalid_date_rerenders_the_form(self, authed_client, packet, container):
        response = authed_client.post(
            reverse('app:planting_create'),
            self._data(packet, container, date='not-a-date'),
        )

        assert response.status_code == 200
        assert 'form' in response.context
        assert not Planting.objects.exists()

    def test_packet_is_required(self, authed_client, db):
        response = authed_client.post(reverse('app:planting_create'), {'date': '2026-03-01'})

        assert response.status_code == 200
        assert response.context['form'].errors['packet']
        assert not Planting.objects.exists()


class TestPacketDetailLink:
    """The packet detail page links to the new planting page for that packet."""

    def test_links_to_new_planting_with_packet(self, authed_client, packet):
        response = authed_client.get(packet.detail_url)

        assertContains(response, f'href="{reverse("app:planting_create")}?packet={packet.pk}"')
        assertContains(response, 'New planting')
