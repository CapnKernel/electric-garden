import pytest


@pytest.fixture
def authed_client(client, django_user_model, db):
    """Return an authenticated client."""
    django_user_model.objects.create_user(email='test@example.com', password='secret123')
    client.login(email='test@example.com', password='secret123')
    return client
