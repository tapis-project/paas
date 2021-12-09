from re import split
import psycopg2
from . import config
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)



def parse_object_data(obj_description, obj_data):
    """
    Parses returned cursor data and returns as a organized dict.
    """
    columns = [col[0] for col in obj_description]
    return [
        dict(zip(columns, row))
        for row in obj_data
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


def do_transaction(command, db_instance, parameterized_values=None):
    conn = None
    try:
        # Read the connection parameters and connect to database.
        if db_instance:
            params = config.config(db_instance)
        else:
            params = config.config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        
        # Mogrify, adds in parameterized_values if they exist, does nothing otherwise.
        # This allows us to print out the full actually used command for debugging.
        full_command = cur.mogrify(command, parameterized_values)
        logger.info(f"Command: {full_command}")
        cur.execute(full_command)
        
        # Get amount of rows affected. (-1 means that query doesn't return anything relevant for .rowcount)
        affected_rows = cur.rowcount
        
        # Try and get object description, also data. Only gets return data, so usually just return an empty array.
        obj_description = cur.description
        try:
            obj_unparsed_data = cur.fetchall()
        except psycopg2.ProgrammingError:
            # Got here because there's no results to fetch
            obj_unparsed_data = []

        # Close cursor properly
        cur.close()
        conn.commit()

    except psycopg2.DatabaseError as e:
        if conn:
            conn.close()
        msg = f"Error accessing database: {e}"
        logger.error(msg)
        raise Exception(msg)
    except Exception as e:
        if conn:
            conn.close()
        msg = f"Error executing command: {command}; e: {e}"
        logger.error(msg)
        raise Exception(msg)
    
    logger.info(f'do_transaction: object_description: {obj_description}, unparsed_data: {obj_unparsed_data}, affected_rows: {affected_rows}')
    return obj_description, obj_unparsed_data, affected_rows


def search_parse(search_params, tenant, obj_name, db_instance):
    # 'obj' references 'database object', so both views and tables.
    # search_params list is [[key, oper, value], ...]
    parameterized_values = []

    # We add where to command now to get ready for query        
    command = " WHERE"

    # If we have search_params we first have to get the objects's columns to ensure
    # columns entered are indeed columns in the obj and not sql injection
    get_obj_data_cmd = (
        "SELECT attname AS column_name, format_type(atttypid, atttypmod) AS data_type "
        "FROM   pg_attribute "
        f"WHERE  attrelid = '{tenant}.{obj_name}'::regclass AND NOT attisdropped AND attnum > 0"
        "ORDER  BY attnum;")
    # Object data retrieved comes in the form [{'column_name': 'nameHere', 'data_type': 'integer'}, ...]
    obj_description, obj_unparsed_data, _ = do_transaction(get_obj_data_cmd, db_instance)
    obj_data = parse_object_data(obj_description, obj_unparsed_data)
    logger.info(f"Got obj data for : {tenant}.{obj_name}. Data: {obj_data}")

    # Now we have the obj data, parse into dict of {'colName': 'dataType'}
    obj_data_dict = {}
    if obj_data:
        for column_data in obj_data:
            obj_data_dict[column_data['column_name']] = column_data['data_type']
            
    # Now we go through search params. First check if key is in objects's columns.
    # if it is we can modify the value to match the key data type (convert to timestamp if need be),
    # then we throw everything into the command.
    for key, oper, val in search_params:
        query_key = key
        query_key_type = ""
        query_oper = oper
        query_val = val
        
        # Check if key is in objects's columns, if it is, set query key and type
        if query_key in obj_data_dict:
            query_key_type = obj_data_dict.get(query_key)
        else:
            msg = f"Column parameter, {query_key}, not found in the columns of {tenant}.{obj_name}."
            logger.warning(msg)
            return Exception(msg)

        # Add to command query.
        # Types and parameterization should follow this: https://www.psycopg.org/docs/usage.html
        # Note: There should be no issue with between and timestamps because postgres should attempt
        # to read in strings as timestamps on it's side. Though datetime objects also work.
        # Note: Converting types isn't neccessary, Postgres parses all strings into the proper format already,
        # we need to parse lists so that we can parameterize them in the case of in/nin/between/nbetween
        oper_aliases = {'.neq': '!=',
                        '.eq': '=',
                        '.lte': '<=',
                        '.lt': '<',
                        '.gte': '>=',
                        '.gt': '>',
                        '.nin': 'NOT IN',
                        '.in': 'IN',
                        '.like': 'LIKE',
                        '.nlike': 'NOT LIKE',
                        '.between': 'BETWEEN',
                        '.nbetween': 'NOT BETWEEN'}

        # Special case, 'IS NULL' and 'IS NOT NULL' as they don't have inputs, we use .null and True/False to specify.
        # Note: I add None to parameterized values instead of adding NULL to the command only so we have the same amount of
        # parameterized_values and search_params. This might make readability more reasonable.
        if query_oper == '.null':
            if query_val.lower() == 'true':
                command += f" {query_key} IS %s AND"
                parameterized_values.append(None)
                continue
            elif query_val.lower() == 'false':
                command += f" {query_key} IS NOT %s AND"
                parameterized_values.append(None)
                continue
            else:
                msg = f".null operator can only receive case-insensitive true or false as inputs. Received {query_val}"
                logger.warning(msg)
                return Exception(msg)

        # Deal with n/between case, have to make tuple of inputs, and formatting of 'where' is different (There's a forced and)
        if query_oper in ['.between', '.nbetween']:
            # between/nbetween has to have a two variable tuple
            query_vals = query_val.split(',')
            if not len(query_vals) == 2:
                msg = f".between/.nbetween operators must have two variables seperated by a comma. Ex. myvar.between=20,40"
                logger.warning(msg)
                return Exception(msg)
            command += f" {query_key} {oper_aliases[query_oper]} %s AND %s AND"
            parameterized_values.append(query_vals[0])
            parameterized_values.append(query_vals[1])
            continue

        # Deal with n/in, have to make tuples of inputs, then it can go through regular pipeline
        if query_oper in ['.in', '.nin']:
            # n/in can have any length as long as it's a tuple
            query_val = tuple(query_val.split(','))

        # For all other cases, add the query to the command here.
        command += f" {query_key} {oper_aliases[query_oper]} %s AND"
        parameterized_values.append(query_val)
    
    # Get rid of the trailing ' AND' in command
    command = command[:-4]
    logger.info(f"Search part of command: {command}")
    
    return command, parameterized_values

def order_parse(order_string, tenant, obj_name, db_instance):
    # 'obj' references 'database object', so both views and tables.
    # input for order should be ?order=col_1,DESC, so order_string is col_1,DESC
    split_string = order_string.split(',')
    column_name = split_string[0]
    if len(split_string) > 2:
        msg = f"Order must be in the format 'columnName,DESC', 'columnName,ASC' or 'columnName'. Got {order_string}"
        logger.warning(msg)
        return Exception(msg)

    if len(split_string) == 2:
        order_dir = split_string[1]
        if not order_dir in ["ASC", "DESC"]:
            msg = f"Order must be in the format 'columnName,DESC', 'columnName,ASC' or 'columnName'. Got {order_string}"
            logger.warning(msg)
            return Exception(msg)
    else:
        order_dir = None

    # We have to get the objects's columns to ensure column entered
    # is indeed a column in the obj and not sql injection
    get_obj_data_cmd = (
        "SELECT attname AS column_name, format_type(atttypid, atttypmod) AS data_type "
        "FROM   pg_attribute "
        f"WHERE  attrelid = '{tenant}.{obj_name}'::regclass AND NOT attisdropped AND attnum > 0"
        "ORDER  BY attnum;")
    # Object data retrieved comes in the form [{'column_name': 'nameHere', 'data_type': 'integer'}, ...]
    obj_description, obj_unparsed_data, _ = do_transaction(get_obj_data_cmd, db_instance)
    obj_data = parse_object_data(obj_description, obj_unparsed_data)
    logger.info(f"Got obj data for : {tenant}.{obj_name}. Data: {obj_data}")

    # Now we have the obj data, parse into dict of {'colName': 'dataType', ...}
    obj_data_dict = {}
    if obj_data:
        for column_data in obj_data:
            obj_data_dict[column_data['column_name']] = column_data['data_type']

    if not column_name in obj_data_dict:
        msg = f"Got a columnName of {column_name} in order. Not in valid column name, columns for this table are: {obj_data_dict.keys()}"
        logger.warning(msg)
        return Exception(msg)        

    if order_dir:
        command = f" ORDER BY {column_name} {order_dir}"
    else:
        command = f" ORDER BY {column_name}"
    logger.info(f"Order part of command: {command}")
    
    return command
