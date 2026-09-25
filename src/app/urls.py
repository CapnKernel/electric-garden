from django.contrib.auth.decorators import login_not_required
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from . import views, wizard

app_name = 'app'

urlpatterns = [
    path('', method_decorator(login_not_required)(TemplateView.as_view(template_name='app/top.html')), name='top'),
    # HTMX endpoint returning Django messages as an OOB-swappable partial.
    path(
        'partials/messages/',
        TemplateView.as_view(template_name='app/base.html#messages-partial'),
        name='messages_partial',
    ),
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
