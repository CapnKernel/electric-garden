from django.shortcuts import render

from .models import Plant, Packet, Planting

def index(request):
    "Just a placeholder for now"

    plants = Plant.objects.all()
    packets = Packet.objects.all()
    plantings = Planting.objects.all()

    context = {
        'plants': plants,
        'packets': packets,
        'plantings': plantings,
    }

    return render(request, 'garden/top.html', context)
