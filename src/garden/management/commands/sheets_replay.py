"""Replay pending or failed Google Sheets change log rows.

The entire replay runs in a single atomic transaction, so if anything goes
wrong the database is left untouched.  Deciding what to do with problematic
data is Stage 3 work.

Stage 2 ships no range-to-model mapping yet, so by default this command only
reports what would be replayed.  Pass ``--mark-error`` to exercise the status
transitions.

Examples:
    # Show what is pending / errored:
    ./manage.py sheets_replay

    # Move every pending row to "error" (useful for testing the transitions):
    ./manage.py sheets_replay --mark-error
"""

from django.core.management.base import BaseCommand

from garden.models import SheetChangeLog
from garden.services import replay


class Command(BaseCommand):
    help = 'Replay pending or failed Google Sheets change log rows in a single transaction.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            action='append',
            choices=[choice.value for choice in SheetChangeLog.Status],
            help='Only replay rows with this status (repeatable; default: pending and error).',
        )
        parser.add_argument(
            '--mark-error',
            action='store_true',
            help='Mark each replayed row as "error" instead of leaving it unchanged.',
        )

    def handle(self, *args, **options):
        statuses = options['status'] or None

        if options['mark_error']:

            def processor(change):
                return SheetChangeLog.Status.ERROR, 'Marked as error by sheets_replay --mark-error.'

        else:

            def processor(change):
                return change.status, 'No processor configured; left unchanged.'

        results = replay(processor=processor, statuses=statuses)

        if not results:
            self.stdout.write('No changes to replay.')
            return

        for result in results:
            self.stdout.write(
                f'#{result.change.pk} {result.change.sheet_name}!{result.change.range} -> {result.status}'
            )

        self.stdout.write(self.style.SUCCESS(f'Replayed {len(results)} change(s).'))
