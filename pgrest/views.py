import datetime
import json
import re
import timeit
import copy

import requests
from cerberus import Validator
from database_tenants.models import Tenants
from django.db import transaction
from django.http import (HttpResponse, HttpResponseBadRequest,
                         HttpResponseForbidden, HttpResponseNotFound,
                         HttpResponseServerError)
from pgrest.db_transactions.data_utils import do_transaction
from rest_framework.views import APIView

from pgrest.db_transactions import (bulk_data, manage_tables, table_data,
                                    view_data)
from pgrest.models import ManageTables, ManageTablesTransition, ManageViews
from pgrest.pycommon import errors
from pgrest.pycommon.auth import get_tenant_id_from_base_url, t
from pgrest.pycommon.logs import get_logger
from pgrest.utils import (can_read, can_write, create_validate_schema,
                          is_admin, is_role_admin, is_user, make_error,
                          make_success)

logger = get_logger(__name__)

# We create a forbidden regex for quick parsing
# Forbidden: \ ` ' " ~  / ? # [ ] ( ) @ ! $ & * + = - . , : ;
FORBIDDEN_CHARS = re.compile("^[^<>\\\/{}[\]~` $'\".:-?#@!$&()*+,;=]*$")


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
    except KeyError:
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
              "expired, or does not represent a valid user in the v2 TACC tenant."
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

        # Grab data about roles from SK.
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
        
        tenant_id = tenant_id.replace('-', '_')

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


