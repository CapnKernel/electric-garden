"""Tests for the PlantingSchedule model and the plant-now dashboard fragment."""

from datetime import date

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from app.models import Packet, Plant, Planting, PlantingEvent, PlantingSchedule

# A Monday in ISO week 46 of 2026, used to freeze "today" in the view tests.
TODAY = date(2026, 11, 9)


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='BR', name='Beetroot')


def make_schedule(plant, start_week, end_week, **kwargs):
    """Create a planting schedule that is active unless the test says otherwise."""
    kwargs.setdefault('active', True)
    return PlantingSchedule.objects.create(plant=plant, start_week=start_week, end_week=end_week, **kwargs)


def record_planting(plant, day):
    """Record one ``planted`` event for the plant on ``day``."""
    packet, _ = Packet.objects.get_or_create(plant=plant, defaults={'id': 100 + plant.pk})
    planting, _ = Planting.objects.get_or_create(packet=packet, defaults={'id': 1000 + plant.pk})
    return PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date=day)


@pytest.fixture
def frozen_today(monkeypatch):
    """Freeze ``timezone.localdate()`` for the view and the model helpers."""
    monkeypatch.setattr('app.models.timezone.localdate', lambda: TODAY)
    return TODAY


# --- week matching -----------------------------------------------------------


@pytest.mark.parametrize('week', [40, 42, 44])
def test_unwrapped_schedule_includes_weeks(plant, week):
    schedule = make_schedule(plant, 40, 44)

    assert list(PlantingSchedule.for_week(week)) == [schedule]


@pytest.mark.parametrize('week', [1, 39, 45, 53])
def test_unwrapped_schedule_excludes_other_weeks(plant, week):
    make_schedule(plant, 40, 44)

    assert not PlantingSchedule.for_week(week).exists()


@pytest.mark.parametrize('week', [44, 50, 53, 1, 8])
def test_wrapping_schedule_includes_weeks(plant, week):
    schedule = make_schedule(plant, 44, 8)

    assert list(PlantingSchedule.for_week(week)) == [schedule]


@pytest.mark.parametrize('week', [9, 20, 43])
def test_wrapping_schedule_excludes_other_weeks(plant, week):
    make_schedule(plant, 44, 8)

    assert not PlantingSchedule.for_week(week).exists()


def test_single_week_schedule(plant):
    schedule = make_schedule(plant, 45, 45)

    assert list(PlantingSchedule.for_week(45)) == [schedule]
    assert not PlantingSchedule.for_week(44).exists()
    assert not PlantingSchedule.for_week(46).exists()


def test_for_date_uses_iso_week_not_day_of_month(plant):
    """9 November 2026 is in ISO week 46; week 11 (a naive month guess) must not match."""
    make_schedule(plant, 46, 46)
    make_schedule(plant, 11, 11)

    schedules = PlantingSchedule.for_date(TODAY)

    assert [schedule.start_week for schedule in schedules] == [46]


def test_for_date_matches_january_side_of_wrapping_schedule(plant):
    make_schedule(plant, 44, 8)

    assert PlantingSchedule.for_date(date(2027, 1, 5)).exists()


def test_for_date_defaults_to_today(plant, frozen_today):
    make_schedule(plant, 46, 46)

    assert PlantingSchedule.for_date().exists()


# --- plant helpers -----------------------------------------------------------


def test_plantable_in_and_plant_weeks_without_schedules(plant):
    assert plant.plantable_in(45) is False
    assert plant.plant_weeks_str == '-'
    assert plant.plant_months_str == '-'


def test_plant_weeks_str_lists_active_schedules(plant):
    make_schedule(plant, 40, 44)
    make_schedule(plant, 44, 8, repeat_every_weeks=3)

    assert plant.plant_weeks_str == 'week 40-44, week 44-8 every 3 weeks'


# --- month hints -------------------------------------------------------------


def test_week_label_is_approximate_month():
    assert PlantingSchedule.week_label(7) == 'Feb, week 2ish'
    assert PlantingSchedule.week_label(53) == 'Dec, week 4ish'


