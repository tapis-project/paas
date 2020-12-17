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
def get_row_from_table(table_name, pk_id, tenant):
    """
    Gets the row with given primary key from the specified table.
    """
    logger.info(f"Getting row with pk {pk_id} from table {tenant}.{table_name}...")
    command = "SELECT * FROM %s.%s WHERE %s_id = %d;" % (tenant, table_name, table_name, int(pk_id))

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        result = dict_fetch_all(cur)
        if len(result) == 0:
            raise Exception
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Row {pk_id} successfully retrieved from table {tenant}.{table_name}.")
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving row with pk \'{pk_id}\' from table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def get_rows_from_table(table_name, query_dict, tenant, limit, **kwargs):
    """
    Gets all rows from given table with an optional limit and filter.
    """
    logger.info(f"Getting rows from table {tenant}.{table_name}")

    try:
        command = "SELECT * FROM %s.%s" % (tenant, table_name)
        if len(query_dict) > 0:
            first = True
            for key, value in query_dict.items():
                if first:

                    if type(value) == 'int' or type(value) == 'float':
                        query = " WHERE \"%s\" = %d" % (key, value)
                    else:
                        query = " WHERE \"%s\" = \'%s\'" % (key, value)
                    first = False
                else:
                    if type(value) == 'int' or type(value) == 'float':
                        query = " AND \"%s\" = %d" % (key, value)
                    else:
                        query = " AND \"%s\" = \'%s\'" % (key, value)
                command = command + query
        if "order" in kwargs:
            order = kwargs["order"].replace(",", " ").strip()
            command = "%s ORDER BY %s " % (command, order)

        command = command + " LIMIT %d;" % (int(limit))
    except Exception as e:
        msg = f"Unable to form database query for table {tenant}.{table_name} with query(ies) {query_dict}: {e}"
        logger.warning(msg)
        raise Exception(msg)

    logger.info(f"Command: {command}")
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
        logger.info(f"Rows successfully retrieved from table {tenant}.{table_name}.")
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving rows from table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def create_row(table_name, columns, val_str, values, tenant):
    """
    Creates a new row in the given table. Returns the primary key ID of the new row.
    """
    logger.info(f"Creating row in {tenant}.{table_name}...")
    command = "INSERT INTO %s.%s(" % (tenant, table_name)
    for col in columns:
        command = "%s %s, " % (command, col)
    command = command[:-2] + ") VALUES(%s) RETURNING %s_id;" % (val_str, table_name)

    logger.info(f"Command: {command}")
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
        logger.info(f"Rows successfully created in table {tenant}.{table_name}.")
        return result_id
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error creating row in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def delete_row(table_name, pk_id, tenant):
    """
    Deletes the specified row in the given table.
    """
    logger.info(f"Deleting row with pk {pk_id} in table {tenant}.{table_name}")
    command = "DELETE FROM %s.%s WHERE %s_id = %d;" % (tenant, table_name, table_name, int(pk_id))

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        result_count = cur.rowcount
        if result_count == 0:
            raise Exception
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Rows successfully created in table {tenant}.{table_name}.")
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error deleting row ID {pk_id} in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def update_row_with_pk(table_name, pk_id, data, tenant):
    """
    Updates a specified row on a table with the given columns and associated values.
    """
    logger.info(f"Updating row with pk \'{pk_id}\' in {tenant}.{table_name}...")
    command = "UPDATE %s.%s SET" % (tenant, table_name)
    for col in data:
        if type(data[col]) == str:
            command = "%s %s = (\'%s\'), " % (command, col, data[col])
        else:
            command = "%s %s = (%s), " % (command, col, data[col])
    command = command[:-2] + " WHERE %s_id = %d;" % (table_name, int(pk_id))

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)

        result_count = cur.rowcount
        if result_count == 0:
            raise Exception
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Row {pk_id} successfully updated in table {tenant}.{table_name}.")
        return result_count
    except psycopg2.DatabaseError as e:
        msg = f"Error executing statement in database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error updating row ID {pk_id} in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)

def update_rows_with_where(table_name, data, tenant, where_clause=None):
    """
    Updates 1+ row(s) on a table with the given columns and associated values based on a where clause. If a where clause
    is not specified, the entire table is updated.
    """
    logger.info(f"Updating rows in {tenant}.{table_name}...")
    command = "UPDATE %s.%s SET" % (tenant, table_name)
    for col in data:
        if type(data[col]) == str:
            command = "%s %s = (\'%s\'), " % (command, col, data[col])
        else:
            command = "%s %s = (%s), " % (command, col, data[col])

    command = command[:-2]
    if where_clause:
        first = True
        for key, value in where_clause.items():
            if first:
                if type(value) == int or type(value) ==  float:
                    query = " WHERE \"%s\" %s %d" % (key, value["operator"], value["value"])
                else:
                    query = " WHERE \"%s\" %s \'%s\'" % (key, value["operator"], value["value"])
                first = False
            else:
                if type(value) == 'int' or type(value) == 'float':
                    query = " AND \"%s\" %s %d" % (key, value["operator"], value["value"])
                else:
                    query = " AND \"%s\" %s \'%s\'" % (key, value["operator"], value["value"])
            command = command + query
    command = command + ';'

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)

        result_count = cur.rowcount
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"{result_count} rows were successfully updated in table {tenant}.{table_name}.")
        return result_count
    except psycopg2.DatabaseError as e:
        msg = f"Error executing update statement in database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error updating rows in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
