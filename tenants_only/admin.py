from django.contrib import admin

from tenants_only.models import Tenants


@admin.register(Tenants)
class TenantsAdmin(admin.ModelAdmin):
    pass
