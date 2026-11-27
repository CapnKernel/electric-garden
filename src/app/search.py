"""Case-insensitive text search over the garden's free-text fields.

A barcode scan that matches no object falls back to this search (see
:func:`app.scan.scan_page`).  Terms match whole words: each term is turned into
a regular expression with word-boundary markers.  A leading or trailing ``*``
removes the corresponding boundary, so ``*berry`` and ``blue*`` both
match ``blueberry``.

The matching runs in the database via ``__iregex`` (Django's SQLite backend
provides the ``REGEXP`` function using Python's :mod:`re`).
"""

import re

from django.db.models import Q

from .models import Container, Packet, Plant, PlantingEvent


def search_pattern(term):
    """Return the case-insensitive, word-boundary regex pattern for ``term``.

    Word boundaries are added at each end unless the term starts (or ends) with
    ``*``, which allows a substring match at that end.  Returns ``None`` when
    there is no text to search for (e.g. the term is only asterisks).
    """
    term = (term or '').strip()
    core = term.strip('*')
    if not core:
        return None
    prefix = '' if term.startswith('*') else r'\b'
    suffix = '' if term.endswith('*') else r'\b'
    return f'{prefix}{re.escape(core)}{suffix}'


def text_search(term):
    """Return the objects matching ``term`` grouped by model.

    Each group is a dict with a ``title`` and a list of ``items``; an item has a
    ``label``, a ``url`` for the object's detail page, a ``detail`` string
    giving the matching context, and ``deleted``, which marks a match that has
    been deleted.  Deleted items are included, so nothing is hidden from a
    search, but they sort after the live ones in each group.  Groups with no
    matches are omitted, so an empty list means nothing was found.
    """
    pattern = search_pattern(term)
    if pattern is None:
        return []

    groups = []

    plants = Plant.objects.filter(Q(code__iregex=pattern) | Q(name__iregex=pattern)).order_by('deleted', 'name')
    if plants:
        groups.append(
            {
                'title': 'Plants',
                'items': [
                    {'label': plant.name, 'url': plant.detail_url, 'detail': plant.code, 'deleted': plant.deleted}
                    for plant in plants
                ],
            }
        )

    packets = (
        Packet.objects.filter(Q(full_name__iregex=pattern) | Q(notes__iregex=pattern))
        .select_related('plant')
        .order_by('deleted', 'plant__name', 'pk')
    )
    if packets:
        groups.append(
            {
                'title': 'Packets',
                'items': [
                    {
                        'label': packet.label,
                        'url': packet.detail_url,
                        'detail': packet.brand or '',
                        'deleted': packet.deleted,
                    }
                    for packet in packets
                ],
            }
        )

    containers = Container.objects.filter(name__iregex=pattern).order_by('deleted', 'name')
    if containers:
        groups.append(
            {
                'title': 'Containers',
                'items': [
                    {
                        'label': container.name,
                        'url': container.detail_url,
                        'detail': container.barcode,
                        'deleted': container.deleted,
                    }
                    for container in containers
                ],
            }
        )

    events = (
        PlantingEvent.objects.filter(Q(location__iregex=pattern) | Q(notes__iregex=pattern))
        .select_related('planting__packet__plant')
        .order_by('planting__deleted', '-date', 'pk')
    )
    if events:
        groups.append(
            {
                'title': 'Planting events',
                'items': [
                    {
                        'label': (
                            f'{event.planting.packet.plant.name} — '
                            f'{event.get_event_type_display()} {event.date:%d %b %Y}'
                        ),
                        'url': event.planting.detail_url,
                        'detail': event.placement.text or event.notes or '',
                        'deleted': event.planting.deleted,
                    }
                    for event in events
                ],
            }
        )

    return groups
