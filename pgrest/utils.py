from django.http import HttpResponseForbidden

from pgrest.pycommon import errors as common_errors
from pgrest.pycommon.auth import t
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)

PGREST_ROLES = ['PGREST_ADMIN', 'PGREST_WRITE', 'PGREST_READ']

def create_validate_schema(columns):
    """
    Takes the column definition of a table and generates two validation schemas, one to be used in row creation
    and the other to be used in row update.
    """
    schema_update = dict()
    schema_create = dict()

    for key in columns.keys():
        key_info = columns[key]
        key_type = key_info["data_type"]
        info_dict = dict()
        if key_type.lower() in {"varchar", "char", "text"}:
            val_length = int(key_info["char_len"])
            info_dict.update({"type": "string", "maxlength": val_length})
        else:
            info_dict.update({"type": key_type.lower()})
        schema_update[key] = info_dict

    for key in columns.keys():
        key_info = columns[key]
        key_type = key_info["data_type"]
        info_dict = dict()
        if key_type.lower() in {"varchar", "char", "text"}:
            val_length = int(key_info["char_len"])
            info_dict.update({"type": "string", "maxlength": val_length})
        else:
            info_dict.update({"type": key_type.lower()})

        if "null" in key_info.keys():
            if not key_info["null"]:
                info_dict.update({"required": True})
            else:
                info_dict.update({"required": False})
        schema_create[key] = info_dict

    return schema_create, schema_update


def is_admin(view):
    """
    Determines if a user has an admin role, and returns a 403 if they do not.
    """
    def wrapper(self, request, *args, **kwargs):
        logger.debug("top of is_admin()")
        if "PGREST_ADMIN" not in request.session['roles']:
            return HttpResponseForbidden(f"User {request.session['username']} does not have permission to manage "
                                         f"database tables.")
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
            return HttpResponseForbidden(f"User {request.session['username']} does not have permission to write.")
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
            return HttpResponseForbidden(f"User {request.session['username']} does not have permission to read.")
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

def grant_role(tenant, username, role):
    """
    Grant the role
    """
    if not role in PGREST_ROLES:
        raise common_errors.BaseTapisError(f"Invalid role {role}; role should be in {PGREST_ROLES}")
    t.sk.grantRole(user=username, tenant=tenant, roleName=role)


tenants = ['a2cps', 'cii', 'tacc', 'dev', 'admin']

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

