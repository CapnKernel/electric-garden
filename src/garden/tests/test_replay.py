"""Tests for the Stage 2 replay service."""

import pytest

from garden.models import Plant, SheetChangeLog
from garden.services import replay


@pytest.fixture
def pending_change(db):
    return SheetChangeLog.objects.create(
        sheet_name='Sheet1',
        range='B2',
        old_values=[['old']],
        new_values=[['new']],
    )


def test_replay_applies_and_stamps_applied_at(pending_change):
    def processor(change):
        return SheetChangeLog.Status.APPLIED, ''

    results = replay(processor=processor)

    assert len(results) == 1
    pending_change.refresh_from_db()
    assert pending_change.status == SheetChangeLog.Status.APPLIED
    assert pending_change.applied_at is not None
    assert pending_change.error_message is None


def test_replay_records_error_message(pending_change):
    def processor(change):
        return SheetChangeLog.Status.ERROR, 'bad data'

    replay(processor=processor)

    pending_change.refresh_from_db()
    assert pending_change.status == SheetChangeLog.Status.ERROR
    assert pending_change.error_message == 'bad data'
    assert pending_change.applied_at is None


def test_replay_rolls_back_everything_on_failure(db):
    first = SheetChangeLog.objects.create(sheet_name='Sheet1', range='A1')
    second = SheetChangeLog.objects.create(sheet_name='Sheet1', range='A2')

    def processor(change):
        if change.pk == second.pk:
            raise RuntimeError('boom')
        return SheetChangeLog.Status.APPLIED, ''

    with pytest.raises(RuntimeError):
        replay(processor=processor)

    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == SheetChangeLog.Status.PENDING
    assert first.applied_at is None
    assert second.status == SheetChangeLog.Status.PENDING


def test_replay_only_touches_requested_statuses(db):
    pending = SheetChangeLog.objects.create(sheet_name='Sheet1', range='A1')
    applied = SheetChangeLog.objects.create(
        sheet_name='Sheet1',
        range='A2',
        status=SheetChangeLog.Status.APPLIED,
    )

    def processor(change):
        return SheetChangeLog.Status.APPLIED, ''

    results = replay(processor=processor, statuses=[SheetChangeLog.Status.PENDING])

    assert [result.change.pk for result in results] == [pending.pk]
    applied.refresh_from_db()
    assert applied.status == SheetChangeLog.Status.APPLIED


def test_replay_persists_conflict_message(db):
    plant = Plant.objects.create(id=1, code='BR', name='Beetroot')
    change = SheetChangeLog.objects.create(
        sheet_name='Plants',
        range='C2',
        key='P=1',
        column_name='Name',
        old_values=[['Beetroot']],
        new_values=[['Detroit']],
    )
    # Django-side change means the sheet's old value no longer matches.
    plant.name = 'Kale'
    plant.save()

    results = replay()

    assert results[0].status == SheetChangeLog.Status.CONFLICT
    change.refresh_from_db()
    assert change.status == SheetChangeLog.Status.CONFLICT
    assert change.error_message
    assert 'Kale' in change.error_message
    assert change.applied_at is None
    plant.refresh_from_db()
    assert plant.name == 'Kale'


def test_replay_without_processor_leaves_rows_unchanged(pending_change):
    results = replay(processor=None)

    assert len(results) == 1
    pending_change.refresh_from_db()
    assert pending_change.status == SheetChangeLog.Status.PENDING


def test_replay_dry_run_rolls_back(db):
    plant = Plant.objects.create(id=1, code='BR', name='Beetroot')
    change = SheetChangeLog.objects.create(
        sheet_name='Plants',
        range='C2',
        key='P=1',
        column_name='Name',
        new_values=[['Changed']],
    )

    results = replay(dry_run=True)

    assert len(results) == 1
    assert results[0].status == SheetChangeLog.Status.APPLIED
    plant.refresh_from_db()
    change.refresh_from_db()
    assert plant.name == 'Beetroot'
    assert change.status == SheetChangeLog.Status.PENDING
    assert change.applied_at is None
