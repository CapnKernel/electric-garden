from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

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


@require_GET
def schedule_list(request):
    """List every planting schedule, in default order.

    The model's default ordering applies: priority (highest first), then plant,
    then start week.  Inactive schedules and schedules for deleted plants are
    included so they can be reviewed.
    """
    schedules = PlantingSchedule.objects.select_related('plant')
    add_url = reverse('admin:app_plantingschedule_add')
    return render(request, 'app/schedule.html', {'schedules': schedules, 'add_url': add_url})
