"""Reconciliation services for Google Sheets change logs.

Stage 2 provides the replay machinery: pending (or failed) ``SheetChangeLog``
rows are handed to a processor, which either applies the change to the target
Django models or records why it could not.

The mapping from a sheet range to a Django model is deliberately left to a
pluggable processor so that Stage 3's UI reconciler can reuse the same entry
point.  Deciding what to do with problematic data is also Stage 3 work; for
now a replay is all-or-nothing.
"""

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from .models import SheetChangeLog

logger = logging.getLogger(__name__)


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
    change.error_message = message if status == SheetChangeLog.Status.ERROR else None
    change.applied_at = timezone.now() if status == SheetChangeLog.Status.APPLIED else None
    change.save(update_fields=['status', 'error_message', 'applied_at'])
    return ProcessResult(change, status, message)


def replay(processor=None, statuses=None):
    """Replay every change in ``statuses`` (default: pending and error).

    The whole replay runs inside a single atomic transaction: if any change
    raises, the transaction is rolled back and no change to the database is
    kept.  The exception propagates to the caller.

    Returns a list of ``ProcessResult``, one per change considered.
    """
    if statuses is None:
        statuses = [SheetChangeLog.Status.PENDING, SheetChangeLog.Status.ERROR]

    changes = list(SheetChangeLog.objects.filter(status__in=statuses).order_by('received_at'))

    with transaction.atomic():
        return [process_change(change, processor=processor) for change in changes]