def test_month_hint_spans_schedule(plant):
    schedule = make_schedule(plant, 37, 44)

    assert schedule.month_hint == 'Sep, week 1ish - Oct, week 4ish'


def test_month_hint_for_single_week(plant):
    schedule = make_schedule(plant, 38, 38)

    assert schedule.month_hint == 'Sep, week 2ish'


# --- succession --------------------------------------------------------------


@pytest.mark.parametrize('interval', [None, 1])
def test_succession_weeks_without_interval_is_every_week(plant, interval):
    schedule = make_schedule(plant, 40, 44, repeat_every_weeks=interval)

    assert schedule.succession_weeks() == [40, 41, 42, 43, 44]


def test_succession_weeks_every_three_weeks(plant):
    schedule = make_schedule(plant, 40, 52, repeat_every_weeks=3)

    assert schedule.succession_weeks() == [40, 43, 46, 49, 52]


def test_succession_weeks_counts_across_year_end(plant):
    schedule = make_schedule(plant, 44, 8, repeat_every_weeks=4)

    assert schedule.succession_weeks() == [44, 48, 52, 3, 7]


def test_succession_interval_longer_than_window(plant):
    schedule = make_schedule(plant, 40, 41, repeat_every_weeks=4)

    assert schedule.succession_weeks() == [40]


def test_interval_does_not_restrict_week_matching(plant):
    make_schedule(plant, 44, 48, repeat_every_weeks=4)

    assert PlantingSchedule.for_week(45).exists()


def test_next_plant_date_none_without_interval(plant):
    make_schedule(plant, 45, 48)

    assert plant.next_plant_date(TODAY) is None


def test_next_plant_date_none_when_no_schedule(plant):
    assert plant.next_plant_date(TODAY) is None


def test_next_plant_date_starts_this_week_when_never_planted(plant):
    make_schedule(plant, 45, 48, repeat_every_weeks=2)

    assert plant.next_plant_date(TODAY) == date(2026, 11, 9)


def test_next_plant_date_counts_from_last_planting(plant):
    make_schedule(plant, 45, 48, repeat_every_weeks=2)
    packet = Packet.objects.create(id=101, plant=plant)
    planting = Planting.objects.create(id=1001, packet=packet)
    PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date=date(2026, 11, 2))

    assert plant.next_plant_date(TODAY) == date(2026, 11, 16)


def test_next_plant_date_never_in_the_past(plant):
    make_schedule(plant, 45, 48, repeat_every_weeks=2)
    packet = Packet.objects.create(id=101, plant=plant)
    planting = Planting.objects.create(id=1001, packet=packet)
    PlantingEvent.objects.create(planting=planting, event_type=PlantingEvent.EventType.PLANTED, date=date(2026, 10, 1))

    assert plant.next_plant_date(TODAY) == TODAY


# --- active staging ----------------------------------------------------------


def test_schedule_is_active_by_default(plant):
    schedule = PlantingSchedule.objects.create(plant=plant, start_week=46, end_week=46)

    assert schedule.active is True
    assert list(PlantingSchedule.for_week(46)) == [schedule]


def test_inactive_schedule_is_hidden_but_kept(plant):
    schedule = make_schedule(plant, 46, 46, active=False)

    assert PlantingSchedule.objects.filter(pk=schedule.pk).exists()
    assert not PlantingSchedule.for_week(46).exists()


def test_inactive_schedule_hidden_from_plant_helpers(plant):
    make_schedule(plant, 45, 48, repeat_every_weeks=2, active=False)

    assert plant.plantable_in(46) is False
    assert plant.plant_weeks_str == '-'
    assert plant.next_plant_date(TODAY) is None


# --- plant status --------------------------------------------------------------

DUE = PlantingSchedule.Status.DUE
PLANTED = PlantingSchedule.Status.PLANTED
OVERDUE = PlantingSchedule.Status.OVERDUE