### Manage Tables
class TableManagement(RoleSessionMixin, APIView):
    """
    GET: Returns information about all of the tables.
    POST: Creates a new table based on user JSON in the tenant and adds table to list of tables in tenant.
    All of these endpoints are restricted to ADMIN role only.
    """
    @is_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/tables")
        req_tenant = request.session['tenant_id']

        # Check for details=true. Decide what a brief description and a detailed description is.
        details = self.request.query_params.get('details')

        # Display information for each table based on details variable.
        tables = ManageTables.objects.filter()

        result = list()
        # If details, form information about the columns and endpoints of the table
        # TODO Fix up this format.
        if details:
            for table in tables:
                result.append({
                    "table_name": table.table_name,
                    "table_id": table.pk,
                    "root_url": table.root_url,
                    "tenant": table.tenant_id,
                    "endpoints": table.endpoints,
                    "primary_key": table.primary_key,
                    "columns": table.column_definition,
                    "update_schema": table.validate_json_update,
                    "create_schema": table.validate_json_create,
                    "tenant_id": table.tenant_id,
                    "constraints": table.constraints,
                    "comments": table.comments
                })
        else:
            for table in tables:
                result.append({
                    "table_name": table.table_name,
                    "table_id": table.pk,
                    "root_url": table.root_url,
                    "tenant": table.tenant_id,
                    "endpoints": table.endpoints,
                    "tenant_id": table.tenant_id,
                    "primary_key": table.primary_key,
                    "constraints": table.constraints,
                    "comments": table.comments
                })

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
            msg = f"Table with name '{table_name}' and tenant_id '{req_tenant}' already exists in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        
        if ManageViews.objects.filter(view_name=table_name, tenant_id=req_tenant).exists():
            msg = f"View with name '{table_name}' and tenant_id '{req_tenant}' already exists in ManageViews table. View and Table names can collide."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if ManageTables.objects.filter(root_url=root_url, tenant_id=req_tenant).exists():
            msg = f"Table with root url '{root_url}' and tenant_id '{req_tenant}' already exists in ManageTables table. " \
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
                existing_enum_names = list(existing_enums.get(req_tenant).keys())
            else:
                existing_enum_names = []
            logger.info(f"Got list of existing enum_names: {existing_enum_names}")
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
                if (isinstance(column_args.get("default"), str)
                    and column_args.get("default").upper() in ["CREATETIME", "UPDATETIME"]
                    and column_args.get('data_type') in ['timestamp', 'date']):
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
            validate_json_create, validate_json_update = create_validate_schema(columns, req_tenant,
                                                                                existing_enum_names)
        except Exception as e:
            msg = f"Unable to create json validation schema for table {table_name}: {e}" \
                  f"\nFailed to create table {table_name}. "
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Create table
        try:
            result = self.post_transaction(table_name, root_url, primary_key, columns, validate_json_create,
                                           validate_json_update, endpoints, existing_enum_names, special_rules,
                                           comments, constraints, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to create table {table_name}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @transaction.atomic
    def post_transaction(self, table_name, root_url, primary_key, columns, validate_json_create, validate_json_update,
                         endpoints, existing_enum_names, special_rules, comments, constraints, tenant_id,
                         db_instance_name):

        new_table = ManageTables.objects.create(table_name=table_name,
                                                root_url=root_url,
                                                column_definition=columns,
                                                validate_json_create=validate_json_create,
                                                validate_json_update=validate_json_update,
                                                endpoints=endpoints,
                                                special_rules=special_rules,
                                                comments=comments,
                                                constraints=constraints,
                                                tenant_id=tenant_id,
                                                primary_key=primary_key)

        ManageTablesTransition.objects.create(manage_table=new_table,
                                              column_definition_tn=columns,
                                              validate_json_create_tn=validate_json_create,
                                              validate_json_update_tn=validate_json_update)

        manage_tables.create_table(table_name, columns, existing_enum_names, constraints, tenant_id, db_instance_name)

        result = {
            "table_name": new_table.table_name,
            "table_id": new_table.pk,
            "root_url": new_table.root_url,
            "endpoints": new_table.endpoints,
            "constraints": new_table.constraints,
            "comments": new_table.comments
        }

        return result


# These are endpoints to manage the tables and contains metadata for the tables.
class TableManagementById(RoleSessionMixin, APIView):
    """
    GET: Returns the table with the provided ID.
    PUT: Updates the table with the provided ID.
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
                "constraints": table.constraints,
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
                "constraints": table.constraints,
                "comments": table.comments
            }

        return HttpResponse(make_success(result=result), content_type='application/json')

    @is_admin
    def put(self, request, *args, **kwargs):
        """Alter tables using Postgres Alter table commands. This is complicated because
        each table has it's column_definition saved in managetables along with table name.
        We use these to ensure row puts are in the proper formatting and that we call the correct
        tables inside of a tenant.
        
        This means that we'll need to get all column defs and also update column defs depending on
        the inputted data. For example, we'll have to change the table name in managetables if a 
        user passes in {"table_name": newNameHere}.
        
        Also important to remember that we might need to rollback these changes. The changes to
        the Django ManageTables table along with changes to the Postgres data that we're modifying.
        Psycopg2 support cursor.rollback() to rollback to the start of any "pending transactions".
        Django also has rollbacks, when Django errors it'll rollback by itself, this however excludes
        model data changes. Meaning we'll have to save whatever Django model data we have as a "init
        state" and revert back to that if there's a problem down the line.

        Args:
            request: request_object
            kwargs: dict of the following
                "root_url": new_root_url,
                "table_name": new_name,
                "comments": new_comments,
                "endpoints": [new_endpoints_list]},
                "column_type": "column_name, type"
                "drop_column": column_name,
                "drop_default": column_name,
                "set_default": "column_name, new_default"
                "add_column": {"name": {"data_type": "integer",
                                        "unique": true,
                                        "null": false}}
        
        Returns:
            200: Description of successful operation.
            400: Description of operation error.
        """
        logger.debug("top of put /manage/tables/<table_id>")
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
        except ManageTables.DoesNotExist:
            msg = f"Table with ID {table_id} does not exist in ManageTables table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Parse out possible update fields.
        root_url = request.data.get('root_url', None)
        table_name = request.data.get('table_name', None)
        comments = request.data.get('comments', None)
        endpoints = request.data.get('endpoints', None) # GET_ALL, GET_ONE, CREATE, UPDATE, DELETE, ALL
        column_type = request.data.get('column_type', None)
        drop_column = request.data.get('drop_column', None)
        drop_default = request.data.get('drop_default', None)
        set_default = request.data.get('set_default', None)
        add_column = request.data.get('add_column', None)
        
        #ONLY ONE CHANGE PER REQUEST
        # We change Django first and then Postgres and Postgres is harder to revert using do_transaction
        updates_to_do = 0
        for update_field in [root_url, table_name, comments, endpoints, column_type, drop_column, drop_default, set_default, add_column]:
            if update_field:
                updates_to_do += 1
        if updates_to_do == 0:
            msg = f"No updates requested"
            logger.warning(msg)
            return HttpResponse(make_success(msg="No updates to table requested. Success."), content_type='application/json')
        if updates_to_do >= 2:
            msg = f"Only one update to table may be done at a time."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Backup table - To revert to if there's a problem
        backup_table = copy.copy(table)
        
        
        # root_url operation
        if root_url:
            if not isinstance(root_url, str):
                msg = f"Error changing root_url for table {backup_table.table_name}. 'root_url' must be a str. Received type {type(root_url)}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            try:
                table.root_url = root_url
                table.save()
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error changing root_url for table '{backup_table.table_name}' from '{backup_table.root_url}' to '{root_url}'. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            return HttpResponse(make_success(msg=f"Successfully changed table root_url to '{root_url}' for table '{backup_table.table_name}'."), content_type='application/json')


        # table_name operation
        if table_name is not None:
            if not isinstance(table_name, str):
                msg = f"Error renaming table {backup_table.table_name}. 'table_name' must be a str. Received type {type(table_name)}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg)) 
                     
            try:
                table.table_name = table_name
                table.save()
                command = f"ALTER TABLE {req_tenant}.{backup_table.table_name} RENAME TO {table_name}"
                do_transaction(command, db_instance_name)
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error changing table name from {backup_table.table_name} to {table_name}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully changed table_name to '{table_name}' from '{backup_table.table_name}'."), content_type='application/json')
        

        # comment operation
        if comments is not None:
            if not isinstance(comments, str):
                msg = f"Error adding comments to table '{backup_table.table_name}'. 'comments' must be a str. Received type {type(comments)}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            try:
                table.comments = comments
                table.save()
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error adding comments to table {backup_table.table_name}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully added comments to table, '{backup_table.table_name}'."), content_type='application/json')
            

        # endpoints operation
        if endpoints is not None:
            valid_endpoints = ["GET_ALL", "GET_ONE", "CREATE", "UPDATE", "DELETE", "ALL", "NONE"]
            if not isinstance(endpoints, list):
                msg = f"Error with put to table with ID {backup_table.table_name}. 'endpoints' must be a list. Received type {type(endpoints)}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            try:
                endpoints = set(endpoints)
                endpoints = list(endpoints)
                if "NONE" in endpoints and len(endpoints) > 1:
                    msg = f"Error, when specifying NONE in endpoints you cannot specify anything else. endpoints: {endpoints}"
                    logger.warning(msg)
                    return HttpResponseBadRequest(make_error(msg=msg))
                if "ALL" in endpoints and len(endpoints) > 1:
                    msg = f"Error, when specifying ALL in endpoints you cannot specify anything else. endpoints: {endpoints}"
                    logger.warning(msg)
                    return HttpResponseBadRequest(make_error(msg=msg))
                for endpoint in endpoints:
                    if endpoint not in valid_endpoints:
                        msg = f"Error with put to table with ID {backup_table.table_name}. Endpoints list can only contain str values from: {valid_endpoints}"
                        logger.warning(msg)
                        return HttpResponseBadRequest(make_error(msg=msg))
                    if endpoint == "ALL":
                        endpoints = valid_endpoints
                        # All/None isn't an actual thing we want to save.
                        endpoints.remove("ALL")
                        endpoints.remove("NONE")
                    if endpoint == "NONE":
                        endpoints = []

                table.endpoints = endpoints
                table.save()
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error changing endpoints for table {backup_table.table_name}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully changed table, '{backup_table.table_name}', to have the following endpoints: {endpoints}"), content_type='application/json')

        # We grab enums to do run 'create_validate_schema' in column_type and drop_column operations
        if column_type or drop_column or add_column:
            existing_enums = manage_tables.get_enums(db_instance_name)
            if existing_enums.get(req_tenant):
                existing_enum_names = list(existing_enums.get(req_tenant).keys())
            else:
                existing_enum_names = []
            logger.info(f"Got list of existing enum_names: {existing_enum_names}")

        # column_type operation
        if column_type:
            if not isinstance(column_type, str):
                msg = f"Error changing column type for table. 'column_type' must be a str. Received type {type(column_type)}. Format should be 'column_name, new_type'"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            split_str = column_type.split(',')
            if not len(split_str) == 2:
                msg = f"Error changing column type for table. 'column_type' should come in format 'column_name, new_type', got {column_type}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            if not split_str[0] or not split_str[1]:
                msg = f"Error changing column type for table. 'column_type' should come in format 'column_name, new_type', got {column_type}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            column_name, new_type = split_str
            column_name = column_name.strip()
            new_type = new_type.strip()
                        
            # Check that new_type is in valid_types or is in existing_enums
            valid_types = ["varchar", "boolean", "integer", "text", "timestamp", "datetime"]
            if new_type not in valid_types + existing_enum_names:
                msg = f"Error changing column type for table. '{new_type}' not in {valid_types + existing_enum_names}. Note: Cannot update to a serial data type."
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Check column_name is legal.
            valid_column_names = table.column_definition.keys()
            if not column_name in valid_column_names:
                msg = f"Error: column_name not in current table. '{column_name}' not in {list(valid_column_names)}."
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            new_column_definition = copy.copy(table.column_definition)
            
            # Make the type change to the column_definition.
            try:
                old_column = new_column_definition[column_name]
                new_column_definition[column_name]['data_type'] = new_type
                if old_column['data_type'] == 'varchar' and new_type != 'varchar':
                    del new_column_definition[column_name]['char_len']
                if new_type == 'varchar' and not new_column_definition[column_name].get('char_len'):
                    new_column_definition[column_name]['char_len'] = '255'
            except Exception as e:
                msg = f"Error changing column type in column_definition. New def: {new_column_definition}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Create a validation schema
            try:
                validate_json_create, validate_json_update = create_validate_schema(new_column_definition, req_tenant, existing_enum_names)
            except Exception as e:
                msg = f"Unable to create json validation schema after changing table column type. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            try:
                table.column_definition = new_column_definition
                table.validate_json_create = validate_json_create
                table.validate_json_update = validate_json_update
                table.save()
                command = f"ALTER TABLE {req_tenant}.{backup_table.table_name} ALTER COLUMN {column_name} TYPE {new_type}"
                do_transaction(command, db_instance_name)
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error changing column_name '{column_name}' to type '{new_type}' in table '{backup_table.table_name}'. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully changed column_name '{column_name}' to type '{new_type}' in table '{backup_table.table_name}'."), content_type='application/json')

        # add_column operation
        if add_column:
            if not isinstance(add_column, dict):
                msg = f"Error with put to table with ID {backup_table.table_name}. 'add_column' must be a dict. Received type {type(add_column)}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            if len(add_column) > 1:
                msg = "add_column dict received is too large. Should be len of '1', in format {'col_name': {'data_type': 'integer', ...}\}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            (column_name, column_args), = add_column.items()
            
            if not isinstance(column_args, dict):
                msg = f"Error with put to table with ID {backup_table.table_name}. 'add_column' must be dict with value of type dict. In format {'col_name': {'data_type': 'integer', ...}\}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))


            ### We now validate the column_definition just to make sure all keys and values are expected and accounted for. Used later to update Django.
            new_column_definition = copy.copy(table.column_definition)
            
            # Append the added column to column definition
            try:
                new_column_definition.update(add_column)
            except Exception as e:
                msg = f"Error adding column to table definition. New def: {new_column_definition}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Create a validation schema
            try:
                validate_json_create, validate_json_update = create_validate_schema(new_column_definition, req_tenant, existing_enum_names)
            except Exception as e:
                msg = f"Unable to create json validation schema after adding column to table definition. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))


            ### Validation complete, now we create the Postgres command we have to run.
            # We need to grab the column type first as it used to decide how to handle the other variables.
            try:
                column_type = column_args["data_type"].upper()
            except KeyError:
                msg = f"Data type not specified for new column. Column args are as follows: {column_args}"
                raise Exception(msg)
            if column_type in {"VARCHAR", "CHAR"}:
                try:
                    char_len = column_args["char_len"]
                    column_type = f"{column_type}({char_len})"
                except KeyError:
                    msg = f"Character max size not received for column {column_name}. Cannot create table {table_name}."
                    logger.warning(msg)
                    raise Exception(msg)

            # Attempt to handle enum data_types
            # This is only a small subsect of postgres data_types, listing them
            # all would be trouble though, so just checking the common ones.
            # Here we are fixing enum data_types given without tenant, i.e., data_type: "animals"
            # Should be "dev.animals", we fix that here if we can.
            if not column_type in ["BOOLEAN", "VARCHAR", "CHAR", "TEXT", "INTEGER", "SERIAL", "FLOAT", "DATE", "TIMESTAMP"]:
                if column_type.lower() in existing_enum_names:
                    column_type = f"{req_tenant}.{column_type}"

            # Changing serial data types to an identity type that allows for user inputted increment and start.
            if column_type == "SERIAL":
                try:
                    serial_start = int(column_args.get("serial_start", 1))
                    serial_increment = int(column_args.get("serial_increment", 1))
                    column_type = f"INTEGER GENERATED BY DEFAULT AS IDENTITY (START WITH {serial_start} INCREMENT BY {serial_increment})"
                except Exception as e:
                    msg = f"Error setting serial data_type for column {key}. e: {e}"
                    logger.warning(msg)
                    raise Exception(msg)

            # Handle foreign keys.
            if "foreign_key" in column_args and column_args["foreign_key"]:
                try:
                    # On_event means either on_delete or on_update for foreign keys. During that event
                    # postgres will complete the event_action specified by the user.
                    # check we have we need
                    ref_table = column_args["reference_table"]
                    ref_column = column_args["reference_column"]
                    on_event = column_args["on_event"]
                    event_action = column_args["event_action"]
                except KeyError as e:
                    msg = f"Required key {e.args[0]} for foreign key not received for column {column_name}. " \
                        f"Cannot create table {table_name}."
                    logger.warning(msg)
                    raise Exception(msg)

                try:
                    on_event = on_event.upper()
                    event_action = event_action.upper()
                except:
                    msg = f"on_event and event_action must both be strings, got {type(on_event)} and {type(event_action)}"
                    logger.warning(msg)
                    raise Exception(msg)

                # Check that on_event is either DELETE or UPDATE
                events = ["ON DELETE", "ON UPDATE"]
                if on_event not in events:
                    msg = f"Invalid on event supplied: {on_event}. Valid event actions: {events}."
                    logger.warning(msg)
                    raise Exception(msg)
                # Do some input checking on event action.
                event_options = ["SET NULL", "SET DEFAULT", "RESTRICT", "NO ACTION", "CASCADE"]
                if event_action not in event_options:
                    msg = f"Invalid event action supplied: {event_action}. Valid event actions: {event_options}."
                    logger.warning(msg)
                    raise Exception(msg)
                # Cannot set on event action to SET NULL if the column does not allow nulls.
                if event_action == "SET NULL" and "null" in column_args and not column_args["null"]:
                    msg = f"Cannot set event action on column {column_name} " \
                            f"as it does not allow nulls in column definition."
                    logger.warning(msg)
                    raise Exception(msg)

                column_type = f"{column_type} REFERENCES {req_tenant}.{ref_table}({ref_column}) {on_event} {event_action}"

            col_str_list = list()
            col_string = f"{column_name} {column_type}"
            col_str_list.append(col_string)

            # Find optional values and assign to variable.
            for key, val in column_args.items():
                if key == "null":
                    if not val:
                        col_str_list.append("NOT NULL")
                elif key == "unique":
                    col_str_list.append("UNIQUE")
                elif key == "default":
                    # Check if default value should be encased in quotes. (str v. int)
                    if type(val) == 'int' or type(val) == 'float':
                        col_str_list.append(f"DEFAULT {val}")
                    else:
                        col_str_list.append(f"DEFAULT '{val}'")
                elif key == "primary_key" and val == True:
                    if not column_args['data_type'].lower() in ['integer', 'varchar', 'serial']:
                        msg = f"primary_key field can only be set on fields of data_type 'integer', 'serial', or 'varchar'." \
                            f" {column_args['data_type']} is not. Cannot create table: {table_name}"
                        logger.warning(msg)
                        raise Exception(msg)
                    if column_args.get('null'):
                        msg = f"primary_key field cannot have 'null' set to True. Field must have unique value." \
                            f" Cannot create table: {table_name}"
                        logger.warning(msg)
                        raise Exception(msg)
                    if column_args.get('default'):
                        msg = f"primary_key field cannot have a 'default' set. Field must have unique value." \
                            f" Cannot create table: {table_name}"
                        logger.warning(msg)
                        raise Exception(msg)
                    primary_key_flag = True
                    col_str_list.append("PRIMARY KEY")
                elif key == "comments":
                    continue
                elif key not in ["data_type", "char_len", "foreign_key", "reference_table", "reference_column", "on_event", "event_action", "serial_start", "serial_increment"]:
                    msg = f"{key} is an invalid argument for column {column_name}. Cannot create table {table_name}"
                    logger.warning(msg)
                    raise Exception(msg)
    
            col_def_command = " ".join(col_str_list)

            # We now have the command to run, but we still need to change things in Django to correspond.
            try:
                table.column_definition = new_column_definition
                table.validate_json_create = validate_json_create
                table.validate_json_update = validate_json_update
                table.save()
                command = f"ALTER TABLE {req_tenant}.{backup_table.table_name} ADD {col_def_command};"
                do_transaction(command, db_instance_name)
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error adding column_name '{column_name}' to table '{backup_table.table_name}'. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully added column, '{column_name}', to table '{backup_table.table_name}'"), content_type='application/json')


        # drop_column operation
        if drop_column:
            column_name = drop_column
            if not isinstance(column_name, str):
                msg = f"Error dropping column in table. 'column_name' must be a str. Received type {type(column_name)}. Format should be 'column_name'"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Check column_name is legal.
            valid_column_names = table.column_definition.keys()
            if not column_name in valid_column_names:
                msg = f"Error: column_name not in current table. '{column_name}' not in {list(valid_column_names)}."
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            new_column_definition = copy.copy(table.column_definition)
            
            # Delete column from column_def
            try:
                del new_column_definition[column_name]
            except Exception as e:
                msg = f"Error dropping column in column_definition. New def: {new_column_definition}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Create a validation schema
            try:
                validate_json_create, validate_json_update = create_validate_schema(new_column_definition, req_tenant, existing_enum_names)
            except Exception as e:
                msg = f"Unable to create json validation schema after changing table column type. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            try:
                table.column_definition = new_column_definition
                table.validate_json_create = validate_json_create
                table.validate_json_update = validate_json_update
                table.save()
                command = f"ALTER TABLE {req_tenant}.{backup_table.table_name} DROP COLUMN {column_name}"
                do_transaction(command, db_instance_name)
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error dropping column_name '{column_name}' in table '{backup_table.table_name}'. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully dropped column, '{column_name}', from table '{backup_table.table_name}'"), content_type='application/json')


        # drop_default operation
        if drop_default:
            column_name = drop_default
            if not isinstance(column_name, str):
                msg = f"Error dropping column default in table. 'column_name' must be a str. Received type {type(column_name)}. Format should be 'column_name'"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Check column_name is legal.
            valid_column_names = table.column_definition.keys()
            if not column_name in valid_column_names:
                msg = f"Error: column_name not in current table. '{column_name}' not in {list(valid_column_names)}."
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            new_column_definition = copy.copy(table.column_definition)
            
            # Delete default from column_def
            try:
                del new_column_definition[column_name]['default']
            except Exception as e:
                msg = f"Error dropping column default in column_definition. New def: {new_column_definition}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Create a validation schema
            try:
                validate_json_create, validate_json_update = create_validate_schema(new_column_definition, req_tenant, existing_enum_names)
            except Exception as e:
                msg = f"Unable to create json validation schema after changing table column type. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            try:
                table.column_definition = new_column_definition
                table.validate_json_create = validate_json_create
                table.validate_json_update = validate_json_update
                table.save()
                command = f"ALTER TABLE {req_tenant}.{backup_table.table_name} ALTER COLUMN {column_name} DROP DEFAULT"
                do_transaction(command, db_instance_name)
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error dropping default from column_name '{column_name}' in table '{backup_table.table_name}'. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully dropped default from column, '{column_name}', from table '{backup_table.table_name}'"), content_type='application/json')


        # set_default operation
        if set_default:
            if not isinstance(set_default, str):
                msg = f"Error setting default for column in table. 'set_default' must be a str. Received type {type(set_default)}. Format should be 'column_name, new_default'"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            split_str = set_default.split(',')
            if not len(split_str) == 2:
                msg = f"Error setting default for column in table. 'set_default' should come in format 'column_name, new_default', got {column_type}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            if not split_str[0] or not split_str[1]:
                msg = f"Error setting default for column in table. 'set_default' should come in format 'column_name, new_default', got {column_type}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            column_name, new_default = set_default
            column_name = column_name.strip()
            new_default = new_default.strip()

            # Check column_name is legal.
            valid_column_names = table.column_definition.keys()
            if not column_name in valid_column_names:
                msg = f"Error: column_name not in current table. '{column_name}' not in {list(valid_column_names)}."
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            new_column_definition = copy.copy(table.column_definition)
            
            # Add new column definition to column_definition.
            try:
                new_column_definition[column_name]["default"] = new_default
            except Exception as e:
                msg = f"Error setting default for column in table. New def: {new_column_definition}. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            # Create a validation schema
            try:
                validate_json_create, validate_json_update = create_validate_schema(new_column_definition, req_tenant, existing_enum_names)
            except Exception as e:
                msg = f"Unable to create json validation schema after changing table column default. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            try:
                table.column_definition = new_column_definition
                table.validate_json_create = validate_json_create
                table.validate_json_update = validate_json_update
                table.save()
                command = f"ALTER TABLE {req_tenant}.{backup_table.table_name} ALTER COLUMN {column_name} SET DEFAULT {new_default}"
                do_transaction(command, db_instance_name)
            except Exception as e:
                # Revert Django
                backup_table.save()
                msg = f"Changes reverted. Error changing default for column_name '{column_name}' to '{new_default}' in table '{backup_table.table_name}'. e: {e}"
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            return HttpResponse(make_success(msg=f"Successfully set column default for column, '{column_name}', on table '{backup_table.table_name}'"), content_type='application/json')



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
    From Brandi, looks like an endpoint that dumps table contents to specified text file on host.
    POST: Dumps table_name in req_tenant to file_path on host.
    WIP. Hasn't been touched since Brandi.
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
                except KeyError:
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
    From Brandi, looks like an opposite of dump, presume give file_name and load the previously
    dumped data back into the database.
    POST: ?
    WIP. Hasn't been touched since Brandi.
    """
    @is_admin
    def post(self, request, *args, **kwargs):
        # req_tenant = "public"
        req_tenant = request.session['tenant_id']


