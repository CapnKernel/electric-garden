from django.shortcuts import render
from django.views.decorators.http import require_GET

from .models import Container, Packet, Plant, Planting


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