def test_one_off_schedule_is_due_when_never_planted(plant):
    schedule = make_schedule(plant, 45, 48)

    assert schedule.plant_status(TODAY) == DUE
    assert schedule.plant_due_date(TODAY) == date(2026, 11, 2)


def test_one_off_schedule_is_planted_within_the_cycle(plant):
    schedule = make_schedule(plant, 45, 48)
    record_planting(plant, date(2026, 11, 2))

    assert schedule.plant_status(TODAY) == PLANTED


def test_one_off_schedule_is_due_again_next_cycle(plant):
    schedule = make_schedule(plant, 45, 48)
    record_planting(plant, date(2025, 11, 3))  # last season, before this cycle's start

    assert schedule.plant_status(TODAY) == DUE


def test_succession_schedule_is_due_when_never_planted(plant):
    schedule = make_schedule(plant, 45, 48, repeat_every_weeks=2)

    assert schedule.plant_status(TODAY) == DUE


def test_succession_schedule_is_planted_before_the_next_planting(plant):
    schedule = make_schedule(plant, 45, 48, repeat_every_weeks=2)
    record_planting(plant, date(2026, 11, 2))

    assert schedule.plant_status(TODAY) == PLANTED
    assert schedule.plant_due_date(TODAY) == date(2026, 11, 16)


def test_succession_schedule_is_due_in_the_week_it_falls_due(plant):
    schedule = make_schedule(plant, 45, 48, repeat_every_weeks=2)
    record_planting(plant, date(2026, 10, 26))

    assert schedule.plant_due_date(TODAY) == TODAY
    assert schedule.plant_status(TODAY) == DUE


def test_succession_schedule_is_overdue_after_its_due_week(plant):
    schedule = make_schedule(plant, 45, 48, repeat_every_weeks=2)
    record_planting(plant, date(2026, 10, 5))

    assert schedule.plant_due_date(TODAY) == date(2026, 10, 19)
    assert schedule.plant_status(TODAY) == OVERDUE


def test_cycle_start_date_handles_a_wrapping_schedule(plant):
    """Week 46 of a 44-8 schedule began in week 44 of the same ISO year."""
    schedule = make_schedule(plant, 44, 8)

    assert schedule.cycle_start_date(TODAY) == date(2026, 10, 26)


def test_cycle_start_date_january_side_of_wrapping_schedule(plant):
    """In week 1 the 44-8 cycle began in week 44 of the previous ISO year."""
    schedule = make_schedule(plant, 44, 8)

    assert schedule.cycle_start_date(date(2027, 1, 5)) == date(2026, 10, 26)


def test_monday_of_clamps_week_53(plant):
    assert PlantingSchedule.monday_of(2027, 53) == date(2027, 12, 27)


# --- dashboard fragment ------------------------------------------------------


def test_plant_now_lists_plant_once_for_overlapping_schedules(authed_client, plant, frozen_today):
    make_schedule(plant, 40, 46)
    make_schedule(plant, 44, 48)

    response = authed_client.get(reverse('app:plant_now'))

    assertContains(response, 'Beetroot')
    assertContains(response, 'week 40-46')
    assert response.content.decode().count('Beetroot') == 1


def test_plant_now_omits_deleted_plant(authed_client, plant, frozen_today):
    make_schedule(plant, 46, 46)
    other = Plant.objects.create(id=2, code='XX', name='Deleted beet', deleted=True)
    make_schedule(other, 46, 46)

    response = authed_client.get(reverse('app:plant_now'))

    assertContains(response, 'Beetroot')
    assertNotContains(response, 'Deleted beet')


def test_plant_now_omits_inactive_schedule_until_activated(authed_client, plant, frozen_today):
    schedule = make_schedule(plant, 46, 46, active=False)

    response = authed_client.get(reverse('app:plant_now'))
    assertNotContains(response, 'Beetroot')

    schedule.active = True
    schedule.save()

    response = authed_client.get(reverse('app:plant_now'))
    assertContains(response, 'Beetroot')