# For dynamic views, all end users will end up here. We will find the corresponding table
# based on the url to get here. We then will formulate a SQL statement to do the need actions.


### Table Rows
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
        logger.debug("top of get /data/<root_url>")
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']

        params = self.request.query_params
        limit = self.request.query_params.get("limit")
        offset = self.request.query_params.get("offset")
        order = self.request.query_params.get("order")

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
        except KeyError as e:
            msg = f"\'{e.args}\' is required to list rows in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            table = ManageTables.objects.get(root_url=root_url, tenant_id=req_tenant)
        except ManageTables.DoesNotExist:
            msg = f"Table with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        if "GET_ALL" not in table.endpoints:
            msg = "API access to LIST ROWS disabled."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            # Parse params, if the key contains a search operation, throw it into search_params
            # search_params list is [[key, oper, value], ...]
            search_params = []
            opers = ['.neq', '.eq', '.lte', '.lt', '.gte', '.gt', '.nin', '.in',
                     '.null', '.between', '.nbetween', '.like', '.nlike']
            for full_key, value in params.items():
                # Check that value is not list, if it is that means the user had two query parameters that were
                # exactly the same and the request object consolidated the inputs, we don't want/need this.
                if isinstance(value, list):
                    msg = f"You may only specify a query value once, ex. ?col1.eq=2&col1.eq=2 is NOT allowed."
                    logger.critical(msg + f" e: {e}")
                    return HttpResponseBadRequest(make_error(msg=msg))

                # If param ends with the operation, we remove the operation and use it later. That
                # should leave only the key value that we can check later against the view's columns
                for oper in opers:
                    if full_key.endswith(oper):
                        key = full_key.replace(oper, "")
                        search_params.append([key, oper, value])
                        break
            logger.info(f"Search params: {search_params}")
            
            # limit and offset checking
            try:
                if limit:
                    limit = int(limit)
                else:
                    limit = None
                    
                if limit == -1:
                    limit = None
                
                if offset:
                    offset = int(offset)
                else:
                    offset = None
            except Exception as e:
                msg = f"Limit and offset query parameters must be ints. Got limit: {type(limit)} and offset: {type(offset)}"
                logger.error(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            if order is not None:
                result = table_data.get_rows_from_table(table.table_name,
                                                        search_params,
                                                        req_tenant,
                                                        limit,
                                                        offset,
                                                        db_instance,
                                                        table.primary_key,
                                                        order=order)
            else:
                result = table_data.get_rows_from_table(table.table_name, search_params, req_tenant, limit, offset,
                                                        db_instance, table.primary_key)
        except Exception as e:
            msg = f"Failed to retrieve rows from table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')

    @can_write
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /data/<root_url>")
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
            table = ManageTables.objects.get(root_url=root_url, tenant_id=req_tenant)
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

        try:
            new_rows = table_data.row_creator(table.table_name,
                                              data,
                                              req_tenant,
                                              table.primary_key,
                                              table.validate_json_create,
                                              db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to add rows to table {table.table_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=new_rows), content_type='application/json')

    @can_write
    def put(self, request, *args, **kwargs):
        logger.debug("top of put /data/<root_url>")
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
            table = ManageTables.objects.get(root_url=root_url, tenant_id=req_tenant)
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
                # where_clause comes in as {variable: {"operator": oper, "value": value}, ...}
                # Need to parse dict to search_param format. [[key, oper, value], ...]
                logger.info(f"Parsing where_clause: {where_clause}")
                search_params = []
                if not isinstance(where_clause, dict):
                    msg = f"Error, where clause should come as a dict, got {type(where_clause)}"
                    logger.error(msg)
                    return HttpResponseBadRequest(make_error(msg=msg))
                for where_key, where_dict in where_clause.items():
                    if not isinstance(where_dict, dict):
                        msg = f"Error in where_clause. Got key, but value should be of type dict, got {where_dict}"
                        logger.error(msg)
                        return HttpResponseBadRequest(make_error(msg=msg))
                    where_oper = where_dict.get("operator")
                    where_value = where_dict.get("value")
                    if not where_oper:
                        msg = f"'operator' must be a key in where_clause dict. where_clause dict: {where_dict}"
                        logger.error(msg)
                        return HttpResponseBadRequest(make_error(msg=msg))
                    if not where_value:
                        msg = f"'value' must be a key in where_clause dict. where_clause dict: {where_dict}"
                        logger.error(msg)
                        return HttpResponseBadRequest(make_error(msg=msg))
                    if not isinstance(where_oper, str):
                        msg = f"'operator' must be a string, got: {where_oper}, type: {type(where_oper)}"
                        logger.error(msg)
                        return HttpResponseBadRequest(make_error(msg=msg))
                    
                    logger.info('HERE WHERE_CLAUSE')
                    opers = ['neq', 'eq', 'lte', 'lt', 'gte', 'gt', 'nin', 'in', 'nlike', 'like', 'between', 'nbetween', 'null']
                    if where_oper not in opers:
                        msg = f"where_oper must be in {opers}, got {where_oper}."
                        logger.error(msg)
                        return HttpResponseBadRequest(make_error(msg=msg))
                    
                    search_params.append([where_key, f".{where_oper}", where_value])
                logger.info(f"Search params: {search_params}")
                table_data.update_rows_with_where(table.table_name, data, req_tenant, db_instance, search_params)
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
            table = ManageTables.objects.get(root_url=root_url, tenant_id=req_tenant)
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
            table = ManageTables.objects.get(root_url=root_url, tenant_id=req_tenant)
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
            table_data.update_row_with_pk(table.table_name,
                                          pk_id,
                                          data,
                                          req_tenant,
                                          table.primary_key,
                                          db_instance=db_instance)
        except Exception as e:
            msg = f"Failed to update row in table {table.table_name} with pk {pk_id} in tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            result = table_data.get_row_from_table(table.table_name,
                                                   pk_id,
                                                   req_tenant,
                                                   table.primary_key,
                                                   db_instance=db_instance)
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
            table = ManageTables.objects.get(root_url=root_url, tenant_id=req_tenant)
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


