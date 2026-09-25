import pytest


# FIXME: We may need to change this scope to 'module', 'class' or 'session'
# I don't yet understand the mechanics of this.
@pytest.fixture(scope='function')
def function_fixture(django_user_model):
    return django_user_model.objects.create(
        preferred_name='Bob',
        full_name='Robert Menzies',
        email='bobm@smct.org.au',
    )


def test_shortname_prefers_preferred(client, function_fixture):
    user = function_fixture
    assert user.get_short_name() == 'Bob'


def test_shortname_finds_full_name(client, function_fixture):
    user = function_fixture
    user.preferred_name = ''

    assert user.get_short_name() == 'Robert Menzies'


def test_shortname_finds_email(client, function_fixture):
    user = function_fixture
    user.preferred_name = ''
    user.full_name = ''

    assert user.get_short_name() == 'bobm'


def test_shortname_fallback(client, function_fixture):
    user = function_fixture
    user.preferred_name = ''
    user.full_name = ''
    user.email = ''

    assert user.get_short_name() == ''
