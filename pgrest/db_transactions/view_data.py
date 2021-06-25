import re
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

def get_row_from_view(view_name, pk_id, tenant, primary_key, db_instance=None):
    """
    Gets the row with given primary key from the specified table.
    """
    logger.info(f"Getting row with pk {pk_id} from view {tenant}.{view_name}...")
    if type(pk_id) == 'int' or type(pk_id) == 'float':
        command = f"SELECT * FROM {tenant}.{view_name} WHERE {primary_key} = {pk_id};"
    else:
        command = f"SELECT * FROM {tenant}.{view_name} WHERE {primary_key} = '{pk_id}';"

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
        logger.info(f"Row {pk_id} successfully retrieved from view {tenant}.{view_name}.")
        #expose_primary_key(result, primary_key)
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving row with pk \'{pk_id}\' from view {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def get_rows_from_view(view_name, query_dict, tenant, limit, offset, db_instance, primary_key, **kwargs):
    """
    Gets all rows from given table with an optional limit and filter.
    """
    logger.info(f"Getting rows from table {tenant}.{view_name}")

    try:
        command = f"SELECT * FROM {tenant}.{view_name}"
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

        command = command + f" LIMIT {int(limit)} "
        command = command + f" OFFSET {int(offset)};"
    except Exception as e:
        msg = f"Unable to form database query for table {tenant}.{view_name} with query(ies) {query_dict}: {e}"
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
        logger.info(f"Rows successfully retrieved from table {tenant}.{view_name}.")
        #expose_primary_key(result, primary_key)
        return result
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        msg = f"Error retrieving rows from table {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def create_view(view_name, view_definition, tenant, db_instance=None):
    """Create view in the PostgreSQL database"""
    try:
        select_query = view_definition['select_query']
        from_table = view_definition['from_table']
        where_query = view_definition['where_query']
    except KeyError:
        msg = f"Error reading view variables from view_definition. v_d: {view_definition}"
        logger.error(msg)
        raise Exception(msg)

    logger.info(f"Creating view {tenant}.{view_name}...")
    if where_query:
        command = f"CREATE OR REPLACE VIEW {tenant}.{view_name} AS SELECT {select_query} FROM {tenant}.{from_table} WHERE {where_query};"
    else:
        command = f"CREATE OR REPLACE VIEW {tenant}.{view_name} AS SELECT {select_query} FROM {tenant}.{from_table};"

    logger.debug(f"Create db command for view {tenant}.{view_name}: {command}")

    conn = None
    try:
        do_transaction(command, db_instance)
        logger.debug(f"View {tenant}.{view_name} successfully created in postgres db.")
    except psycopg2.DatabaseError as e:
        if conn:
            conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        if conn:
            conn.close()
        msg = f"Error creating view {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def delete_view(view_name, tenant, db_instance=None):
    """ Drop view in the PostgreSQL database"""
    logger.info(f"Dropping view {tenant}.{view_name}...")
    # Maybe we shouldn't CASCADE?
    command = f"DROP VIEW {tenant}.{view_name} CASCADE;"
    conn = None
    logger.info(f"Drop view command for {tenant}.{view_name}: {command}")
    try:
        do_transaction(command, db_instance)
        logger.info(f"View {tenant}.{view_name} successfully dropped from postgres db.")
    except psycopg2.DatabaseError as e:
        if conn:
            conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        if conn:
            conn.close()
        msg = f"Error dropping view {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
