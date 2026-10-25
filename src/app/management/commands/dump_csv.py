"""Dump the garden tables to CSV files.

One CSV is written per model (``Containers``, ``Plants``, ``Packets``,
``Plantings``), mirroring the sheets of ``Electric garden.xlsx`` so the output
can be read back by ``load_xlsx``.  The first column is always the barcode,
which is a property rather than a model field.  Foreign keys are written as the
related object's barcode.

The default output directory is ``ai-assistance`` at the project root (the
parent of the ``src`` directory that holds ``manage.py``), not relative to the
current working directory.

Examples:
    ./manage.py dump_csv
    ./manage.py dump_csv --output-dir ai-assistance
    ./manage.py dump_csv --output-dir ai-assistance --models Plants Plantings
"""

import csv
from datetime import date, datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.models import Container, Packet, Plant, Planting

# Project root: the parent of the directory containing ``manage.py`` (``src``).
PROJECT_ROOT = Path(settings.BASE_DIR).parent

# Import order matters: parents before children, matching ``load_xlsx``.
MODELS = [Container, Plant, Packet, Planting]


def _text(value):
    """Render a value the way a spreadsheet cell would."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class Command(BaseCommand):
    help = 'Dump the Container, Plant, Packet and Planting tables to CSV files.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            default='ai-assistance',
            help='Directory to write the CSV files into, relative to the project root (default: ai-assistance).',
        )
        parser.add_argument(
            '--models',
            nargs='+',
            metavar='MODEL',
            help='Only dump these models (by plural sheet name, e.g. Plants).',
        )

    def handle(self, *args, **options):
        output_dir = Path(options['output_dir'])
        if not output_dir.is_absolute():
            output_dir = PROJECT_ROOT / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        models = MODELS
        if options['models']:
            wanted = {name.lower() for name in options['models']}
            models = [model for model in MODELS if model._meta.verbose_name_plural.lower() in wanted]
            unknown = wanted - {model._meta.verbose_name_plural.lower() for model in models}
            if unknown:
                raise CommandError(f'Unknown model(s): {", ".join(sorted(unknown))}')

        for model in models:
            count = self._dump_model(model, output_dir)
            self.stdout.write(f'{model._meta.verbose_name_plural.title()}: wrote {count} row(s).')

    def _dump_model(self, model, output_dir):
        """Write one CSV per model.  Returns the number of rows written."""
        fields = [field for field in model._meta.fields if field.name != 'id']
        header = ['Barcode'] + [field.verbose_name.title() for field in fields]

        path = output_dir / f'{model._meta.verbose_name_plural.title()}.csv'
        count = 0
        with path.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for instance in model.objects.all().order_by('pk'):
                row = [instance.barcode]
                for field in fields:
                    value = getattr(instance, field.name)
                    if field.is_relation:
                        value = value.barcode if value is not None else None
                    row.append(_text(value))
                writer.writerow(row)
                count += 1
        return count
