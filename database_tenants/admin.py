from django.contrib import admin

from database_tenants.models import Tenants


@admin.register(Tenants)
class TenantsAdmin(admin.ModelAdmin):
    pass