def test_plant_now_groups_rows_by_status(authed_client, plant, frozen_today):
    planted = Plant.objects.create(id=2, code='CB', name='Cabbage')
    overdue = Plant.objects.create(id=3, code='LE', name='Lettuce')
    make_schedule(plant, 45, 48)  # never planted, so due
    make_schedule(planted, 45, 48, repeat_every_weeks=2)
    record_planting(planted, date(2026, 11, 2))  # next planting not yet due
    make_schedule(overdue, 45, 48, repeat_every_weeks=2)
    record_planting(overdue, date(2026, 10, 5))

    response = authed_client.get(reverse('app:plant_now'))

    content = response.content.decode()
    assert content.index('Plant now') < content.index('Beetroot') < content.index('Overdue')
    assert content.index('Overdue') < content.index('Lettuce') < content.index('Already planted')
    assert content.index('Already planted') < content.index('Cabbage')
    assertContains(response, 'since 19 Oct')
    assertContains(response, 'next 16 Nov')


def test_plant_now_shows_a_placeholder_when_nothing_is_plantable(authed_client, db, frozen_today):
    response = authed_client.get(reverse('app:plant_now'))

    assertContains(response, 'Nothing to plant in ISO week 46.')


def test_plant_now_requires_login(client, db):
    response = client.get(reverse('app:plant_now'))

    assert response.status_code == 302


# --- schedule list -----------------------------------------------------------


def test_schedule_list_shows_every_schedule(authed_client, plant):
    other = Plant.objects.create(id=2, code='CB', name='Cabbage')
    make_schedule(plant, 45, 48)
    make_schedule(other, 40, 44)

    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, 'Beetroot')
    assertContains(response, 'Cabbage')


def test_schedule_list_includes_inactive_and_deleted_plant_schedules(authed_client, plant):
    deleted = Plant.objects.create(id=2, code='XX', name='Deleted plant', deleted=True)
    make_schedule(plant, 45, 48, active=False)
    make_schedule(deleted, 46, 46)

    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, 'Beetroot')
    assertContains(response, 'Deleted plant')
    assertContains(response, 'inactive')


def test_schedule_list_orders_by_priority_then_plant(authed_client, plant):
    other = Plant.objects.create(id=2, code='CB', name='Cabbage')
    beetroot_schedule = make_schedule(plant, 45, 48, priority=1)
    cabbage_schedule = make_schedule(other, 40, 44, priority=10)

    response = authed_client.get(reverse('app:schedule'))

    assert list(response.context['schedules']) == [cabbage_schedule, beetroot_schedule]


def test_schedule_list_orders_active_before_inactive(authed_client, plant):
    active = make_schedule(plant, 40, 44, priority=1)
    inactive = make_schedule(plant, 45, 48, priority=10, active=False)

    response = authed_client.get(reverse('app:schedule'))

    assert list(response.context['schedules']) == [active, inactive]


def test_schedule_list_links_to_admin(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, reverse('admin:app_plantingschedule_add'))
    assertContains(response, reverse('admin:app_plantingschedule_change', args=[schedule.pk]))


def test_schedule_page_loads_contents_with_htmx(authed_client, plant):
    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, f'hx-get="{reverse("app:schedule_contents")}"')
    assertContains(response, 'hx-trigger="load"')


def test_schedule_page_has_reorder_indicator(authed_client):
    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, 'id="schedule-spinner"')
    assertContains(response, 'reorder-indicator')
    assertContains(response, "indicator: '#schedule-spinner'")
    assertNotContains(response, 'hx-indicator="#schedule-spinner"')
    assertContains(response, 'Reordering…')


def test_schedule_page_blocks_cross_group_drags(authed_client):
    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, "dropEffect = 'none'")
    assertContains(response, 'Cannot move a schedule between active and inactive groups')


