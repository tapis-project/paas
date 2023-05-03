import re
import psycopg2
from cerberus import Validator
from . import config
from .data_utils import do_transaction, parse_object_data, search_parse, order_parse, expose_primary_key
from tapisservice.logs import get_logger
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

        if limit:
            command += f" LIMIT {int(limit)} "
        if offset:
            command += f" OFFSET {int(offset)};"
    except Exception as e:
        msg = f"Unable to add order, limit, offset, and search for table {tenant}.{table_name}: {e}"
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


def row_creator(table_name, data, tenant, primary_key, validate_json_create, db_instance=None):
    """
    Creates new rows in a given table. Does it all in one transaction. Command will be the following.
    Returns the rows that are inserted. Note, this means we need column_names and value_lists to match
    throughout. Meaning we need to get all table columns, check column values, and list new data properly.
    
    Command:
        INSERT INTO table_name (column_list)
        VALUES
            (value_list_1),
            (value_list_2),
            (value_list_3)
        RETURNING *
    """
    logger.info(f"In row_creator for {tenant}.{table_name}...")
    
    # Check data is a dict or list (lists create multiple rows at once).
    if not type(data) in [dict, list]:
        msg = f"Data for row creation should be of type dict or list (which contains dicts). Received '{type(data)}'"
        logger.debug(msg)
        raise Exception(msg)

    # We put dicts in lists so we can use list parsing functions throughout no matter amount of rows being created.
    if isinstance(data, dict):
        data = [data]

    # Validate data is list of dicts, and validate the row definitions to make sure they have proper column_names and all.
    for row_def in data:
        if not isinstance(row_def, dict):
            msg = f"Data lists during row creation should contain dicts of row_information. List contained type '{type(data)}'. Item: {row_def}"
            logger.debug(msg)
            raise Exception(msg)

        # Validate each row against the table's json schema.
        try:
            v = Validator(validate_json_create)
            if not v.validate(row_def):
                msg = f"Row definition determined invalid from validation schema; errors: {v.errors}; row def: {row_def}"
                logger.warning(msg)
                raise Exception(msg)
        except Exception as e:
            msg = f"Error occurred when validating the data from the validation schema; Details: {e}"
            logger.error(msg)
            raise Exception(msg)

    # We get all column names from validate_json_create (table def on ManageTables)
    # we have INSERT reference all column_values. For each row, we either put in correct
    # column value or DEFAULT to use whatever the DEFAULT value is if nothing is specified
    # by the user.
    # e.g. INSERT INTO dev.table1(col_1, col_2, col_3)
    #      VALUES
    #          (col_1_val, DEFAULT, col_3_val), etc.
    logger.info(f"Creating row(s) in {tenant}.{table_name}...")
    logger.info(f"Data received for new row endpoint: {data}")

    columns = set(validate_json_create.keys()) # These are all column names
    logger.info(f"Current table columns: {columns}")
    command = f"INSERT INTO {tenant}.{table_name}({', '.join(columns)}) VALUES " # INSERT INTO dev.table(col_one, col_two, col_three) VALUES

    # We have to create command and get data for command at the same time because if a column value
    # is not provided we have to use "DEFAULT", but that doesn't work through parameterized
    # values, only through raw SQL. So we do it this way, using parameterized values (%s) in the 
    # command and providing parameters in do_transaction()
    
    parameterized_values = []
    for row_data in data:
        row_insert_command = "("
        for column_key in columns:
            try:
                column_val = row_data[column_key]
            except KeyError:
                # add default if user didn't specify column value.
                row_insert_command += "DEFAULT, "
                continue
            if column_key == primary_key and isinstance(column_val, str):
                if not FORBIDDEN_CHARS.match(column_val):
                    msg = f"The primary_key value must be url safe. Value inputted for pk '{primary_key}' was '{column_val}'"
                    logger.error(msg)
                    raise Exception(msg)
            parameterized_values.append(column_val)
            row_insert_command += "%s, "
        row_insert_command = f"{row_insert_command[:-2]}), " # "(col_one, -> (col_one) "
        command += row_insert_command

    command = command[:-2]
    command += "RETURNING *"

    # Run command
    logger.info("Created command and got parameterized values. Running command")
    try:
        obj_description, obj_unparsed_data, _ = do_transaction(command, db_instance, parameterized_values)
        row_creator_result = parse_object_data(obj_description, obj_unparsed_data)
        logger.info(f"Rows successfully added to table {tenant}.{table_name}.")
    except Exception as e:
        msg = f"Error adding rows to table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return row_creator_result


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
        if isinstance(data[col], str):
            command = f"{command} {col} = (\'{data[col]}\'), "
        elif isinstance(data[col], type(None)):
            command = f"{command} {col} = (NULL), "
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
        if isinstance(data[col], str):
            command = f"{command} {col} = (\'{data[col]}\'), "
        elif isinstance(data[col], type(None)):
            command = f"{command} {col} = (NULL), "
        else:
            command = f"{command} {col} = ({data[col]}), "

    command = command[:-2]
    
    parameterized_values = []
    if search_params:
        search_command, parameterized_values = search_parse(search_params, tenant, table_name, db_instance)
        command += search_command
    command += ';'
    
    # Run command
    try:
        obj_description, obj_unparsed_data, affected_rows = do_transaction(command, db_instance, parameterized_values)
        logger.info(f"{affected_rows} rows were successfully updated in table {tenant}.{table_name}.")
    except Exception as e:
        msg = f"Error updating rows in table {tenant}.{table_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return affected_rows