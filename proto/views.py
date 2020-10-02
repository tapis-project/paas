import json
import logging

from cerberus import Validator


from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from rest_framework.views import APIView

from proto.models import ManageTables
from proto.db_transactions import create_table

logger = logging.getLogger(__name__)


class TableManagement(APIView):
    """
    GET: Returns information about all of the tables.
    POST: Creates a new table in ManageTables, and then a new table from the json provided by the user.
    """
    def get(self, request, *args, **kwargs):
        # TODO Check and store role from JWT. Must be an admin.
        # TODO Check and store tenant from JWT.
        req_tenant = "dev"

        # Check for details=true. Decide what a brief description and a detailed description is.
        details = self.request.query_params.get('details')

        # Display information for each table based on details variable.
        tables = ManageTables.objects.filter(tenant_id=req_tenant)

        result = dict()
        # If details, form information about the columns and endpoints of the table
        # TODO Fix up this format.
        if details:
            for table in tables:
                result.update({"table name": table.table_name,
                               "root url": table.root_url,
                               "endpoints": table.endpoints,
                               "columns": table.columns})
        else:
            for table in tables:
                result.update({"table name": table.table_name,
                               "root url": table.root_url,
                               "endpoints": table.endpoints})

        return HttpResponse(details, content_type='application/json')

    def post(self, request, *args, **kwargs):
        # TODO Check and store role from JWT. Must be an admin.
        # TODO Get tenant ID from jwt.
        req_tenant = "dev"

        # Parse out required fields.
        try:
            table_name = request.data['table_name']
            columns = request.data['columns']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating a new table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        # Parse out optional fields.
        root_url = request.data.get('root_url', table_name)
        table_role = request.data.get('table_role', None)

        no_list_all = request.data.get('no_list_all', False)
        no_list_one = request.data.get('no_list_one', False)
        no_create = request.data.get('no_create', False)
        no_update = request.data.get('no_update', False)
        no_delete = request.data.get('no_delete', False)
        no_endpoints = request.data.get('no_endpoints', False)

        run_migrations = request.data.get('run_migrations', False)

        # TODO Usher table role to SK API

        try:
            create_table.create_tables(table_name, columns)
        except Exception as e:
            msg = f"Failed to create table {table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        if not no_endpoints:
            endpoints = ["GET_ONE", "GET_ALL", "CREATE", "UPDATE", "DELETE"]
            if no_list_one:
                endpoints.remove("GET_ONE")
            if no_list_all:
                endpoints.remove("GET_ALL")
            if no_create:
                endpoints.remove("CREATE")
            if no_update:
                endpoints.remove("UPDATE")
            if no_delete:
                endpoints.remove("DELETE")
        else:
            endpoints = []

        validate_json = self.create_validate_schema(columns)

        ManageTables.objects.create(table_name=table_name, root_url=root_url, column_definition=columns,
                                    validate_json=validate_json, endpoints=endpoints, tenant_id=req_tenant)

        # TODO if run_migration is True, run migration.

    def create_validate_schema(self, columns):
        # TODO Create schema based on columns input. Schema will be applied to user input to put data into this table.
        schema = {}
        return schema


# TODO how are we doing roles? I know we're doing a layered approach. Row pem > table pem > tenant pem.
# Trying to determine how to house these.



# ------------------------------------------------------------------------------
# These are endpoints to manage the tables and contains metadata for the tables.
class TableManagementById(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Generates SQL to list details for the specified table.
        # Returns in a JSON format.
        pass

    def put(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Generates SQL to update the structure of a table.
        # Will need to run migration for update - this may be rough.
        # Put have "actions" that will need to be included in the json. Either "add_column" - adds a column,
        # "update_column" - updates a column, "flush" - flush a table, "update_table" - updates the table.
        pass

    def delete(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Generates SQL to drop the specified table.
        # Will need to run migration for delete.
        pass


class TableManagementDump(APIView):
    """
    """
    def post(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Dumps data for the table(s) specified in the json. Results in a json form.
        pass


class TableManagementLoad(APIView):
    """
    """
    def post(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Loads data for the table(s) specified in the json. Data must be provided in json form.
        pass


# For dynamic views, all end users will end up here. We will find the corresponding table
# based on the url to get here. We then will formulate a SQL statement to do the need actions.

# Once we figure out the table and row, these are just simple SQL crud operations.
class DynamicView(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # Checks role. Must be allowed to see table.
        # Allows users to view all rows in a table.
        pass

    def post(self, request, *args, **kwargs):
        # Checks role. Must be allowed to add to table.
        # Create a new row in the table.
        pass


class DynamicViewById(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # Checks role. Must be allowed to view this row.
        pass

    def put(self, request, *args, **kwargs):
        # Checks role. Must be allowed to update this row.
        pass

    def delete(self, request, *args, **kwargs):
        # Checks role. Must be allowed to delete this row.
        pass
