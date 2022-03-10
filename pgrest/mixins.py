import requests

from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden

from pgrest.__init__ import t
from tapisservice.logs import get_logger
logger = get_logger(__name__)


class RoleSessionMixin:
    """
    """
    # Override dispatch to decode token and store variables before routing the request.
    def dispatch(self, request, *args, **kwargs):
        try:
            # pull token from the request, and decode it to get the user that is sending in request.
            try:
                # TODO correctly pull token
                agave_token = request.META['HTTP_AUTHORIZATION']
            except KeyError as e:
                logger.warning(f"User not authenticated. Exception: {e}")
                return HttpResponse('Unauthorized', status=401)

            try:
                url = "https://api.tacc.utexas.edu/profiles/v2/me"
                head = {'Authorization': f'Bearer {agave_token}'}
                response = requests.get(url, headers=head)

            except Exception as e:
                msg = f"Unable to retrieve user profile from Agave."
                logger.error(msg)
                return HttpResponseForbidden(msg)

            try:
                username = response.json()['result']['username']
            except KeyError:
                msg = "Unable to parse Agave token response for username."
                logger.error(msg)
                return HttpResponseForbidden(msg)

            # TODO send username to SK, then store username and role in the session
            # roles = t.sk.getUserRoles(user='jstubbs', tenant='tacc', _tapis_set_x_headers_from_service=True)
            # request.session['roles'] = roles
            # request.session['username'] = username

            # Store accounts and active status for benchmarking associates.
        except Exception as e:
            logger.error(f"Bad Request. Exception: {e}")
            return HttpResponseBadRequest(f"There was an error while fulfilling user request. Message: {e}")
