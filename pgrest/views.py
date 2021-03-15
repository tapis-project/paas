import json
import requests
import logging


from cerberus import Validator

from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseServerError, HttpResponseNotFound, \
    HttpResponseForbidden

from rest_framework.views import APIView

from pgrest.models import ManageTables, ManageTablesTransition, Tenants
from pgrest.db_transactions import manage_tables, table_data, bulk_data
from pgrest.pycommon.auth import t, get_tenant_id_from_base_url
from pgrest.utils import create_validate_schema, can_read, can_write, is_admin

logger = logging.getLogger(__name__)


class RoleSessionMixin:
    """
    Retrieves username from Agave for tacc.prod token, then retrieves roles for this user in SK and stores data
    in django session.
    """
    # Override dispatch to decode token and store variables before routing the request.
    def dispatch(self, request, *args, **kwargs):
        logger.debug("top of dispatch")
        try:
            # pull token from the request, and decode it to get the user that is sending in request.
            try:
                # Pull token from header `tapis-v2-token`
                # Note: any HTTP headers in the request are converted to META keys by converting all characters to
                # uppercase, replacing any hyphens with underscores and adding an HTTP_ prefix to the name.
                v2_token = request.META['HTTP_TAPIS_V2_TOKEN']
            except KeyError as e:
                logger.warning(f"User not authenticated. Exception: {e}")
                return HttpResponse('Unauthorized', status=401)

            try:
                url = "https://api.tacc.utexas.edu/profiles/v2/me"
                head = {'Authorization': f'Bearer {v2_token}'}
                response = requests.get(url, headers=head)
            except Exception:
                msg = f"Unable to retrieve user profile from Agave."
                logger.error(msg)
                return HttpResponseForbidden(msg)
            logger.debug(f"got response from profiles API: {response}")

            try:
                # Get the base url from the incoming request, and then use the
                request_url = request.scheme + "://" + request.get_host()

                # NOTE!!!!! This top one can be uncommented for local dev.
                # Bottom one HAS to be uncommented for deployed services.
                # tenant_id = get_tenant_id_from_base_url("https://admin.develop.tapis.io", t.tenant_cache)
                tenant_id = get_tenant_id_from_base_url(request_url, t.tenant_cache)
            except Exception as e:
                msg = f"Error occurred while calculating tenant ID from the request base URL."
                logger.error(msg)
                return HttpResponseBadRequest(msg)
            logger.debug(f"got tenant_id: {tenant_id}")

            try:
                username = response.json()['result']['username']
            except KeyError:
                msg = "Unable to parse Agave token response for username."
                logger.error(msg)
                return HttpResponseForbidden(msg)
            logger.debug(f"got username: {username}")

            try:
                roles = t.sk.getUserRoles(user=username, tenant=tenant_id)
                role_list = list()
                for name in roles.names:
                    role_list.append(name)
            except Exception as e:
                msg = f"Error occurred while retrieving roles from SK: {e}"
                logger.error(msg)
                return HttpResponseBadRequest(msg)
            logger.debug(f"got roles: {role_list}")

            try:
                db_instance_name = Tenants.objects.get(tenant_name=tenant_id).db_instance_name
            except Exception as e:
                msg = f"Error occurred while retrieving the db instance name for tenant {tenant_id}: {e}. " \
                      f"Available tenants: {Tenants.objects.all().values()}"
                logger.error(msg)
                return HttpResponseBadRequest(msg)
            logger.debug(f"got db_instance_name: {db_instance_name}")

            request.session['roles'] = role_list
            request.session['username'] = username
            request.session['tenant_id'] = tenant_id
            request.session['db_instance_name'] = db_instance_name

            return super().dispatch(request, *args, **kwargs)

        except Exception as e:
            logger.error(f"Unable to determine roles associated with authenticated user. Exception: {e}")
            return HttpResponseBadRequest(f"There was an error while fulfilling user request. Message: {e}")


