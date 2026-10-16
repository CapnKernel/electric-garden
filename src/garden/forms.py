from django import forms

from .models import Planting, PlantingEvent


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


class PlantingForm(forms.ModelForm):
    """Form for editing a planting."""

    # CSS classes applied to each field's widget in ``__init__``.
    widget_classes = {
        'packet': 'form-select',
        'germinated': 'form-control',
        'deleted': 'form-check-input',
    }

    class Meta:
        model = Planting
        fields = ('packet', 'germinated', 'deleted')
        widgets = {
            'germinated': forms.NumberInput(attrs={'min': 0, 'max': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, css_class in self.widget_classes.items():
            widget = self.fields[name].widget
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {css_class}'.strip()


class PlantingEventForm(forms.ModelForm):
    """Form for editing a single planting event."""

    # CSS classes applied to each field's widget in ``__init__``.
    widget_classes = {
        'event_type': 'form-select',
        'date': 'form-control datepicker',
        'planted_in': 'form-select',
        'location': 'form-control',
        'notes': 'form-control',
    }

    class Meta:
        model = PlantingEvent
        fields = ('event_type', 'date', 'planted_in', 'location', 'notes')
        widgets = {
            # A text input enhanced by Flatpickr (see ``static/js/datepicker.js``).
            # ``format`` must be ISO-8601 so the underlying value is unambiguous;
            # Flatpickr displays it as ``d-mmm-yy`` via its ``altFormat``.  The
            # ``datepicker`` class is applied via ``widget_classes``.
            'date': forms.DateInput(attrs={'autocomplete': 'off'}, format='%Y-%m-%d'),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, css_class in self.widget_classes.items():
            widget = self.fields[name].widget
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {css_class}'.strip()
