"""Tests for the garden template filters and tags."""

from datetime import date, timedelta

import pytest
from django.template import Context, Engine, Template, TemplateSyntaxError
from django.utils import timezone

from app.models import Packet, Plant
from app.templatetags.garden_tags import ago, friendly_date, join_model_ids


def _render(source):
    return Template(source).render(Context())


def test_heading_wraps_content():
    rendered = _render('{% load app_tags %}{% heading %}Page title{% endheading %}')

    assert rendered == '<h1>Page title</h1>'


def test_heading_blank_renders_nothing():
    rendered = _render('{% load app_tags %}{% heading %}   \n  {% endheading %}')

    assert rendered.strip() == ''


def test_heading_block_can_be_overridden():
    """The block nested in ``{% heading %}`` must remain visible to child templates."""
    engine = Engine(
        loaders=[
            (
                'django.template.loaders.locmem.Loader',
                {
                    'base.html': (
                        '{% load app_tags %}{% heading %}{% block h1 %}Default{% endblock h1 %}{% endheading %}'
                    ),
                    'child.html': '{% extends "base.html" %}{% block h1 %}Child title{% endblock h1 %}',
                },
            )
        ],
        libraries={'app_tags': 'app.templatetags.app_tags'},
    )

    assert engine.get_template('child.html').render(Context()) == '<h1>Child title</h1>'


@pytest.mark.parametrize(
    ('tag', 'expected'),
    [
        ('card_title', '<h2 class="card-title h5 mb-0">Title</h2>'),
        ('section_title', '<h3 class="h4">Title</h3>'),
        ('subsection_title', '<h3 class="h5">Title</h3>'),
        ('alert_title', '<h3 class="alert-heading h5">Title</h3>'),
        ('page_alert_title', '<h2 class="alert-heading h5">Title</h2>'),
    ],
)
def test_role_headings(tag, expected):
    rendered = _render(f'{{% load app_tags %}}{{% {tag} %}}Title{{% end{tag} %}}')

    assert rendered == expected


def test_role_heading_blank_renders_nothing():
    rendered = _render('{% load app_tags %}{% card_title %}   \n  {% endcard_title %}')

    assert rendered.strip() == ''


def test_join_model_ids_defaults_to_comma(db):
    first = Plant.objects.create(id=1, code='A', name='A')
    second = Plant.objects.create(id=2, code='B', name='B')

    assert join_model_ids([first, second]) == '1,2'


def test_join_model_ids_accepts_separator(db):
    first = Plant.objects.create(id=1, code='A', name='A')
    second = Plant.objects.create(id=2, code='B', name='B')

    assert join_model_ids([first, second], '|') == '1|2'


def test_join_model_ids_empty_list():
    assert join_model_ids([]) == ''


def test_join_model_ids_rejects_mixed_models(db):
    plant = Plant.objects.create(id=1, code='A', name='A')
    packet = Packet.objects.create(id=101, plant=plant)

    with pytest.raises(TemplateSyntaxError):
        join_model_ids([plant, packet])


@pytest.fixture
def frozen_today(monkeypatch):
    """Freeze the date ``ago`` measures from."""
    today = date(2026, 11, 9)
    monkeypatch.setattr('app.templatetags.garden_tags.timezone.localdate', lambda: today)
    return today


@pytest.mark.parametrize(
    ('day', 'expected'),
    [
        (date(2026, 11, 9), 'today'),
        (date(2026, 11, 8), '1 day ago'),
        (date(2026, 11, 6), '3 days ago'),
        (date(2026, 11, 2), '1 week ago'),
        (date(2026, 10, 29), '1 week 4 days ago'),
        (date(2026, 10, 19), '3 weeks ago'),
        (date(2026, 11, 10), ''),
    ],
)
def test_ago_renders_weeks_and_days(frozen_today, day, expected):
    assert ago(day) == expected


def test_ago_renders_empty_for_none(frozen_today):
    assert ago(None) == ''


def test_today_renders_as_today():
    assert friendly_date(timezone.localdate()) == 'Today'


def test_other_date_renders_formatted():
    other = timezone.localdate() - timedelta(days=1)
    rendered = friendly_date(other)

    assert rendered != 'Today'
    assert rendered != ''


def test_none_renders_empty():
    assert friendly_date(None) == ''
