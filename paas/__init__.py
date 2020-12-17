from pgrest.pycommon.config import conf

def get_django_db():
    """
    Returns the django db parameters for the settings.py file --
    """
    # loop through the database connections; if "local" appears, use that for
    # the Django DB, otherwise, use "kubernetes".
    kube_db = {}
    for db in conf.databases:
        if db['dbinstancename'] == "local":
            return db
        elif db['dbinstancename'] == 'kubernetes':
            kube_db = db
    return kube_db

