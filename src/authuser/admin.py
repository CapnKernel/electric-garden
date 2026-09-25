from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


class UserAdmin(BaseUserAdmin):
    ordering = ('email',)
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'full_name')

    fieldset_patch = {
        None: ('-username', 'email'),
        'Personal info': ('-first_name', '-last_name', '-email', 'full_name', 'preferred_name'),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.list_display = [f for f in self.list_display if f not in ('username', 'first_name', 'last_name')]

    def get_fieldsets(self, request, obj=None):
        old_fieldsets = super().get_fieldsets(request, obj)
        new_fieldsets = dict(old_fieldsets)
        patch = self.fieldset_patch
        for k, v in new_fieldsets.items():
            if k in patch:
                field_names = v['fields']
                del_list = tuple(v1[1:] for v1 in patch[k] if v1.startswith('-'))
                add_list = tuple(v1 for v1 in patch[k] if not v1.startswith('-'))
                field_names = list(f for f in field_names if f not in del_list)
                for f in add_list:
                    if f not in field_names:
                        field_names.insert(0, f)
                v['fields'] = field_names

        new_fieldsets = list((k, v) for k, v in new_fieldsets.items())

        return new_fieldsets


admin.site.register(User, UserAdmin)
