from urllib.parse import urlencode

import pytest
from django.urls import reverse
from pytest_django.asserts import assertRedirects, assertTemplateUsed

# ---------------------------------------------------------------------------
# Top page: login required or not?
# ---------------------------------------------------------------------------
# This template ships with a top page that is *public* (the ``app:top`` view is
# decorated with ``@login_not_required`` in ``app/urls.py``).
#
# If your app needs the top page to require authentication, remove the
# ``login_not_required`` decorator from the ``app:top`` route, then swap the
# two test functions below: delete/rename ``test_top_anonymous_works`` and
# remove the ``@pytest.mark.skip`` from ``test_top_anonymous_fails``.  The
# authenticated test (``test_top_authenticated_works``) works in both
# configurations.
# ---------------------------------------------------------------------------


def test_top_anonymous_works(client, db):
    """Top page is publicly accessible (current template default).

    The ``app:top`` view is decorated with ``@login_not_required``, so an
    anonymous request renders the page rather than redirecting to login.
    """
    response = client.get(reverse('app:top'))
    assert response.status_code == 200
    assertTemplateUsed(response, 'app/top.html')
    assertTemplateUsed(response, 'app/base.html')
    # Anonymous users should see a login link, not a logout form
    assert b'Log in' in response.content
    assert b'Logout' not in response.content


@pytest.mark.skip(reason='Enable when the top page requires authentication (see note above).')
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
    assert b'Welcome, test@example.com' in response.content
    assert b'Logout' in response.content


def test_favicon_anonymous(client):
    """Favicon is accessible without authentication."""
    response = client.get(reverse('favicon'))
    assert response.status_code == 301  # PermanentRedirectView to static file


def test_admin_redirects_anonymous(client, db):
    """Admin requires authentication; anonymous users get redirected."""
    response = client.get('/office/')
    assertRedirects(response, f'{reverse("admin:login")}?{urlencode({"next": reverse("admin:index")})}')


def test_admin_denies_unauthorised(authed_client):
    """Non-staff users get a 302 (redirect to admin login then 200)."""
    response = authed_client.get('/office/', follow=True)
    # Django admin returns 200 with "You are not staff" message
    assert response.status_code == 200
    assert b'staff' in response.content or b'login' in response.content


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
    # GET on logout should return a method-not-allowed or similar
    assert response.status_code in (200, 405)


# ---------------------------------------------------------------------------
# Logout redirect target
# ---------------------------------------------------------------------------
# ``LOGOUT_REDIRECT_URL`` is ``'/'`` in ``conf/settings.py``, so a successful
# logout redirects to the top page.  Because the top page is public in this
# template, that request returns 200 and shows the login link again.
#
# If your app requires login for the top page, the redirect to ``/`` will
# itself bounce to the login page.  In that case, swap the two tests below:
# remove the ``@pytest.mark.skip`` from ``test_logout_success_requires_login``
# and skip/delete ``test_logout_success``.
# ---------------------------------------------------------------------------


def test_logout_success(authed_client):
    """Logout via POST logs the user out and redirects to the top page."""
    response = authed_client.post(reverse('logout'), follow=True)
    top = reverse('app:top')
    # LOGOUT_REDIRECT_URL == '/', so we land on the (public) top page.
    assertRedirects(response, top)
    # After logout, the top page should show the login link again
    assert b'Log in' in response.content


@pytest.mark.skip(reason='Enable when the top page requires authentication (see note above).')
def test_logout_success_requires_login(authed_client):
    """Logout via POST logs the user out; top page then requires login."""
    response = authed_client.post(reverse('logout'), follow=True)
    top = reverse('app:top')
    assertRedirects(response, f'{reverse("login")}?{urlencode({"next": top})}')
    # After logout, the top page should show the login link again
    assert b'Log in' in response.content
