"""Repopulate the garden database from an .xlsx workbook.

The workbook is expected to contain one sheet per garden model, named after the
model's plural (``Containers``, ``Plants``, ``Packets``, ``Plantings``), as
produced by ``Electric garden.xlsx``.  All existing garden data is deleted and
the workbook is re-imported inside a single transaction, so a failure leaves the
database untouched.

Each sheet's first row is a header naming the model fields to populate.  The
first column is always the barcode, which is translated back into a primary key
via the model's ``pk_from_barcode``.  Foreign keys are given as barcodes and
resolved to primary keys.  Rows are turned into model instances with a
``ModelForm``, mirroring how a web form would populate the same models.

Examples:
    ./manage.py load_xlsx "Electric garden.xlsx"
    ./manage.py load_xlsx "Electric garden.xlsx" --dry-run
"""

import graphlib
from datetime import date, datetime

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.forms import modelform_factory

from garden.models import Container, Packet, Plant, Planting
from garden.services import field_name_for_header, model_for_sheet

# Import order matters: parents must exist before children reference them.
MODELS = [Container, Plant, Packet, Planting]


def _clean(value):
    """Normalise a cell value: strip strings, treat blanks as None."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _text(value):
    """Return a cell as a string, or None when blank."""
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _date(value):
    """Return a cell as a ``datetime.date``, or None when blank."""
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


class Command(BaseCommand):
    help = 'Delete all garden data and repopulate it from an .xlsx workbook.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to the .xlsx workbook.')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Don't save results.",
        )

    def handle(self, *args, **options):
        path = options['path']
        try:
            workbook = openpyxl.load_workbook(path, data_only=True)
        except FileNotFoundError as exc:
            raise CommandError(f'No such file: {path}') from exc

        # Compose the list of models from the workbook's sheets.
        models = []
        for sheet_name in workbook.sheetnames:
            model = model_for_sheet(sheet_name)
            if model is not None:
                models.append(model)
        if not models:
            raise CommandError('Workbook contains no recognised garden sheets.')

        # Order models so parents are imported before the children that
        # reference them (and deleted in the reverse order).
        models = self._dependency_order(models)

        counts = {}
        with transaction.atomic():
            for model in reversed(models):
                model.objects.all().delete()
            for model in models:
                counts[model] = self._load_sheet(model, workbook[model._meta.verbose_name_plural.title()])
            if options['dry_run']:
                transaction.set_rollback(True)

        for model, count in counts.items():
            self.stdout.write(f'{model._meta.verbose_name_plural.title()}: imported {count} row(s).')
        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry run: database left unchanged.'))
        else:
            self.stdout.write(self.style.SUCCESS('Database repopulated.'))

    def _dependency_order(self, models):
        """Topologically sort models so referenced models come first."""
        selected = set(models)
        graph = {}
        for model in models:
            dependencies = set()
            for field in model._meta.fields:
                if field.is_relation and field.related_model in selected:
                    dependencies.add(field.related_model)
            graph[model] = dependencies
        return list(graphlib.TopologicalSorter(graph).static_order())

    def _load_sheet(self, model, worksheet):
        """Create one instance per data row, using the header row for field names.

        Returns the number of rows loaded.
        """
        rows = worksheet.iter_rows(values_only=True)
        try:
            header = list(next(rows))
        except StopIteration:
            return 0

        # Trim trailing empty header cells (openpyxl pads to the sheet width).
        while header and _clean(header[-1]) is None:
            header.pop()

        # Map each column index to a model field name (or None to ignore it).
        # The first column is always the barcode, which is a property rather
        # than a model field, so it is handled explicitly.
        columns = []
        for index, title in enumerate(header):
            if index == 0:
                columns.append('barcode')
            else:
                f_name = self._field_name(model, title)
                # If the column name couldn't be converted to a field,
                # f_name will be None.  We still append it, otherwise
                # We'll have problems indexing into the row.
                columns.append(f_name)

        form_class = modelform_factory(model, fields=[field for field in columns if field and field != 'barcode'])

        count = 0
        for row in rows:
            # Skip rows that carry no data beyond the barcode
            if all(_clean(cell) is None for cell in row[1:]):
                continue
            data = {}
            raw = {}
            for index, field in enumerate(columns):
                if field is None or index >= len(row):
                    continue
                raw[field] = row[index]
                try:
                    data[field] = self._convert(model, field, row[index])
                except ValueError as exc:
                    self.stderr.write(
                        f'Skipping {model.__name__} {row[0]}: could not convert '
                        f'column {index} ({header[index]!r}) value {row[index]!r}: {exc}'
                    )
                    self.stderr.write(f'  row: {row}')
                    data = None
                    break
            if data is None:
                continue
            if data.get('barcode') is None:
                # We need a barcode
                continue
            form = form_class(data)
            if not form.is_valid():
                self.stderr.write(f'Skipping {model.__name__} {row[0]}:')
                self.stderr.write(form.errors.as_text())
                self.stderr.write(f'  raw values: {raw}')
                continue
            # ``objects.create`` translates the barcode into a primary key.
            model.objects.create(**data)
            count += 1
        return count

    def _field_name(self, model, header):
        """Map a sheet column name to a model field name, or None to ignore it."""
        return field_name_for_header(model, _clean(header))

    def _convert(self, model, field_name, value):
        """Convert a raw cell value into something suitable for a ``ModelForm``."""
        if field_name == 'barcode':
            return _clean(value)
        field = model._meta.get_field(field_name)
        if field.is_relation:
            related = field.related_model
            barcode = _clean(value)
            if barcode is None:
                return None
            return related.pk_from_barcode(barcode)
        if field.get_internal_type() == 'DateField':
            return _date(value)
        if field.get_internal_type() == 'BooleanField':
            return _clean(value) is not None
        return _text(value)
