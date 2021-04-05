
# docker-compose run api python manage.py makemigrations
# docker-compose run api python manage.py migrate

from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField


class ManageTables(models.Model):
    manage_table_id = models.AutoField(primary_key=True)
    # table name for SQL statement
    table_name = models.CharField(max_length=255, unique=True)
    # Will be the base url, used to help identify in the dynamic view
    root_url = models.CharField(max_length=255, unique=True)
    # Defines the columns, used in SQL statement to create the table. Can specify:
    # null (boolean) - default is False
    # type - required
    # max_length - required on char types
    # unique - default is False
    # default - default value if one isn't specified
    column_definition = JSONField()
    # Schema generated from the column_definitions to be used against user input.
    validate_json_create = JSONField()
    validate_json_update = JSONField()
    # default is all 5, but will remove specific endpoints if specified in json.
    endpoints = ArrayField(models.CharField(max_length=255))
    # Table level roles. If not specified, we default to tenant level role.
    # required_roles = ArrayField(null=True, blank=True)
    # Tenant id to use.
    tenant_id = models.CharField(max_length=255)
    # Primary key to be set for the table.
    primary_key = models.CharField(max_length=255)

    def __str__(self):
        return 'Table ID: %s | Root URL: %s' % (self.manage_table_id, self.root_url)


class ManageTablesTransition(models.Model):
    manage_table_transition_id = models.AutoField(primary_key=True)
    manage_table = models.ForeignKey(ManageTables, on_delete=models.CASCADE)
    column_definition_tn = JSONField()
    validate_json_create_tn = JSONField()
    validate_json_update_tn = JSONField()
    table_name_tn = models.CharField(max_length=255, unique=True, null=True, blank=True)
    # Status field


class Tenants(models.Model):
    tenant_id = models.AutoField(primary_key=True)
    tenant_name = models.CharField(max_length=255, unique=True)
    db_instance_name = models.CharField(max_length=255)

