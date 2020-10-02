
import psycopg2
from config import config


# TODO create exceptions
def create_tables(table_name, columns):
    """ create tables in the PostgreSQL database"""

    command = (
        f"""
        CREATE TABLE {table_name} (
        {table_name}_id SERIAL PRIMARY KEY,
        """)

    for key, val in columns.items():
        column_name = key.upper()
        column_args = val

        # We need to grab the column type first as it used to decide how to handle the other variables.
        try:
            column_type = column_args["data_type"]
        except KeyError as e:
            msg = f"Data type not received for column {column_name}. Cannot create table {table_name}"
            logger.error(msg)
            raise Exception(msg)

        if column_type in {"VARCHAR", "CHAR", "TEXT"}:
            try:
                char_len = column_args["char_len"]
                column_type = f"{column_type}({char_len})"
            except KeyError as e:
                msg = f"Character max size not received for column {column_name}. Cannot create table {table_name}"
                logger.error(msg)
                raise Exception(msg)

        col_str_list = list()
        col_string = f"{column_name} {column_type}"
        col_str_list.append(col_string)

        # Find optional values and assign to variable.
        for key, val in column_args.items():
            if key == "null":
                if not val:
                    col_str_list.append("NOT NULL")

            elif key == "unique":
                col_str_list.append("UNIQUE")

            elif key == "default":
                col_str_list.append(f"DEFAULT {val}")

            else:
                msg = f"{key} is an invalid argument for column {column_name}. Cannot create table {table_name}"
                logger.error(msg)
                raise Exception(msg)

        col_def = " ".join(col_str_list)
        command = command + f" {col_def}\n"

    command = command + ")"

    conn = None
    try:
        # Read the connection parameters and connect to database.
        params = config()
        conn = psycopg2.connect(**params)
        cur = conn.cursor()
        cur.execute(command)
        cur.close()
        conn.commit()
    except psycopg2.DatabaseError as e:
        msg = f"Error accessing database: {e.message}"
        logger.error(msg)
        raise Exception
    except Exception as e:
        msg = f"Error creating table {table_name}: {e}"
        logger.error(msg)
        raise Exception
