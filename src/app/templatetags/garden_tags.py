"""Custom template filters and tags for the garden app."""

from django import template
from django.db.models import Model
from django.template import TemplateSyntaxError
from django.utils import timezone
from django.utils.formats import date_format

register = template.Library()


@register.filter
def join_model_ids(value, arg=','):
    """Return a separator-joined string of the primary keys of model instances.

    All elements must be instances of the same model type.
    """
    instances = list(value)
    if not instances:
        return ''

    model_type = type(instances[0])
    if not issubclass(model_type, Model):
        raise TemplateSyntaxError('The "join_model_ids" filter expects model instances.')
    if any(not isinstance(instance, model_type) for instance in instances):
        raise TemplateSyntaxError('The "join_model_ids" filter expects all elements to be the same model type.')

    return arg.join(str(instance.pk) for instance in instances)


@register.filter
def ago(value):
    """Say how long before today that ``value`` was, e.g. '3 weeks 2 days ago'.

    A date today renders as ``today``; a future date (or no date) renders as an
    empty string.
    """
    if value is None:
        return ''
    days = (timezone.localdate() - value).days
    if days < 0:
        return ''
    if days == 0:
        return 'today'
    weeks, days = divmod(days, 7)
    parts = [f'{count} {unit}{"s" if count > 1 else ""}' for count, unit in ((weeks, 'week'), (days, 'day')) if count]
    return f'{" ".join(parts)} ago'


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
