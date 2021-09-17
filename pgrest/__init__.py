from pgrest.pycommon.config import conf

# the first import of the tapipy client is somewhat expensive (a few seconds), so we do it here at service start up
# to prevent paying the cost later..
from pgrest.pycommon.auth import t
