import json
import re
import timeit

import datetime
from cerberus import Validator
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseServerError, HttpResponseNotFound, \
    HttpResponseForbidden
import requests
from rest_framework.views import APIView

from pgrest.models import ManageTables, ManageTablesTransition, Tenants, ManageViews
from pgrest.db_transactions import manage_tables, table_data, bulk_data, view_data
from pgrest.pycommon.auth import t, get_tenant_id_from_base_url
from pgrest.pycommon import errors
from pgrest.utils import create_validate_schema, can_read, can_write, is_admin, make_error, make_success
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)


# We create a forbidden regex for quick parsing
# Forbidden: \ ` ' " ~  / ? # [ ] ( ) @ ! $ & * + = - . , : ;
FORBIDDEN_CHARS =  re.compile("^[^<>\\\/{}[\]~` $'\".:-?#@!$&()*+,;=]*$")


# Error views
def error_404(request, exception, template_name=None):
    return HttpResponse(make_error(msg="The HTTP path and/or method are not available from this service."),
                        content_type='application/json',
                        status=404)

def error_400(request, exception, template_name=None):
    return HttpResponse(make_error(msg="The HTTP path and/or method are not available from this service."),
                        content_type='application/json',
                        status=400)

def error_500(request):
    return HttpResponse(make_error(msg="Something went wrong, Please try your request again later."),
                        content_type='application/json',
                        status=500)


def resolve_tapis_v3_token(request, tenant_id):
    """
    Validates a tapis v3 token in the X-Tapis-Token header
    """
    v3_token = request.META.get('HTTP_X_TAPIS_TOKEN')
    if v3_token:
        try:
            claims = t.tenant_cache.validate_token(v3_token)
        except errors.NoTokenError as e:
            msg = "No Tapis token found in the request. Be sure to specify the X-Tapis-Token header."
            logger.info(msg)
            return None, HttpResponseForbidden(make_error(msg=msg))
        except errors.AuthenticationError as e:
            msg = f"Tapis token validation failed; details: {e}"
            logger.info(msg)
            return None, HttpResponseForbidden(make_error(msg=msg))
        except Exception as e:
            msg = f"Unable to validate the Tapis token; details: {e}"
            logger.info(msg)
            return None, HttpResponseForbidden(make_error(msg=msg))

        # validate that the tenant claim matches the computed tenant_id
        # NOTE -- this does not work for service tokens; for those, have to check the OBO header.
        token_tenant = claims.get('tapis/tenant_id')
        if not token_tenant == tenant_id:
            msg = f"Unauthorized; the tenant claim in the token ({token_tenant}) did not match the associated " \
                  f"tenant in the request ({tenant_id})."
            return None, HttpResponseForbidden(make_error(msg=msg))
        return claims['tapis/username'], None
    else:
        msg = "No Tapis token found."
    return None, HttpResponseForbidden(make_error(msg=msg))


def get_username_for_request(request, tenant_id):
    """
    Determines the username for the request from possible headers. We support Tapis v2 OAuth tokens via the
    Tapis-v2-token header, and the usual Tapis v3 authentication and headers (e.g., X-Tapis-Token)
    """
    # first look for a v2 token -- if they have passed that, we assume that is what they want to use.
    try:
        # Pull token from header `tapis-v2-token`
        # Note: any HTTP headers in the request are converted to META keys by converting all characters to
        # uppercase, replacing any hyphens with underscores and adding an HTTP_ prefix to the name.
        v2_token = request.META['HTTP_TAPIS_V2_TOKEN']
    except KeyError as e:
        logger.debug("No v2 token header found; will look for a v3 token...")
        return resolve_tapis_v3_token(request, tenant_id)

    try:
        url = "https://api.tacc.utexas.edu/profiles/v2/me"
        head = {'Authorization': f'Bearer {v2_token}'}
        response = requests.get(url, headers=head)
    except Exception as e:
        msg = f"Got exception making request to profiles API. Exception: {e}"
        logger.error(msg)
        msg = "Unable to validate v2 token; internal error looking up the associated profile."
        return None, HttpResponseForbidden(make_error(msg=msg))
    logger.debug(f"got response from profiles API: {response}")
    # get username
    try:
        username = response.json()['result']['username']
    except KeyError:
        msg = "Unable to validate v2 token; either the token is invalid, " \
              "expired, or does not reoresnt a valid user in the v2 TACC tenant."
        logger.error(msg)
        return None, HttpResponseForbidden(make_error(msg=msg))
    logger.debug(f"got username: {username}")
    return username, None


