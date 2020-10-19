import json
import logging

from cerberus import Validator

from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseServerError, HttpResponseForbidden

from rest_framework.views import APIView

from proto.models import ManageTables
from proto.db_transactions import manage_tables, table_data

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
                               "table_id": table.pk,
                               "root url": table.root_url,
                               "endpoints": table.endpoints,
                               "columns": table.column_definition})
        else:
            for table in tables:
                result.update({"table name": table.table_name,
                               "table_id": table.pk,
                               "root url": table.root_url,
                               "endpoints": table.endpoints})

        return HttpResponse(json.dumps(result), content_type='application/json')

    @transaction.atomic
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

        # TODO Usher table role to SK API

        if ManageTables.objects.filter(table_name=table_name).exists():
            msg = f"Table with name \'{table_name}\' already exists in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            manage_tables.create_table(table_name, columns)
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

        try:
            new_table = ManageTables.objects.create(table_name=table_name, root_url=root_url, column_definition=columns,
                                validate_json=validate_json, endpoints=endpoints, tenant_id=req_tenant)
        except Exception as e:
            msg = f"Failed to add table {table_name} to the ManageTables table: {e}"
            logger.error(msg)

            # Drop table that was created above
            return HttpResponseBadRequest(msg)

        result = {
                "table name": new_table.table_name,
                "table_id": new_table.pk,
                "root url": new_table.root_url,
                "endpoints": new_table.endpoints
        }

        return HttpResponse(json.dumps(result), content_type='application/json')

    def create_validate_schema(self, columns):
        # TODO Create schema based on columns input. Schema will be applied to user input to put data into this table.
        schema = {}
        return schema


# TODO how are we doing roles? I know we're doing a layered approach. Row pem > table pem > tenant pem.
# Trying to determine how to house these.

# These are endpoints to manage the tables and contains metadata for the tables.
class TableManagementById(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # TODO Check and store role from JWT. Must be an admin.
        # TODO Check and store tenant from JWT.
        req_tenant = "dev"

        # Check for details=true. Decide what a brief description and a detailed description is.
        details = self.request.query_params.get('details')

        # Parse out required fields.
        try:
            table_id = self.kwargs['manage_table_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to list a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        # Display information for each table based on details variable.
        try:
            table = ManageTables.objects.get(pk=table_id, tenant_id=req_tenant)
        except ManageTables.DoesNotExist:
            msg = f"Table with id {table_id} does not exist in the ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        # If details, form information about the columns and endpoints of the table
        # TODO Fix up this format.
        if details:
            result = {
                "table name": table.table_name,
                "table_id": table.pk,
                "root url": table.root_url,
                "endpoints": table.endpoints,
                "columns": table.column_definition
            }
        else:
            result = {
                "table name": table.table_name,
                "table_id": table.pk,
                "root url": table.root_url,
                "endpoints": table.endpoints
            }

        return HttpResponse(json.dumps(result), content_type='application/json')

    @transaction.atomic
    def put(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Generates SQL to update the structure of a table.
        # Will need to run migration for update - this may be rough.
        # Put have "actions" that will need to be included in the json. Either "add_column" - adds a column,
        # "update_column" - updates a column, "flush" - flush a table, "update_table" - updates the table.
        pass

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        # TODO Check and store role from JWT. Must be an admin.
        # TODO Get tenant ID from jwt.
        req_tenant = "dev"

        # Parse out required fields.
        try:
            table_id = self.kwargs['manage_table_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to drop a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table = ManageTables.objects.get(pk=table_id)
        except ManageTables.DoesNotExist:
            msg = f"Table with ID {table_id} does not exist in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            manage_tables.delete_table(table.table_name)
        except Exception as e:
            msg = f"Failed to drop table {table.table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        try:
            ManageTables.objects.get(table_name=table.table_name, tenant_id=req_tenant).delete()
        except Exception as e:
            msg = f"Failed to drop table {table.table_name} from the ManageTables table: {e}"
            logger.error(msg)

            return HttpResponseBadRequest(msg)

        return HttpResponse(200)


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
    Lists the rows in the given table.
    """
    def get(self, request, *args, **kwargs):
        # TODO Check and store role from JWT.
        # TODO Check and store tenant from JWT.
        req_tenant = "dev"

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to list rows in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            result = table_data.get_rows_from_table(table.table_name)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(result), content_type='application/json')

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        # TODO Check and store role from JWT.
        # TODO Check and store tenant from JWT.
        req_tenant = "dev"

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to list rows in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)
        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            data = request.data['data']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating new row in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        # Separate columns and values out into two lists, then convert the lists to a string for the SQL query.
        columns = list()
        values = list()
        for k, v in data.items():
            columns.append(k)
            values.append(v)

        value_str = '%s, ' * len(values)
        value_str = value_str[:-2]

        try:
            result_id = table_data.create_row(table.table_name, columns, value_str, values)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)
        try:
            result = table_data.get_row_from_table(table.table_name, result_id)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(result), content_type='application/json')


class DynamicViewById(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # TODO Check and store role from JWT.
        # TODO Check and store tenant from JWT.
        req_tenant = "dev"

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
            pk = self.kwargs['primary_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to get row from a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            result = table_data.get_row_from_table(table.table_name, pk)
        except Exception as e:
            msg = f"Failed to retrieve row from table {table.table_name} with pk {pk_id}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(result), content_type='application/json')

    def put(self, request, *args, **kwargs):
        # Checks role. Must be allowed to update this row.
        pass

    def delete(self, request, *args, **kwargs):
        # TODO Check and store role from JWT.
        # TODO Check and store tenant from JWT.
        req_tenant = "dev"

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
            pk = self.kwargs['primary_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to delete row from a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table_data.delete_row(table.table_name, pk)
        except Exception as e:
            msg = f"Failed to delete row from table {table.table_name} with pk {pk_id}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(status=200)
