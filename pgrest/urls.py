# docker-compose run api python manage.py

from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns
from pgrest import views


urlpatterns = [

    # ---- table management --- #

    # POST
    url('^v3/pgrest/manage/tenants', views.CreateTenant.as_view()),

    # GET SINGLE, PUT, DELETE
    url('^v3/pgrest/manage/tables/(?P<manage_table_id>.+)', views.TableManagementById.as_view()),
    # GET ALL, POST, PUT
    url('^v3/pgrest/manage/tables', views.TableManagement.as_view()),

    # ---- dynamic views --- #
    # GET SINGLE, PUT, DELETE
    url('^v3/pgrest/data/(?P<root_url>.+)/(?P<primary_id>.+)', views.DynamicViewById.as_view()),
    # GET ALL, POST, PUT
    url('^v3/pgrest/data/(?P<root_url>.+)', views.DynamicView.as_view()),

]
urlpatterns = format_suffix_patterns(urlpatterns)

