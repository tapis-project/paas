from tapipy.tapis import Tapis, TapisResult

from pgrest.pycommon.config import conf
from pgrest.pycommon import errors
from pgrest.pycommon.logs import get_logger
logger = get_logger(__name__)

class Tenants(object):
    """
    Class for managing the tenants available in the tenants registry, including metadata associated with the tenant.
    """
    def __init__(self):
        self.primary_site = None
        self.service_running_at_primary_site = None
        self.tenants = self.get_tenants()

    def extend_tenant(self, t):
        """
        Method to add additional attributes to tenant object that are specific to a single service, such as the private
        keys for the Tokens API or the LDAP passwords for the authenticator. The service should implement this mwthod
        :param t:
        :return:
        """
        return t

    def get_tenants(self):
        """
        Retrieve the set of tenants and associated data that this service instance is serving requests for.
        :return:
        """
        logger.debug("top of get_tenants()")
        # if this is the first time we are calling get_tenants, set the service_running_at_primary_site attribute.
        if not hasattr(self, "service_running_at_primary_site"):
            self.service_running_at_primary_site = False
        # the tenants service is a special case, as it must be a) configured to serve all tenants and b) actually
        # maintains the list of tenants in its own DB. in this case, we call a special method to use the tenants service
        # code that makes direct db access to get necessary data.
        if conf.service_name == 'tenants':
            self.service_running_at_primary_site = True
            return self.get_tenants_for_tenants_api()
        else:
            logger.debug("this is not the tenants service; calling tenants API to get sites and tenants...")
            # if this case, this is not the tenants service, so we will try to get
            # the list of tenants by making API calls to the tenants service.
            # NOTE: we intentionally create a new Tapis client with *no authentication* so that we can call the Tenants
            # API even _before_ the SK is started up. If we pass a JWT, the Tenants will try to validate it as part of
            # handling our request, and this validation will fail if SK is not available.
            t = Tapis(base_url=conf.primary_site_admin_tenant_base_url, resource_set='local') # TODO -- remove resource_set='local'
            try:
                tenants = t.tenants.list_tenants()
                sites = t.tenants.list_sites()
            except Exception as e:
                msg = f"Got an exception trying to get the list of sites and tenants. Exception: {e}"
                logger.error(msg)
                raise errors.BaseTapisError("Unable to retrieve sites and tenants from the Tenants API.")
            for t in tenants:
                self.extend_tenant(t)
                for s in sites:
                    if hasattr(s, "primary") and s.primary:
                        self.primary_site = s
                        if s.site_id == conf.service_site_id:
                            logger.debug(f"this service is running at the primary site: {s.site_id}")
                            self.service_running_at_primary_site = True
                    if s.site_id == t.site_id:
                        t.site = s
            return tenants

    def get_tenants_for_tenants_api(self):
        """
        This method computes the tenants and sites for the tenants service only. Note that the tenants service is a
        special case because it must retrieve the sites and tenants from its own DB, not from
        """
        logger.debug("this is the tenants service, pulling sites and tenants from db...")
        # NOTE: only in the case of the tenants service will we be able to import this function; so this import needs to
        # stay guarded in this method.
        if not conf.service_name == 'tenants':
            raise errors.BaseTapisError("get_tenants_for_tenants_api called by a service other than tenants.")
        from service.models import get_tenants as tenants_api_get_tenants
        from service.models import get_sites as tenants_api_get_sites
        # in the case where the tenants api migrations are running, this call will fail with a sqlalchemy.exc.ProgrammingError
        # because the tenants table will not exist yet.
        tenants = []
        result = []
        logger.info("calling the tenants api's get_sites() function...")
        try:
            sites = tenants_api_get_sites()
        except Exception as e:
            logger.info(
                "WARNING - got an exception trying to compute the sites.. "
                "this better be the tenants migration container.")
            return tenants
        logger.info("calling the tenants api's get_tenants() function...")
        try:
            tenants = tenants_api_get_tenants()
        except Exception as e:
            logger.info(
                "WARNING - got an exception trying to compute the tenants.. "
                "this better be the tenants migration container.")
            return tenants
        # for each tenant, look up its corresponding site record and save it on the tenant record--
        for t in tenants:
            # Remove datetime objects --
            t.pop('create_time')
            t.pop('last_update_time')
            # convert the tenants to TapisResult objects, and then append the sites object.
            tn = TapisResult(**t)
            for s in sites:
                if 'primary' in s.keys() and s['primary']:
                    self.primary_site = TapisResult(**s)
                if s['site_id'] == tn.site_id:
                    tn.site = TapisResult(**s)
                    result.append(tn)
                    break
        return result

    def reload_tenants(self):
        self.tenants = self.get_tenants()

    def get_tenant_config(self, tenant_id=None, url=None):
        """
        Return the config for a specific tenant_id from the tenants config based on either a tenant_id or a URL.
        One or the other (but not both) must be passed.
        :param tenant_id: (str) The tenant_id to match.
        :param url: (str) The URL to use to match.
        :return:
        """
        def find_tenant_from_id():
            logger.debug(f"top of find_tenant_from_id for tenant_id: {tenant_id}")
            for tenant in self.tenants:
                try:
                    if tenant.tenant_id == tenant_id:
                        logger.debug(f"found tenant {tenant_id}")
                        return tenant
                except TypeError as e:
                    logger.error(f"caught the type error: {e}")
            logger.info(f"did not find tenant: {tenant_id}. self.tenants: {self.tenants}")
            return None

        def find_tenant_from_url():
            for tenant in self.tenants:
                if tenant.base_url in url:
                    return tenant
                base_url_at_primary_site = self.get_base_url_for_tenant_primary_site(tenant.tenant_id)
                if base_url_at_primary_site in url:
                    return tenant
            return None

        logger.debug(f"top of get_tenant_config; called with tenant_id: {tenant_id}; url: {url}")
        # allow for local development by checking for localhost:500 in the url; note: using 500, NOT 5000 since services
        # might be running on different 500x ports locally, e.g., 5000, 5001, 5002, etc..
        if url and 'http://localhost:500' in url:
            logger.debug("http://localhost:500 in url; resolving tenant id to dev.")
            tenant_id = 'dev'
        if tenant_id:
            logger.debug(f"looking for tenant with tenant_id: {tenant_id}")
            t = find_tenant_from_id()
        elif url:
            logger.debug(f"looking for tenant with url {url}")
            # convert URL from http:// to https://
            if url.startswith('http://'):
                logger.debug("url started with http://; stripping and replacing with https")
                url = url[len('http://'):]
                url = 'https://{}'.format(url)
            logger.debug(f"looking for tenant with URL: {url}")
            t = find_tenant_from_url()
        else:
            raise errors.BaseTapisError("Invalid call to get_tenant_config; either tenant_id or url must be passed.")
        if t:
            return t
        # try one reload and then give up -
        logger.debug(f"did not find tenant; going to reload tenants.")
        self.reload_tenants()
        logger.debug(f"tenants reloaded. Tenants list is now: {tenants.tenants}")
        if tenant_id:
            t = find_tenant_from_id()
        elif url:
            t = find_tenant_from_url()
        if t:
            return t
        raise errors.BaseTapisError("invalid tenant id.")

    def get_base_url_for_service_request(self, tenant_id, service):
        """
        Get the base_url that should be used for a service request based on the tenant_id and the service
        that to which the request is targeting.
        """
        logger.debug(f"top of get_base_url_for_service_request() for tenant_id: {tenant_id} and service: {service}")
        tenant_config = self.get_tenant_config(tenant_id=tenant_id)
        try:
            # get the services hosted by the owning site of the tenant
            site_services = tenant_config.site.services
        except AttributeError:
            logger.info("tenant_config had no site or services; setting site_service to [].")
            site_services = []
        # the SK and token services always use the same site as the site the service is running on --
        if service == 'sk' or service == 'security' or service == 'tokens':
            # if the site_id for the service is the same as the site_id for the request, use the tenant URL:
            if conf.service_site_id == tenant_config.site_id:
                base_url = tenant_config.base_url
                logger.debug(f"service {service} was SK or tokens and tenant's site was the same as the configured site; "
                             f"returning tenant's base_url: {base_url}")
                return base_url
            else:
                # otherwise, we use the primary site (NOTE: if we are here, the configured site_id is different from the
                # tenant's owning site. this only happens when the running service is at the primary site; services at
                # associate sites never handle requests for tenants they do not own.
                base_url = self.get_base_url_for_tenant_primary_site(tenant_id)
                logger.debug(f'base_url for {tenant_id} and {service} was: {base_url}')
                return base_url
        # if the service is hosted by the site, we use the base_url associated with the tenant --
        if service in site_services:
            base_url = tenant_config.base_url
            logger.debug(f"service {service} was hosted at site; returning tenant's base_url: {base_url}")
            return base_url
        # otherwise, we use the primary site
        base_url = self.get_base_url_for_tenant_primary_site(tenant_id)
        logger.debug(f'base_url for {tenant_id} and {service} was: {base_url}')
        return base_url

    def get_base_url_for_tenant_primary_site(self, tenant_id):
        """
        Compute the base_url for a tenant owned by an associate site.
        """
        try:
            base_url_template = self.primary_site.tenant_base_url_template
        except AttributeError:
            raise errors.BaseTapisError(
                f"Could not compute the base_url for tenant {tenant_id} at the primary site."
                f"The primary site was missing the tenant_base_url_template attribute.")
        return base_url_template.replace('${tenant_id}', tenant_id)

    def get_site_admin_tenants_for_service(self):
        """
        Get all tenants for which this service might need to interact with.
        """
        # services running at the primary site must interact with all sites, so this list comprehension
        # just pulls out the tenant's that are admin tenant id's for some site.
        logger.debug("top of get_site_admin_tenants_for_service")
        if self.service_running_at_primary_site:
            admin_tenants = [t.tenant_id for t in self.tenants if t.tenant_id == t.site.site_admin_tenant_id]
        # otherwise, this service is running at an associate site, so it only needs itself and the primary site.
        else:
            admin_tenants = [conf.service_tenant_id]
            for t in self.tenants:
                if t.tenant_id == t.site.site_admin_tenant_id and hasattr(t.site, 'primary') and t.site.primary:
                    admin_tenants.append(t.tenant_id)
        logger.debug(f"site admin tenants for service: {admin_tenants}")
        return admin_tenants

# singleton object with all the tenant data and automatic reload functionality.
# services that override the base Tenants class with a custom class that implements the extend_tenant() method should
# create singletons of that child class and not use this object.
tenants = Tenants()
