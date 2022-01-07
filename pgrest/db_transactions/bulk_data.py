import sys

from subprocess import Popen, check_call, call, PIPE
from tapisservice.logs import get_logger
logger = get_logger(__name__)


def dump_data(table_name, file_path, tenant):
    """
    Dump data from the table specified into a json at the file_path. If table_name is "ALL", dump all tables.
    """
    logger.info(f"Dumping data from table {tenant}.{table_name} to {file_path}...")

    command = f'/usr/local/bin/pg_dump --host={"paas_db_1"} ' \
            f'--dbname={"postgres"} ' \
            f'--username={"postgres"} ' \
            f'--no-password ' \
            f'--schema-only={tenant} ' \
            '-Fc ' \
            f'--file={file_path}'

    p = Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE)

    # ok = p.communicate("AjKKl9090PORT".encode())
    # return ok[1]

    proc = Popen(command, shell=True, stdin=PIPE,stdout=PIPE, env={
        'PGPASSWORD': "AjKKl9090PORT"
    })
    proc.wait()
    print(proc.returncode)
    print("done")
