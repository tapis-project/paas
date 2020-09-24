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
    validate_json = JSONField()
    # default is all 5, but will remove specific endpoints if specified in json.
    endpoints = ArrayField()
    # Table level roles. If not specified, we default to tenant level role.
    # required_roles = ArrayField(null=True, blank=True)
    tenant_id = models.CharField(max_length=255)

    def __str__(self):
        return 'Table ID: %s | Root URL: %s' % (self.manage_table_id, self.root_url)


