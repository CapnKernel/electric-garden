from typing import ClassVar

from django import forms
from django.db.models import Q
from django.utils import timezone

from .models import Container, Packet, Planting, PlantingEvent
from .placement import Placement


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
        placement = event.placement
        self.initial['date'] = event.date
        self.initial['planted_in'] = placement.container.pk if placement.container is not None else None
        self.initial['location'] = placement.text
        self.defaulted_fields = {'date', 'planted_in', 'location'}
        self.today_button_disabled = event.date == timezone.localdate()

    @property
    def placement(self):
        """The placement the form was submitted with; valid after ``is_valid()``."""
        if not hasattr(self, 'cleaned_data'):
            return Placement()
        return Placement(container=self.cleaned_data.get('planted_in'), text=self.cleaned_data.get('location'))

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


class PlantingCreateForm(forms.ModelForm):
    """Form for creating a planting and its initial ``planted`` event.

    The planting itself only needs a packet; the remaining fields describe the
    accompanying event.  When ``packet`` is passed in (from a ``?packet=`` GET
    argument) the packet select is fixed to it and disabled, so the planting
    cannot be created against a different packet.
    """

    widget_classes = (
        ('packet', 'form-select'),
        ('date', 'form-control datepicker'),
        ('planted_in', 'form-select'),
        ('location', 'form-control'),
        ('notes', 'form-control'),
    )

    date = forms.DateField(
        label='Date planted',
        # Left empty for the user to fill in, or fill with the "Today" button.
        # A text input enhanced by Flatpickr (see ``static/js/datepicker.js``).
        widget=forms.DateInput(attrs={'autocomplete': 'off'}, format='%Y-%m-%d'),
    )
    planted_in = forms.ModelChoiceField(
        queryset=Container.objects.filter(deleted=False).order_by('name'),
        required=False,
    )
    location = forms.CharField(max_length=100, required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}))

    class Meta:
        model = Planting
        fields = ('packet',)

    def __init__(self, *args, packet=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.locked_packet = packet
        if packet is not None:
            # Keep the locked packet in the queryset: a disabled select is
            # validated against it, and the packet may since have been deleted.
            self.fields['packet'].queryset = Packet.objects.filter(pk=packet.pk)
            self.fields['packet'].initial = packet.pk
            self.fields['packet'].disabled = True
        else:
            self.fields['packet'].queryset = Packet.objects.filter(deleted=False).select_related('plant')
        # Deleted containers are not offered for new plantings, but a container
        # the form was already rendered with (and has been deleted since) must
        # still validate, so it stays in the queryset.
        selected_container = self['planted_in'].value()
        try:
            selected_container = int(selected_container)
        except (TypeError, ValueError):
            selected_container = None
        if selected_container is not None:
            self.fields['planted_in'].queryset = Container.objects.filter(
                Q(deleted=False) | Q(pk=selected_container)
            ).order_by('name')
        for name, css_class in self.widget_classes:
            widget = self.fields[name].widget
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {css_class}'.strip()
        # The placement recorded most recently.  It is deliberately *not* used as
        # the field's initial values, because it would be unusual to plant
        # something over the top of an existing planting.  Instead it is
        # advertised in the labels as a guide, and can be copied into the fields
        # with a button then edited.
        self.default_placement = PlantingEvent.last_placement()
        if self.default_placement.container is not None:
            self.fields['planted_in'].label = f'Planted in last: {self.default_placement.container}'
        if self.default_placement.text:
            self.fields['location'].label = f'Location last: {self.default_placement.text}'

    @property
    def placement(self):
        """The placement the form was submitted with; valid after ``is_valid()``."""
        if not hasattr(self, 'cleaned_data'):
            return Placement()
        return Placement(container=self.cleaned_data.get('planted_in'), text=self.cleaned_data.get('location'))

    def defaults_resubmitted(self):
        """Return the submitted placement if it is unchanged, keyed by label.

        Call after ``is_valid()``.  Copying a default is allowed, but the view
        confirms it with the user, since an unchanged placement may mean the
        copy button was pressed without the value being edited.
        """
        if self.default_placement.is_empty or self.placement != self.default_placement:
            return {}
        details = {}
        if self.default_placement.container is not None:
            details['Planted in'] = str(self.default_placement.container)
        if self.default_placement.text:
            details['Location'] = self.default_placement.text
        return details
