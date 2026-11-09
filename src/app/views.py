from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .models import Container, Packet, Plant, Planting, PlantingSchedule


@require_GET
def top(request):
    """Dashboard showing counts of active plants, packets and plantings."""
    return render(request, 'app/top.html')


@require_GET
def dash_stats(request):
    """HTMX endpoint returning the dashboard statistics fragment."""
    ctx = {
        'plant_count': Plant.objects.filter(deleted=False).count(),
        'packet_count': Packet.objects.filter(deleted=False).count(),
        'planting_count': Planting.objects.filter(deleted=False).count(),
        'container_count': Container.objects.count(),
    }

    return render(request, 'app/top.html#dash-stats-cards', ctx)


@require_GET
def plant_now(request):
    """HTMX endpoint grouping the current week's planting schedules by status.

    Rows are split into due, already planted and overdue, using
    ``PlantingSchedule.plant_status``.  A plant with overlapping schedules is listed
    once, under its earliest-starting matching schedule.
    """
    today = timezone.localdate()
    schedules = PlantingSchedule.for_date(today).filter(plant__deleted=False).select_related('plant')

    status = PlantingSchedule.Status
    groups = {status.DUE: [], status.PLANTED: [], status.OVERDUE: []}
    seen = set()
    for schedule in schedules:
        if schedule.plant_id in seen:
            continue
        seen.add(schedule.plant_id)
        groups[schedule.plant_status(today)].append(
            {
                'schedule': schedule,
                'last': schedule.plant.last_planted_date(),
                'due': schedule.plant_due_date(today) if schedule.repeat_every_weeks else None,
            }
        )

    ctx = {
        'week': today.isocalendar().week,
        'due_rows': groups[status.DUE],
        'planted_rows': groups[status.PLANTED],
        'overdue_rows': groups[status.OVERDUE],
    }
    return render(request, 'app/top.html#plant-now', ctx)


def _schedule_context(highlight_id=None):
    """Context for the schedule page and its HTMX fragment."""
    return {
        'schedules': PlantingSchedule.objects.select_related('plant').order_by(
            '-active', '-priority', 'start_week', 'plant_id'
        ),
        'add_url': reverse('admin:app_plantingschedule_add'),
        'highlight_id': highlight_id,
    }


@require_GET
def schedule_list(request):
    """List every planting schedule, active first.

    Within the active/inactive groups the order is priority (highest first),
    then plant, then start week.  Inactive schedules and schedules for deleted
    plants are included so they can be reviewed.
    """
    return render(request, 'app/schedule.html', _schedule_context())


@require_GET
def schedule_contents(request):
    """HTMX endpoint returning the schedule table fragment."""
    return render(request, 'app/schedule.html#schedule-contents', _schedule_context())


@require_POST
def schedule_toggle(request, pk):
    """Toggle a planting schedule's active state and return the updated list."""
    schedule = get_object_or_404(PlantingSchedule, pk=pk)
    schedule.active = not schedule.active
    schedule.save(update_fields=['active'])
    return render(
        request,
        'app/schedule.html#schedule-contents',
        _schedule_context(highlight_id=schedule.pk),
    )


@require_POST
def schedule_reorder(request):
    """Move a schedule after another and re-space that group's priorities.

    ``dragged`` is the schedule being moved; ``after`` is the schedule it should
    follow, or blank to move it to the top of its active/inactive group.
    """
    try:
        dragged_id = int(request.POST.get('dragged', ''))
        after_id = int(request.POST['after']) if request.POST.get('after') else None
    except (TypeError, ValueError):
        return HttpResponseBadRequest('Invalid schedule ids.')

    dragged = get_object_or_404(PlantingSchedule, pk=dragged_id)
    after = get_object_or_404(PlantingSchedule, pk=after_id) if after_id is not None else None
    if after is not None and after.active != dragged.active:
        return HttpResponseBadRequest('Schedules must be in the same active/inactive group.')

    siblings = list(
        PlantingSchedule.objects.filter(active=dragged.active)
        .exclude(pk=dragged.pk)
        .order_by('-priority', 'start_week', 'plant_id')
    )
    if after is None:
        index = 0
    else:
        index = next((position + 1 for position, schedule in enumerate(siblings) if schedule.pk == after.pk), None)
        if index is None:
            return HttpResponseBadRequest('The after schedule is not in the same active/inactive group.')
    siblings.insert(index, dragged)

    total = len(siblings)
    for position, schedule in enumerate(siblings):
        schedule.priority = (total - position) / (total + 1)
    PlantingSchedule.objects.bulk_update(siblings, ['priority'])
    return render(request, 'app/schedule.html#schedule-contents', _schedule_context())
