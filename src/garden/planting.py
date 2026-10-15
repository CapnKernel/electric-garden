"""Views for editing plantings and their events."""

from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import PlantingEventForm, PlantingForm
from .models import Planting, PlantingEvent
from .scan import render_scan_result


def planting_edit(request, pk):
    """Edit a planting and its events.

    GET shows the planting form plus a formset of its events; POST saves both
    and redirects back to the scan result for that planting.
    """
    planting = get_object_or_404(Planting, pk=pk)
    if request.method == 'POST':
        form = PlantingForm(request.POST, instance=planting)
        if form.is_valid():
            form.save()
            return redirect(f'{reverse("scan")}?barcode={planting.barcode}')
    else:
        form = PlantingForm(instance=planting)

    context = {
        'planting': planting,
        'form': form,
        'event_form': PlantingEventForm(),
    }
    return render(request, 'garden/planting_edit.html', context)


def planting_result(request, pk):
    """Return the ``scan-result`` fragment for a planting (GET).

    Used as the htmx target when cancelling an event form, so the scan result
    is restored without a full page load.
    """
    planting = get_object_or_404(Planting, pk=pk)
    return render_scan_result(request, planting)


def planting_event_create(request, pk):
    """Create a new event for a planting.

    GET returns the event form; POST saves the event and re-renders the scan
    result for the planting.
    """
    planting = get_object_or_404(Planting, pk=pk)
    if request.method == 'POST':
        form = PlantingEventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.planting = planting
            event.save()
            return render_scan_result(request, planting)
    else:
        form = PlantingEventForm()
    return render(
        request,
        'garden/partials/planting_event_form.html',
        {'planting': planting, 'form': form, 'event': None},
    )


def planting_event_edit(request, pk):
    """Edit an existing planting event.

    GET returns the event form; POST saves the event and re-renders the scan
    result for the event's planting.
    """
    event = get_object_or_404(PlantingEvent, pk=pk)
    if request.method == 'POST':
        form = PlantingEventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            return render_scan_result(request, event.planting)
    else:
        form = PlantingEventForm(instance=event)
    return render(
        request,
        'garden/partials/planting_event_form.html',
        {'planting': event.planting, 'form': form, 'event': event},
    )


@require_POST
def planting_event_delete(request, pk):
    """Delete a planting event and re-render the scan result for its planting."""
    event = get_object_or_404(PlantingEvent, pk=pk)
    planting = event.planting
    event.delete()
    return render_scan_result(request, planting)
