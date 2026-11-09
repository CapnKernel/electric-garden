from typing import ClassVar

from django import forms
from django.utils import timezone

from .models import PlantingEvent


class GerminationRowForm(forms.Form):
    """One row of the container germination form.

    ``germinated`` is a checkbox; ``score`` is a 0-3 slider rendered in the
    template (0 = nothing germinated, 3 = everything germinated).  The slider is
    always active and is bound to a hidden ``score`` field, so it only submits a
    value once the user has used it.  Interacting with the slider also ticks
    ``germinated``; ticking ``germinated`` without choosing a score is an error.
    """

    planting_id = forms.IntegerField(widget=forms.HiddenInput)
    germinated = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'x-model': 'germinated'}),
    )
    # Hidden field driven by Alpine (``:value="score ?? ''"``): empty until the
    # template's slider is used, so no default score is ever submitted.
    score = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=3,
        widget=forms.HiddenInput(attrs={':value': "score ?? ''"}),
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('germinated') and cleaned.get('score') is None:
            self.add_error('score', 'Choose a germination score between 0 and 3.')
        return cleaned


class PlantingEventForm(forms.ModelForm):
    """Form for editing a single planting event."""

    # CSS classes applied to each field's widget in ``__init__``.
    widget_classes = (
        ('event_type', 'form-select'),
        ('date', 'form-control datepicker'),
        ('planted_in', 'form-select'),
        ('location', 'form-control'),
        ('notes', 'form-control'),
    )

    class Meta:
        model = PlantingEvent
        fields = ('event_type', 'date', 'planted_in', 'location', 'notes')
        widgets: ClassVar = {
            # A text input enhanced by Flatpickr (see ``static/js/datepicker.js``).
            # ``format`` must be ISO-8601 so the underlying value is unambiguous;
            # Flatpickr displays it as ``d-mmm-yy`` via its ``altFormat``.  The
            # ``datepicker`` class is applied via ``widget_classes``.
            'date': forms.DateInput(attrs={'autocomplete': 'off'}, format='%Y-%m-%d'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, planting=None, **kwargs):
        super().__init__(*args, **kwargs)
        for name, css_class in self.widget_classes:
            widget = self.fields[name].widget
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {css_class}'.strip()
        # Set when the calculated date default is today, so the template can
        # disable the "Today" button (it would be a no-op).
        self.today_button_disabled = False
        # Fields pre-filled from a previous event, so the template can flag them
        # and prompt the user to check the values.
        self.defaulted_fields = set()
        if planting is not None and self.instance.pk is None and not self.is_bound:
            self._apply_defaults(planting)

    def _apply_defaults(self, planting):
        """Pre-fill a new event from existing planting events.

        The event type follows the planting's progress: an existing germinated
        event means the next event is likely a transplant, an existing planted
        event means germination, and a planting with no events is being planted.
        A planting with only other event types gets no default.  Date, container
        and location are copied from the most recent event of the default type
        across all plantings, if there is one.
        """
        event_type = self._default_event_type(planting)
        if event_type is None:
            return
        self.initial['event_type'] = event_type
        event = PlantingEvent.objects.filter(event_type=event_type).order_by('-date', '-pk').first()
        if event is None:
            return
        self.initial['date'] = event.date
        self.initial['planted_in'] = event.planted_in_id
        self.initial['location'] = event.location
        self.defaulted_fields = {'date', 'planted_in', 'location'}
        self.today_button_disabled = event.date == timezone.localdate()

    @staticmethod
    def _default_event_type(planting):
        """Return the event type to default to for a new event, or ``None``."""
        event_types = set(planting.events.values_list('event_type', flat=True))
        if PlantingEvent.EventType.GERMINATED in event_types:
            return PlantingEvent.EventType.TRANSPLANTED
        if PlantingEvent.EventType.PLANTED in event_types:
            return PlantingEvent.EventType.GERMINATED
        if not event_types:
            return PlantingEvent.EventType.PLANTED
        return None
