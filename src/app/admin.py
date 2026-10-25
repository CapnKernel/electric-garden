from django.contrib import admin

from .models import Container, Packet, Plant, Planting, PlantingEvent


class PacketInline(admin.TabularInline):
    """Show the packets contained in a container on the container's page."""

    model = Packet
    extra = 0
    fields = ('barcode', 'plant', 'brand', 'full_name', 'expiry', 'deleted')
    readonly_fields = ('barcode',)
    show_change_link = True


class ContainerPlantingEventInline(admin.TabularInline):
    """Show the planting events that refer to this container.

    ``PlantingEvent.planted_in`` is the foreign key to ``Container``, so this
    inline lists the events recorded as having been planted in the container.
    """

    model = PlantingEvent
    fk_name = 'planted_in'
    extra = 0
    fields = ('planting', 'event_type', 'date', 'location', 'notes')
    readonly_fields = ('planting', 'event_type', 'date', 'location', 'notes')
    show_change_link = True
    can_delete = False


@admin.register(Container)
class ContainerAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'name')
    search_fields = ('name',)
    inlines = (PacketInline, ContainerPlantingEventInline)


admin.site.register(Plant)
admin.site.register(Packet)


class PlantingEventInline(admin.TabularInline):
    """Show the events of a planting on its admin page."""

    model = PlantingEvent
    extra = 0
    fields = ('event_type', 'date', 'planted_in', 'location', 'notes')
    show_change_link = True


@admin.register(Planting)
class PlantingAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'packet', 'first_event_date', 'germinated', 'deleted', 'last_scanned_at')
    list_filter = ('deleted',)
    search_fields = ('packet__plant__name', 'events__location', 'events__notes')
    fieldsets = ((None, {'fields': ('barcode', 'packet', 'germinated', 'deleted', 'last_scanned_at')}),)
    readonly_fields = ('barcode', 'last_scanned_at')
    inlines = (PlantingEventInline,)


@admin.register(PlantingEvent)
class PlantingEventAdmin(admin.ModelAdmin):
    list_display = ('planting', 'event_type', 'date', 'planted_in', 'location')
    list_filter = ('event_type',)
    search_fields = ('planting__barcode', 'location', 'notes')
    date_hierarchy = 'date'
