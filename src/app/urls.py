from django.urls import path
from django.views.generic import TemplateView

from . import views, wizard  # noqa: F401 - wizard is used by the commented-out URL block below
from .planting import (
    container_germination,
    planting_edit,
    planting_event_create,
    planting_event_delete,
    planting_event_edit,
    planting_result,
)
from .scan import scan_hxpost, scan_page

app_name = 'app'

urlpatterns = [
    path('', views.top, name='top'),
    # HTMX endpoint returning Django messages as an OOB-swappable partial.
    path(
        'partials/messages/',
        TemplateView.as_view(template_name='app/base.html#messages-partial'),
        name='messages_partial',
    ),
    # Garden URLs (formerly mounted under /garden/).
    path('scan/', scan_page, name='scan'),
    path('scan_hxpost/', scan_hxpost, name='scan_hxpost'),
    path('planting/<int:pk>/edit/', planting_edit, name='planting_edit'),
    path('planting/<int:pk>/result/', planting_result, name='planting_result'),
    path('planting/<int:pk>/event/new/', planting_event_create, name='planting_event_create'),
    path('planting/event/<int:pk>/edit/', planting_event_edit, name='planting_event_edit'),
    path('planting/event/<int:pk>/delete/', planting_event_delete, name='planting_event_delete'),
    path('container/<int:pk>/germination/', container_germination, name='container_germination'),
    # Wizard endpoints: Insert code from below.  FIXME: Remove from production
]

"""
    # Wizard endpoints.  Move this up to activate wizard.  See also tests/test_wizard.py
    path('item/<int:pk>/wizard_page/', wizard.wizard_page, name='wizard_page'),
    path('item/<int:pk>/wizard_name_hx/', wizard.wizard_name_hx, name='wizard_name_hx'),
    path('item/<int:pk>/wizard_name_hxpost/', wizard.wizard_name_hxpost, name='wizard_name_hxpost'),
    path('item/<int:pk>/wizard_description_hx/', wizard.wizard_description_hx, name='wizard_description_hx'),
    path(
        'item/<int:pk>/wizard_description_hxpost/',
        wizard.wizard_description_hxpost,
        name='wizard_description_hxpost',
    ),
    path('item/<int:pk>/wizard_confirm_hx/', wizard.wizard_confirm_hx, name='wizard_confirm_hx'),
    path('item/<int:pk>/wizard_confirm_hxpost/', wizard.wizard_confirm_hxpost, name='wizard_confirm_hxpost'),
"""
