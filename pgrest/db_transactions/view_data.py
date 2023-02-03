import re
import psycopg2
from . import config
from .data_utils import do_transaction, parse_object_data, search_parse, order_parse
from tapisservice.logs import get_logger
logger = get_logger(__name__)


def get_row_from_view(view_name, pk_id, tenant, primary_key, db_instance=None):
    """
    Gets the row with given primary key from the specified table.
    """
    logger.info(f"Getting row with pk {pk_id} from view {tenant}.{view_name}...")
    if type(pk_id) == 'int' or type(pk_id) == 'float':
        command = f"SELECT * FROM {tenant}.{view_name} WHERE {primary_key} = {pk_id};"
    else:
        command = f"SELECT * FROM {tenant}.{view_name} WHERE {primary_key} = '{pk_id}';"

    # Run command
    try:
        obj_description, obj_unparsed_data, _ = do_transaction(command, db_instance)
        result = parse_object_data(obj_description, obj_unparsed_data)
        if len(result) == 0:
            msg = f"Error. Received no result when retrieving row with pk \'{pk_id}\' from view {tenant}.{view_name}."
            logger.error(msg)
            raise Exception(msg)
        logger.info(f"Row {pk_id} successfully retrieved from view {tenant}.{view_name}.")
    except Exception as e:
        msg = f"Error retrieving row with pk \'{pk_id}\' from view {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return result


def get_rows_from_view(view_name, search_params, tenant, limit, offset, db_instance, primary_key, **kwargs):
    """
    Gets all rows from given table with an optional limit and filter.
    """
    logger.info(f"Getting rows from table {tenant}.{view_name}")
    command = f"SELECT * FROM {tenant}.{view_name}"

    # Add search params, order, limit, and offset to command
    try:
        parameterized_values = []
        if search_params:
            search_command, parameterized_values = search_parse(search_params, tenant, view_name, db_instance)
            command += search_command

        if "order" in kwargs:
            order = kwargs["order"]
            order_command = order_parse(order, tenant, view_name, db_instance)
            command += order_command

        if limit:
            command += f" LIMIT {int(limit)} "
        if offset:
            command += f" OFFSET {int(offset)};"
    except Exception as e:
        msg = f"Unable to add order, limit, and offset for view {tenant}.{view_name}: {e}"
        logger.warning(msg)
        raise Exception(msg)

    # Run command
    try:
        obj_description, obj_unparsed_data, _ = do_transaction(command, db_instance, parameterized_values)
        result = parse_object_data(obj_description, obj_unparsed_data)
        logger.info(f"Rows successfully retrieved from view {tenant}.{view_name}.")
    except Exception as e:
        msg = f"Error retrieving rows from view {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
    return result


def create_view(view_name, view_definition, tenant, db_instance=None):
    """Create view in the PostgreSQL database"""
    try:
        from_table = view_definition['from_table']
        materialized_view_raw_sql = view_definition.get('materialized_view_raw_sql', None)
        raw_sql = view_definition['raw_sql']
        select_query = view_definition['select_query']
        where_query = view_definition['where_query']
    except KeyError:
        msg = f"Error reading view variables from view_definition. v_d: {view_definition}"
        logger.error(msg)
        raise Exception(msg)

    logger.info(f"Creating view {tenant}.{view_name}...")

    if raw_sql:
        command = f"CREATE OR REPLACE VIEW {tenant}.{view_name} {raw_sql}"
    elif materialized_view_raw_sql:
        command = f"CREATE MATERIALIZED VIEW {tenant}.{view_name} {materialized_view_raw_sql}"
    else:
        if where_query:
            command = f"CREATE OR REPLACE VIEW {tenant}.{view_name} AS SELECT {select_query} FROM {tenant}.{from_table} WHERE {where_query};"
        else:
            command = f"CREATE OR REPLACE VIEW {tenant}.{view_name} AS SELECT {select_query} FROM {tenant}.{from_table};"

    metadata = {"command": command}
    logger.debug(f"Create db command for view {tenant}.{view_name}: {command}")

    # Run command
    try:
        do_transaction(command, db_instance)
        if materialized_view_raw_sql:
            logger.debug(f"Materialized view {tenant}.{view_name} successfully created in postgres db.")
        else:
            logger.debug(f"View {tenant}.{view_name} successfully created in postgres db.")
    except Exception as e:
        msg = f"Error creating view {tenant}.{view_name}: {e}"
        logger.error(f"{msg} -- Command: {command}")
        raise Exception(msg, metadata)
    return metadata


def delete_view(view_name, tenant, materialized_view=False, db_instance=None):
    """ Drop view (or materialized view) in the PostgreSQL database"""
    # Maybe we shouldn't CASCADE?
    if materialized_view:
        logger.info(f"Dropping materialized view {tenant}.{view_name}...")
        command = f"DROP MATERIALIZED VIEW IF EXISTS {tenant}.{view_name} CASCADE;"
        logger.info(f"Drop materialized view command for {tenant}.{view_name}: {command}")
    else:
        logger.info(f"Dropping view {tenant}.{view_name}...")
        command = f"DROP VIEW IF EXISTS {tenant}.{view_name} CASCADE;"
        logger.info(f"Drop view command for {tenant}.{view_name}: {command}")

    # Run command
    try:
        do_transaction(command, db_instance)
        if materialized_view:
            logger.info(f"Materialized view {tenant}.{view_name} successfully dropped from postgres db.")
        else:   
            logger.info(f"View {tenant}.{view_name} successfully dropped from postgres db.")
    except Exception as e:
        if materialized_view:
            msg = f"Error dropping materialized view {tenant}.{view_name}: {e}"
        else:
            msg = f"Error dropping view {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)


def refresh_view(view_name, tenant, db_instance=None):
    """ Refresh materialized view in the PostgreSQL database"""
    logger.info(f"Refreshing materialized view {tenant}.{view_name}...")
    command = f"REFRESH MATERIALIZED VIEW {tenant}.{view_name};"
    logger.info(f"REFRESH materialized view command for {tenant}.{view_name}: {command}")

    # Run command
    try:
        do_transaction(command, db_instance)
        logger.info(f"Materialized view {tenant}.{view_name} successfully refreshed in postgres db.")
    except Exception as e:
        msg = f"Error refreshing materialized view {tenant}.{view_name}: {e}"
        logger.error(msg)
        raise Exception(msg)
