from django.contrib import admin

from .models import Container, Packet, Plant, Planting, SheetChangeLog

admin.site.register(Container)
admin.site.register(Plant)
admin.site.register(Packet)
admin.site.register(Planting)


@admin.register(SheetChangeLog)
class SheetChangeLogAdmin(admin.ModelAdmin):
    list_display = ('received_at', 'sheet_name', 'range', 'key', 'column_name', 'status', 'user_email')
    list_filter = ('status', 'sheet_name')
    search_fields = ('sheet_name', 'range', 'key', 'column_name', 'user_email')
    readonly_fields = ('received_at',)
    date_hierarchy = 'received_at'
