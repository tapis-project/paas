from pgrest.pycommon.config import conf

# check for missing passwords and read them from a file--
for idx, db_conf in enumerate(conf.databases):
    if db_conf['dbpassword'] == "":
        name = db_conf['dbinstancename']
        with open(f'/code/databases/{name}', 'r') as f:
            dbpass = f.read()
        conf.databases[idx]['dbpassword'] = dbpass

