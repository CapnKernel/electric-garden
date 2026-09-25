from django.urls import reverse
from pytest_django.asserts import assertContains


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
        # Trigger an action which stores a success message
        authed_client.post(reverse('message'), {'message': 'moved from A to B'})

        response = authed_client.get(reverse('app:messages_partial'))

        assert response.status_code == 200
        assertContains(response, 'alert-success')
        assertContains(response, 'moved from')

    def test_shows_success_message(self, authed_client):
        """Messages partial renders success-level messages."""
        # Don't follow redirect — the redirect itself stores the message
        authed_client.post(reverse('message'), {'message': 'moved from A to B'})

        response = authed_client.get(reverse('app:messages_partial'))

        assert response.status_code == 200
        assertContains(response, 'alert-success')
        assertContains(response, 'moved from')

    def test_consumes_messages(self, authed_client):
        """After fetching messages_partial, the storage is cleared."""
        # Trigger an action which stores a success message
        authed_client.post(reverse('message'), {'message': 'moved from A to B'})

        # First fetch consumes the messages
        authed_client.get(reverse('app:messages_partial'))
        # Second fetch should have no messages
        response = authed_client.get(reverse('app:messages_partial'))

        assert b'alert' not in response.content

    def test_is_fragment_only(self, authed_client):
        """The partial response contains only the messages fragment, not a full HTML document."""
        response = authed_client.get(reverse('app:messages_partial'))

        content = response.content.decode()
        assert '<!DOCTYPE html>' not in content
        assert '<html' not in content
        assert '<head>' not in content
        assert '<body>' not in content
        # The partial returns the inner messages content, not the container div
        assert '<div id="messages-container">' not in content


class TestMessagesInBaseTemplate:
    """Tests that the base template correctly renders messages."""

    def test_has_messages_container_with_htmx_attrs(self, authed_client):
        """The base template renders a messages container with htmx attributes."""
        response = authed_client.get(reverse('app:top'))

        content = response.content.decode()
        assert 'id="messages-container"' in content
        assert 'hx-get="' in content
        assert 'messages_partial' in content or '/partials/messages/' in content
        assert 'hx-trigger=' in content
        assert 'messages-updated' in content
        assert 'hx-swap="innerHTML"' in content

    def test_renders_messages_directly(self, authed_client):
        """Messages are rendered directly in the base template (non-JS fallback)."""
        # Trigger an action which stores a success message
        authed_client.post(reverse('message'), {'message': 'moved from A to B'})

        response = authed_client.get(reverse('app:top'))
        assertContains(response, 'alert-success')
        assertContains(response, 'moved from')

    def test_no_duplicate_messages_containers(self, authed_client):
        """Full page render should have exactly one messages-container div."""
        response = authed_client.get(reverse('app:top'))
        content = response.content.decode()

        count = content.count('id="messages-container"')
        assert count == 1, f'Expected 1 messages-container, found {count}'
