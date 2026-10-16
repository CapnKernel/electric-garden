"""Tests for the garden template filters."""

from datetime import timedelta

from django.utils import timezone

from garden.templatetags.garden_extras import friendly_date


def test_today_renders_as_today():
    assert friendly_date(timezone.localdate()) == 'Today'


def test_other_date_renders_formatted():
    other = timezone.localdate() - timedelta(days=1)
    rendered = friendly_date(other)

    assert rendered != 'Today'
    assert rendered != ''


def test_none_renders_empty():
    assert friendly_date(None) == ''
