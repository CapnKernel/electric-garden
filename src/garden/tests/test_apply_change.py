"""Tests for the Stage 2 apply_change processor."""

import pytest

from garden.models import Plant, SheetChangeLog
from garden.services import apply_change, field_name_for_header, model_for_sheet


@pytest.fixture
def plant(db):
    return Plant.objects.create(id=1, code='BR', name='Beetroot')


def _change(**overrides):
    defaults = {
        'sheet_name': 'Plants',
        'range': 'C2',
        'key': 'P=1',
        'column_name': 'Name',
        'new_values': [['Beetroot, Detroit']],
    }
    defaults.update(overrides)
    return SheetChangeLog.objects.create(**defaults)


def test_model_for_sheet_drops_plural_s():
    assert model_for_sheet('Plants') is Plant
    assert model_for_sheet('Nonsense') is None


def test_field_name_for_header_matches_field():
    assert field_name_for_header(Plant, 'Name') == 'name'
    assert field_name_for_header(Plant, 'Spacing') == 'spacing'


def test_field_name_for_header_applies_aliases():
    assert field_name_for_header(Plant, '🗑') == 'deleted'


def test_field_name_for_header_ignores_unknown():
    assert field_name_for_header(Plant, 'Age') is None


def test_apply_change_updates_instance(plant):
    change = _change()
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.APPLIED
    assert message == ''
    plant.refresh_from_db()
    assert plant.name == 'Beetroot, Detroit'


def test_apply_change_errors_without_key(plant):
    change = _change(key=None)
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.ERROR
    assert 'key' in message


def test_apply_change_errors_without_column_name(plant):
    change = _change(column_name=None)
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.ERROR
    assert 'column_name' in message


def test_apply_change_errors_for_unknown_sheet(plant):
    change = _change(sheet_name='Nonsense')
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.ERROR
    assert 'No model' in message


def test_apply_change_errors_for_unknown_column(plant):
    change = _change(column_name='Age')
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.ERROR
    assert 'does not map' in message


def test_apply_change_creates_missing_instance(plant):
    change = _change(key='P=999', new_values=[['Kale']])
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.APPLIED
    assert 'Created' in message
    created = Plant.objects.get(pk=999)
    assert created.name == 'Kale'
    assert created.barcode == 'P=999'


def test_apply_change_errors_for_invalid_barcode(plant):
    change = _change(key='not-a-barcode')
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.ERROR
    assert 'Invalid barcode' in message


def test_apply_change_errors_for_barcode_column(plant):
    change = _change(column_name='Barcode')
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.ERROR
    assert 'barcode' in message.lower()


def test_apply_change_coerces_boolean(plant):
    change = _change(column_name='🗑', new_values=[['TRUE']])
    status, _ = apply_change(change)

    assert status == SheetChangeLog.Status.APPLIED
    plant.refresh_from_db()
    assert plant.deleted is True


def test_apply_change_clears_nullable_value_when_blank(plant):
    plant.spacing = '15'
    plant.save()
    change = _change(column_name='Spacing', new_values=[['']])
    status, _ = apply_change(change)

    assert status == SheetChangeLog.Status.APPLIED
    plant.refresh_from_db()
    assert plant.spacing is None


def test_apply_change_errors_when_blanking_required_value(plant):
    change = _change(column_name='Name', new_values=[['']])
    status, message = apply_change(change)

    assert status == SheetChangeLog.Status.ERROR
    assert 'Could not save' in message
    plant.refresh_from_db()
    assert plant.name == 'Beetroot'
