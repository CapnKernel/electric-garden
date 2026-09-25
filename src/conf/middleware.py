import zoneinfo

from django.conf import settings
from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.contrib.messages.api import get_messages
from django.utils import timezone


class TimezoneMiddleware(object):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tzname = settings.TIME_ZONE
        if tzname:
            timezone.activate(zoneinfo.ZoneInfo(tzname))

        return self.get_response(request)


class LoginRequiredExemptMiddleware(LoginRequiredMiddleware):
    """
    Extends Django's built-in LoginRequiredMiddleware with support for
    AUTH_EXEMPT_VIEW_NAMES — a tuple of view names (as named in
    urlpatterns) that are exempt from the login requirement.
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.user.is_authenticated:
            return None

        exempt_names = getattr(settings, 'AUTH_EXEMPT_VIEW_NAMES', ())
        resolver_match = request.resolver_match
        if resolver_match and resolver_match.view_name in exempt_names:
            return None

        return super().process_view(request, view_func, view_args, view_kwargs)


class HtmxMessagesMiddleware:
    """Automatically sets HX-Trigger response header on htmx requests that added messages.

    When an htmx request adds messages to the storage, this middleware
    appends 'messages-updated' to the HX-Trigger header so the client-side
    messages container can refresh itself.
    TODO: This would be a candidate for sending to django-htmx.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(request, 'htmx', False):
            storage = get_messages(request)
            if hasattr(storage, 'added_new') and storage.added_new:
                existing = response.get('HX-Trigger', '')
                response['HX-Trigger'] = ','.join(filter(None, (existing, 'messages-updated')))

        return response
