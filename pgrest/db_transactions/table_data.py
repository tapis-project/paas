import re
import psycopg2
from . import config
from .data_utils import do_transaction, parse_object_data, search_parse, order_parse, expose_primary_key
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)

# We create a forbidden regex for quick parsing
# Forbidden: \ ` ' " ~  / ? # [ ] ( ) @ ! $ & * + = - . , : ;
FORBIDDEN_CHARS =  re.compile("^[^<>\\\/{}[\]~` $'\".:-?#@!$&()*+,;=]*$")


def get_row_from_table(table_name, pk_id, tenant, primary_key, db_instance=None):
    """
    Gets the row with given primary key from the specified table.
    """
    logger.info(f"Getting row with pk {pk_id} from table {tenant}.{table_name}...")
    if type(pk_id) == 'int' or type(pk_id) == 'float':
        command = f"SELECT * FROM {tenant}.{table_name} WHERE {primary_key} = {pk_id};"
    else:
        command = f"SELECT * FROM {tenant}.{table_name} WHERE {primary_key} = '{pk_id}';"
    
    # Run command
    try:
        obj_description, obj_unparsed_data, _ = do_transaction(command, db_instance)
        result = parse_object_data(obj_description, obj_unparsed_data)
        if len(result) == 0:
            msg = f"Error. Received no result when retrieving row with pk \'{pk_id}\' from view {tenant}.{table_name}."
            logger.error(msg)
            raise Exception(msg)
        expose_primary_key(result, primary_key)
        logger.info(f"Row {pk_id} successfully retrieved from view {tenant}.{table_name}.")
    except Exception as e:
        msg = f"Error retrieving row with pk \'{pk_id}\' from view {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return result


def get_rows_from_table(table_name, search_params, tenant, limit, offset, db_instance, primary_key, **kwargs):
    """
    Gets all rows from given table with an optional limit and filter.
    """
    logger.info(f"Getting rows from table {tenant}.{table_name}")
    command = f"SELECT * FROM {tenant}.{table_name}"

    # Add search params, order, limit, and offset to command
    try:
        parameterized_values = []
        if search_params:
            search_command, parameterized_values = search_parse(search_params, tenant, table_name, db_instance)
            command += search_command

        if "order" in kwargs:
            order = kwargs["order"]
            order_command = order_parse(order, tenant, table_name, db_instance)
            command += order_command

        command = command + f" LIMIT {int(limit)} "
        command = command + f" OFFSET {int(offset)};"
    except Exception as e:
        msg = f"Unable to add order, limit, and offset for table {tenant}.{table_name}: {e}"
        logger.warning(msg)
        raise Exception(msg)

    # Run command
    try:
        obj_description, obj_unparsed_data, _ = do_transaction(command, db_instance, parameterized_values)
        result = parse_object_data(obj_description, obj_unparsed_data)
        expose_primary_key(result, primary_key)
        logger.info(f"Rows successfully retrieved from table {tenant}.{table_name}.")
    except Exception as e:
        msg = f"Error retrieving rows from table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return result


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
                if not FORBIDDEN_CHARS.match(v):
                    msg = f"The primary_key value must be url safe. Value inputted {v}"
                    logger.error(msg)
                    raise Exception(msg)
        command = f"{command} {k}, "

    # Get the correct number of '%s' for the SQL query. (e.g. "%s, %s, %s, %s, %s, %s")
    parameterized_values = list(data.values())
    value_str = '%s, ' * len(parameterized_values)
    value_str = value_str[:-2]
    command = command[:-2] + f") VALUES({value_str}) RETURNING {primary_key};"

    # Run command
    try:
        obj_description, obj_unparsed_data, _ = do_transaction(command, db_instance, parameterized_values)
        result = parse_object_data(obj_description, obj_unparsed_data)
        # We used "RETURNING %pk" in command, so we should get the PK value for later use.
        result_id = result[0][primary_key]
        logger.info(f"Rows successfully created in table {tenant}.{table_name}.")
    except Exception as e:
        msg = f"Error creating row in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return result_id


def delete_row(table_name, pk_id, tenant, primary_key, db_instance=None):
    """
    Deletes the specified row in the given table.
    """
    logger.info(f"Deleting row with pk {pk_id} in table {tenant}.{table_name}")
    if type(pk_id) == 'int' or type(pk_id) == 'float':
        command = f"DELETE FROM {tenant}.{table_name} WHERE {primary_key} = {pk_id};"
    else:
        command = f"DELETE FROM {tenant}.{table_name} WHERE {primary_key} = '{pk_id}';"

    # Run command
    try:
        _, _, affected_rows = do_transaction(command, db_instance)
        if affected_rows == 0:
            msg = f"Error. Delete row affected 0 rows, expected to delete 1."
            logger.error(msg)
            raise Exception(msg)
        logger.info(f"Row successfully deleted from table {tenant}.{table_name}.")
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

    # Run command
    try:
        _, _, affected_rows = do_transaction(command, db_instance)
        if affected_rows == 0:
            msg = f"Error. Delete row affected 0 rows, expected to delete 1."
            logger.error(msg)
            raise Exception(msg)
        logger.info(f"Row {pk_id} successfully updated in table {tenant}.{table_name}.")
    except Exception as e:
        msg = f"Error updating row ID {pk_id} in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def update_rows_with_where(table_name, data, tenant, db_instance, search_params=None):
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
    
    parameterized_values = []
    if search_params:
        search_command, parameterized_values = search_parse(search_params, tenant, table_name, db_instance)
        command += search_command
    command = command + ';'
    
    # Run command
    try:
        obj_description, obj_unparsed_data, affected_rows = do_transaction(command, db_instance, parameterized_values)
        logger.info(f"{affected_rows} rows were successfully updated in table {tenant}.{table_name}.")
    except Exception as e:
        msg = f"Error updating rows in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return affected_rows