class TableManagement(RoleSessionMixin, APIView):
    """
    GET: Returns information about all of the tables.
    POST: Creates a new table in ManageTables, and then a new table from the json provided by the user.
    All of these endpoints are restricted to ADMIN role only.
    """
    @is_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/tables")
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']

        # Check for details=true. Decide what a brief description and a detailed description is.
        details = self.request.query_params.get('details')

        # Display information for each table based on details variable.
        tables = ManageTables.objects.filter(tenant_id=req_tenant)

        result = list()
        # If details, form information about the columns and endpoints of the table
        # TODO Fix up this format.
        if details:
            for table in tables:
                result.append({"table_name": table.table_name,
                               "table_id": table.pk,
                               "root_url": table.root_url,
                               "tenant": table.tenant_id,
                               "endpoints": table.endpoints,
                               "columns": table.column_definition,
                               "update_schema": table.validate_json_update,
                               "create_schema": table.validate_json_create,
                               "tenant_id": table.tenant_id})
        else:
            for table in tables:
                result.append({"table_name": table.table_name,
                               "table_id": table.pk,
                               "root_url": table.root_url,
                               "tenant": table.tenant_id,
                               "endpoints": table.endpoints,
                               "tenant_id": table.tenant_id})

        return HttpResponse(json.dumps(result), content_type='application/json')

    @is_admin
    def post(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']

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
        list_all = request.data.get('list_all', True)
        list_one = request.data.get('list_one', True)
        create = request.data.get('create', True)
        update = request.data.get('update', True)
        delete = request.data.get('delete', True)
        endpoints = request.data.get('endpoints', True)

        if ManageTables.objects.filter(table_name=table_name).exists():
            msg = f"Table with name \'{table_name}\' already exists in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        if ManageTables.objects.filter(root_url=root_url).exists():
            msg = f"Table with root url \'{root_url}\' already exists in ManageTables table. " \
                  f"Table name: {table_name}"
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        if endpoints:
            endpoints = ["GET_ONE", "GET_ALL", "CREATE", "UPDATE", "DELETE"]
            if not list_one:
                endpoints.remove("GET_ONE")
            if not list_all:
                endpoints.remove("GET_ALL")
            if not create:
                endpoints.remove("CREATE")
            if not update:
                endpoints.remove("UPDATE")
            if not delete:
                endpoints.remove("DELETE")
        else:
            endpoints = []

        try:
            validate_json_create, validate_json_update = create_validate_schema(columns)
        except Exception as e:
            msg = f"Unable to create json validation schema for table {table_name}: {e}" \
                  f"\nFailed to create table {table_name}. "
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            result = self.post_transaction(table_name, root_url, columns, validate_json_create, validate_json_update,
                                           endpoints, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to create table {table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(result), content_type='application/json')

    @transaction.atomic
    def post_transaction(self, table_name, root_url, columns, validate_json_create, validate_json_update,
                         endpoints, tenant_id, db_instance_name):

        new_table = ManageTables.objects.create(table_name=table_name, root_url=root_url, column_definition=columns,
                                                validate_json_create=validate_json_create,
                                                validate_json_update=validate_json_update,
                                                endpoints=endpoints, tenant_id=tenant_id)

        ManageTablesTransition.objects.create(manage_table=new_table, column_definition_tn=columns,
                                              validate_json_create_tn=validate_json_create,
                                              validate_json_update_tn=validate_json_update)

        manage_tables.create_table(table_name, columns, tenant_id, db_instance_name)

        result = {
            "table_name": new_table.table_name,
            "table_id": new_table.pk,
            "root_url": new_table.root_url,
            "endpoints": new_table.endpoints
        }

        return result


# These are endpoints to manage the tables and contains metadata for the tables.
class TableManagementById(RoleSessionMixin, APIView):
    """
    GET: Returns the table with the provided ID.
    PUT: Updates the table with the provided ID. Work in progress.
    DELETE: Drops the table with the provided ID.
    All of these endpoints are restricted to ADMIN role only.
    """
    @is_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/tables/<id>")
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']

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
            # table = ManageTables.objects.get(pk=table_id, tenant_id=req_tenant)
            table = ManageTables.objects.get(pk=table_id)

        except ManageTables.DoesNotExist:
            msg = f"Table with id {table_id} does not exist in the ManageTables table."
            logger.warning(msg)
            return HttpResponseNotFound(msg)

        # If details, form information about the columns and endpoints of the table
        # TODO Fix up this format.
        if details:
            result = {
                "table_name": table.table_name,
                "table_id": table.pk,
                "root_url": table.root_url,
                "endpoints": table.endpoints,
                "columns": table.column_definition,
                "tenant_id": table.tenant_id,
                "update schema": table.validate_json_update,
                "create schema": table.validate_json_create
            }
        else:
            result = {
                "table_name": table.table_name,
                "table_id": table.pk,
                "root_url": table.root_url,
                "endpoints": table.endpoints,
                "tenant_id": table.tenant_id
            }

        return HttpResponse(json.dumps(result), content_type='application/json')

    @is_admin
    def put(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']

        # Parse out required fields.
        try:
            table_id = self.kwargs['manage_table_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to update a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table = ManageTables.objects.get(pk=table_id)
            transition_table = ManageTablesTransition.objects.get(manage_table=table)
        except ManageTables.DoesNotExist:
            msg = f"Table with ID {table_id} does not exist in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)
        except ManageTablesTransition.DoesNotExist:
            msg = f"Transition table for table with ID {table_id} does not exist."
            logger.warning(msg)
            return HttpResponseServerError(msg)

        # Parse out possible update fields.
        root_url = request.data.get('root_url', None)
        table_name = request.data.get('table_name', None)
        update_cols = request.data.get('columns', None)

        list_all = request.data.get('list_all', ("GET_ALL" in table.endpoints))
        list_one = request.data.get('list_one', ("GET_ONE" in table.endpoints))
        create = request.data.get('create', ("CREATE" in table.endpoints))
        update = request.data.get('update', ("UPDATE" in table.endpoints))
        delete = request.data.get('delete', ("DELETE" in table.endpoints))
        endpoints = request.data.get('endpoints', True)

        if root_url is not None:
            table.root_url = root_url
            table.save()
        if not endpoints:
            table.endpoints = list()
            table.save()
        else:
            set_endpoints = set(table.endpoints)
            if list_all:
                set_endpoints.add("GET_ALL")
            else:
                if "GET_ALL" in set_endpoints:
                    set_endpoints.remove("GET_ALL")

            if list_one:
                set_endpoints.add("GET_ONE")
            else:
                if "GET_ONE" in set_endpoints:
                    set_endpoints.remove("GET_ONE")

            if create:
                set_endpoints.add("CREATE")
            else:
                if "CREATE" in set_endpoints:
                    set_endpoints.remove("CREATE")

            if update:
                set_endpoints.add("UPDATE")
            else:
                if "UPDATE" in set_endpoints:
                    set_endpoints.remove("UPDATE")

            if delete:
                set_endpoints.add("DELETE")
            else:
                if "DELETE" in set_endpoints:
                    set_endpoints.remove("DELETE")

            table.endpoints = list(set_endpoints)
            table.save()

            if table_name is not None:
                transition_table.table_name_tn = table_name
                transition_table.save()

            if update_cols is not None:
                current_cols = transition_table.column_definition_tn
                for col_name, col_info in current_cols.items():
                    if "action" not in col_info:
                        msg = f"Action field is required to update column {col_name}"
                        logger.warning(msg)
                        return HttpResponseBadRequest(msg)

                    if col_info["action"] == 'DROP':
                        current_cols.pop(col_name, None)
                    elif col_info["action"] == "ADD":
                        current_cols[col_name] = col_info
                    elif col_info["action"] == "ALTER":
                        current_cols.pop(col_name, None)
                        current_cols[col_name] = col_info
                    else:
                        msg = f"Invalid action for column {col_name} received: {col_info['action']}"
                        logger.warning(msg)
                        return HttpResponseBadRequest(msg)

                    transition_table.save()

                try:
                    validate_json_create_tn, validate_json_update_tn = create_validate_schema(current_cols)
                    transition_table.validate_json_create_tn = validate_json_create_tn
                    transition_table.validate_json_update_tn = validate_json_update_tn
                    transition_table.save()
                except Exception as e:
                    msg = f"Unable to create json validation schema for updating table {table_name}: {e}" \
                          f"\nFailed to update transition table for {table_name}. "
                    logger.warning(msg)
                    return HttpResponseBadRequest(msg)

                # generate migration script
                # apply and roll back, error if it does not work
                # if works, open process that creates a new file and pipes generated migration into it.


    # def create_update_table_migration(swlf, table_name, tenant, update_dict):
    #     logger.info(f"Generating script to update table {tenant}.{table_name}...")
    #
    #     command = "ALTER TABLE %s" % table_name
    #     if "table_name" in update_dict:
    #         command = command + " RENAME TO %s"
    #
    #     if "columns" in update_dict:
    #         for col_name, col_info in update_dict["columns"].items():
    #             if col["action"] == "DROP":
    #                 command = command + " DROP %s IF EXISTS column %s" % col_name, col_info["on_delete"]


        return HttpResponse(200)

    @is_admin
    def delete(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']

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
            return HttpResponseNotFound(msg)

        try:
            self.delete_transaction(table, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to drop table {table.table_name} from the ManageTables table: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(200)

    @transaction.atomic
    def delete_transaction(self, table, tenant_id, db_instance_name):
        ManageTables.objects.get(table_name=table.table_name, tenant_id=tenant_id).delete()
        manage_tables.delete_table(table.table_name, tenant_id, db_instance=db_instance_name)


class TableManagementDump(RoleSessionMixin, APIView):
    """
    Work in progress.
    """
    @is_admin
    def post(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']

        # Can send in ALL or list of table name(s)
        if request.data == "all":
            pass
        else:
            for table_name, info in request.data.items():
                try:
                    file_path = info["file_path"]
                except KeyError as e:
                    msg = f"file_path is required to dump data from table {table_name}."
                    logger.warning(msg)
                    return HttpResponseBadRequest(msg)
                info.get("delimiter", ',')

                try:
                    dump = bulk_data.dump_data(table_name, file_path, req_tenant)
                    print(dump)
                except Exception as e:
                    print("awww, ", e)

        return HttpResponse(200)


class TableManagementLoad(RoleSessionMixin, APIView):
    """
    Work in progress.
    """
    @is_admin
    def post(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']

# For dynamic views, all end users will end up here. We will find the corresponding table
# based on the url to get here. We then will formulate a SQL statement to do the need actions.


# Once we figure out the table and row, these are just simple SQL crud operations.
class DynamicView(RoleSessionMixin, APIView):
    """
    GET: Lists the rows in the given table based on root url. Restricted to READ and above role.
    POST: Creates a new row in the table based on root URL. Restricted to WRITE and above role.
    PUT: Updates the rows in the given table based on filter. If no filter is provided, updates the entire table.
    Restricted to WRITE and above role.
    """
    @can_read
    def get(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']

        params = self.request.query_params
        limit = self.request.query_params.get("limit")
        order = self.request.query_params.get("order")

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
            return HttpResponseNotFound(msg)

        if "GET_ALL" not in table.endpoints:
            msg = "API access to LIST ROWS disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        query_dict = dict()
        for param in params:
            if param.lower().startswith('where'):
                table_columns = table.column_definition.keys()
                if param[6:] in table_columns or param[6:] == 'pk':
                    query_dict.update({param[6:]: params[param]})
                else:
                    msg = f"Invalid query parameter: {param[6:]}"
                    logger.warning(msg)
                    return HttpResponseBadRequest(msg)

        try:
            if limit is None:
                limit = 10
            if order is not None:
                result = table_data.get_rows_from_table(table.table_name, query_dict, req_tenant,
                                                        limit, db_instance, order=order)
            else:
                result = table_data.get_rows_from_table(table.table_name, query_dict, req_tenant, limit, db_instance)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(result), content_type='application/json')

    @can_write
    def post(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']

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

        if "CREATE" not in table.endpoints:
            msg = "API access to CREATE disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            data = request.data['data']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating new row in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        # Validate against the table's json schema.
        try:
            v = Validator(table.validate_json_create)
            if not v.validate(data):
                msg = f"Data determined invalid from json validation schema: {v.errors}"
                logger.warning(msg)
                return HttpResponseBadRequest(msg)
        except Exception as e:
            msg = f"Error occurred when validating the data from the json validation schema: {e}"
            logger.error(msg)
            pass
            # return HttpResponseBadRequest(msg)

        # Separate columns and values out into two lists.
        columns = list()
        values = list()
        for k, v in data.items():
            columns.append(k)
            values.append(v)
        # Get the correct number of '%s' for the SQL query.
        value_str = '%s, ' * len(values)
        value_str = value_str[:-2]

        try:
            result_id = table_data.create_row(table.table_name, columns, value_str, values, req_tenant,
                                              db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)
        try:
            result = table_data.get_row_from_table(table.table_name, result_id, req_tenant, db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(result), content_type='application/json')
    @can_write
    def put(self, request, *args, **kwargs):
            # req_tenant = "public"
            req_tenant = request.session['tenant_id']
            db_instance = request.session['db_instance_name']

            # Parse out required fields.
            result_dict = json.loads(request.body.decode())
            try:
                root_url = self.kwargs["root_url"]
                data = result_dict["data"]
            except KeyError as e:
                msg = f"\'{e.args}\' is required to update rows in a table."
                logger.warning(msg)
                return HttpResponseBadRequest(msg)
            where_clause = result_dict.get("where", None)

            try:
                table = ManageTables.objects.get(root_url=root_url)
            except ManageTables.DoesNotExist:
                msg = f"Table with root url {root_url} does not exist."
                logger.warning(msg)
                return HttpResponseBadRequest(msg)

            if "UPDATE" not in table.endpoints:
                msg = "API access to UPDATE disabled."
                logger.warning(msg)
                return HttpResponseBadRequest(msg)

            try:
                v = Validator(table.validate_json_update)
                if not v.validate(data):
                    msg = f"Data determined invalid from json validation schema: {v.errors}"
                    logger.warning(msg)
                    return HttpResponseBadRequest(msg)
            except Exception as e:
                msg = f"Error occurred when validating the data from the json validation schema: {e}"
                logger.error(msg)
                return HttpResponseBadRequest(msg)

            try:
                if where_clause:
                    table_data.update_rows_with_where(table.table_name, data, req_tenant, db_instance, where_clause)
                else:
                    table_data.update_rows_with_where(table.table_name, data, req_tenant, db_instance)
            except Exception as e:
                msg = f"Failed to update row in table {table.table_name} with pk {pk_id} on tenant {req_tenant}. {e}"
                logger.error(msg)
                return HttpResponseBadRequest(msg)

            return HttpResponse(status=200)


class DynamicViewById(RoleSessionMixin, APIView):
    """
    GET: Lists a row in a table, based on root url and ID. Restricted to READ and above role.
    PUT: Updates a single row in a table by the ID. Restricted to WRITE and above role.
    DELETE: Deletes a single row in a table by the ID. Restricted to WRITE and above role.
    """
    @can_read
    def get(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
            pk_id = self.kwargs['primary_id']
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

        if "GET_ONE" not in table.endpoints:
            msg = "API access to LIST SINGLE ROW disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            result = table_data.get_row_from_table(table.table_name, pk_id, req_tenant)
        except Exception as e:
            msg = f"Failed to retrieve row from table {table.table_name} with pk {pk_id} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(result), content_type='application/json')

    @can_write
    def put(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
            pk_id = self.kwargs['primary_id']
            data = request.data['data']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to update a row in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        if "UPDATE" not in table.endpoints:
            msg = "API access to UPDATE disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            v = Validator(table.validate_json_update)
            if not v.validate(data):
                msg = f"Data determined invalid from json validation schema: {v.errors}"
                logger.warning(msg)
                return HttpResponseBadRequest(msg)
        except Exception as e:
            msg = f"Error occurred when validating the data from the json validation schema: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        try:
            table_data.update_row_with_pk(table.table_name, pk_id, data, req_tenant, db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to update row in table {table.table_name} with pk {pk_id} in tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        try:
            return_result = table_data.get_row_from_table(table.table_name, pk_id, req_tenant)
        except Exception as e:
            msg = f"Failed to retrieve row from table {table.table_name} with pk {pk_id} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(json.dumps(return_result), content_type='application/json', status=200)

    @can_write
    def delete(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
            pk_id = self.kwargs['primary_id']
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

        if "DELETE" not in table.endpoints:
            msg = "API access to DELETE disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            table_data.delete_row(table.table_name, pk_id, req_tenant, db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to delete row from table {table.table_name} with pk {pk_id} in tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(status=200)


class CreateTenant(APIView):
    def post(self, request, *args, **kwargs):
        try:
            schema_name = request.data['schema_name']
            db_instance = request.data['db_instance']

        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating new row in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            Tenants.objects.get_or_create(tenant_name=schema_name, db_instance_name=db_instance)
        except Exception as e:
            msg = f"Unable to insert new role into Tenants Django table for tenant " \
                  f"{schema_name} and db_instance {db_instance}: {e}"
            logger.warning(msg)
            return HttpResponseBadRequest(msg)

        try:
            manage_tables.create_schema(schema_name, db_instance)
        except Exception as e:
            msg = f"Failed to create new schema {schema_name} in db_instance {db_instance}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(msg)

        return HttpResponse(200)

