from django.urls import path

from .planting import (
    planting_edit,
    planting_event_create,
    planting_event_delete,
    planting_event_edit,
    planting_result,
)
from .scan import scan_hxpost, scan_page

urlpatterns = [
    path('', scan_page, name='scan'),
    path('scan_hxpost/', scan_hxpost, name='scan_hxpost'),
    path('planting/<int:pk>/edit/', planting_edit, name='planting_edit'),
    path('planting/<int:pk>/result/', planting_result, name='planting_result'),
    path('planting/<int:pk>/event/new/', planting_event_create, name='planting_event_create'),
    path('planting/event/<int:pk>/edit/', planting_event_edit, name='planting_event_edit'),
    path('planting/event/<int:pk>/delete/', planting_event_delete, name='planting_event_delete'),
]
