import json
import datetime

from django.http import HttpResponseForbidden
from django.core.serializers.json import DjangoJSONEncoder

from pgrest.pycommon import errors as common_errors
from pgrest.pycommon.auth import t
from pgrest.pycommon.config import conf
from pgrest.pycommon.logs import get_logger

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

    for key, key_info in columns.items():
        key_type = key_info["data_type"].lower()
        info_dict = dict()
        if key_type in ["varchar", "char"]:
            try:
                val_length = int(key_info["char_len"])
                info_dict.update({"type": "string", "maxlength": val_length})
            except KeyError:
                raise KeyError(f"Unable to create table. {key_type} data types requires char_len field.")
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
        schema_update[key] = info_dict

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
            if not key_info["null"]:
                info_dict.update({"required": True,
                                  "nullable": True})
            else:
                info_dict.update({"required": False,
                                  "nullable": True})
        schema_create[key] = info_dict

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


def create_roles(tenants=[]):
    """
    Creates the basic set of roles required by PgREST in SK for a given set of tenants.
    """
    for tn in tenants:
        t.sk.createRole(roleName='PGREST_READ',
                        roleTenant=tn,
                        description='Role granting read access to all tables in the PgREST API.')
        t.sk.createRole(roleName='PGREST_WRITE',
                        roleTenant=tn,
                        description='Role granting write access to all tables in the PgREST API.')
        t.sk.createRole(roleName='PGREST_ADMIN',
                        roleTenant=tn,
                        description='Role granting admin rights to all tables in the PgREST API.')
        t.sk.createRole(roleName='PGREST_ROLE_ADMIN',
                        roleTenant=tn,
                        description='Role granting ability to use PgREST Role endpoints.')
        # This doesn't really belong, but we need to delete our PGREST_TEST role because the testsuite
        # creates it and uses it, but we need to delete it each run. There's no delete role endpoint
        # though. Also we need to "reserve" the role between running the tests. So we delete it now.
        try:
            t.sk.deleteRoleByName(roleName='PGREST_TEST', tenant=tn)
        except:
            pass

def grant_role(tenant, username, role):
    """
    Grant the role
    """
    if not role in PGREST_ROLES:
        raise common_errors.BaseTapisError(f"Invalid role {role}; role should be in {PGREST_ROLES}")
    t.sk.grantRole(user=username, tenant=tenant, roleName=role)


tenants = conf.tenants

# make sure roles exist --
create_roles(tenants)

# set up project admins --
admins = ['jstubbs', 'cgarcia']

for a in admins:
    for tn in tenants:
        grant_role(tn, a, 'PGREST_ADMIN')

# additional roles by tenant
grant_role('a2cps','ctjordan', 'PGREST_ADMIN')
grant_role('a2cps','pscherer', 'PGREST_ADMIN')
grant_role('a2cps', 'vaughn', 'PGREST_ADMIN')

grant_role('cii','ctjordan', 'PGREST_ADMIN')
grant_role('cii','pscherer', 'PGREST_ADMIN')
grant_role('cii','waller', 'PGREST_ADMIN')