def get_user_sk_roles(tenant, username):
    logger.debug(f"Getting SK roles on tenant {tenant} and user {username}")
    start_timer = timeit.default_timer()
    try:
        roles_obj = t.sk.getUserRoles(tenant=tenant, user=username)
    except Exception as e:
        end_timer = timeit.default_timer()
        total = (end_timer - start_timer) * 1000
        if total > 4000:
            logger.critical(f"t.sk.getUserRoles took {total} to run for user {username}, tenant: {tenant}")
        raise e
    end_timer = timeit.default_timer()
    total = (end_timer - start_timer) * 1000
    if total > 4000:
        logger.critical(f"t.sk.getUserRoles took {total} to run for user {username}, tenant: {tenant}")
    roles_list = roles_obj.names
    logger.debug(f"Roles received: {roles_list}")
    return roles_list


class RoleSessionMixin:
    """
    Retrieves username from Agave for tacc.prod token, then retrieves roles for this user in SK and stores data
    in django session.
    """
    # Override dispatch to decode token and store variables before routing the request.
    def dispatch(self, request, *args, **kwargs):
        logger.info(f"top of dispatch; headers: {request.META.keys()}")
        # first, determine tenant_id from base URL --
        tenant_id = None
        try:
            # Get the base url from the incoming request, and then use that to determine tenant_id
            request_url = request.scheme + "://" + request.get_host()
            # during local development, we honor a special X-Tapis-local-tenant header, for specifying the
            # tenant one wants to interact with, but ONLY in local development
            if 'http://localhost' in request_url or 'http://testserver' in request_url:
                tapis_local_tenant = request.META.get('HTTP_X_TAPIS_LOCAL_TENANT')
                logger.warning(f"This is local development; request_url was: {request_url}; "
                               f"tapis_local_tenant: {tapis_local_tenant}")
                if tapis_local_tenant:
                    tenant_id = tapis_local_tenant
            if not tenant_id:
                tenant_id = get_tenant_id_from_base_url(request_url, t.tenant_cache)
        except Exception as e:
            msg = f"Error occurred while calculating tenant ID from the request base URL."
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        logger.info(f"request tenant_id: {tenant_id}")

        # next, determine the username associated with the authentication token --
        try:
            # get user associated with request
            username, error_response = get_username_for_request(request, tenant_id)
            if error_response:
                return error_response
        except Exception as e:
            logger.error(f"Unable to determine username associated with the authentication token. Exception: {e}")
            return HttpResponseBadRequest(
                make_error(msg=f"There was an error parsing the authentication headers. Details: {e}"))
        logger.info(f"request username: {username}")

        try:
            roles = t.sk.getUserRoles(user=username, tenant=tenant_id)
            role_list = list()
            for name in roles.names:
                role_list.append(name)
        except Exception as e:
            msg = f"Error occurred while retrieving roles from SK: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        logger.debug(f"got roles: {role_list}")

        try:
            db_instance_name = Tenants.objects.get(tenant_name=tenant_id).db_instance_name
        except Exception as e:
            msg = f"Error occurred while retrieving the db instance name for tenant '{tenant_id}'. " \
                  f"Details: {e}."
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        logger.debug(f"got db_instance_name: {db_instance_name}")

        request.session['roles'] = role_list
        request.session['username'] = username
        request.session['tenant_id'] = tenant_id
        request.session['db_instance_name'] = db_instance_name

        return super().dispatch(request, *args, **kwargs)


