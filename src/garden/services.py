"""Reconciliation services for Google Sheets change logs.

Stage 2 provides the replay machinery: pending (or failed) ``SheetChangeLog``
rows are handed to a processor, which either applies the change to the target
Django models or records why it could not.

The default processor (:func:`apply_change`) locates a model instance from the
change's ``sheet_name`` and ``key`` and updates it with the change's new value.
The sheet's column header (``column_name``) is mapped to a model field using
the same rules as the ``load_xlsx`` importer.  The processor is pluggable so
that Stage 3's UI reconciler can reuse the same entry point.  Deciding what to
do with problematic data is also Stage 3 work; for now a replay is
all-or-nothing.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime

from django.apps import apps
from django.db import transaction
from django.utils import timezone

from .models import SheetChangeLog

logger = logging.getLogger(__name__)

# Header names that do not correspond to a model field, mapped to the field they
# should populate.  Headers not listed here are normalised (lowercased, spaces
# replaced with underscores) and matched against the model's fields.
HEADER_ALIASES = {
    '🗑': 'deleted',  # wastebasket
    'Plant barcode': 'plant',
    'Packet barcode': 'packet',
    'Planting notes': 'notes',
}

# Headers that carry no model data and should be ignored.
IGNORED_HEADERS = {
    "seen '26",
    'age',
}


def model_for_sheet(sheet_name):
    """Look up a garden model from a sheet name by dropping the plural 's'."""
    try:
        return apps.get_model('garden', sheet_name[:-1])
    except LookupError:
        return None


def field_name_for_header(model, header):
    """Map a sheet column header to a model field name, or None to ignore it.

    Mirrors the importer's rules: strip variation selectors, apply
    ``HEADER_ALIASES``, lowercase, replace spaces with underscores, then match
    against the model's field names and attribute names.
    """
    if header is None:
        return None
    name = str(header).strip()
    if not name:
        return None
    # Strip variation selectors (e.g. U+FE0F) so emoji headers match reliably.
    name = name.replace('\ufe0f', '')
    name = HEADER_ALIASES.get(name, name)
    name = name.lower()
    if name in IGNORED_HEADERS:
        return None
    name = name.replace(' ', '_')
    for field in model._meta.get_fields():
        if field.name == name or getattr(field, 'attname', None) == name:
            return field.name
    return None


def _coerce(field, value):
    """Coerce a raw sheet value into something the field can store.

    Foreign keys are given as barcodes in the sheet, so they are resolved to
    the related instance (mirroring the ``load_xlsx`` importer).
    """
    if isinstance(value, str):
        value = value.strip()
        if value == '':
            return None
    if value is None:
        return None
    if field.is_relation:
        related = field.related_model
        try:
            return related.objects.get(pk=related.pk_from_barcode(str(value)))
        except related.DoesNotExist as exc:
            raise ValueError(f'no {related.__name__} with barcode {value!r}') from exc
    internal = field.get_internal_type()
    if internal == 'BooleanField':
        return str(value).strip().lower() not in ('', '0', 'false', 'no')
    if internal == 'DateField':
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.fromisoformat(str(value)).date()
    if internal in ('IntegerField', 'BigIntegerField', 'SmallIntegerField'):
        return int(value)
    return str(value)


def _as_text(value):
    """Render a value the way a spreadsheet cell would, for comparison."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def apply_change(change):
    """Apply one ``SheetChangeLog`` row to its target model instance.

    Returns a ``(status, message)`` tuple suitable for :func:`process_change`.
    The change must carry a ``sheet_name``, a ``key`` and a ``column_name``;
    the key is the barcode of the row to update, and the column name is mapped
    to a model field.  The new value is taken from ``new_values``.

    If no instance exists for the key but the key is a valid barcode for the
    model, a new instance is created with that primary key.

    Before writing, the sheet's ``old_values`` are compared against the current
    database value.  If they differ, the row was changed in Django after the
    sheet was read, so applying the sheet value would silently clobber that
    change; the row is reported as ``conflict`` instead.
    """
    if not change.sheet_name or not change.key:
        return SheetChangeLog.Status.ERROR, 'Change has no sheet_name or key; cannot locate a row.'

    model = model_for_sheet(change.sheet_name)
    if model is None:
        return SheetChangeLog.Status.ERROR, f'No model found for sheet {change.sheet_name!r}.'

    if not change.column_name:
        return SheetChangeLog.Status.ERROR, 'Change has no column_name; cannot determine the field.'

    field_name = field_name_for_header(model, change.column_name)
    if field_name is None:
        return SheetChangeLog.Status.ERROR, f'Column {change.column_name!r} does not map to a field.'
    if field_name == 'barcode':
        return SheetChangeLog.Status.ERROR, 'The barcode column cannot be updated.'

    try:
        pk = model.pk_from_barcode(change.key)
    except (ValueError, AttributeError) as exc:
        return SheetChangeLog.Status.ERROR, f'Invalid barcode {change.key!r}: {exc}'

    new_value = None
    if change.new_values:
        new_value = change.new_values[0][0]

    field = model._meta.get_field(field_name)
    try:
        value = _coerce(field, new_value)
    except (TypeError, ValueError) as exc:
        return SheetChangeLog.Status.ERROR, f'Could not convert {new_value!r} for {field_name}: {exc}'

    # ``get_or_create`` keeps the lookup-and-create atomic, so two concurrent
    # replays cannot both try to insert the same primary key.
    try:
        instance, created = model.objects.get_or_create(pk=pk, defaults={field_name: value})
    except Exception as exc:  # noqa: BLE001 - surface any creation failure as an error row
        return SheetChangeLog.Status.ERROR, f'Could not create {model.__name__} {change.key!r}: {exc}'

    if created:
        return SheetChangeLog.Status.APPLIED, f'Created {model.__name__} {change.key!r}.'

    # Conflict check: the sheet told us what the cell held before the edit.  If
    # the database no longer matches, someone changed it here in the meantime.
    if change.old_values:
        old_value = change.old_values[0][0]
        current = _as_text(getattr(instance, field_name))
        expected = _as_text(old_value)
        if current != expected:
            return (
                SheetChangeLog.Status.CONFLICT,
                f'{model.__name__} {change.key!r} {field_name}: sheet expected {expected!r} '
                f'but database holds {current!r}.',
            )

    setattr(instance, field_name, value)
    # The save runs in its own savepoint: a failure (e.g. NOT NULL) rolls back
    # just this write, leaving the surrounding replay transaction usable.
    try:
        with transaction.atomic():
            instance.save(update_fields=[field_name])
    except Exception as exc:  # noqa: BLE001 - e.g. NOT NULL / validation failures
        return SheetChangeLog.Status.ERROR, f'Could not save {model.__name__} {change.key!r}: {exc}'
    return SheetChangeLog.Status.APPLIED, ''


