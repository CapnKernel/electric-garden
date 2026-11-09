"""Tests for text search and the scan fallback to it."""

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains

from app.models import Container, Packet, Plant, Planting, PlantingEvent
from app.search import search_pattern, text_search


@pytest.fixture
def garden_data(db):
    plant = Plant.objects.create(id=1, code='BR', name='Beetroot')
    carrot = Plant.objects.create(id=2, code='CA', name='Carrot')
    Plant.objects.create(id=3, code='XX', name='Beetroot gone', deleted=True)

    packet = Packet.objects.create(
        id=101, plant=plant, brand="Mr Fothergill's", full_name='Boltardy', notes='Plant in full sun'
    )
    Packet.objects.create(id=102, plant=carrot, full_name='Nantes', notes='Keep moist')
    Packet.objects.create(id=103, plant=plant, full_name='Boltardy gone', deleted=True)

    container = Container.objects.create(id=1, name='Blue ribbon 1')

    planting = Planting.objects.create(id=1001, packet=packet)
    deleted_planting = Planting.objects.create(id=1002, packet=packet, deleted=True)

    PlantingEvent.objects.create(
        planting=planting,
        event_type=PlantingEvent.EventType.PLANTED,
        date='2024-01-01',
        location='Front garden parsley box',
        notes="From Kath's seedling box",
    )
    PlantingEvent.objects.create(
        planting=deleted_planting,
        event_type=PlantingEvent.EventType.PLANTED,
        date='2024-02-01',
        notes="From Kath's deleted box",
    )
    return {
        'plant': plant,
        'packet': packet,
        'container': container,
        'planting': planting,
    }


class TestSearchPattern:
    """Tests for turning a search term into a word-boundary regex."""

    def test_none_for_empty_or_stars(self):
        assert search_pattern('') is None
        assert search_pattern('   ') is None
        assert search_pattern('*') is None

    def test_adds_word_boundaries(self):
        assert search_pattern('bean') == r'\bbean\b'

    def test_leading_star_drops_start_boundary(self):
        assert search_pattern('*berry') == r'berry\b'

    def test_trailing_star_drops_end_boundary(self):
        assert search_pattern('blue*') == r'\bblue'

    def test_both_stars_allow_substring(self):
        assert search_pattern('*err*') == 'err'

    def test_escapes_regex_characters(self):
        assert search_pattern('a.b') == r'\ba\.b\b'

    def test_multi_word_phrase_gets_outer_boundaries(self):
        assert search_pattern('blue ribbon') == r'\bblue\ ribbon\b'


class TestTextSearch:
    """Tests for the grouped results returned by ``text_search``."""

    def test_matches_plant_name(self, garden_data):
        groups = text_search('Beetroot')

        assert [group['title'] for group in groups] == ['Plants']
        item = groups[0]['items'][0]
        assert item['label'] == 'Beetroot'
        assert item['url'] == garden_data['plant'].detail_url

    def test_matches_plant_code(self, garden_data):
        groups = text_search('BR')

        assert groups[0]['title'] == 'Plants'
        assert groups[0]['items'][0]['detail'] == 'BR'

    def test_matches_packet_full_name(self, garden_data):
        groups = text_search('Boltardy')

        assert groups[0]['title'] == 'Packets'
        assert groups[0]['items'][0]['url'] == garden_data['packet'].detail_url

    def test_matches_packet_notes(self, garden_data):
        assert text_search('moist')[0]['title'] == 'Packets'

    def test_matches_container_name(self, garden_data):
        groups = text_search('ribbon')

        assert groups[0]['title'] == 'Containers'
        assert groups[0]['items'][0]['url'] == garden_data['container'].detail_url

    def test_matches_event_location(self, garden_data):
        groups = text_search('parsley')

        assert groups[0]['title'] == 'Planting events'
        assert groups[0]['items'][0]['url'] == garden_data['planting'].detail_url

    def test_matches_event_notes(self, garden_data):
        assert text_search('Kath')[0]['title'] == 'Planting events'

    def test_is_case_insensitive(self, garden_data):
        assert text_search('BEETROOT')[0]['title'] == 'Plants'
        assert text_search('boltardy')[0]['title'] == 'Packets'
        assert text_search('BLUE RIBBON')[0]['title'] == 'Containers'

    def test_matches_whole_words_only(self, garden_data):
        assert text_search('Beet') == []
        assert text_search('oltardy') == []

    def test_trailing_star_allows_prefix_substring(self, garden_data):
        assert text_search('Beet*')[0]['title'] == 'Plants'
        assert text_search('Bolt*')[0]['title'] == 'Packets'

    def test_leading_star_allows_suffix_substring(self, garden_data):
        assert text_search('*oltardy')[0]['title'] == 'Packets'

    def test_matches_multi_word_phrase(self, garden_data):
        assert text_search('blue ribbon')[0]['title'] == 'Containers'

    def test_excludes_deleted_objects(self, garden_data):
        assert text_search('gone') == []

    def test_no_match_returns_empty(self, garden_data):
        assert text_search('zucchini') == []


class TestScanFallback:
    """A scan that matches no barcode falls back to text search."""

    def test_scan_page_renders_search_results(self, authed_client, garden_data):
        response = authed_client.get(reverse('app:scan'), {'q': 'Boltardy'})

        assert response.status_code == 200
        assert response.context['q'] == 'Boltardy'
        assert response.context['error'] is None
        assert [group['title'] for group in response.context['search_results']] == ['Packets']
        assertContains(response, 'Packets')

    def test_scan_hxpost_renders_search_results(self, authed_client, garden_data):
        response = authed_client.post(reverse('app:scan_hxpost'), {'q': 'Kath'}, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        assert 'HX-Redirect' not in response.headers
        assert response.context['error'] is None
        assert [group['title'] for group in response.context['search_results']] == ['Planting events']
        assertContains(response, 'Planting events')

    def test_results_link_to_detail_pages(self, authed_client, garden_data):
        response = authed_client.post(reverse('app:scan_hxpost'), {'q': 'Boltardy'}, HTTP_HX_REQUEST='true')

        assertContains(response, f'href="{garden_data["packet"].detail_url}"')

    def test_no_search_results_keeps_error(self, authed_client, garden_data):
        response = authed_client.get(reverse('app:scan'), {'q': 'zucchini'})

        assert response.context['search_results'] == []
        assert response.context['error'] == 'No object found for barcode zucchini'

    def test_matching_barcode_still_redirects(self, authed_client, garden_data):
        response = authed_client.get(reverse('app:scan'), {'q': 'P=1'})

        assert response.status_code == 302
        assert response['Location'] == garden_data['plant'].detail_url
