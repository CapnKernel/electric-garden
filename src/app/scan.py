"""Barcode scanning and detail-page views for the garden app.

Barcodes are strings of the form ``P=<int>`` (for plants, packets or
plantings) or ``PC=<int>`` (for containers).  Scanning is an action: it records
the scan time on the object and then navigates to its detail page, so the
browser URL always names the object being viewed.

A string that matches no barcode is treated as a search term, and the browser
is sent to the search page.  Detail pages are rendered by :func:`detail_view`.
"""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods
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


def search_url(term):
    """URL of the search page for ``term``."""
    return f'{reverse("app:search")}?{urlencode({"q": term})}'


def _navigate(request, url):
    """Send the browser to ``url``, letting htmx drive the navigation if it can."""
    if request.htmx:
        return HttpResponseClientRedirect(url)
    return redirect(url)


@require_http_methods(['GET', 'POST'])
def scan_action(request):
    """Resolve a scanned barcode and navigate to where it belongs.

    ``GET /scan/`` renders the scanner.  Otherwise the scanned value is read
    from the POST (the htmx form) or from ``?q=`` (links, barcode scanners and
    browsers without htmx): a barcode marks its object and navigates to the
    detail page, while anything else is treated as a search term for
    :func:`search_page`.
    """
    raw = request.POST.get('q') if request.method == 'POST' else request.GET.get('q')
    barcode = (raw or '').strip()
    if not barcode and request.method == 'GET':
        return render(request, 'app/scan.html')

    try:
        obj = scan_and_mark(barcode)
    except BarcodeNotFound:
        return _navigate(request, search_url(barcode))
    return _navigate(request, obj.detail_url)


@require_GET
def search_page(request):
    """Search the garden's free-text fields and show the matches.

    A scanned string that is not a barcode arrives here as ``?q=``.  With no
    term the page prompts for one; an unmatched term shows an alert instead of
    empty groups.
    """
    term = request.GET.get('q', '').strip()
    results = text_search(term)
    context = {
        'q': term,
        'search_results': results,
        'error': f'No match for {term}.' if term and not results else None,
    }
    return render(request, 'app/search.html', context)


def detail_view(request, model, pk, fragment=False):
    """Render the detail page for ``model`` instance ``pk`` without recording a scan.

    This backs the per-object detail URLs in ``urls.py`` (see
    ``BarcodedBase.detail_url``), so simply viewing an object does not change
    its ``last_scanned_at``.  ``fragment=True`` returns only the detail card, for
    the htmx swaps that follow an inline change.
    """
    obj = get_object_or_404(model, pk=pk)
    template = 'app/detail.html#detail' if fragment else 'app/detail.html'
    return render(request, template, {'obj': obj})


def render_detail_fragment(request, obj):
    """Re-render one object's detail card, e.g. after a planting event change."""
    return render(request, 'app/detail.html#detail', {'obj': obj})
