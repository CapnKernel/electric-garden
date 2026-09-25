import os

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse, HttpResponseForbidden
from django.views.static import serve


# Media files: served via X-Sendfile through uWSGI's --file-serve-mode.
# View does its own auth check, so mark it login_not_required
@login_not_required
def serve_protected_media(request, file_path):
    """
    Serve media files, with authorization.

    In production (DEBUG=False), returns an X-Sendfile header
    so uWSGI serves the file directly via sendfile() after
    Django authorizes the request.

    In development (DEBUG=True), serves the file directly via
    django.views.static.serve so no uWSGI file serving is required.
    """
    if not request.user.is_authenticated:
        return HttpResponseForbidden('Authentication required')

    if settings.DEBUG:
        # Local development: serve directly via Django
        return serve(request, file_path, document_root=settings.MEDIA_ROOT)

    # Production: return X-Sendfile for uWSGI to serve via sendfile()
    response = HttpResponse()
    response['X-Sendfile'] = os.path.join(settings.MEDIA_ROOT, file_path)
    response['Content-Type'] = ''
    return response
