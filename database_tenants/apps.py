from django.apps import AppConfig
from django.db import connection
from django.http import HttpResponseForbidden

from django_tenants.utils import get_tenant_model
from django_tenants.middleware.main import TenantMainMiddleware
from pgrest.utils import make_error
from pgrest.pycommon.auth import t, get_tenant_id_from_base_url
from pgrest.pycommon.logs import get_logger

logger = get_logger(__name__)

class TenantsOnlyConfig(AppConfig):
    name = 'database_tenants'

class GetTenantsFromRequest(TenantMainMiddleware):
    """
    Determines tenant by the value of the ``X-DTS-SCHEMA`` HTTP header.
    """        
    def process_request(self, request):
        # Connection needs first to be at the public schema, as this is where
        # the tenant metadata is stored.

        hostname = self.hostname_from_request(request)

        # createTenants should be be set public schema always
        if "/pgrest/manage/tenants" in request.path and request.method == "POST":
            connection.set_schema_to_public()
        else:
            # Try and get tenant_id from request url and tapipy
            try:
                request_url = request.scheme + "://" + request.get_host()
                tenant_id = get_tenant_id_from_base_url(request_url, t.tenant_cache)
                logger.debug(f"Got tenant information, tenant_id = {tenant_id}, request_url = {request_url}, hostname = {hostname}")
            except Exception as e:
                msg = f"Error getting tenant_id from request_url = {request_url}."
                logger.critical(msg + f" e: {e}")
                return HttpResponseForbidden(make_error(msg=msg))

            # Check if tenant exists with tenant_name == tenant_id
            tenant_model = get_tenant_model()
            if not tenant_model.objects.filter(tenant_name=tenant_id).exists():
                msg = f"Could not find tenant with tenant_id equal to {tenant_id}"
                logger.critical(msg)
                return HttpResponseForbidden(make_error(msg=msg))
            logger.debug(f"Found tenant matching tenant_id = {tenant_id}")

            # Try and set the schema to tenant_id
            try:
                connection.set_schema(tenant_id)
                logger.debug(f"Django Tenant: Set schema to {tenant_id}")
            except Exception as e:
                msg=f"Error setting schema to tenant_id = {tenant_id}"
                logger.critical(msg + f" e: {e}")
                return HttpResponseForbidden(make_error(msg=msg))

        # Uncomment and fix if you want to set up multiple tenant types with Django Tenants
        #self.setup_url_routing(request)