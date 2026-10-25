from django.shortcuts import render

from .models import Packet, Plant, Planting


def top(request):
    """Dashboard showing counts of active plants, packets and plantings."""
    context = {
        'plant_count': Plant.objects.filter(deleted=False).count(),
        'packet_count': Packet.objects.filter(deleted=False).count(),
        'planting_count': Planting.objects.filter(deleted=False).count(),
    }
    return render(request, 'app/top.html', context)
