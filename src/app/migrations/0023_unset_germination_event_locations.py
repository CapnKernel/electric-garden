from django.db import migrations


def unset_germination_event_locations(apps, schema_editor):
    "Clear ``planted_in`` and ``location`` from every ``germinated`` event"

    PlantingEvent = apps.get_model('app', 'PlantingEvent')
    PlantingEvent.objects.filter(event_type='germinated').update(planted_in=None, location=None)


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0022_check_germination_event_locations'),
    ]

    operations = [
        # Irreversible: the cleared values are duplicates of the preceding
        # planted or transplanted event, so there is nothing to restore.
        migrations.RunPython(unset_germination_event_locations, migrations.RunPython.noop),
    ]
