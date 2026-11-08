from urllib.parse import urlencode

from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects, assertTemplateUsed

# ---------------------------------------------------------------------------
# Top page requires authentication.
# ---------------------------------------------------------------------------


def test_top_anonymous_fails(client, db):
    """Top page is inaccessible without authentication."""
    top = reverse('app:top')
    response = client.get(top)
    assertRedirects(response, f'{reverse("login")}?{urlencode({"next": top})}')


def test_top_authenticated_works(authed_client):
    """Top page shows different content for authenticated users."""
    response = authed_client.get(reverse('app:top'))
    assert response.status_code == 200
    assertTemplateUsed(response, 'app/top.html')
    assertTemplateUsed(response, 'app/base.html')
    # Authenticated users should see a logout form, not a login link
    assertContains(response, 'Welcome, test@example.com')
    assertContains(response, 'Logout')


def test_favicon_anonymous(client):
    """Favicon is accessible without authentication."""
    response = client.get(reverse('favicon'))
    assert response.status_code == 301  # PermanentRedirectView to static file


def test_admin_redirects_anonymous(client, db):
    """Admin requires authentication; anonymous users get redirected."""
    response = client.get('/office/')
    assertRedirects(response, f'{reverse("admin:login")}?{urlencode({"next": reverse("admin:index")})}')


def test_admin_denies_unauthorised(authed_client):
    """Non-staff users are sent to the admin login page."""
    response = authed_client.get(reverse('admin:index'))

    assertRedirects(response, f'{reverse("admin:login")}?{urlencode({"next": reverse("admin:index")})}')


def test_login_page_anonymous(client, db):
    """Login page is accessible without authentication."""
    response = client.get(reverse('login'))
    assert response.status_code == 200
    assertTemplateUsed(response, 'registration/login.html')


def test_password_reset_anonymous(client):
    """Password reset pages are accessible without authentication."""
    response = client.get(reverse('password_reset'))
    assert response.status_code == 200
    assertTemplateUsed(response, 'registration/my_password_reset_form.html')


def test_password_reset_done_anonymous(client):
    """Password reset done page is accessible without authentication."""
    response = client.get(reverse('password_reset_done'))
    assert response.status_code == 200
    assertTemplateUsed(response, 'registration/my_password_reset_done.html')


def test_logout_requires_post(authed_client):
    """Logout via GET should not work (requires POST)."""
    response = authed_client.get(reverse('logout'))

    assert response.status_code == 405


# ---------------------------------------------------------------------------
# Logout redirect target
# ---------------------------------------------------------------------------
# ``LOGOUT_REDIRECT_URL`` is ``'/'`` in ``conf/settings.py``, so a successful
# logout redirects to the top page.  Because the top page requires login, the
# redirect to ``/`` bounces to the login page.
# ---------------------------------------------------------------------------


def test_logout_success_requires_login(authed_client):
    """Logout via POST logs the user out; top page then requires login."""
    response = authed_client.post(reverse('logout'), follow=True)
    top = reverse('app:top')
    assertRedirects(response, f'{reverse("login")}?{urlencode({"next": top})}')
    # After logout, the login page is shown instead of the dashboard
    assertContains(response, 'Log in')
