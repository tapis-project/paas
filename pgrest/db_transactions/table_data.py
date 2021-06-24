import psycopg2
from . import config
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)

FORBIDDEN_CHARS = ['\\', ' ', '"', ':', '/', '?', '#', '[', ']', '@', '!', '$', '&', "'", '(', ')', '*', '+', ',', ';', '=']


def dict_fetch_all(cursor):
    """
    Return all rows from a cursor as a dict
    """
    columns = [col[0] for col in cursor.description]
    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]

def expose_primary_key(result_list, primary_key):
    list_with_id_field = []
    if result_list:
        for result_dict in result_list:
            try:
                list_entry = result_dict.update({'_pkid': result_dict[primary_key]})
            except:
                msg = f"Error finding 'primary_key' field, {primary_key} in result list: {result_list}"
                logger.error(msg)
                raise Exception(msg)
            list_with_id_field.append(list_entry)
    return list_with_id_field

def get_row_from_table(table_name, pk_id, tenant, primary_key, db_instance=None):
    """
    Gets the row with given primary key from the specified table.
    """
    logger.info(f"Getting row with pk {pk_id} from table {tenant}.{table_name}...")
    if type(pk_id) == 'int' or type(pk_id) == 'float':
        command = f"SELECT * FROM {tenant}.{table_name} WHERE {primary_key} = {pk_id};"
    else:
        command = f"SELECT * FROM {tenant}.{table_name} WHERE {primary_key} = '{pk_id}';"

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
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
        expose_primary_key(result, primary_key)
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving row with pk \'{pk_id}\' from table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def get_rows_from_table(table_name, query_dict, tenant, limit, db_instance, primary_key, **kwargs):
    """
    Gets all rows from given table with an optional limit and filter.
    """
    logger.info(f"Getting rows from table {tenant}.{table_name}")

    try:
        command = f"SELECT * FROM {tenant}.{table_name}"
        if len(query_dict) > 0:
            first = True
            for key, value in query_dict.items():
                if first:
                    if type(value) == 'int' or type(value) == 'float':
                        query = f" WHERE \"{key}\" = {value}"
                    else:
                        query = f" WHERE \"{key}\" = \'{value}\'"
                    first = False
                else:
                    if type(value) == 'int' or type(value) == 'float':
                        query = f" AND \"{key}\" = {value}"
                    else:
                        query = f" AND \"{key}\" = \'{value}\'"
                command = command + query
        if "order" in kwargs:
            order = kwargs["order"].replace(",", " ").strip()
            command = f"{command} ORDER BY {order} "

        command = command + f" LIMIT {int(limit)};"
    except Exception as e:
        msg = f"Unable to form database query for table {tenant}.{table_name} with query(ies) {query_dict}: {e}"
        logger.warning(msg)
        raise Exception(msg)

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
            params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        result = dict_fetch_all(cur)
        cur.close()
        conn.commit()
        # Success.
        logger.info(f"Rows successfully retrieved from table {tenant}.{table_name}.")
        expose_primary_key(result, primary_key)
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving rows from table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def create_row(table_name, data, tenant, primary_key, db_instance=None):
    """
    Creates a new row in the given table. Returns the primary key ID of the new row.
    """
    logger.info(f"Creating row in {tenant}.{table_name}...")
    command = f"INSERT INTO {tenant}.{table_name}("
    # Checking data to ensure it's URL safe.
    for k, v in data.items():
        if k == primary_key:
            if isinstance(v, str):
                for char in FORBIDDEN_CHARS:
                    if char in v:
                        msg = f"The primary_key value must be url safe. {char} found in 'key:val' given: '{k}: {v}'." \
                              f" The following chars are not url safe: {FORBIDDEN_CHARS}."
                        logger.error(msg)
                        raise Exception(msg)
        command = f"{command} {k}, "

    # Get the correct number of '%s' for the SQL query. (e.g. "%s, %s, %s, %s, %s, %s")
    values = list(data.values())
    value_str = '%s, ' * len(values)
    value_str = value_str[:-2]
    command = command[:-2] + f") VALUES({value_str}) RETURNING {primary_key};"

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
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


def delete_row(table_name, pk_id, tenant, primary_key, db_instance=None):
    """
    Deletes the specified row in the given table.
    """
    logger.info(f"Deleting row with pk {pk_id} in table {tenant}.{table_name}")
    if type(pk_id) == 'int' or type(pk_id) == 'float':
        command = f"DELETE FROM {tenant}.{table_name} WHERE {primary_key} = {pk_id};"
    else:
        command = f"DELETE FROM {tenant}.{table_name} WHERE {primary_key} = '{pk_id}';"

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
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


def update_row_with_pk(table_name, pk_id, data, tenant, primary_key, db_instance=None):
    """
    Updates a specified row on a table with the given columns and associated values.
    """
    logger.info(f"Updating row with pk \'{pk_id}\' in {tenant}.{table_name}...")
    command = f"UPDATE {tenant}.{table_name} SET"
    for col in data:
        if type(data[col]) == str:
            command = f"{command} {col} = (\'{data[col]}\'), "
        else:
            command = f"{command} {col} = ({data[col]}), "
    if type(pk_id) == 'int' or type(pk_id) == 'float':
        command = command[:-2] + f" WHERE {primary_key} = {pk_id};"
    else:
        command = command[:-2] + f" WHERE {primary_key} = '{pk_id}';"

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
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


def update_rows_with_where(table_name, data, tenant, db_instance, where_clause=None):
    """
    Updates 1+ row(s) on a table with the given columns and associated values based on a where clause. If a where clause
    is not specified, the entire table is updated.
    """
    logger.info(f"Updating rows in {tenant}.{table_name}...")
    command = f"UPDATE {tenant}.{table_name} SET"
    for col in data:
        if type(data[col]) == str:
            command = f"{command} {col} = (\'{data[col]}\'), "
        else:
            command = f"{command} {col} = ({data[col]}), "

    command = command[:-2]
    if where_clause:
        first = True
        for key, value in where_clause.items():
            if first:
                if type(value) == int or type(value) == float:
                    query = f" WHERE \"{key}\" {value['operator']} {value['value']}"
                else:
                    query = f" WHERE \"{key}\" {value['operator']} \'{value['value']}\'"
                first = False
            else:
                if type(value) == 'int' or type(value) == 'float':
                    query = f" AND \"{key}\" {value['operator']} {value['value']}"
                else:
                    query = f" AND \"{key}\" {value['operator']} \'{value['value']}\'"
            command = command + query
    command = command + ';'

    logger.info(f"Command: {command}")
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
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
