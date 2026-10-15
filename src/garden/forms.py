from django import forms

from .models import Planting, PlantingEvent


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
            'germinated': forms.NumberInput(attrs={'min': 0, 'max': 5}),
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
