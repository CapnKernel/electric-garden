from urllib.parse import urlencode

import pytest
from django.conf import settings
from django.test import override_settings
from django.urls import reverse
from pytest_django.asserts import assertRedirects


class TestLoginRequiredExemptMiddleware:
    def test_exempt_view_allows_anonymous(self, client, db):
        """An exempt view (login) is accessible without authentication."""
        response = client.get(reverse('login'))
        assert response.status_code == 200

    def test_exempt_password_reset_allows_anonymous(self, client, db):
        """An exempt view (password_reset) is accessible without authentication."""
        response = client.get(reverse('password_reset'))
        assert response.status_code == 200

    def test_non_exempt_view_redirects_anonymous(self, client, db):
        """A non-exempt view redirects unauthenticated users to admin's LOGIN_URL."""
        admin_index = reverse('admin:index')
        response = client.get(admin_index)
        assertRedirects(
            response,
            f'{reverse("admin:login")}?{urlencode({"next": reverse("admin:index")})}',
        )

    def test_authenticated_user_can_access_any_view(self, client, db, django_user_model):
        """An authenticated user can access any view, exempt or not."""
        django_user_model.objects.create_user(email='test@example.com', password='secret', is_staff=True)
        client.login(email='test@example.com', password='secret')
        response = client.get(reverse('admin:index'))
        assert response.status_code == 200

    def test_authenticated_user_exempt_view(self, client, db, django_user_model):
        """An authenticated user can also access exempt views."""
        django_user_model.objects.create_user(email='test@example.com', password='secret')
        client.login(email='test@example.com', password='secret')
        response = client.get(reverse('login'))
        assert response.status_code == 200

    @override_settings(AUTH_EXEMPT_VIEW_NAMES=())
    def test_empty_exempt_list_still_allows_decorated_views(self, client, db):
        """Views decorated with @login_not_required are exempt regardless of
        AUTH_EXEMPT_VIEW_NAMES — the decorator takes precedence over the middleware."""
        response = client.get(reverse('login'))
        assert response.status_code == 200