@dataclass
class ProcessResult:
    """Outcome of processing a single ``SheetChangeLog`` row."""

    change: SheetChangeLog
    status: str
    message: str = ''


def process_change(change, processor=None):
    """Process one ``SheetChangeLog`` row and persist its new status.

    ``processor`` is a callable taking the change and returning a
    ``(status, message)`` tuple.  When omitted, the change is left as-is and
    reported as such.

    Exceptions from ``processor`` are *not* caught here: they propagate so the
    caller can decide whether to roll back (see :func:`replay`).  A processor
    that wants to record a failure without aborting should return
    ``(Status.ERROR, message)`` instead of raising an exception.
    """
    if processor is None:
        return ProcessResult(change, change.status, 'No processor configured; left unchanged.')

    status, message = processor(change)

    change.status = status
    # Keep the explanation for anything that did not apply cleanly, so a
    # conflict or error can be understood later from the audit row alone.
    change.error_message = message if status in (SheetChangeLog.Status.ERROR, SheetChangeLog.Status.CONFLICT) else None
    change.applied_at = timezone.now() if status == SheetChangeLog.Status.APPLIED else None
    change.save(update_fields=['status', 'error_message', 'applied_at'])
    return ProcessResult(change, status, message)


def replay(processor=apply_change, statuses=None, dry_run=False):
    """Replay every change in ``statuses`` (default: pending and error).

    The whole replay runs inside a single atomic transaction: if any change
    raises, the transaction is rolled back and no change to the database is
    kept.  The exception propagates to the caller.

    ``processor`` defaults to :func:`apply_change`.  When ``dry_run`` is true
    the work is still performed (so errors surface) but the transaction is
    rolled back, leaving the database untouched.

    Returns a list of ``ProcessResult``, one per change considered.
    """
    if statuses is None:
        statuses = [SheetChangeLog.Status.PENDING, SheetChangeLog.Status.ERROR]

    changes = list(SheetChangeLog.objects.filter(status__in=statuses).order_by('received_at'))

    with transaction.atomic():
        results = [process_change(change, processor=processor) for change in changes]
        if dry_run:
            transaction.set_rollback(True)
        return results
