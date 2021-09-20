from django.db import models
from django_tenants.models import TenantMixin, DomainMixin


class Tenants(TenantMixin):
    tenant_id = models.AutoField(primary_key=True)
    schema_name = models.CharField(max_length=255, unique=True)
    tenant_name = models.CharField(max_length=255, unique=True)
    db_instance_name = models.CharField(max_length=255)

    auto_create_schema = True

class Domain(DomainMixin):
    pass