import logging
import psycopg2
from . import config

logger = logging.getLogger(__name__)


# TODO create exceptions
def create_table(table_name, columns, tenant):
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
            elif key != "data_type" and key != "char_len":
                msg = f"{key} is an invalid argument for column {column_name}. Cannot create table {table_name}"
                raise Exception(msg)

        col_def = " ".join(col_str_list)
        command = command + f"{col_def},\n"

    remove = command.rindex(",")
    command = command[:remove] + ")"
    logger.info(f"Create db command for table {table_name}: {command}")

    conn = None
    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Table {tenant}.{table_name} successfully created in postgres db.")
    except psycopg2.DatabaseError as e:
        conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        conn.close()
        msg = f"Error creating table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def delete_table(table_name, tenant):
    """ Drop table in the PostgreSQL database"""
    logger.info(f"Dropping table {tenant}.{table_name}...")
    command = "DROP TABLE %s.%s CASCADE;" % (tenant, table_name)

    logger.info(f"Drop table command for {tenant}.{table_name}: {command}")
    conn = None
    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Table {tenant}.{table_name} successfully dropped from postgres db.")
    except psycopg2.DatabaseError as e:
        conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        conn.close()
        msg = f"Error dropping table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)





