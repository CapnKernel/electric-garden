from django.db import migrations
from django.db.models import Q


def check_germination_event_locations(apps, schema_editor):
    """Assert germination events do not disagree with the preceding location.

    For every ``germinated`` event, the immediately preceding ``planted`` or
    ``transplanted`` event (in ``date``, ``pk`` order) of the same planting is
    used as the authority for where the planting was.  Any ``planted_in`` or
    ``location`` recorded on the germination event must match it, otherwise the
    germination event carries data that cannot be safely dropped.

    Unset values on the germination event are not checked: they duplicate
    nothing, so nothing is lost by dropping them.
    """
    PlantingEvent = apps.get_model('app', 'PlantingEvent')

    germinated_events = PlantingEvent.objects.filter(event_type='germinated').order_by('planting_id', 'date', 'pk')
    for event in germinated_events.iterator():
        preceding = (
            PlantingEvent.objects.filter(planting_id=event.planting_id)
            .filter(Q(date__lt=event.date) | Q(date=event.date, pk__lt=event.pk))
            .filter(event_type__in=['planted', 'transplanted'])
            .order_by('-date', '-pk')
            .first()
        )
        where = f'Germinated event {event.pk} of planting {event.planting_id}'
        if preceding is None:
            assert event.planted_in_id is None and event.location is None, (
                f'{where} has planted_in={event.planted_in_id!r} location={event.location!r} '
                'but no preceding planted or transplanted event to compare against.'
            )
            continue
        if event.planted_in_id is not None:
            assert event.planted_in_id == preceding.planted_in_id, (
                f'{where} has planted_in={event.planted_in_id!r}, but preceding event '
                f'{preceding.pk} has planted_in={preceding.planted_in_id!r}.'
            )
        if event.location is not None:
            assert event.location == preceding.location, (
                f'{where} has location={event.location!r}, but preceding event '
                f'{preceding.pk} has location={preceding.location!r}.'
            )


class Migration(migrations.Migration):
    dependencies = [
        ('app', '0021_alter_container_options'),
    ]

    operations = [
        migrations.RunPython(check_germination_event_locations, migrations.RunPython.noop),
    ]
