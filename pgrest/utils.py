import json
import datetime

from django.http import HttpResponseForbidden
from django.core.serializers.json import DjangoJSONEncoder

from tapisservice import errors as common_errors
from pgrest.__init__ import t
from tapisservice.config import conf
from tapisservice.logs import get_logger
from tapipy.errors import UnauthorizedError

logger = get_logger(__name__)

PGREST_ROLES = ['PGREST_ADMIN', 'PGREST_WRITE', 'PGREST_READ', 'PGREST_ROLE_ADMIN']

def timestampJSONEncoder(raw_object):
    """
    We need this to catch timestamps being returned and change how
    they're converted to JSON. Without this json.dumps gets caught up
    when trying to return datetimes. Credits to:
    https://stackoverflow.com/questions/11875770/how-to-overcome-datetime-datetime-not-json-serializable
    """
    if isinstance(raw_object, (datetime.date, datetime.datetime)):
        return raw_object.isoformat()
    raise TypeError (f"Type {type(raw_object)} not serializable")

def get_version():
    """
    Get the version of the API running.
    """
    return "dev" # TODO


def make_error(msg=None, metadata={}):
    """
    Create an error JSON response in the standard Tapis 4-stanza format.
    """
    if not msg:
        msg = "There was an error."
    if not isinstance(metadata, dict):
        raise TypeError("Got exception formatting response. Metadata should be dict.")
    d = {"status": "error",
         "message": msg,
         "version": get_version(),
         "result": None,
         "metadata": metadata}
    return json.dumps(d)


def make_success(result=None, msg=None, metadata={}):
    """
    Create an error JSON response in the standard Tapis 4-stanza format.
    """
    if not msg:
        msg = "The request was successful."
    if not isinstance(metadata, dict):
        raise TypeError("Got exception formatting response. Metadata should be dict.")
    d = {"status": "success",
         "message": msg,
         "version": get_version(),
         "result": result,
         "metadata": metadata}
    return json.dumps(d, default=timestampJSONEncoder)


def create_validate_schema(columns, tenant, existing_enum_names):
    """
    Takes the column definition of a table and generates two validation schemas, one to be used in row creation
    and the other to be used in row update.
    """
    logger.info("Top of create_validate_schema()")
    schema_update = dict()
    schema_create = dict()

    # We once had different update and create schemas. I couldn't figure out a valid reason for this.
    # Only difference is schema_update should never have "required" field. As users should always be able
    # to update a row's value. 
    for key, key_info in columns.items():
        key_type = key_info["data_type"]
        info_dict = dict()
        if key_type in ["varchar", "char"]:
            val_length = int(key_info["char_len"])
            info_dict.update({"type": "string", "maxlength": val_length})
        elif key_type == "text":
            info_dict.update({"type": "string"})
        elif key_type == "serial":
            info_dict.update({"type": "integer"})
        elif key_type == "date":
            info_dict.update({"type": "string"})
        elif key_type == "timestamp":
            info_dict.update({"type": "string"})
        elif '[]' in key_type:
            info_dict.update({"type": "list"})
        elif key_type in existing_enum_names or f'{tenant}.{key_type}' in existing_enum_names:
            info_dict.update({"type": "string"})
        else:
            info_dict.update({"type": key_type})

        if "null" in key_info.keys():
            if key_info["null"]: #true
                info_dict.update({"required": False,
                                  "nullable": True})
            else: #false
                info_dict.update({"required": True,
                                  "nullable": False})
        schema_create[key] = info_dict.copy()

        # Update schema should never have required fields. Users should always be able to update a row's value.
        info_dict.update({"required": False})
        schema_update[key] = info_dict.copy()

    return schema_create, schema_update


def is_admin(view):
    """
    Determines if a user has an admin role, and returns a 403 if they do not.
    """
    def wrapper(self, request, *args, **kwargs):
        logger.debug("top of is_admin()")
        roles = request.session['roles']
        if "PGREST_ADMIN" not in roles:
            msg = f"User {request.session['username']} does not have permission to manage database tables."
            return HttpResponseForbidden(make_error(msg=msg))
        else:
            return view(self, request, *args, **kwargs)
    return wrapper


def is_role_admin(view):
    """
    Determines if a user has an role admin role, and returns a 403 if they do not.
    """
    def wrapper(self, request, *args, **kwargs):
        logger.debug("top of is_role_admin()")
        roles = request.session['roles']
        if "PGREST_ADMIN" not in roles and "PGREST_ROLE_ADMIN" not in roles:
            msg = f"User {request.session['username']} does not have permission to manage pgrest roles."
            return HttpResponseForbidden(make_error(msg=msg))
        else:
            return view(self, request, *args, **kwargs)
    return wrapper


def can_write(view):
    """
    Determines if a user has an admin or a write role, and returns a 403 if they do not.
    """
    def wrapper(self, request, *args, **kwargs):
        roles = request.session["roles"]
        if "PGREST_ADMIN" not in roles and "PGREST_WRITE" not in roles:
            msg = f"User {request.session['username']} does not have permission to write."
            return HttpResponseForbidden(make_error(msg=msg))
        else:
            return view(self, request, *args, **kwargs)
    return wrapper


