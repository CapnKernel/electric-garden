"""Views for editing plantings and their events."""

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import GerminationRowForm, PlantingEventForm, PlantingForm
from .models import Container, Planting, PlantingEvent
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
            changed = form.has_changed()
            planting = form.save()
            if changed:
                planting.mark_scanned()
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
            planting.mark_scanned()
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
            changed = form.has_changed()
            form.save()
            if changed:
                event.planting.mark_scanned()
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


def _container_plantings(container):
    """Return the plantings currently planted in ``container``.

    A planting is "in" the container when its most recent event that names a
    container (``planted_in``) points at this container.  This means a planting
    that was later transplanted elsewhere is no longer listed here.
    """
    return container.plantings


def _germination_rows(container):
    """Build the initial data for the container germination form rows.

    ``score`` is the planting's recorded score, or ``None`` when none has been
    set; there is deliberately no default so an untouched slider is unset.
    """
    return [
        {
            'planting_id': planting.pk,
            'germinated': planting.germinated is not None,
            'score': planting.germinated,
        }
        for planting in _container_plantings(container)
    ]


def container_germination(request, pk):
    """Show and save the germination state of a container's plantings.

    GET renders a full page titled with the container name, one row per
    planting.  POST saves the germination state of each planting; on success it
    redirects to the container's scan page, and on validation failure it
    re-renders the form fragment (via htmx) so nothing entered is lost.
    """
    container = get_object_or_404(Container, pk=pk)
    plantings = _container_plantings(container)

    if request.method == 'POST':
        forms = [GerminationRowForm(request.POST, prefix=str(planting.pk)) for planting in plantings]
        if all(form.is_valid() for form in forms):
            try:
                _save_germination(container, plantings, forms)
            except Exception as exc:  # noqa: BLE001 - surface any save failure to the user
                messages.error(request, f'Could not save germination: {exc}')
            else:
                return _scan_redirect(request, container)

        rows = list(zip(plantings, forms))
        return render(
            request,
            'garden/partials/container_germination_form.html',
            {'container': container, 'rows': rows},
        )

    forms = [GerminationRowForm(initial=row, prefix=str(row['planting_id'])) for row in _germination_rows(container)]
    rows = list(zip(plantings, forms))
    return render(request, 'garden/container_germination.html', {'container': container, 'rows': rows})


def _scan_redirect(request, container):
    """Redirect to the container's scan page, honouring htmx and plain requests."""
    scan_url = f'{reverse("scan")}?barcode={container.barcode}'
    if request.headers.get('HX-Request'):
        response = HttpResponse(status=204)
        response['HX-Redirect'] = scan_url
        return response
    return redirect(scan_url)


def _save_germination(container, plantings, forms):
    """Persist the germination state from ``forms`` onto ``plantings``.

    A planting whose row is checked gets its ``germinated`` score set and a
    ``germinated`` event created (or updated) dated today.  A planting whose
    row is unchecked has its ``germinated`` cleared and any existing
    ``germinated`` event removed.
    """
    today = timezone.localdate()
    with transaction.atomic():
        for planting, form in zip(plantings, forms):
            germinated = form.cleaned_data['germinated']
            score = form.cleaned_data['score'] if germinated else None
            changed = planting.germinated != score
            planting.germinated = score
            planting.save(update_fields=['germinated'])

            event = (
                planting.events.filter(event_type=PlantingEvent.EventType.GERMINATED).order_by('-date', '-pk').first()
            )
            if germinated:
                if event is None:
                    PlantingEvent.objects.create(
                        planting=planting,
                        event_type=PlantingEvent.EventType.GERMINATED,
                        date=today,
                        planted_in=container,
                    )
                    changed = True
                elif event.date != today or event.planted_in_id != container.pk:
                    event.date = today
                    event.planted_in = container
                    event.save(update_fields=['date', 'planted_in'])
                    changed = True
            elif event is not None:
                event.delete()
                changed = True

            if changed:
                planting.mark_scanned()
