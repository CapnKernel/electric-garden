"""Custom template filters for the garden app."""

from django import template
from django.utils import timezone
from django.utils.formats import date_format

register = template.Library()


@register.filter
def friendly_date(value):
    """Render a date for display.

    A date that falls on today renders as ``Today``; any other date is shown
    using the project's date format.
    """
    if value is None:
        return ''
    if value == timezone.localdate():
        return 'Today'
    return date_format(value)
