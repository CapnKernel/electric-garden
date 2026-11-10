"""Views for managing plantings and their events."""

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_htmx.http import HttpResponseClientRedirect

from .forms import GerminationRowForm, PlantingCreateForm, PlantingEventForm
from .models import Container, Packet, Planting, PlantingEvent
from .scan import render_scan_result


def planting_create(request):
    """Create a planting together with its first ``planted`` event.

    GET renders the form; a ``?packet=`` argument fixes the packet select to that
    packet.  POST creates both records in one transaction and redirects to the
    new planting's detail page.
    """

    def locked_packet():
        """Return the packet named by a ``?packet=`` GET argument, or ``None``."""
        packet_id = request.GET.get('packet')
        if not packet_id:
            return None
        return get_object_or_404(Packet, pk=packet_id)

    packet = locked_packet()
    if request.method == 'POST':
        form = PlantingCreateForm(request.POST, packet=packet)
        if form.is_valid():
            with transaction.atomic():
                planting = form.save()
                PlantingEvent.objects.create(
                    planting=planting,
                    event_type=PlantingEvent.EventType.PLANTED,
                    date=form.cleaned_data['date'],
                    planted_in=form.cleaned_data['planted_in'],
                    location=form.cleaned_data['location'],
                    notes=form.cleaned_data['notes'],
                )
            return redirect(planting.detail_url)
    else:
        form = PlantingCreateForm(packet=packet)
    return render(request, 'app/planting_create.html', {'form': form, 'packet': packet})


def planting_event_create(request, pk):
    """Create a new event for a planting.

    GET returns the event form; POST saves the event and re-renders the scan
    result for the planting.
    """
    planting = get_object_or_404(Planting, pk=pk)
    if request.method == 'POST':
        form = PlantingEventForm(request.POST, planting=planting)
        if form.is_valid():
            event = form.save(commit=False)
            event.planting = planting
            event.save()
            planting.mark_scanned()
            return render_scan_result(request, planting)
    else:
        form = PlantingEventForm(planting=planting)
    return render(
        request,
        'app/scan.html#planting-event-form',
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
        'app/scan.html#planting-event-form',
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

    A planting is "in" the container when its most recent located event (see
    ``Container.plantings``) records this container.  A later transplant, into
    another container or to a free-text location, means it is no longer listed
    here.
    """
    return container.plantings


def _germination_rows(plantings):
    """Build the initial data for the germination form rows.

    ``score`` is the planting's recorded score, or ``None`` when none has been
    set; there is deliberately no default so an untouched slider is unset.
    """
    return [
        {
            'planting_id': planting.pk,
            'germinated': planting.germinated is not None,
            'score': planting.germinated,
        }
        for planting in plantings
    ]


def _germination(request, obj, plantings, germination_url, heading):
    """Show and save the germination state of ``plantings``.

    Shared by the container and planting germination views.  ``obj`` is the
    object the form belongs to (used for the redirect and admin link),
    ``germination_url`` is the form's submit target and ``heading`` titles the
    page.  GET renders a full page with one row per planting.  POST saves the
    germination state of each planting; on success it redirects to ``obj``'s
    scan page, and on validation failure it re-renders the form fragment (via
    htmx) so nothing entered is lost.
    """
    if request.method == 'POST':
        forms = [GerminationRowForm(request.POST, prefix=str(planting.pk)) for planting in plantings]
        if all(form.is_valid() for form in forms):
            try:
                _save_germination(plantings, forms)
            except Exception as exc:  # noqa: BLE001 - surface any save failure to the user
                messages.error(request, f'Could not save germination: {exc}')
            else:
                return _detail_redirect(request, obj)

        return render(
            request,
            'app/germination.html#germination-form',
            _germination_context(obj, plantings, forms, germination_url, heading),
        )

    forms = [GerminationRowForm(initial=row, prefix=str(row['planting_id'])) for row in _germination_rows(plantings)]
    return render(
        request,
        'app/germination.html',
        _germination_context(obj, plantings, forms, germination_url, heading),
    )


def _germination_context(obj, plantings, forms, germination_url, heading):
    """Build the context shared by the full page and htmx fragment render."""
    return {
        'rows': list(zip(plantings, forms)),
        'heading': heading,
        'germination_url': germination_url,
        'detail_url': obj.detail_url,
        'admin_url': obj.admin_url,
    }


def container_germination(request, pk):
    """Show and save the germination state of a container's plantings."""
    container = get_object_or_404(Container, pk=pk)
    return _germination(
        request,
        obj=container,
        plantings=_container_plantings(container),
        germination_url=reverse('app:container_germination', kwargs={'pk': container.pk}),
        heading=f'Germination - {container.name} ({container.barcode})',
    )


def planting_germination(request, pk):
    """Show and save the germination state of a single planting."""
    planting = get_object_or_404(Planting, pk=pk)
    return _germination(
        request,
        obj=planting,
        plantings=[planting],
        germination_url=reverse('app:planting_germination', kwargs={'pk': planting.pk}),
        heading=f'Germination - {planting}',
    )


def _detail_redirect(request, obj):
    """Redirect to ``obj``'s detail page, honouring htmx and plain requests."""
    if request.htmx:
        return HttpResponseClientRedirect(obj.detail_url)
    return redirect(obj.detail_url)


def _save_germination(plantings, forms):
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
                    # A germinated event records only when germination was seen;
                    # the container and location stay on the planted event (see
                    # PlantingEvent.clean).
                    PlantingEvent.objects.create(
                        planting=planting,
                        event_type=PlantingEvent.EventType.GERMINATED,
                        date=today,
                    )
                    changed = True
                elif event.date != today:
                    event.date = today
                    event.save(update_fields=['date'])
                    changed = True
            elif event is not None:
                event.delete()
                changed = True

            if changed:
                planting.mark_scanned()
