"""Replay pending or failed Google Sheets change log rows.

The entire replay runs in a single atomic transaction, so if anything goes
wrong the database is left untouched.  Deciding what to do with problematic
data is Stage 3 work.

By default each change is applied to its target model instance via
``services.apply_change``.  Pass ``--dry-run`` to report what would happen
without touching anything.

Examples:
    # Apply every pending / errored change:
    ./manage.py sheets_replay

    # Show what would be replayed, without changing anything:
    ./manage.py sheets_replay --dry-run
"""

from django.core.management.base import BaseCommand

from garden.models import SheetChangeLog
from garden.services import apply_change, replay


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
            '--dry-run',
            action='store_true',
            help='Report what would be replayed without changing anything.',
        )

    def handle(self, *args, **options):
        statuses = options['status'] or None

        results = replay(processor=apply_change, statuses=statuses, dry_run=options['dry_run'])

        if not results:
            self.stdout.write('No changes to replay.')
            return

        for result in results:
            self.stdout.write(
                f'#{result.change.pk} {result.change.sheet_name}!{result.change.range} -> {result.status}'
            )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'Dry run: {len(results)} change(s) would be replayed.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Replayed {len(results)} change(s).'))
