import logging
import psycopg2
from . import config

logger = logging.getLogger(__name__)


def dict_fetch_all(cursor):
    """
    Return all rows from a cursor as a dict
    """
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


# TODO create exceptions
def get_row_from_table(table_name, pk_id):
    """
    Gets the row with given primary key from the specified table.
    """
    logger.info(f"Getting row with pk {pk_id} from table {table_name}...")

    command = "SELECT * FROM %s WHERE %s_id = %d;" % (table_name, table_name, int(pk_id))

    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        result = dict_fetch_all(cur)
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Row {pk_id} successfully retrieved from table {table_name}.")
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving row with pk \'{pk_id}\' from table {table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def get_rows_from_table(table_name, limit=10):
    """
    Gets all rows from given table with an optional limit and filter.
    """
    logger.info(f"Getting rows from table {table_name}")

    command = "SELECT * FROM %s LIMIT %d;" % (table_name, limit)

    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        result = dict_fetch_all(cur)
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Rows successfully retrieved from table {table_name}.")
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving rows from table {table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def create_row(table_name, columns, val_str, values):
    """
    Creates a new row in the given table. Returns the primary key ID of the new row.
    """
    logger.info(f"Creating row in {table_name}...")
    command = "INSERT INTO %s(" % table_name
    for col in columns:
        command = "%s %s, " % (command, col)
    command = command[:-2] + ") VALUES(%s) RETURNING %s_id;" % (val_str, table_name)

    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command, values)
        result_id = cur.fetchone()[0]
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Rows successfully created in table {table_name}.")
        return result_id
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error creating row in table {table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def delete_row(table_name, pk_id):
    """
    Deletes the specified row in the given table.
    """
    logger.info(f"Deleting row with pk {pk_id} in table {table_name}")

    command = "DELETE FROM %s WHERE %s_id = %d;" % (table_name, table_name, int(pk_id))

    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Rows successfully created in table {table_name}.")
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error creating row in table {table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def update_row(table_name, pk_id, columns, values):
    """
    Updates a specified row on a table with the given columns and associated values.
    """
    logger.info(f"Updating row with pk \'{pk_id}\' in {table_name}...")
