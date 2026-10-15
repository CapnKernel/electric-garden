"""Barcode scanning views for the garden app.

Barcodes are strings of the form ``P=<int>`` (for plants, packets or
plantings) or ``PC=<int>`` (for containers).  Scanning looks up and displays
information, and records the scan time on the object via ``mark_scanned()``.
"""

from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import Container, Packet, Plant, Planting


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


def render_scan_result(request, obj):
    """Render the ``scan-result`` fragment for a scanned object.

    Used by the planting-event CRUD views to re-render the scan result after a
    change, so the page updates in place via htmx.
    """
    return render(request, 'garden/scan.html#scan-result', {'barcode': obj.barcode, 'obj': obj, 'error': None})


def scan_page(request):
    """Full page presenting a prefocused barcode input.

    The input posts to :func:`scan_hxpost` via htmx; the returned fragment
    replaces the ``scan-result`` region and re-renders the input ready for
    the next scan.

    If a ``barcode`` query parameter is supplied (e.g.
    ``/garden/scan/?barcode=P%3D1111``), the result is shown immediately as
    if that barcode had just been scanned.
    """
    barcode = request.GET.get('barcode', '').strip()
    obj = None
    error = None
    if barcode:
        try:
            obj = scan_and_mark(barcode)
        except BarcodeNotFound as exc:
            error = str(exc)

    context = {
        'barcode': barcode,
        'obj': obj,
        'error': error,
    }
    return render(request, 'garden/scan.html', context)


@require_POST
def scan_hxpost(request):
    """Handle a scanned barcode and return the ``scan-result`` fragment.

    Displays information about the scanned object (or an error), then
    re-renders the input field ready for the next barcode.
    """
    barcode = request.POST.get('barcode', '').strip()
    obj = None
    error = None
    try:
        obj = scan_and_mark(barcode)
    except BarcodeNotFound as exc:
        error = str(exc)

    context = {
        'barcode': barcode,
        'obj': obj,
        'error': error,
    }
    return render(request, 'garden/scan.html#scan-result', context)
