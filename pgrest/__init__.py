from pgrest.pycommon.config import conf

# the first import of the tapipy client is somewhat expensive (a few seconds), so we do it here at service start up
# to prevent paying the cost later..
from pgrest.pycommon.auth import t

# check for missing passwords and read them from a file--
for idx, db_conf in enumerate(conf.databases):
    if db_conf['dbpassword'] == "":
        name = db_conf['dbinstancename']
        with open(f'/code/databases/{name}', 'r') as f:
            dbpass = f.read()
        conf.databases[idx]['dbpassword'] = dbpass

