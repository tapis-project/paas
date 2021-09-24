#!/usr/bin/python
from ..pycommon.config import conf
from ..pycommon.logs import get_logger
logger = get_logger(__name__)


def config(db_instance='default'):
    # This is used to get which database we should be getting info from. Each Tenant object
    # has it's specific db_instance in the database. We take a request, calculate the db_instance,
    # then when called, we use this db_instance to connect to the proper database.
    db_instances = conf.databases
    try:
        db_config = db_instances[db_instance]
    except KeyError:
        msg = f'Can not find a db_instance named "{db_instance}". Possible db_instances are {db_instances.keys()}'
        logger.critical(msg)
        raise KeyError(msg)

    # db config should have ENGINE, NAME, USER, PASSWORD, HOST, PORT, OPTIONS is optional.
    for key in ["ENGINE", "NAME", "USER", "PASSWORD", "HOST", "PORT"]:
        if not key in db_config:
            msg = f'"{key}" is missing from schema definition for db_instance "{db_instance}"'
            logger.critical(msg)
            raise KeyError(msg)
    
    # Create the db_connection to be used by psycopg2
    db_connection = {"dbname": db_config["NAME"],
                     "user": db_config["USER"],
                     "password": db_config["PASSWORD"],
                     "host": db_config["HOST"],
                     "port": db_config["PORT"]}
    if "OPTIONS" in db_config and "options" in db_config["OPTIONS"]:
        db_connection.update(db_config["OPTIONS"])
    return db_connection