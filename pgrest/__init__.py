# the first import of the tapipy client is somewhat expensive (a few seconds), so we do it here at service start up
# to prevent paying the cost later..
from tapisservice.auth import get_service_tapis_client
from tapisservice.tenants import TenantCache
from tapisservice.logs import get_logger
logger = get_logger(__name__)

Tenants = TenantCache()
try:
    t = get_service_tapis_client(tenants=Tenants)
except Exception as e:
    logger.error(f'Could not instantiate tapy service client. Exception: {e}')
    raise e