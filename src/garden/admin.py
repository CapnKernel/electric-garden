from django.contrib import admin

from .models import Container, Packet, Plant, Planting

admin.site.register(Container)
admin.site.register(Plant)
admin.site.register(Packet)
admin.site.register(Planting)
