
# docker-compose run api python manage.py makemigrations
# docker-compose run api python manage.py migrate

from django.db import models
from django.contrib.postgres.fields import JSONField, ArrayField
from django.utils import tree


class ManageViews(models.Model):
    manage_view_id = models.AutoField(primary_key=True)
    # view name for SQL statement
    view_name = models.CharField(max_length=255)
    # Will be the base url, used to help identify in the dynamic view
    root_url = models.CharField(max_length=255)
    # Definition of view
    view_definition = JSONField()
    # Tenant id to use.
    tenant_id = models.CharField(max_length=255)
    # Table permission rules
    permission_rules = ArrayField(base_field=models.CharField(max_length=255), null=True, blank=True, size=None)
    # default is all 5, but will remove specific endpoints if specified in json.
    endpoints = ArrayField(models.CharField(max_length=255))
    # Comments area to document view more.
    comments = models.TextField(null=True)

    def __str__(self):
        return 'View ID: %s | Root URL: %s' % (self.manage_view_id, self.root_url)


class ManageTables(models.Model):
    manage_table_id = models.AutoField(primary_key=True)
    # table name for SQL statement
    table_name = models.CharField(max_length=255)
    # Will be the base url, used to help identify in the dynamic view
    root_url = models.CharField(max_length=255)
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
    # Special_Rules key, used to hold misc data for parsing tables/rows.
    special_rules = JSONField()
    # Comments area to document table more.
    comments = models.TextField()
    # Constraints
    constraints = JSONField()

    def __str__(self):
        return 'Table ID: %s | Root URL: %s' % (self.manage_table_id, self.root_url)


class ManageTablesTransition(models.Model):
    manage_table_transition_id = models.AutoField(primary_key=True)
    manage_table = models.ForeignKey(ManageTables, on_delete=models.CASCADE)
    column_definition_tn = JSONField()
    validate_json_create_tn = JSONField()
    validate_json_update_tn = JSONField()
    table_name_tn = models.CharField(max_length=255, unique=True, null=True, blank=True)
