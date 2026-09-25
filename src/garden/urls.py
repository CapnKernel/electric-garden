from django.urls import path

from .api import api
from .views import index

urlpatterns = [
    path('', index, name='index'),
    path('api/', api.urls),
]
