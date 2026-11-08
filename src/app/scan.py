"""Barcode scanning views for the garden app.

Barcodes are strings of the form ``P=<int>`` (for plants, packets or
plantings) or ``PC=<int>`` (for containers).  A scan records the scan time on
the object via ``mark_scanned()`` and then redirects to that object's detail
page, so the browser URL always names the object being viewed.
"""

from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST
from django_htmx.http import HttpResponseClientRedirect

from .models import Container, Packet, Plant, Planting
from .search import text_search


class BarcodeNotFound(Exception):
    """Raised when a scanned barcode does not match any object in the db."""


def lookup_barcode(barcode):
    """Resolve a scanned barcode to a model instance.

    Returns the matching ``Plant``, ``Packet``, ``Planting`` or
    ``Container`` instance.  Raises :class:`BarcodeNotFound` if the barcode
    is malformed or no corresponding object exists.
    """
    barcode = (barcode or '').strip()
    if not barcode:
        raise BarcodeNotFound('No barcode provided.')

    # Containers use the 'PC=' prefix; everything else uses 'P='.
    if obj := Container.from_barcode(barcode):
        return obj

    # Plants, packets and plantings share the 'P=' prefix, so try each in
    # turn.  The numeric ranges are disjoint by convention, but we still
    # check all three to be safe.
    for model in (Plant, Packet, Planting):
        if obj := model.from_barcode(barcode):
            return obj

    raise BarcodeNotFound(f'No object found for barcode {barcode}')


def scan_and_mark(barcode):
    """Look up ``barcode`` and record the scan time on the object.

    Returns the object, or raises :class:`BarcodeNotFound`.
    """
    obj = lookup_barcode(barcode)
    obj.mark_scanned()
    return obj


def _search_context(q, exc):
    """Return the scan-result context for a string that matched no barcode.

    ``q`` is used as a text-search term, and its results are shown instead of
    an error.  ``exc``'s message is reported only when the search finds nothing
    either.
    """
    search_results = text_search(q)
    return {
        'q': q,
        'obj': None,
        'error': None if search_results else str(exc),
        'search_results': search_results,
    }


def render_scan_result(request, obj):
    """Render the ``scan-result`` fragment for a scanned object.

    Used by the planting-event CRUD views to re-render the scan result after a
    change, so the page updates in place via htmx.
    """
    return render(request, 'app/scan.html#scan-result', {'q': obj.barcode, 'obj': obj, 'error': None})


@require_GET
def render_detail(request, model, pk):
    """Render the full page for ``model`` instance ``pk`` without recording a scan.

    This backs the per-object detail URLs in ``urls.py`` (see
    ``BarcodedBase.detail_url``), so simply viewing an object does not change
    its ``last_scanned_at``.
    """
    obj = get_object_or_404(model, pk=pk)
    return render(request, 'app/scan.html', {'q': obj.barcode, 'obj': obj, 'error': None})


@require_GET
def scan_page(request):
    """Full page presenting a prefocused barcode input.

    Without a barcode it renders an empty input, which posts to
    :func:`scan_hxpost` via htmx.

    With a ``q`` query parameter (e.g. ``/scan/?q=P%3D1111``) the value is
    scanned and the browser is redirected to the object's detail page, so the
    address bar names the object rather than the scan endpoint.  A value that
    matches no barcode is used as a text-search term, and the matching objects
    are shown instead of an error.
    """
    barcode = request.GET.get('q', '').strip()
    context = {
        'q': barcode,
        'obj': None,
        'error': None,
        'search_results': [],
    }
    if barcode:
        try:
            return redirect(scan_and_mark(barcode).detail_url)
        except BarcodeNotFound as exc:
            context = _search_context(barcode, exc)

    return render(request, 'app/scan.html', context)


@require_POST
def scan_hxpost(request):
    """Handle a scanned barcode from the htmx input.

    On success the object is looked up and marked as scanned, and htmx is told
    to navigate to its detail page (see :func:`render_detail`) so the URL
    matches the object shown.  A string that matches no barcode is used as a
    text-search term; the matching objects are returned in the
    ``scan-result`` fragment instead of an error.
    """
    barcode = request.POST.get('q', '').strip()
    try:
        obj = scan_and_mark(barcode)
    except BarcodeNotFound as exc:
        context = _search_context(barcode, exc)
    else:
        return HttpResponseClientRedirect(obj.detail_url)

    return render(request, 'app/scan.html#scan-result', context)

