
from django.http import HttpResponseForbidden


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
    def wrapper(request, *args, **kwargs):
        if "admin" not in request.session['roles']:
            return HttpResponseForbidden(f"User {request.session['username']} does not have permission to manage "
                                         f"database tables.")
        else:
            return view(request, *args, **kwargs)
    return wrapper


def can_write(view):
    """
    Determines if a user has an admin or a write role, and returns a 403 if they do not.
    """
    def wrapper(request, *args, **kwargs):
        roles = request.session["role"]
        if "admin" not in roles and "write" not in roles:
            return HttpResponseForbidden(f"User {request.session['username']} does not have permission to write.")
        else:
            return view(request, *args, **kwargs)
    return wrapper


def can_read(view):
    """
    Determines if a user has an admin role, or write role, or read role, and returns a 403 if they do not.
    """
    def wrapper(request, *args, **kwargs):
        roles = request.session["role"]
        if "admin" not in roles and "write" not in roles and "read" not in roles:
            return HttpResponseForbidden(f"User {request.session['username']} does not have permission to read.")
        else:
            return view(request, *args, **kwargs)
    return wrapper

