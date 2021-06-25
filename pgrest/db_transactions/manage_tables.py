import re
import psycopg2
from . import config
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)

# We create a forbidden regex for quick parsing
# Forbidden: \ ` ' " ~  / ? # [ ] ( ) @ ! $ & * + = - . , : ;
FORBIDDEN_CHARS =  re.compile("^[^<>\\\/{}[\]~` $'\".:-?#@!$&()*+,;=]*$")


def do_transaction(command, db_instance):
    # Read the connection parameters and connect to database.
    if db_instance:
        params = config.config(db_instance)
    else:
        params = config.config()
    conn = psycopg2.connect(**params)
    cur = conn.cursor()
    cur.execute(command)
    cur.close()
    conn.commit()


# TODO create exceptions
def create_table(table_name, columns, existing_enum_names, constraints, tenant, db_instance=None):
    """Create table in the PostgreSQL database"""
    logger.info(f"Creating table {tenant}.{table_name}...")

    if not FORBIDDEN_CHARS.match(table_name):
        msg = f"Forbidden char found in table name {table_name}. Table name inputted: {table_name}"
        logger.warning(msg)
        raise Exception(msg)

    command = f"CREATE TABLE {tenant}.{table_name} ("
    primary_key_flag = False

    for key, val in columns.items():
        column_name = key.upper()
        column_args = val

        # We need to grab the column type first as it used to decide how to handle the other variables.
        try:
            column_type = column_args["data_type"].upper()
        except KeyError:
            msg = f"Data type not received for column {column_name}. Cannot create table {table_name}"
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
        if not column_type in ["BOOLEAN", "VARCHAR", "CHAR", "TEXT", "INTEGER", "FLOAT", "DATE", "TIMESTAMP"]:
            if column_type.lower() in existing_enum_names:
                column_type = f"{tenant}.{column_type}"

        # Handle foreign keys.
        if "foreign_key" in column_args and column_args["foreign_key"]:
            try:
                # check we have we need
                ref_table = column_args["reference_table"]
                ref_column = column_args["reference_column"]
                on_delete = column_args["on_delete"]

                # Do some input checking on delete action.
                delete_options = ["SET NULL", "SET DEFAULT", "RESTRICT", "NO ACTION", "CASCADE"]
                if on_delete.upper() not in delete_options:
                    msg = f"Invalid delete supplied: {on_delete}. Valid delete actions: {delete_options}."
                    logger.warning(msg)
                    raise Exception(msg)
                # Cannot set on delete action to SET NULL if the column does not allow nulls.
                if on_delete.upper() == "SET NULL" and "null" in column_args and not column_args["null"]:
                    msg = f"Cannot set delete action on column {column_name} " \
                          f"as it does not allow nulls in column definition."
                    logger.warning(msg)
                    raise Exception(msg)

                column_type = f"{column_type} REFERENCES {tenant}.{ref_table}({ref_column}) ON DELETE {on_delete}"

            except KeyError as e:
                msg = f"Required key {e.args[0]} not received for column {column_name}. " \
                      f"Cannot create table {table_name}."
                logger.warning(msg)
                raise Exception(msg)

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
            elif key not in ["data_type", "char_len", "foreign_key", "reference_table", "reference_column", "on_delete"]:
                msg = f"{key} is an invalid argument for column {column_name}. Cannot create table {table_name}"
                logger.warning(msg)
                raise Exception(msg)

        col_def = " ".join(col_str_list)
        command = command + f"{col_def},\n"

    # Check if this column was set as the "primary_key" column.
    if not primary_key_flag:
        command = command + f"{table_name}_id SERIAL PRIMARY KEY,\n"

    # Checking multi-value unique constraints
    # Proper format is {"constraint": {"unique": {"uniqueConstraintName": ["Col1", "Col2"]}}}
    try:
        unique_columns = constraints.get('unique', {})
    except Exception as e:
        msg = f"Error getting unique_columns from constraints inputted for table {table_name} on tenant {tenant}"
        logger.warning(msg)
        raise Exception(msg)

    if not isinstance(unique_columns, dict):
        msg = f"Error with unique constraints. Got {unique_columns} of type {type(unique_columns)}, not dict."
        logger.warning(msg)
        raise Exception(msg)

    if unique_columns:
        for constraint_name, constraint_values in unique_columns.items():
            # Ensure constraint_name is not forbidden
            if not FORBIDDEN_CHARS.match(constraint_name):
                msg = f"constraint_name is not url safe. Value must be alphanumeric with _ and - optional. Value inputted: {constraint_name}"
                logger.warning(msg)
                raise Exception(msg)
            # Ensure constraint_values is a list and it's non-empty and len() > 1
            if not isinstance(constraint_values, list):
                msg = f"Unique constraint dictionary should have a value of type list. Value inputted: {constraint_values}"
                logger.warning(msg)
                raise Exception(msg)
            if len(constraint_values) <= 1:
                msg = f"Multi-variable unique restraints require more than one column to be specified. Value inputted: {constraint_values}"
                logger.warning(msg)
                raise Exception(msg)
            # Check constraint values are strings and not forbidden
            for value in constraint_values:
                if not isinstance(value, str):
                    msg = f"Unique constraint list should consist of string types. {value} is not of type string in list: {constraint_values}"
                    logger.warning(msg)
                    raise Exception(msg)
                if not FORBIDDEN_CHARS.match(value):
                    msg = f"Unique constraint list should consist of string types. {value} is not of type string in list: {constraint_values}"
                    logger.warning(msg)
                    raise Exception(msg)
            # Create unique constraint.
            command = command + f"CONSTRAINT {constraint_name} UNIQUE ({', '.join(constraint_values)}),\n"

    remove = command.rindex(",")
    command = command[:remove] + ")"

    logger.debug(f"Create db command for table {table_name}: {command}")

    conn = None
    try:
        do_transaction(command, db_instance)
        logger.debug(f"Table {tenant}.{table_name} successfully created in postgres db.")
    except psycopg2.DatabaseError as e:
        if conn:
            conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        if conn:
            conn.close()
        msg = f"Error creating table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def delete_table(table_name, tenant, db_instance=None):
    """ Drop table in the PostgreSQL database"""
    logger.info(f"Dropping table {tenant}.{table_name}...")
    command = f"DROP TABLE {tenant}.{table_name} CASCADE;"
    conn = None
    logger.info(f"Drop table command for {tenant}.{table_name}: {command}")
    try:
        do_transaction(command, db_instance)
        logger.info(f"Table {tenant}.{table_name} successfully dropped from postgres db.")
    except psycopg2.DatabaseError as e:
        if conn:
            conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        if conn:
            conn.close()
        msg = f"Error dropping table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def create_schema(schema_name, db_instance=None):
    """Create schema for a tenant in the PostgreSQL database"""
    logger.info(f"Creating schema {schema_name}...")

    command = f"CREATE SCHEMA IF NOT EXISTS {schema_name};"

    conn = None
    try:
        do_transaction(command, db_instance)
        logger.info(f"Schema {schema_name} successfully created in postgres db.")
    except psycopg2.DatabaseError as e:
        if conn:
            conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        if conn:
            conn.close()
        msg = f"Error creating schema {schema_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def parse_enums(enums, tenant, db_instance_name=None):
    logger.info(f"Parsing enum json information. enums: {enums}")
    if not isinstance(enums, dict):
        msg = f"enums declaration for table should be of type 'dict', not type '{type(enums)}'." \
                " Dict should be formatted as {'enum_key1': ['string1', 'string2', ...], ...}"
        logger.error(msg)
        raise Exception(msg)
    for enum_key, enum_list in enums.items():
        enum_key = enum_key.lower()
        logger.info(f"Parsing enum with enum_key {enum_key}.")
        if not isinstance(enum_list, list):
            msg = f"String values for enum should be declared in a list. Received type: {type(enum_list)}."
            logger.error(msg)
            raise Exception(msg)
        if not FORBIDDEN_CHARS.match(enum_key):
            msg = f"Forbidden char found in enum name {enum_key}. Enum name inputted: {enum_key}"
            logger.warning(msg)
            raise Exception(msg)
        for enum_val in enum_list:
            logger.info(enum_val)
            if not isinstance(enum_val, str):
                msg = f"enum list values must be strings. Got type {enum_val}."
                logger.error(msg)
                raise Exception(msg)
            if not FORBIDDEN_CHARS.match(enum_val):
                msg = f"Forbidden char found in enum value {enum_val}. Enum value inputted: {enum_val}"
                logger.warning(msg)
                raise Exception(msg)
        create_enum(enum_key, enum_list, tenant, db_instance_name)