class TableManagement(RoleSessionMixin, APIView):
    """
    GET: Returns information about all of the tables.
    POST: Creates a new table in ManageTables, and then a new table from the json provided by the user.
    All of these endpoints are restricted to ADMIN role only.
    """
    @is_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/tables")
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
                               "primary_key": table.primary_key,
                               "columns": table.column_definition,
                               "update_schema": table.validate_json_update,
                               "create_schema": table.validate_json_create,
                               "tenant_id": table.tenant_id,
                               "comments": table.comments})
        else:
            for table in tables:
                result.append({"table_name": table.table_name,
                               "table_id": table.pk,
                               "root_url": table.root_url,
                               "tenant": table.tenant_id,
                               "endpoints": table.endpoints,
                               "tenant_id": table.tenant_id,
                               "primary_key": table.primary_key,
                               "comments": table.comments})

        return HttpResponse(make_success(result=result), content_type='application/json')

    @is_admin
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /manage/tables")
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']

        # Parse out required fields.
        try:
            table_name = request.data['table_name']
            columns = request.data['columns']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating a new table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Parse out optional fields.
        root_url = request.data.get('root_url', table_name)
        list_all = request.data.get('list_all', True)
        list_one = request.data.get('list_one', True)
        create = request.data.get('create', True)
        update = request.data.get('update', True)
        delete = request.data.get('delete', True)
        endpoints = request.data.get('endpoints', True)
        enums = request.data.get('enums', None)
        comments = request.data.get('comments', "")
        constraints = request.data.get('constraints', {})

        if ManageTables.objects.filter(table_name=table_name, tenant_id=req_tenant).exists():
            msg = f"Table with name \'{table_name}\' and tenant_id \'{req_tenant}\' already exists in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if ManageTables.objects.filter(root_url=root_url).exists():
            msg = f"Table with root url \'{root_url}\' already exists in ManageTables table. " \
                  f"Table name: {table_name}"
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

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

        # Create enums
        if enums:
            try:
                manage_tables.parse_enums(enums, req_tenant, db_instance_name)
            except Exception as e:
                msg = f"Failed to create enums for table {table_name}. e:{e}"
                logger.error(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

        # We grab enums to do some checks
        try:
            existing_enums = manage_tables.get_enums(db_instance_name)    
            if existing_enums.get(req_tenant):
                existing_enums_names = list(existing_enums.get(req_tenant).keys())
            else:
                existing_enums_names = []
            logger.info(f"Got list of existing enum_names: {existing_enums_names}")
        except Exception as e:
            msg = f"Failed to get enums for table {table_name}. e:{e}"
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Going through data and parsing out some table column data.
        # primary_key is added to the primary_key column.
        # CREATETIME or UPDATETIME are added to the specials_rules column.
        try:
            primary_key = None
            special_rules = {"CREATETIME": [], "UPDATETIME": []}
            for column_key, column_args in columns.items():
                if column_args.get("primary_key"):
                    if primary_key:
                        msg = "Found two columns with 'primary_key' set to True, only one primary" \
                            " key may exist in each table."
                        logger.warning(msg)
                        return HttpResponseBadRequest(make_error(msg=msg))
                    else:
                        primary_key = column_key
                if column_args.get("default") in ["CREATETIME", "UPDATETIME"] and column_args.get('data_type') in ['timestamp', 'date']:
                    # Create new managetables column for parsing during create/update row.
                    special_rules[column_args["default"]].append(column_key)
                    # Change the defaults to "NOW()" so the columns automatically update time during creation.
                    columns[column_key]["default"] = 'NOW()'
            if not primary_key:
                primary_key = f"{table_name}_id"
        except Exception as e:
            msg = f"Failed to parse primary keys and special rules from data for table {table_name}. e:{e}"
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Checking constraints
        if not isinstance(constraints, dict):
            msg = f"Constraints should be of type dict. Object inputted: {constraints} for table {table_name} on tenant {req_tenant}"
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Create a validation schema
        try:
            validate_json_create, validate_json_update = create_validate_schema(columns, req_tenant, existing_enums_names)
        except Exception as e:
            msg = f"Unable to create json validation schema for table {table_name}: {e}" \
                  f"\nFailed to create table {table_name}. "
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Create table
        try:
            result = self.post_transaction(table_name, root_url, primary_key, columns, validate_json_create, validate_json_update,
                                           endpoints, existing_enums_names, special_rules, comments, constraints, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to create table {table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @transaction.atomic
    def post_transaction(self, table_name, root_url, primary_key, columns, validate_json_create, validate_json_update,
                         endpoints, existing_enum_names, special_rules, comments, constraints, tenant_id, db_instance_name):

        new_table = ManageTables.objects.create(table_name=table_name, root_url=root_url, column_definition=columns,
                                                validate_json_create=validate_json_create,
                                                validate_json_update=validate_json_update,
                                                endpoints=endpoints, special_rules=special_rules,
                                                comments=comments, constraints=constraints,
                                                tenant_id=tenant_id, primary_key=primary_key)

        ManageTablesTransition.objects.create(manage_table=new_table, column_definition_tn=columns,
                                              validate_json_create_tn=validate_json_create,
                                              validate_json_update_tn=validate_json_update)

        manage_tables.create_table(table_name, columns, existing_enum_names, constraints, tenant_id, db_instance_name)

        result = {
            "table_name": new_table.table_name,
            "table_id": new_table.pk,
            "root_url": new_table.root_url,
            "endpoints": new_table.endpoints,
            "comments": new_table.comments
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
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table_id = int(table_id)
        except:
            msg = "Invalid table id; the table id must be an integer."
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Display information for each table based on details variable.
        try:
            table = ManageTables.objects.get(pk=table_id)

        except ManageTables.DoesNotExist:
            msg = f"Table with id {table_id} does not exist in the ManageTables table."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))
        except Exception as e:
            msg = f"Could not retrieve description of table with id {table_id}. Details: {e}"
            logger.debug(msg)
            return HttpResponseNotFound(make_error(msg=msg))

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
                "create schema": table.validate_json_create,
                "primary_key": table.primary_key,
                "comments": table.comments
            }
        else:
            result = {
                "table_name": table.table_name,
                "table_id": table.pk,
                "root_url": table.root_url,
                "endpoints": table.endpoints,
                "tenant_id": table.tenant_id,
                "primary_key": table.primary_key,
                "comments": table.comments
            }

        return HttpResponse(make_success(result=result), content_type='application/json')

    @is_admin
    def put(self, request, *args, **kwargs):
        logger.debug("top of put /manage/tables/<id>")
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']

        # Parse out required fields.
        try:
            table_id = self.kwargs['manage_table_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to update a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(pk=table_id)
            transition_table = ManageTablesTransition.objects.get(manage_table=table)
        except ManageTables.DoesNotExist:
            msg = f"Table with ID {table_id} does not exist in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        except ManageTablesTransition.DoesNotExist:
            msg = f"Transition table for table with ID {table_id} does not exist."
            logger.warning(msg)
            return HttpResponseServerError(make_error(msg=msg))

        # Parse out possible update fields.
        root_url = request.data.get('root_url', None)
        table_name = request.data.get('table_name', None)
        update_cols = request.data.get('columns', None)
        comments = request.data.get('comments', None)
        list_all = request.data.get('list_all', ("GET_ALL" in table.endpoints))
        list_one = request.data.get('list_one', ("GET_ONE" in table.endpoints))
        create = request.data.get('create', ("CREATE" in table.endpoints))
        update = request.data.get('update', ("UPDATE" in table.endpoints))
        delete = request.data.get('delete', ("DELETE" in table.endpoints))
        endpoints = request.data.get('endpoints', True)

        if root_url is not None:
            table.root_url = root_url
            table.save()
        if comments is not None:
            table.comments = comments
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
                        return HttpResponseBadRequest(make_error(msg=msg))

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
                        return HttpResponseBadRequest(make_error(msg=msg))

                    transition_table.save()

                # We grab enums to do some checks
                existing_enums = manage_tables.get_enums(db_instance_name)    
                if existing_enums.get(req_tenant):
                    existing_enums_names = list(existing_enums.get(req_tenant).keys())
                else:
                    existing_enums_names = []
                logger.info(f"Got list of existing enum_names: {existing_enums_names}")

                try:
                    validate_json_create_tn, validate_json_update_tn = create_validate_schema(current_cols, req_tenant, existing_enums)
                    transition_table.validate_json_create_tn = validate_json_create_tn
                    transition_table.validate_json_update_tn = validate_json_update_tn
                    transition_table.save()
                except Exception as e:
                    msg = f"Unable to create json validation schema for updating table {table_name}: {e}" \
                          f"\nFailed to update transition table for {table_name}. "
                    logger.warning(msg)
                    return HttpResponseBadRequest(make_error(msg=msg))

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


        return HttpResponse(make_success(msg="Table put successfully."), content_type='application/json')

    @is_admin
    def delete(self, request, *args, **kwargs):
        logger.debug("top of del /manage/tables/<id>")
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']

        # Parse out required fields.
        try:
            table_id = self.kwargs['manage_table_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to drop a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(pk=table_id)
        except ManageTables.DoesNotExist:
            msg = f"Table with ID {table_id} does not exist in ManageTables table."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        try:
            self.delete_transaction(table, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to drop table {table.table_name} from the ManageTables table: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(msg="Table deleted successfully."), content_type='application/json')

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
                    return HttpResponseBadRequest(make_error(msg=msg))
                info.get("delimiter", ',')

                try:
                    dump = bulk_data.dump_data(table_name, file_path, req_tenant)
                    print(dump)
                except Exception as e:
                    print("awww, ", e)

        return HttpResponse(make_success(msg="Table dumped successfully."), content_type='application/json')


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
        logger.debug("top of get /data/<data_root_url>")
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
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        if "GET_ALL" not in table.endpoints:
            msg = "API access to LIST ROWS disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        query_dict = dict()
        for param in params:
            if param.lower().startswith('where'):
                table_columns = table.column_definition.keys()
                if param[6:] in table_columns or param[6:] == 'pk':
                    query_dict.update({param[6:]: params[param]})
                else:
                    msg = f"Invalid query parameter: {param[6:]}"
                    logger.warning(msg)
                    return HttpResponseBadRequest(make_error(msg=msg))

        try:
            if limit is None:
                limit = 10
            if order is not None:
                result = table_data.get_rows_from_table(table.table_name, query_dict, req_tenant,
                                                        limit, db_instance, table.primary_key, order=order)
            else:
                result = table_data.get_rows_from_table(table.table_name, query_dict, req_tenant, limit, db_instance, table.primary_key)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @can_write
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /data/<data_root_url>")
        try:
            req_tenant = request.session['tenant_id']
            db_instance = request.session['db_instance_name']
        except Exception as e:
            msg = f"Invalid request; unable to determine database instance; Details: {e}"
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to list rows in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            msg = f"Could not parse the request; unable to determine root_url; Details: {e}"
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            msg = f"Could not parse the request; unable to look up corresponding table; Details: {e}"
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            request_content_type = request.content_type.lower()
        except Exception as e:
            logger.error(f"could not parse request content type; look into this, e: {e}")
            request_content_type = request.content_type
        if not 'json' in request_content_type:
            msg = f"Content-type application/json is required; found {request_content_type} instead."
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if "CREATE" not in table.endpoints:
            msg = "API access to CREATE disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            data = request.data['data']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating new row in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            msg = f"Could not parse the request. Did you include a data attribute? Is it valid JSON? Details: {e}"
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Validate against the table's json schema.
        try:
            v = Validator(table.validate_json_create)
            if not v.validate(data):
                msg = f"Data determined invalid from validation schema; errors: {v.errors}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            msg = f"Error occurred when validating the data from the validation schema; Details: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            result_id = table_data.create_row(table.table_name, data, req_tenant, table.primary_key,
                                              db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        try:
            result = table_data.get_row_from_table(table.table_name, result_id, req_tenant, table.primary_key, db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @can_write
    def put(self, request, *args, **kwargs):
        logger.debug("top of put /data/<data_root_url>")
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
            return HttpResponseBadRequest(make_error(msg=msg))
        where_clause = result_dict.get("where", None)

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if "UPDATE" not in table.endpoints:
            msg = "API access to UPDATE disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Check if any keys in the table.special_rules are in the UPDATETIME list. If they are,
        #  we check posted data, if they didn't set it, we set it to current time.
        try:
            special_rules = table.special_rules
            for key_to_update in special_rules['UPDATETIME']:
                if not data.get(key_to_update):
                    data[key_to_update] = datetime.datetime.utcnow().isoformat()
        except Exception as e:
            msg = f"Error occurred updating time for {key_to_update}; Details: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            v = Validator(table.validate_json_update)
            if not v.validate(data):
                msg = f"Data determined invalid from json validation schema: {v.errors}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            msg = f"Error occurred when validating the data from the json validation schema: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            if where_clause:
                table_data.update_rows_with_where(table.table_name, data, req_tenant, db_instance, where_clause)
            else:
                table_data.update_rows_with_where(table.table_name, data, req_tenant, db_instance)
        except Exception as e:
            msg = f"Failed to update row in table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(msg="Table put successfully."), content_type='application/json')


class DynamicViewById(RoleSessionMixin, APIView):
    """
    GET: Lists a row in a table, based on root url and ID. Restricted to READ and above role.
    PUT: Updates a single row in a table by the ID. Restricted to WRITE and above role.
    DELETE: Deletes a single row in a table by the ID. Restricted to WRITE and above role.
    """
    @can_read
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /data/<root_url>/<pk>")
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
            pk_id = self.kwargs['primary_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to get row from a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if "GET_ONE" not in table.endpoints:
            msg = "API access to LIST SINGLE ROW disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            result = table_data.get_row_from_table(table.table_name, pk_id, req_tenant, table.primary_key, db_instance)
        except Exception as e:
            msg = f"Failed to retrieve row from table {table.table_name} with pk {pk_id} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @can_write
    def put(self, request, *args, **kwargs):
        logger.debug("top of put /data/<root_url>/<pk>")
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
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if "UPDATE" not in table.endpoints:
            msg = "API access to UPDATE disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Check if any keys in the table.special_rules are in the UPDATETIME list. If they are,
        #  we check posted data, if they didn't set it, we set it to current time.
        try:
            special_rules = table.special_rules
            for key_to_update in special_rules['UPDATETIME']:
                if not data.get(key_to_update):
                    data[key_to_update] = datetime.datetime.utcnow().isoformat()
        except Exception as e:
            msg = f"Error occurred updating time for {key_to_update}; Details: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            v = Validator(table.validate_json_update)
            if not v.validate(data):
                msg = f"Data determined invalid from json validation schema: {v.errors}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            msg = f"Error occurred when validating the data from the json validation schema: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table_data.update_row_with_pk(table.table_name, pk_id, data, req_tenant, table.primary_key, db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to update row in table {table.table_name} with pk {pk_id} in tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            result = table_data.get_row_from_table(table.table_name, pk_id, req_tenant, table.primary_key, db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to retrieve row from table {table.table_name} with pk {pk_id} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @can_write
    def delete(self, request, *args, **kwargs):
        logger.debug("top of del /data/<root_url>/<pk>")
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
            pk_id = self.kwargs['primary_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to delete row from a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(root_url=root_url)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if "DELETE" not in table.endpoints:
            msg = "API access to DELETE disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table_data.delete_row(table.table_name, pk_id, req_tenant, table.primary_key, db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to delete row from table {table.table_name} with pk {pk_id} in tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(msg="Row delected successfully."), content_type='application/json')

class CreateTenant(APIView):
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /manage/tenants")
        try:
            schema_name = request.data['schema_name']
            db_instance = request.data['db_instance']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating new row in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            Tenants.objects.get_or_create(tenant_name=schema_name, db_instance_name=db_instance)
        except Exception as e:
            msg = f"Unable to insert new role into Tenants Django table for tenant " \
                  f"{schema_name} and db_instance {db_instance}: {e}"
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            manage_tables.create_schema(schema_name, db_instance)
        except Exception as e:
            msg = f"Failed to create new schema {schema_name} in db_instance {db_instance}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(msg=f"Tenant '{schema_name}' created successfully."), content_type='application/json')


### Views
# Once we figure out the table and row, these are just simple SQL crud operations.
class ViewsResource(RoleSessionMixin, APIView):
    """
    GET: Lists the rows in the given view based on root url. Restricted to READ and above role.
    POST: Creates a new row in the view based on root URL. Restricted to WRITE and above role.
    PUT: Updates the rows in the given view based on filter. If no filter is provided, updates the entire table.
    Restricted to WRITE and above role.
    """
    @can_read
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /views/<view_root_url>")
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']
        req_username = request.session['username']

        params = self.request.query_params
        limit = self.request.query_params.get("limit")
        order = self.request.query_params.get("order")

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to list rows in a view."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            view = ManageViews.objects.get(root_url=root_url)
        except ManageViews.DoesNotExist:
            msg = f"View with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        # Permission check, permission_rules cross-refed with sk roles
        # Get all user roles from sk and check if view's permission_rules are a subset of user_roles
        user_roles = get_user_sk_roles(req_tenant, req_username)
        try:
            if not set(view.permission_rules).issubset(set(user_roles)):
                msg = f"User {req_username} in tenant {req_tenant} does not have permission to access table {view.view_name} in tenant {req_tenant}."
                logger.debug(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            msg = f"Error checking permissions for view {view.view_name} on tenant {req_tenant}. Error: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if "GET_ALL" not in view.endpoints:
            msg = "API access to LIST ROWS disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        query_dict = dict()

        try:
            if limit is None:
                limit = 10
            if order is not None:
                result = view_data.get_rows_from_view(view.view_name, query_dict, req_tenant,
                                                      limit, db_instance, view.manage_view_id, order=order)
            else:
                result = view_data.get_rows_from_view(view.view_name, query_dict, req_tenant, limit, db_instance, view.manage_view_id)
        except Exception as e:
            msg = f"Failed to retrieve rows from view {view.view_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')


class ViewManagement(RoleSessionMixin, APIView):
    """
    GET: Returns information about all of the views.
    POST: Creates a new table in ManageViews, and then a new view from the json provided by the user.
    All of these endpoints are restricted to ADMIN role only.
    """
    @is_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/views")
        req_tenant = request.session['tenant_id']

        # Check for details=true. Decide what a brief description and a detailed description is.
        details = self.request.query_params.get('details')

        # Display information for each table based on details variable.
        tables = ManageViews.objects.filter(tenant_id=req_tenant)

        result = list()
        # If details, form information about the columns and endpoints of the table
        # TODO Fix up this format.
        if details:
            for table in tables:
                result.append({"view_name": table.view_name,
                               "manage_view_id": table.pk,
                               "root_url": table.root_url,
                               "view_definition": table.view_definition,
                               "permission_rules": table.permission_rules,
                               "endpoints": table.endpoints,
                               "tenant_id": table.tenant_id})
        else:
            for table in tables:
                result.append({"view_name": table.view_name,
                               "manage_view_id": table.pk,
                               "root_url": table.root_url,
                               "endpoints": table.endpoints,
                               "tenant_id": table.tenant_id})

        return HttpResponse(make_success(result=result), content_type='application/json')

    @is_admin
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /manage/views")
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']

        # Parse out required fields.
        try:
            view_name = request.data['view_name']
            select_query = request.data['select_query']
            from_table = request.data['from_table']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating a new table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Parse out optional fields.
        root_url = request.data.get('root_url', view_name)
        where_query = request.data.get('where_query', None)
        permission_rules = request.data.get('permission_rules', [])
        list_all = request.data.get('list_all', True)
        list_one = request.data.get('list_one', True)
        create = request.data.get('create', True)
        update = request.data.get('update', True)
        delete = request.data.get('delete', True)
        endpoints = request.data.get('endpoints', True)

        # view_name checks
        if not isinstance(view_name, str):
            msg = f"The view_name must be of type string. Got type: {type(view_name)}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        if not FORBIDDEN_CHARS.match(view_name):
            msg = f"The view_name inputted is not url safe. Value must be alphanumeric with _ and - optional. Value inputted: {view_name}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Check for existence of view_name, table_name, and root_url
        if ManageViews.objects.filter(view_name=view_name, tenant_id=req_tenant).exists():
            msg = f"View with name \'{view_name}\' and tenant_id \'{req_tenant}\' already exists in ManageViews table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if ManageViews.objects.filter(root_url=root_url).exists():
            msg = f"View with root url \'{root_url}\' already exists in ManageViews table. " \
                  f"View name: {view_name}"
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if not ManageTables.objects.filter(table_name=from_table, tenant_id=req_tenant).exists():
            msg = f"Table with name \'{from_table}\' and tenant_id \'{req_tenant}\' does not exist in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Get endpoint rules
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

        # Create view_definition
        view_definition = {"select_query": select_query,
                           "from_table": from_table,
                           "where_query": where_query}

        # Create view
        try:
            result = self.post_view_transaction(view_name, root_url, view_definition, permission_rules, endpoints, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to create view {view_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @transaction.atomic
    def post_view_transaction(self, view_name, root_url, view_definition, permission_rules, endpoints, tenant_id, db_instance_name):

        new_view = ManageViews.objects.create(view_name=view_name, root_url=root_url, view_definition=view_definition,
                                              permission_rules=permission_rules, endpoints=endpoints, tenant_id=tenant_id)

        view_data.create_view(view_name, view_definition, tenant_id, db_instance=db_instance_name)

        result = {
            "view_name": new_view.view_name,
            "view_id": new_view.pk,
            "root_url": new_view.root_url,
            "endpoints": new_view.endpoints
        }

        return result


class ViewManagementById(RoleSessionMixin, APIView):
    """
    GET: Returns information about all of the views.
    POST: Creates a new table in ManageViews, and then a new view from the json provided by the user.
    All of these endpoints are restricted to ADMIN role only.
    """
    @is_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/views/<id>")
        req_tenant = request.session['tenant_id']

        # Check for details=true. Decide what a brief description and a detailed description is.
        details = self.request.query_params.get('details')

        # Parse out required fields.
        try:
            view_id = self.kwargs['manage_view_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to list a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            view_id = int(view_id)
        except:
            msg = "Invalid view id; the view id must be an integer."
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageViews.objects.get(pk=view_id)
        except ManageViews.DoesNotExist:
            msg = f"View with id {view_id} does not exist in the ManageViews table."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))
        except Exception as e:
            msg = f"Could not retrieve description of view with id {view_id}. Details: {e}"
            logger.debug(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        if details:
            result = {"view_name": table.view_name,
                      "manage_view_id": table.pk,
                      "root_url": table.root_url,
                      "view_definition": table.view_definition,
                      "permission_rules": table.permission_rules,
                      "endpoints": table.endpoints,
                      "tenant_id": table.tenant_id}
        else:
            result = {"view_name": table.view_name,
                      "manage_view_id": table.pk,
                      "root_url": table.root_url,
                      "endpoints": table.endpoints,
                      "tenant_id": table.tenant_id}

        return HttpResponse(make_success(result=result), content_type='application/json')

    @is_admin
    def delete(self, request, *args, **kwargs):
        logger.debug("top of del /views/<view_root_url>")
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']

        # Parse out required fields.
        try:
            view_id = self.kwargs['manage_view_id']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to drop a view."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            view = ManageViews.objects.get(pk=view_id)
        except ManageViews.DoesNotExist:
            msg = f"View with ID {view_id} does not exist in ManageViews table."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        try:
            self.delete_transaction(view, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to drop view {view.view_name} from the ManageViews table: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(msg="View deleted successfully."), content_type='application/json')

    @transaction.atomic
    def delete_view_transaction(self, view, tenant_id, db_instance_name):
        ManageViews.objects.get(view_name=view.view_name, tenant_id=tenant_id).delete()
        view_data.delete_view(view.view_name, tenant_id, db_instance=db_instance_name)