from tapipy.tapis import Tapis, TapisResult
from pgrest.pycommon.config import conf
from pgrest.pycommon import errors
from pgrest.pycommon.tenants import tenants as default_tenants


def get_service_tapis_client(tenant_id=None,
                             base_url=None,
                             jwt=None,
                             resource_set='local',  # TODO -- change to 'tapipy' when resources are updated.
                             custom_spec_dict=None,
                             download_latest_specs=False,
                             tenants=default_tenants):
    """
    Returns a Tapis client for the service using the service's configuration. If tenant_id is not passed, uses the first
    tenant in the service's tenants configuration.
    :param tenant_id: (str) The tenant_id associated with the tenant to configure the client with.
    :param base_url: (str) The base URL for the tenant to configure the client with.
    :return: (tapipy.tapis.Tapis) A Tapipy client object.
    """
    # if there is no base_url the primary_site_admin_tenant_base_url configured for the service:
    if not base_url:
        base_url = conf.primary_site_admin_tenant_base_url
    if not tenant_id:
        tenant_id = conf.service_tenant_id
    if not tenants:
        # the following would work to reference this module's tenants object, but we'll choose to raise
        # an error instead; it could be that
        # tenants = sys.modules[__name__].tenants
        raise errors.BaseTapisError("As a Tapis service, passing in the appropriate tenants manager object"
                                    "is required.")
    t = Tapis(base_url=base_url,
              tenant_id=tenant_id,
              username=conf.service_name,
              account_type='service',
              service_password=conf.service_password,
              jwt=jwt,
              resource_set=resource_set,
              custom_spec_dict=custom_spec_dict,
              download_latest_specs=download_latest_specs,
              tenants=tenants,
              is_tapis_service=True)
    if not jwt:
        t.get_tokens()
    return t


# singleton tapipy client which can be imported and used by the service
# directly
t = get_service_tapis_client()


def get_tenant_id_from_base_url(base_url, tenants):
    """
    Return the tenant_id associated with the base URL of a request.
    """
    request_tenant = tenants.get_tenant_config(url=base_url)
    return request_tenant.tenant_id
