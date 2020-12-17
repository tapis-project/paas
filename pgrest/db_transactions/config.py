#!/usr/bin/python
from pgrest.pycommon.config import conf
PARAMS_MAP = {
    "dbhost":"host",
    "dbname": "database",
    "dbuser": "user",
    "dbpassword": "password",
    "dbport": "port",
    # this key not used and cannot be passed as part of the connection package..
    # "dbinstancename": "collection"
}

def config(db_instance='local'):
    # get section, default to postgresql
    db = {}
    for db_conf in conf.databases:
        if db_conf['dbinstancename'] == db_instance:
            for k,v in db_conf.items():
                try:
                    db[PARAMS_MAP[k]] = v
                except KeyError:
                    # some param keys are not needed by the psycopg2 connection object.
                    pass
            return db
    raise Exception(f'Database {db_instance} not found in config.')

