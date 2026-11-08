from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

MESSAGE = 'moved from A to B'


def _add_message(client):
    """Store a success message, as any view reporting a completed action does."""
    client.post(reverse('message'), {'message': MESSAGE})


class TestMessagesPartialEndpoint:
    """Tests for the messages_partial HTMX endpoint."""

    def test_returns_empty_when_no_messages(self, authed_client):
        """GET to messages_partial with no messages returns empty fragment."""
        response = authed_client.get(reverse('app:messages_partial'))

        assert response.status_code == 200
        # The partial returns only the inner messages content (no container wrapper)
        content = response.content.decode().strip()
        assert content == ''

    def test_renders_messages(self, authed_client):
        """GET to messages_partial with messages in storage renders them."""
        _add_message(authed_client)

        response = authed_client.get(reverse('app:messages_partial'))

        assert response.status_code == 200
        assertContains(response, 'alert-success')
        assertContains(response, MESSAGE)

    def test_consumes_messages(self, authed_client):
        """After fetching messages_partial, the storage is cleared."""
        _add_message(authed_client)

        # First fetch consumes the messages
        first = authed_client.get(reverse('app:messages_partial'))
        # Second fetch should have no messages
        second = authed_client.get(reverse('app:messages_partial'))

        assertContains(first, MESSAGE)
        assertNotContains(second, 'alert')

    def test_is_fragment_only(self, authed_client):
        """The partial response contains only the messages fragment, not a full HTML document."""
        response = authed_client.get(reverse('app:messages_partial'))

        assertNotContains(response, '<!DOCTYPE html>')
        assertNotContains(response, '<html')
        assertNotContains(response, '<head>')
        assertNotContains(response, '<body>')
        # The partial returns the inner messages content, not the container div
        assertNotContains(response, '<div id="messages-container">')


class TestMessagesInBaseTemplate:
    """Tests that the base template correctly renders messages."""

    def test_has_messages_container_with_htmx_attrs(self, authed_client):
        """The base template renders a messages container with htmx attributes."""
        response = authed_client.get(reverse('app:top'))

        assertContains(response, 'id="messages-container"')
        assertContains(response, f'hx-get="{reverse("app:messages_partial")}"')
        assertContains(response, 'hx-trigger="messages-updated from:body"')
        assertContains(response, 'hx-swap="innerHTML"')

    def test_renders_messages_directly(self, authed_client):
        """Messages are rendered directly in the base template (non-JS fallback)."""
        _add_message(authed_client)

        response = authed_client.get(reverse('app:top'))

        assertContains(response, 'alert-success')
        assertContains(response, MESSAGE)

    def test_no_duplicate_messages_containers(self, authed_client):
        """Full page render should have exactly one messages-container div."""
        response = authed_client.get(reverse('app:top'))

        count = response.content.decode().count('id="messages-container"')
        assert count == 1, f'Expected 1 messages-container, found {count}'