def can_read(view):
    """
    Determines if a user has an admin role, or write role, or read role, and returns a 403 if they do not.
    """
    def wrapper(self, request, *args, **kwargs):
        roles = request.session["roles"]
        if "PGREST_ADMIN" not in roles and "PGREST_WRITE" not in roles and "PGREST_READ" not in roles:
            msg = f"User {request.session['username']} does not have permission to read."
            return HttpResponseForbidden(make_error(msg=msg))
        else:
            return view(self, request, *args, **kwargs)
    return wrapper


def is_user(view):
    """
    Determines if a user has an user role, or read role, or write role, or admin role, and returns a 403 if they do not.
    """
    def wrapper(self, request, *args, **kwargs):
        roles = request.session["roles"]
        if "PGREST_ADMIN" not in roles and "PGREST_WRITE" not in roles and "PGREST_READ" not in roles and "PGREST_USER" not in roles:
            msg = f"User {request.session['username']} is not a user on this tenant for PgREST."
            return HttpResponseForbidden(make_error(msg=msg))
        else:
            return view(self, request, *args, **kwargs)
    return wrapper


def get_tenant_id_from_base_url(base_url, tenants):
    """
    Return the tenant_id associated with the base URL of a request.
    """
    if base_url and 'http://testserver' in base_url:
        logger.debug("http://testserver in url; resolving tenant id to dev for Django testing.")
        return 'dev'
    if base_url and 'http://localhost:500' in base_url:
        logger.debug("http://localhost:500 in url; resolving tenant id to tacc for user testing.")
        return 'tacc'

    request_tenant = tenants.get_tenant_config(url=base_url)
    return request_tenant.tenant_id

def create_roles(tenants=[]):
    """
    Creates the basic set of roles required by PgREST in SK for a given set of tenants.
    """
    for tn in tenants:
        try:
            t.sk.createRole(roleName='PGREST_READ',
                            roleTenant=tn,
                            description='Role granting read access to all tables in the PgREST API.',
                            _tapis_set_x_headers_from_service=True)
            t.sk.createRole(roleName='PGREST_USER',
                            roleTenant=tn,
                            description='Role granting read access to all /view/ endpoints in the PgREST API.',
                            _tapis_set_x_headers_from_service=True)
            t.sk.createRole(roleName='PGREST_WRITE',
                            roleTenant=tn,
                            description='Role granting write access to all tables in the PgREST API.',
                            _tapis_set_x_headers_from_service=True)
            t.sk.createRole(roleName='PGREST_ADMIN',
                            roleTenant=tn,
                            description='Role granting admin rights to all tables in the PgREST API.',
                            _tapis_set_x_headers_from_service=True)
            t.sk.createRole(roleName='PGREST_ROLE_ADMIN',
                            roleTenant=tn,
                            description='Role granting ability to use PgREST Role endpoints.',
                            _tapis_set_x_headers_from_service=True)
        except UnauthorizedError as e:
            logger.warning((f"Unauthorized error creating roles for tenant {tn}. PgREST probably cannot",
                            f"act on behalf of users of this tenant. e: {e}"))
            pass

        # This doesn't really belong, but we need to delete our PGREST_TEST role because the testsuite
        # creates it and uses it, but we need to delete it each run. There's no delete role endpoint
        # though. Also we need to "reserve" the role between running the tests. So we delete it now.
        try:
            t.sk.deleteRoleByName(roleName='PGREST_TEST', tenant=tn, _tapis_set_x_headers_from_service=True)
        except:
            pass

def grant_role(tenant, username, role):
    """
    Grant the role
    """
    if not role in PGREST_ROLES:
        raise common_errors.BaseTapisError(f"Invalid role {role}; role should be in {PGREST_ROLES}")
    t.sk.grantRole(user=username, tenant=tenant, roleName=role, _tapis_set_x_headers_from_service=True)



# Get all sites and tenants for all sites.
SITE_TENANT_DICT = {} # {site_id1: [tenant1, tenant2, ...], site_id2: ...}
for tenant in t.tenant_cache.tenants.values():
    if not SITE_TENANT_DICT.get(tenant.site_id):
        SITE_TENANT_DICT[tenant.site_id] = []
    SITE_TENANT_DICT[tenant.site_id].append(tenant.tenant_id)
curr_tenant_obj = t.tenant_cache.get_tenant_config(tenant_id=t.tenant_id)
# Delete excess sites when current site is not primary. Non-primary sites will never have to manage other sites.
if not curr_tenant_obj.site.primary:
    SITE_TENANT_DICT = {curr_tenant_obj.site: SITE_TENANT_DICT[curr_tenant_obj.site]}


# Get all tenants that this code should make PgREST roles for.
role_tenants = []
for site, tenants in SITE_TENANT_DICT.items():
    role_tenants += tenants

# make sure roles exist --
create_roles(role_tenants)

try:
    # set up project admins --
    admins = []

    for a in admins:
        for tn in role_tenants:
            try:
                grant_role(tn, a, 'PGREST_ADMIN')
            except:
                pass

    # additional roles by tenant
    grant_role('a2cps', 'ctjordan', 'PGREST_ADMIN')
    grant_role('a2cps', 'pscherer', 'PGREST_ADMIN')
    grant_role('a2cps', 'vaughn', 'PGREST_ADMIN')

    grant_role('cii', 'ctjordan', 'PGREST_ADMIN')
    grant_role('cii', 'pscherer', 'PGREST_ADMIN')
    grant_role('cii', 'waller', 'PGREST_ADMIN')
except Exception as e:
    logger.info("Issue setting roles, probably because you're not using 'tacc' site. This is not an issue, service should be good.")