### Views
class ViewManagement(RoleSessionMixin, APIView):
    """
    GET: Returns information about all of the views in the req_tenant.
    POST: Creates a new view based on user JSON in the tenant and adds table to list of views in tenant.
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
                result.append({
                    "view_name": table.view_name,
                    "manage_view_id": table.pk,
                    "root_url": table.root_url,
                    "view_definition": table.view_definition,
                    "permission_rules": table.permission_rules,
                    "endpoints": table.endpoints,
                    "tenant_id": table.tenant_id,
                    "comments": table.comments
                })
        else:
            for table in tables:
                result.append({
                    "view_name": table.view_name,
                    "manage_view_id": table.pk,
                    "root_url": table.root_url,
                    "endpoints": table.endpoints,
                    "tenant_id": table.tenant_id,
                    "comments": table.comments
                })

        return HttpResponse(make_success(result=result), content_type='application/json')

    @is_admin
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /manage/views")
        req_tenant = request.session['tenant_id']
        db_instance_name = request.session['db_instance_name']
        req_username = request.session['username']

        # Parse out required fields.
        try:
            view_name = request.data['view_name']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating a new view."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Parse out optional fields.
        root_url = request.data.get('root_url', view_name)
        raw_sql = request.data.get('raw_sql', None)
        from_table = request.data.get('from_table', None)
        select_query = request.data.get('select_query', None)
        where_query = request.data.get('where_query', None)
        permission_rules = request.data.get('permission_rules', [])
        list_all = request.data.get('list_all', True)
        list_one = request.data.get('list_one', True)
        create = request.data.get('create', True)
        update = request.data.get('update', True)
        delete = request.data.get('delete', True)
        endpoints = request.data.get('endpoints', True)
        comments = request.data.get('comments', "")

        # Check required selection parameters.
        # Check view_name is acceptable
        if not isinstance(view_name, str):
            msg = f"The view_name must be of type string. Got type: {type(view_name)}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        
        if not FORBIDDEN_CHARS.match(view_name):
            msg = f"The view_name inputted is not url safe. Value must be alphanumeric with _ and - optional. Value inputted: {view_name}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Check for existence of view_name in tenant.
        if ManageViews.objects.filter(view_name=view_name, tenant_id=req_tenant).exists():
            msg = f"View with name \'{view_name}\' and tenant_id \'{req_tenant}\' already exists in ManageViews table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Check for view_name in table names (they collide when dealing with sql (e.g. dev.my_item_name))
        if ManageTables.objects.filter(table_name=view_name, tenant_id=req_tenant).exists():
            msg = f"Table with name '{view_name}' and tenant_id '{req_tenant}' already exists in ManageTables table. View and Table names are not allowed to collide."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Check for existence of root_url in tenant.
        if ManageViews.objects.filter(root_url=root_url).exists():
            msg = f"View with root url \'{root_url}\' and tenant_id {req_tenant} already exists in ManageViews table. " \
                  f"View name: {view_name}"
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # If raw_sql being used, select_query, where_query, from_table are disallowed.
        if raw_sql:
            # Permission check, ensure user has PGREST_ADMIN role.
            # Get all user roles from sk and check if user has role.
            user_roles = get_user_sk_roles(req_tenant, req_username)
            if not "PGREST_ADMIN" in user_roles:
                msg = f"User {req_username} in tenant {req_tenant} requires PGREST_ADMIN role for raw_sql view creation."
                logger.debug(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            if select_query:
                msg = f"User may only specify raw_sql or select_query, got both."
                logger.error(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
            
            if where_query:
                msg = f"When using a raw_sql query, where_query is not allowed, got both."
                logger.error(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            if from_table:
                msg = f"When using a raw_sql query, table_name is not allowed, got both."
                logger.error(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
        else:
            if not from_table:
                msg = "'from_table' is required when creating a new view."
                logger.warning(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
                        
            # Check for existence of from_table in tenant.
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
        view_definition = {"from_table": from_table, "raw_sql": raw_sql, "select_query": select_query, "where_query": where_query}

        # Create view
        try:
            result, metadata = self.post_view_transaction(view_name, root_url, view_definition, permission_rules, endpoints,
                                                comments, req_tenant, db_instance_name)
        except Exception as er:
            logger.error(er)
            error = er.args[0]
            metadata = er.args[1]
            msg = f"Failed to create view {view_name}. {error}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg, metadata=metadata))

        return HttpResponse(make_success(result=result, metadata=metadata), content_type='application/json')

    @transaction.atomic
    def post_view_transaction(self, view_name, root_url, view_definition, permission_rules, endpoints, comments,
                              tenant_id, db_instance_name):

        new_view = ManageViews.objects.create(view_name=view_name,
                                              root_url=root_url,
                                              view_definition=view_definition,
                                              permission_rules=permission_rules,
                                              endpoints=endpoints,
                                              comments=comments,
                                              tenant_id=tenant_id)

        metadata = view_data.create_view(view_name, view_definition, tenant_id, db_instance=db_instance_name)

        result = {
            "view_name": new_view.view_name,
            "view_id": new_view.pk,
            "root_url": new_view.root_url,
            "endpoints": new_view.endpoints,
            "comments": new_view.comments
        }

        return result, metadata


class ViewManagementById(RoleSessionMixin, APIView):
    """
    GET: Returns information about view with view_id in req_tenant.
    DEL: Deletes view with view_id in req_tenant.
    All of these endpoints are restricted to ADMIN role only.
    """
    @is_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/views/<manage_view_id>")
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
            result = {
                "view_name": table.view_name,
                "manage_view_id": table.pk,
                "root_url": table.root_url,
                "view_definition": table.view_definition,
                "permission_rules": table.permission_rules,
                "endpoints": table.endpoints,
                "tenant_id": table.tenant_id,
                "comments": table.comments
            }
        else:
            result = {
                "view_name": table.view_name,
                "manage_view_id": table.pk,
                "root_url": table.root_url,
                "endpoints": table.endpoints,
                "tenant_id": table.tenant_id,
                "comments": table.comments
            }

        return HttpResponse(make_success(result=result), content_type='application/json')

    @is_admin
    def delete(self, request, *args, **kwargs):
        logger.debug("top of del /manage/views/<manage_view_id>")
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
            view_id = int(view_id)
        except:
            msg = "Invalid view id; the view id must be an integer."
            logger.debug(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            view = ManageViews.objects.get(pk=view_id)
        except ManageViews.DoesNotExist:
            msg = f"View with ID {view_id} does not exist in ManageViews table."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        try:
            self.delete_view_transaction(view, req_tenant, db_instance_name)
        except Exception as e:
            msg = f"Failed to drop view {view.view_name} from the ManageViews table: {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(msg="View deleted successfully."), content_type='application/json')

    @transaction.atomic
    def delete_view_transaction(self, view, tenant_id, db_instance_name):
        ManageViews.objects.get(view_name=view.view_name, tenant_id=tenant_id).delete()
        view_data.delete_view(view.view_name, tenant_id, db_instance=db_instance_name)


class ViewsResource(RoleSessionMixin, APIView):
    """
    GET: Lists the rows in the given view based on root url. Restricted to USER role and above.
    If the user is solely PGREST_USER then the only access they have is to `view` endpoints
    with permission rules that their user follows.
    """
    @is_user
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /views/<root_url>")
        req_tenant = request.session['tenant_id']
        db_instance = request.session['db_instance_name']
        req_username = request.session['username']

        params = self.request.query_params
        limit = self.request.query_params.get("limit")
        offset = self.request.query_params.get("offset")
        order = self.request.query_params.get("order")

        # Parse out required fields.
        try:
            root_url = self.kwargs['root_url']
        except KeyError as e:
            msg = f"{e.args} is required to list rows in a view."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            view = ManageViews.objects.get(root_url=root_url, tenant_id=req_tenant)
        except ManageViews.DoesNotExist:
            msg = f"View with root url {root_url} does not exist."
            logger.warning(msg)
            return HttpResponseNotFound(make_error(msg=msg))

        # Permission check, permission_rules cross-refed with sk roles
        # Get all user roles from sk and check if view's permission_rules are a subset of user_roles
        user_roles = get_user_sk_roles(req_tenant, req_username)
        try:
            if not set(view.permission_rules).issubset(set(user_roles)):
                msg = (f"User {req_username} in tenant {req_tenant} does not have permission to access view {view.view_name}"
                       f" in tenant {req_tenant}. User roles: {user_roles}. Required roles: {view.permission_rules}")
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

        try:
            # Parse params, if the key contains a search operation, throw it into search_params
            # search_params list is [[key, oper, value], ...]
            search_params = []
            opers = ['.neq', '.eq', '.lte', '.lt', '.gte', '.gt', '.nin', '.in',
                     '.null', '.between', '.nbetween', '.like', '.nlike']
            for full_key, value in params.items():
                # Check that value is not list, if it is that means the user had two query parameters that were
                # exactly the same and the request object consolidated the inputs, we don't want/need this.
                if isinstance(value, list):
                    msg = f"You may only specify a query value once, ex. ?col1.eq=2&col1.eq=2 is NOT allowed."
                    logger.critical(msg + f" e: {e}")
                    return HttpResponseBadRequest(make_error(msg=msg))

                # If param ends with the operation, we remove the operation and use it later. That
                # should leave only the key value that we can check later against the view's columns
                for oper in opers:
                    if full_key.endswith(oper):
                        key = full_key.replace(oper, "")
                        search_params.append([key, oper, value])
                        break
            logger.info(f"Search params: {search_params}")
            
            # limit and offset checking
            try:
                if limit:
                    limit = int(limit)
                else:
                    limit = None
                    
                if limit == -1:
                    limit = None
                
                if offset:
                    offset = int(offset)
                else:
                    offset = None
            except Exception as e:
                msg = f"Limit and offset query parameters must be ints. Got limit: {type(limit)} and offset: {type(offset)}"
                logger.error(msg)
                return HttpResponseBadRequest(make_error(msg=msg))

            if order is not None:
                result = view_data.get_rows_from_view(view.view_name,
                                                      search_params,
                                                      req_tenant,
                                                      limit,
                                                      offset,
                                                      db_instance,
                                                      view.manage_view_id,
                                                      order=order)
            else:
                result = view_data.get_rows_from_view(view.view_name, search_params, req_tenant, limit, offset, db_instance,
                                                      view.manage_view_id)
        except Exception as e:
            msg = f"Failed to retrieve rows from view {view.view_name} on tenant {req_tenant}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=result), content_type='application/json')


### Roles
class RoleManagement(RoleSessionMixin, APIView):
    """
    GET: Gets all PGREST_* views and returns them in a list.
    POST: Create a new role in the security kernel with PgREST owner.
    All of these endpoints are restricted to ROLE_ADMIN role only.
    Role endpoints only deal with roles using `PGREST_*` formatting.
    """
    @is_role_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/roles")
        req_tenant = request.session['tenant_id']

        try:
            full_tenant_role_list = t.sk.getRoleNames(tenant=req_tenant).names
        except Exception as e:
            msg = f"Error getting roles for tenant '{req_tenant}' from sk."
            logger.critical(msg + f" e: {e}")
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            pgrest_role_list = []
            for role in full_tenant_role_list:
                if role.startswith("PGREST_"):
                    pgrest_role_list.append(role)
        except Exception as e:
            msg = f"Error parsing roles received from sk."
            logger.critical(msg + f" e: {e}")
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=pgrest_role_list), content_type='application/json')

    @is_role_admin
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /manage/roles")
        req_tenant = request.session['tenant_id']

        # Parse out required fields.
        try:
            role_name = request.data['role_name']
            role_description = request.data['description']
        except KeyError as e:
            msg = f"{e.args} is required when creating a new role."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if not role_name.startswith("PGREST_"):
            msg = f'User created role names must start with "PGREST_", got {role_name}'
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        privileged_roles = ["PGREST_ADMIN", "PGREST_ROLE_ADMIN", "PGREST_WRITE", "PGREST_READ", "PGREST_USER"]
        if role_name.upper() in privileged_roles:
            msg = f"User created role names can't be in {privileged_roles}, regardless of case, got {role_name}."
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Check to see if role already exists
        try:
            role_info = t.sk.getRoleByName(tenant=req_tenant, roleName=role_name)
            msg = f"Role with name {role_name} already exists for this tenant"
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))
        except Exception as e:
            # Means the role didn't exist, so we pass
            pass

        try:
            t.sk.createRole(roleTenant=req_tenant, roleName=role_name, description=role_description)
        except Exception as e:
            msg = f"Error creating role. e: {e}"
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result="Role successfully created"), content_type='application/json')


class RoleManagementByName(RoleSessionMixin, APIView):
    """
    GET: Gets sk info about the role along with all users granted the role.
    POST: Manages who's in the role, grant and revoke methods are available.
    """
    @is_role_admin
    def get(self, request, *args, **kwargs):
        logger.debug("top of get /manage/roles/{role_name}")
        req_tenant = request.session['tenant_id']

        # Parse out required fields.
        try:
            role_name = self.kwargs['role_name']
        except KeyError as e:
            msg = f"{e.args} is required to get the role."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if not role_name.startswith("PGREST_"):
            msg = f'User created role names must start with "PGREST_", got {role_name}'
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Get role info
        try:
            role_info = t.sk.getRoleByName(tenant=req_tenant, roleName=role_name)
            role_info = role_info.__dict__
        except Exception as e:
            msg = f"Error getting role info. e: {e}"
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Get users in role
        try:
            role_user_list = t.sk.getUsersWithRole(tenant=req_tenant, roleName=role_name).names
        except Exception as e:
            msg = f"Error getting users in role. e: {e}"
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Add users in role to role info dict
        try:
            role_info['usersInRole'] = role_user_list
        except Exception as e:
            msg = f"Error adding users in role list to role info dict. e: {e}"
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(result=role_info), content_type='application/json')

    @is_role_admin
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /manage/roles/{role_name}")
        req_tenant = request.session['tenant_id']

        # Parse out required fields.
        try:
            role_name = self.kwargs['role_name']
        except KeyError as e:
            msg = f"{e.args} is required to grant/revoke a role."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Get required fields from data.
        try:
            method = request.data['method']
            username = request.data['username']
        except KeyError as e:
            msg = f"{e.args} is required to grant/revoke a role."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if not isinstance(method, str):
            msg = f"Method must be of type str, got type {type(method)}"
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        method = method.lower()
        if not method in ['grant', 'revoke']:
            msg = f'Must specify method of either "grant" or "revoke", got "{method}"'
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if not role_name.startswith("PGREST_"):
            msg = f'User created role names must start with "PGREST_", got {role_name}'
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        # Users are allowed to manage the PGREST_USER endpoint
        privileged_roles = ["PGREST_ADMIN", "PGREST_ROLE_ADMIN", "PGREST_WRITE", "PGREST_READ"]
        if role_name.upper() in privileged_roles:
            msg = f"Can't manage the following privileged roles, {privileged_roles}, got {role_name}."
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if not isinstance(username, str):
            msg = f"Username must be of type str, got type {type(username)}"
            logger.critical(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        if method == "grant":
            try:
                granted_role = t.sk.grantRole(tenant=req_tenant, roleName=role_name, user=username)
                # returns 'changes': 1 if a change was made, otherwise 0.
                if granted_role.changes:
                    return HttpResponse(make_success(result="Role granted to user"), content_type='application/json')
                else:
                    return HttpResponse(make_success(result="No changes made. User already has role"),
                                        content_type='application/json')
            except Exception as e:
                msg = f"Error calling sk and granting role {role_name} to user {username}. e: {e}"
                logger.critical(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
        elif method == "revoke":
            try:
                revoked_role = t.sk.revokeUserRole(tenant=req_tenant, roleName=role_name, user=username)
                # returns 'changes': 1 if a change was made, otherwise 0.
                if revoked_role.changes:
                    return HttpResponse(make_success(result="Role revoked from user"), content_type='application/json')
                else:
                    return HttpResponse(make_success(result="No changes made. User already didn't have role"),
                                        content_type='application/json')
            except Exception as e:
                msg = f"Error calling sk and revoking role {role_name} to user {username}. e: {e}"
                logger.critical(msg)
                return HttpResponseBadRequest(make_error(msg=msg))
        else:
            return HttpResponseBadRequest(make_error(msg=f"It should be impossible to get here. {method}, {username}"))
