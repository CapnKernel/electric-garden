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
