from django.shortcuts import render

from .models import Packet, Plant, Planting


def top(request):
    """Dashboard showing counts of active plants, packets and plantings."""
    return render(request, 'app/top.html')


def dash_stats(request):
    """HTMX endpoint returning the dashboard statistics fragment."""
    ctx = {
        'plant_count': Plant.objects.filter(deleted=False).count(),
        'packet_count': Packet.objects.filter(deleted=False).count(),
        'planting_count': Planting.objects.filter(deleted=False).count(),
    }

    return render(request, 'app/top.html#dash-stats-cards', ctx)
