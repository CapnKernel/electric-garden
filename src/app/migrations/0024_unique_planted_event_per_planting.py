from collections import Counter

from django.db import migrations, models


def check_single_planted_event(apps, schema_editor):
    """Assert no planting has more than one ``planted`` event.

    The unique constraint below cannot be added while duplicates exist, so this
    step fails with the offending planting ids instead of a database error.
    """
    PlantingEvent = apps.get_model('app', 'PlantingEvent')

    counts = Counter(PlantingEvent.objects.filter(event_type='planted').values_list('planting_id', flat=True))
    duplicates = sorted(planting_id for planting_id, count in counts.items() if count > 1)
    if duplicates:
        raise RuntimeError('Plantings with more than one planted event: ' + ', '.join(str(pk) for pk in duplicates))


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0023_unset_germination_event_locations'),
    ]

    operations = [
        migrations.RunPython(check_single_planted_event, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='plantingevent',
            constraint=models.UniqueConstraint(
                condition=models.Q(('event_type', 'planted')),
                fields=('planting',),
                name='unique_planted_event_per_planting',
            ),
        ),
    ]