def create_enum(enum_name, fields, tenant, db_instance=None):
    """Create table in the PostgreSQL database"""
    logger.info(f"Creating enum {tenant}.{enum_name} with fields: {fields}")

    enums_created = []

    existing_enums = get_enums(db_instance)
    if existing_enums.get(tenant):
        if existing_enums[tenant].get(enum_name):
            logger.info(f"Enum {tenant}.{enum_name} already exists, skipping.")
            return

    command = f"CREATE TYPE {tenant}.{enum_name} AS ENUM ("

    # Check that we receive list.
    if not isinstance(fields, list):
        msg = f"When declaring an ENUM type, fields should be a list, got '{type(fields)}'"
        logger.error(msg)
        raise Exception(msg)

    # Check if list is populated.
    if not fields:
        msg = f"No fields for ENUM received. Fields received: {fields}"
        logger.error(msg)
        raise Exception(msg)

    enums_created = []
    # Check that fields are strings.
    for field in fields:
        if isinstance(field, str):
            if "'" in field:
                msg = f'ENUM fields cannot contain apostrophes. "{field}" does.'
                logger.error(msg)
                raise Exception(msg)
            command += f"'{field}', "
            enums_created.append(f"{tenant}.{enum_name}")
        else:
            msg = f"All ENUM fields must be strings, '{field}' is of type '{type(field)}'"
            logger.error(msg)
            raise Exception(msg)

    # Get rid of excess comma.
    remove = command.rindex(",")
    command = command[:remove] + ")"
    logger.debug(f"Create enum command for enum {enum_name}: {command}")

    # Run postgres command
    conn = None
    try:
        do_transaction(command, db_instance)
        logger.debug(f"Enum {tenant}.{enum_name} successfully created in postgres db.")
        return
    except psycopg2.DatabaseError as e:
        if conn:
            conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        if conn:
            conn.close()
        msg = f"Error creating enum {tenant}.{enum_name}: {e}"
        logger.error(msg)
        raise Exception(msg)



