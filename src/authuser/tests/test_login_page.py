from django.urls import reverse
from pytest_django.asserts import assertNotContains


class TestLoginPage:
    def test_has_no_navbar(self, client, db):
        response = client.get(reverse('login'))

        assert response.status_code == 200
        assertNotContains(response, 'id="navbarNav"')

    def test_has_no_scan_input(self, client, db):
        response = client.get(reverse('login'))

        assert response.status_code == 200
        assertNotContains(response, 'name="barcode"')
