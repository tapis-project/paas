import psycopg2
from . import config
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)


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
def create_table(table_name, columns, tenant, db_instance=None):
    """Create table in the PostgreSQL database"""
    logger.info(f"Creating table {tenant}.{table_name}...")

    command = "CREATE TABLE %s.%s (%s_id SERIAL PRIMARY KEY, " % (tenant, table_name, table_name)
    for key, val in columns.items():
        column_name = key.upper()
        column_args = val

        # We need to grab the column type first as it used to decide how to handle the other variables.
        try:
            column_type = column_args["data_type"].upper()
        except KeyError:
            msg = f"Data type not received for column {column_name}. Cannot create table {table_name}"
            raise Exception(msg)
        if column_type in {"VARCHAR", "CHAR", "TEXT"}:
            try:
                char_len = column_args["char_len"]
                column_type = "%s(%s)" % (column_type, char_len)
            except KeyError:
                msg = f"Character max size not received for column {column_name}. Cannot create table {table_name}."
                logger.warning(msg)
                raise Exception(msg)
        # Handle foreign keys.
        if "FK" in column_args and column_args["FK"]:
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

                column_type = "%s REFERENCES %s.%s(%s) ON DELETE %s" % (column_type, tenant, ref_table, ref_column, on_delete)

            except KeyError as e:
                msg = f"Required key {e.args[0]} not received for column {column_name}. " \
                      f"Cannot create table {table_name}."
                logger.warning(msg)
                raise Exception(msg)

        col_str_list = list()
        col_string = "%s %s" % (column_name, column_type)
        col_str_list.append(col_string)

        # Find optional values and assign to variable.
        for key, val in column_args.items():
            if key == "null":
                if not val:
                    col_str_list.append("NOT NULL")
            elif key == "unique":
                col_str_list.append("UNIQUE")
            elif key == "default":
                col_str_list.append("DEFAULT %s" % val)
            elif key not in ["data_type", "char_len", "FK", "reference_table", "reference_column", "on_delete"]:
                msg = f"{key} is an invalid argument for column {column_name}. Cannot create table {table_name}"
                raise Exception(msg)

        col_def = " ".join(col_str_list)
        command = command + f"{col_def},\n"

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
    command = "DROP TABLE %s.%s CASCADE;" % (tenant, table_name)
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

    command = "CREATE SCHEMA IF NOT EXISTS %s;" % (schema_name, )

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




