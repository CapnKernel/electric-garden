import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects


# The wizard URLs are currently commented out in ``app/urls.py``, so these
# tests are skipped until the endpoints are re-enabled.
pytestmark = pytest.mark.skip(reason='Wizard endpoints are disabled in app/urls.py')


class TestWizardPage:
    def test_wizard_page_renders_shell(self, authed_client):
        """GET to the wizard page renders the shell and loads the first step."""
        item = Item.objects.create(name='Widget')

        response = authed_client.get(reverse('app:wizard_page', kwargs={'pk': item.pk}))

        assertContains(response, 'Relabel: Widget')
        assertContains(response, reverse('app:wizard_name_hx', kwargs={'pk': item.pk}))

    def test_first_step_shows_current_name(self, authed_client):
        """Step 1 pre-fills the item's current name."""
        item = Item.objects.create(name='Widget')

        response = authed_client.get(reverse('app:wizard_name_hx', kwargs={'pk': item.pk}))

        assertContains(response, 'Step 1 of 3')
        assertContains(response, 'value="Widget"')


class TestWizardNavigation:
    def test_name_step_advances_to_description(self, authed_client):
        """Submitting step 1 returns the step 2 fragment with state carried forward."""
        item = Item.objects.create(name='Widget')

        response = authed_client.post(
            reverse('app:wizard_name_hxpost', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': ''},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, 'Step 2 of 3')
        # The name is carried forward in a hidden field.
        assertContains(response, 'name="name"')
        assertContains(response, 'value="Renamed Widget"')

    def test_name_step_requires_name(self, authed_client):
        """Submitting step 1 with a blank name re-renders step 1 with an error."""
        item = Item.objects.create(name='Widget')

        response = authed_client.post(
            reverse('app:wizard_name_hxpost', kwargs={'pk': item.pk}),
            {'name': '', 'description': ''},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, 'Step 1 of 3')
        assertContains(response, 'Name is required.')

    def test_description_step_advances_to_confirm(self, authed_client):
        """Submitting step 2 returns the step 3 review fragment."""
        item = Item.objects.create(name='Widget')

        response = authed_client.post(
            reverse('app:wizard_description_hxpost', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': 'A shiny widget'},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, 'Step 3 of 3')
        assertContains(response, 'Renamed Widget')
        assertContains(response, 'A shiny widget')

    def test_back_button_preserves_state(self, authed_client):
        """The back button re-fetches the previous step with state passed via GET."""
        item = Item.objects.create(name='Widget')

        response = authed_client.get(
            reverse('app:wizard_name_hx', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': 'A shiny widget'},
            HTTP_HX_REQUEST='true',
        )

        assertContains(response, 'Step 1 of 3')
        assertContains(response, 'value="Renamed Widget"')
        # The description is carried forward in a hidden field.
        assertContains(response, 'value="A shiny widget"')

    def test_back_then_next_preserves_edited_value(self, authed_client):
        """Editing step 2, going back, then forward again keeps the edited value.

        The back button uses hx-include to send the live form values, so the
        description typed on step 2 survives a round-trip through step 1.
        """
        item = Item.objects.create(name='Widget')

        # Step 1: submit a new name, advancing to step 2.
        response = authed_client.post(
            reverse('app:wizard_name_hxpost', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': ''},
            HTTP_HX_REQUEST='true',
        )
        assertContains(response, 'Step 2 of 3')

        # Step 2: go back to step 1, including the live (edited) description.
        response = authed_client.get(
            reverse('app:wizard_name_hx', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': 'Edited on step 2'},
            HTTP_HX_REQUEST='true',
        )
        assertContains(response, 'Step 1 of 3')
        assertContains(response, 'value="Edited on step 2"')

        # Step 1: press Next again, carrying the description forward.
        response = authed_client.post(
            reverse('app:wizard_name_hxpost', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': 'Edited on step 2'},
            HTTP_HX_REQUEST='true',
        )
        assertContains(response, 'Step 2 of 3')
        assertContains(response, 'Edited on step 2')


class TestWizardApply:
    def test_confirm_applies_changes(self, authed_client):
        """Submitting step 3 updates the item and logs history."""
        item = Item.objects.create(name='Widget', description='Old description')

        response = authed_client.post(
            reverse('app:wizard_confirm_hxpost', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': 'A shiny widget'},
            HTTP_HX_REQUEST='true',
        )

        # For htmx requests the redirect is a client-side HX-Redirect header.
        assert response.status_code == 200
        assert response.headers['HX-Redirect'] == reverse('app:item_detail', kwargs={'pk': item.pk})

        item.refresh_from_db()
        assert item.name == 'Renamed Widget'
        assert item.description == 'A shiny widget'

        history = ItemHistory.objects.filter(item=item, action='UPDATE')
        assert history.count() == 1
        assert history.first().metadata['name'] == 'Renamed Widget'

    def test_confirm_redirects_plain_request(self, authed_client):
        """A non-htmx submission gets a normal HTTP redirect."""
        item = Item.objects.create(name='Widget')

        response = authed_client.post(
            reverse('app:wizard_confirm_hxpost', kwargs={'pk': item.pk}),
            {'name': 'Renamed Widget', 'description': ''},
        )

        assertRedirects(response, reverse('app:item_detail', kwargs={'pk': item.pk}))
