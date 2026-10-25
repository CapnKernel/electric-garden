"""Rename the legacy ``garden`` app's database objects to the ``app`` label.

FIXME: Remove this command and its call in ``entrypoint.sh`` once it has been
run successfully on the VPS and no ``garden_*`` tables remain.

The ``garden`` app was merged into ``app``, which changes the default table
names (``garden_container`` -> ``app_container``) and the app label recorded in
``django_migrations`` and ``django_content_type``.  This command performs the
one-off renames so existing data is preserved.  It is idempotent: once the
renames have happened it does nothing.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

LEGACY_APP_LABEL = 'garden'
NEW_APP_LABEL = 'app'


class Command(BaseCommand):
    help = "Rename legacy garden_* tables and app-label records to 'app' (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Perform the changes in a transaction, then roll it back.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Emitted on every run so it is visible in the container logs until the
        # command is removed (see the FIXME above).
        self.stdout.write(
            self.style.WARNING(
                'FIXME: migrate_garden_to_app is still installed.  Remove it and its entrypoint '
                'call once the garden_* tables have been renamed on the VPS.'
            )
        )
        if dry_run:
            if not connection.features.can_rollback_ddl:
                raise CommandError(
                    '--dry-run is not supported on this database because its DDL cannot be rolled back.'
                )
            self.stdout.write(
                self.style.WARNING('Dry run: changes will be made in a transaction and then rolled back.')
            )

        tables = set(connection.introspection.table_names())
        with transaction.atomic():
            renamed = self._rename_tables(sorted(tables))
            updated = self._update_records(tables)
            if dry_run:
                transaction.set_rollback(True)

        if not renamed and not updated:
            self.stdout.write('Nothing to migrate.')
        if dry_run:
            self.stdout.write(self.style.WARNING('Dry run: transaction rolled back; no changes were saved.'))

    def _rename_tables(self, tables):
        """Rename every ``garden_*`` table to ``app_*``.  Return the renames made."""
        renamed = []
        prefix = f'{LEGACY_APP_LABEL}_'
        for old_name in tables:
            if not old_name.startswith(prefix):
                continue
            new_name = f'{NEW_APP_LABEL}_{old_name[len(prefix) :]}'
            if new_name in tables:
                self.stdout.write(
                    self.style.WARNING(f'Both {old_name} and {new_name} exist; leaving {old_name} unchanged.')
                )
                continue
            with connection.cursor() as cursor:
                cursor.execute(
                    f'ALTER TABLE {connection.ops.quote_name(old_name)} '
                    f'RENAME TO {connection.ops.quote_name(new_name)}'
                )
            if connection.vendor == 'sqlite':
                self._rename_sqlite_sequence(old_name, new_name)
            self.stdout.write(f'Renamed table {old_name} -> {new_name}')
            renamed.append((old_name, new_name))
        return renamed

    def _rename_sqlite_sequence(self, old_name, new_name):
        """Keep SQLite's AUTOINCREMENT counters attached to the renamed table."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'")
            if cursor.fetchone():
                cursor.execute(
                    'UPDATE sqlite_sequence SET name = %s WHERE name = %s',
                    [new_name, old_name],
                )

    def _update_records(self, tables):
        """Relabel rows in the migration and content-type tables.  Return rows updated."""
        updates = (
            ('django_migrations', 'app'),
            ('django_content_type', 'app_label'),
        )
        changed = 0
        for table, column in updates:
            if table not in tables:
                continue
            with connection.cursor() as cursor:
                cursor.execute(
                    f'UPDATE {connection.ops.quote_name(table)} '
                    f'SET {connection.ops.quote_name(column)} = %s '
                    f'WHERE {connection.ops.quote_name(column)} = %s',
                    [NEW_APP_LABEL, LEGACY_APP_LABEL],
                )
                count = cursor.rowcount
            if count:
                self.stdout.write(f'Updated {count} {table}.{column} row(s) to {NEW_APP_LABEL!r}')
                changed += count
        return changed