def test_schedule_contents_returns_schedules(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.get(reverse('app:schedule_contents'))

    assert list(response.context['schedules']) == [schedule]


def test_schedule_contents_renders_only_the_partial(authed_client, plant):
    make_schedule(plant, 45, 48)

    response = authed_client.get(reverse('app:schedule_contents'))

    assertContains(response, 'Beetroot')
    assertNotContains(response, '<html')


def test_schedule_page_renders_toggle_button(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, f'hx-post="{reverse("app:schedule_toggle", args=[schedule.pk])}"')


def test_schedule_toggle_deactivates_schedule(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.post(reverse('app:schedule_toggle', args=[schedule.pk]))

    schedule.refresh_from_db()
    assert schedule.active is False
    assertContains(response, 'bg-secondary-subtle')


def test_schedule_toggle_activates_schedule(authed_client, plant):
    schedule = make_schedule(plant, 45, 48, active=False)

    response = authed_client.post(reverse('app:schedule_toggle', args=[schedule.pk]))

    schedule.refresh_from_db()
    assert schedule.active is True
    assertContains(response, 'bg-success-subtle')


def test_schedule_toggle_returns_resorted_list(authed_client, plant):
    toggled = make_schedule(plant, 40, 44, priority=1)
    inactive = make_schedule(plant, 45, 48, priority=10, active=False)

    response = authed_client.post(reverse('app:schedule_toggle', args=[toggled.pk]))

    toggled.refresh_from_db()
    assert toggled.active is False
    assert list(response.context['schedules']) == [inactive, toggled]


def test_schedule_toggle_marks_deactivated_schedule(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.post(reverse('app:schedule_toggle', args=[schedule.pk]))

    assert response.context['highlight_id'] == schedule.pk
    assertContains(response, 'data-toggled="deactivated"')


def test_schedule_toggle_marks_activated_schedule(authed_client, plant):
    schedule = make_schedule(plant, 45, 48, active=False)

    response = authed_client.post(reverse('app:schedule_toggle', args=[schedule.pk]))

    assert response.context['highlight_id'] == schedule.pk
    assertContains(response, 'data-toggled="activated"')


def test_schedule_list_has_no_toggle_mark(authed_client, plant):
    make_schedule(plant, 45, 48)

    response = authed_client.get(reverse('app:schedule'))

    assert response.context['highlight_id'] is None
    assertNotContains(response, 'data-toggled')


def test_schedule_toggle_requires_post(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.get(reverse('app:schedule_toggle', args=[schedule.pk]))

    assert response.status_code == 405


def test_schedule_page_renders_drag_handles(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.get(reverse('app:schedule'))

    assertContains(response, 'draggable="true"')
    assertContains(response, f'data-id="{schedule.pk}"')
    assertContains(response, 'x-data="scheduleReorder')


def test_schedule_reorder_moves_after_schedule(authed_client, plant):
    other = Plant.objects.create(id=2, code='CB', name='Cabbage')
    third = Plant.objects.create(id=3, code='LE', name='Lettuce')
    first = make_schedule(plant, 40, 44)
    second = make_schedule(other, 41, 45)
    third = make_schedule(third, 42, 46)

    response = authed_client.post(
        reverse('app:schedule_reorder'),
        {'dragged': third.pk, 'after': first.pk},
    )

    first.refresh_from_db()
    second.refresh_from_db()
    third.refresh_from_db()
    assert list(response.context['schedules']) == [first, third, second]
    assert first.priority == 0.75
    assert third.priority == 0.5
    assert second.priority == 0.25


def test_schedule_reorder_moves_to_top_when_after_is_blank(authed_client, plant):
    other = Plant.objects.create(id=2, code='CB', name='Cabbage')
    first = make_schedule(plant, 40, 44)
    second = make_schedule(other, 41, 45)

    response = authed_client.post(
        reverse('app:schedule_reorder'),
        {'dragged': second.pk, 'after': ''},
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert list(response.context['schedules']) == [second, first]
    assert second.priority == 2 / 3
    assert first.priority == 1 / 3


def test_schedule_reorder_rejects_cross_group_move(authed_client, plant):
    active = make_schedule(plant, 40, 44)
    inactive = make_schedule(plant, 45, 48, active=False)

    response = authed_client.post(
        reverse('app:schedule_reorder'),
        {'dragged': inactive.pk, 'after': active.pk},
    )

    assert response.status_code == 400
    assertContains(response, 'Schedules must be in the same active/inactive group.', status_code=400)


def test_schedule_reorder_rejects_self_as_after(authed_client, plant):
    schedule = make_schedule(plant, 45, 48)

    response = authed_client.post(
        reverse('app:schedule_reorder'),
        {'dragged': schedule.pk, 'after': schedule.pk},
    )

    assert response.status_code == 400


def test_schedule_reorder_rejects_invalid_ids(authed_client, plant):
    response = authed_client.post(
        reverse('app:schedule_reorder'),
        {'dragged': 'not-an-id', 'after': ''},
    )

    assert response.status_code == 400


def test_schedule_reorder_requires_post(authed_client, plant):
    response = authed_client.get(reverse('app:schedule_reorder'))

    assert response.status_code == 405


# --- admin -------------------------------------------------------------------


def test_plant_admin_renders_planting_schedule_inline(admin_client, plant):
    response = admin_client.get(reverse('admin:app_plant_change', args=[plant.pk]))

    assertContains(response, 'planting_schedules-__prefix__-start_week')
    assertContains(response, 'planting_schedules-__prefix__-start_date')
    assertContains(response, 'planting_schedules-__prefix__-active')


def test_admin_converts_picked_dates_to_iso_weeks(admin_client, plant):
    url = reverse('admin:app_plantingschedule_add')

    response = admin_client.post(
        url,
        {
            'plant': plant.pk,
            'priority': '0',
            'start_date': '2026-11-09',  # ISO week 46
            'end_date': '2026-12-07',  # ISO week 50
            'repeat_every_weeks': '',
            'notes': '',
        },
    )

    assert response.status_code == 302
    schedule = PlantingSchedule.objects.get()
    assert (schedule.start_week, schedule.end_week) == (46, 50)


def test_admin_accepts_a_week_number_for_one_end(admin_client, plant):
    url = reverse('admin:app_plantingschedule_add')

    admin_client.post(
        url,
        {
            'plant': plant.pk,
            'priority': '0',
            'start_date': '2027-01-05',  # ISO week 1, year discarded
            'end_week': 8,
            'repeat_every_weeks': '',
            'notes': '',
        },
    )

    schedule = PlantingSchedule.objects.get()
    assert (schedule.start_week, schedule.end_week) == (1, 8)


def test_admin_requires_a_week_or_a_date(admin_client, plant):
    url = reverse('admin:app_plantingschedule_add')

    response = admin_client.post(url, {'plant': plant.pk, 'priority': '0', 'repeat_every_weeks': '', 'notes': ''})

    assert response.status_code == 200
    assertContains(response, 'Enter a start week number or pick a date.')
    assert not PlantingSchedule.objects.exists()


def test_admin_bulk_actions_toggle_active(admin_client, plant):
    schedule = make_schedule(plant, 46, 46, active=False)
    url = reverse('admin:app_plantingschedule_changelist')
    selection = {'_selected_action': [str(schedule.pk)]}

    admin_client.post(url, {'action': 'activate', **selection})
    schedule.refresh_from_db()
    assert schedule.active is True

    admin_client.post(url, {'action': 'deactivate', **selection})
    schedule.refresh_from_db()
    assert schedule.active is False


def test_admin_bulk_action_leaves_unselected_rows_alone(admin_client, plant):
    selected = make_schedule(plant, 46, 46, active=False)
    untouched = make_schedule(plant, 40, 44, active=False)
    url = reverse('admin:app_plantingschedule_changelist')

    admin_client.post(url, {'action': 'activate', '_selected_action': [str(selected.pk)]})

    selected.refresh_from_db()
    untouched.refresh_from_db()
    assert selected.active is True
    assert untouched.active is False