def get_enums(db_instance=None):
    # Gets all enums from postgres and organizes them by schema (tenant) and name, returns values.
    command = "select n.nspname as enum_schema, t.typname as enum_name, string_agg(e.enumlabel, ', ') " \
              "as enum_value from pg_type t join pg_enum e on t.oid = e.enumtypid join " \
              "pg_catalog.pg_namespace n ON n.oid = t.typnamespace group by enum_schema, enum_name;"

    conn = None
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
            params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        enums = dict_fetch_all(cur)
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Successfully retrieved all created enums from postgres db: {enums}")
        return enums
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving enums: {e}"
        logger.error(msg)
        raise Exception(msg)


def dict_fetch_all(cursor):
    """
    Return all rows from a cursor as a dict
    enum formatted as {'tenant': {'enum1': ['enumval1', enumval2'],
                                  'enum2': ['enumval1']},
                                  ...}
    """
    enum_dict = {}
    all_rows = cursor.fetchall()
    # rows come back in tenant, enum_name, enum_value order.
    for row in all_rows:
        if enum_dict.get(row[0]):
            enum_dict[row[0]].update({row[1]: row[2]})
        else:
            enum_dict[row[0]] = {row[1]: row[2]}

    if not isinstance(enum_dict, dict):
        msg = f"Internal Error: Report please. Err: 'enum_dict' should be a dict, not {type(enum_dict)}"
        logger.error(msg)
        raise Exception(msg)
    
    for tenant, enum in enum_dict.items():
        if not isinstance(enum, dict):
            msg = f"Internal Error: Report please. Err: 'enum' should be a dict, not {type(enum)}"
            logger.error(msg)
            raise Exception(msg)

    return enum_dict