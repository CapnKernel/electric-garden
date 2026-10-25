from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from .models import Container, Packet, Plant, Planting, PlantingEvent


class BarcodeIdAdminMixin:
    """Allow an object to be created with a barcode ID supplied as ``?id=``."""

    readonly_fields = ('barcode',)

    @admin.display(description='Scan')
    def scan_link(self, obj):
        if obj.pk is None:
            return '-'
        return format_html('<a href="{}">Scan</a>', obj.scan_url)

    def save_model(self, request, obj, form, change):
        if not change and 'id' in request.GET:
            try:
                custom_id = int(request.GET['id'])
            except (TypeError, ValueError):
                pass
            else:
                if not self.model.objects.filter(pk=custom_id).exists():
                    obj.pk = custom_id
        super().save_model(request, obj, form, change)

    def response_add(self, request, obj, post_url_continue=None):
        if '_addanother' in request.POST:
            add_url = reverse(f'admin:{self.model._meta.app_label}_{self.model._meta.model_name}_add')
            return HttpResponseRedirect(f'{add_url}?id={obj.pk}')
        return super().response_add(request, obj, post_url_continue)


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
class ContainerAdmin(BarcodeIdAdminMixin, admin.ModelAdmin):
    list_display = ('barcode', 'name', 'scan_link')
    search_fields = ('name',)
    inlines = (PacketInline, ContainerPlantingEventInline)


@admin.register(Plant)
class PlantAdmin(BarcodeIdAdminMixin, admin.ModelAdmin):
    list_display = ('barcode', 'code', 'name', 'deleted', 'scan_link')


@admin.register(Packet)
class PacketAdmin(BarcodeIdAdminMixin, admin.ModelAdmin):
    list_display = ('barcode', 'plant', 'brand', 'full_name', 'deleted', 'scan_link')


class PlantingEventInline(admin.TabularInline):
    """Show the events of a planting on its admin page."""

    model = PlantingEvent
    extra = 0
    fields = ('event_type', 'date', 'planted_in', 'location', 'notes')
    show_change_link = True


@admin.register(Planting)
class PlantingAdmin(BarcodeIdAdminMixin, admin.ModelAdmin):
    list_display = ('barcode', 'packet', 'first_event_date', 'germinated', 'deleted', 'last_scanned_at', 'scan_link')
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
