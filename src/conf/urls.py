"""
URL configuration.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

import sys

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect
from django.templatetags.static import static
from django.urls import include, path
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.views.generic.base import RedirectView
from django.views.static import serve

from conf.xaccel import serve_protected_media

urlpatterns = [
    path('office/', admin.site.urls),
    path('accounts/', include('authuser.urls')),
    path(
        'favicon.ico',
        method_decorator(login_not_required)(RedirectView.as_view(url=static('favicon.ico'), permanent=True)),
        name='favicon',
    ),
    # app handles top-level
    path('', include('app.urls')),
    path('garden/', include('garden.urls')),
]

if any('pytest' in arg for arg in sys.argv) or 'pytest' in sys.modules:
    # Test-only endpoint used to exercise the messages partial.  Only
    # active during test.   The message text comes from the ``message``
    # POST/GET parameter (defaulting to a generic success message) and
    # is rendered by ``app:messages_partial``.
    class MessageView(TemplateView):
        def post(self, request, *args, **kwargs):
            text = request.POST.get('message') or request.GET.get('message') or 'Action completed.'
            messages.success(request, text)
            return redirect('app:top')

    urlpatterns += [
        path('post_test_message/', MessageView.as_view(), name='message'),
    ]

if settings.DEBUG:
    urlpatterns += [
        # If we're running behind a web server, we won't see media requests,
        # so this will do nothing.  Kept for local development.
        path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
        path('__debug__/', include('debug_toolbar.urls')),
    ]
else:
    # Media files: in production, served via X-Sendfile through uWSGI
    # after authorization.  The view does its own auth check.
    urlpatterns += [
        path('media/<path:path>', serve_protected_media, name='protected-media'),
    ]
