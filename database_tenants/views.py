from django.shortcuts import render
from rest_framework.views import APIView
from django.http import HttpResponse, HttpResponseBadRequest

from database_tenants.models import Tenants
from pgrest.utils import make_error, make_success
from pgrest.pycommon.logs import get_logger

logger = get_logger(__name__)


# Create tenants here.
class CreateTenant(APIView):
    def post(self, request, *args, **kwargs):
        logger.debug("top of post /manage/tenants")
        try:
            schema_name = request.data['schema_name']
            db_instance = request.data['db_instance']
        except KeyError as e:
            msg = f"\'{e.args}\' is required when creating new row in a table."
            logger.warning(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            tenant = Tenants(schema_name = schema_name,
                             tenant_name = schema_name,
                             db_instance_name = db_instance)
        except Exception as e:
            msg = f"Unable to create new tenant for Tenants table"
            logger.warning(msg + f" e: {e}")
            return HttpResponseBadRequest(make_error(msg=msg))

        try:
            tenant.save()
        except Exception as e:
            msg = f"Failed to create new tenant {schema_name} in db_instance {db_instance}. {e}"
            logger.error(msg)
            return HttpResponseBadRequest(make_error(msg=msg))

        return HttpResponse(make_success(msg=f"Tenant '{schema_name}' created successfully."), content_type='application/json')
