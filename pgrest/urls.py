# docker-compose run api python manage.py

from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns
from pgrest import views
from database_tenants import views as tenant_views


urlpatterns = [

    # ---- table management --- #
    # Tenants: POST
    url('^v3/pgrest/manage/tenants', tenant_views.CreateTenant.as_view()),

    # Tables: GET SINGLE, PUT, DELETE
    url('^v3/pgrest/manage/tables/(?P<manage_table_id>.+)', views.TableManagementById.as_view()),
    # Tables: GET ALL, POST, PUT
    url('^v3/pgrest/manage/tables', views.TableManagement.as_view()),

    # Materialized View Refresh: GET
    url('^v3/pgrest/manage/views/(?P<manage_view_id>.+)/refresh', views.ViewsRefreshResource.as_view()),
    # (Materialized) Views: GET SINGLE, DELETE
    url('^v3/pgrest/manage/views/(?P<manage_view_id>.+)', views.ViewManagementById.as_view()),
    # (Materialized) Views: GET ALL, POST
    url('^v3/pgrest/manage/views', views.ViewManagement.as_view()),

    # Roles: GET SINGLE, DELETE
    url('^v3/pgrest/manage/roles/(?P<role_name>.+)', views.RoleManagementByName.as_view()),
    # Roles: GET ALL, POST
    url('^v3/pgrest/manage/roles', views.RoleManagement.as_view()),


    # ---- dynamic views --- #
    # Tables: GET SINGLE, PUT, DELETE
    url('^v3/pgrest/data/(?P<root_url>.+)/(?P<primary_id>.+)', views.DynamicViewById.as_view()),
    # Tables: GET ALL, POST, PUT
    url('^v3/pgrest/data/(?P<root_url>.+)', views.DynamicView.as_view()),

    # (Materialized) Views: GET ALL
    url('^v3/pgrest/views/(?P<root_url>.+)', views.ViewsResource.as_view()),

    # Health Check
    url('^v3/pgrest/healthcheck', views.HealthCheck.as_view()),

]
urlpatterns = format_suffix_patterns(urlpatterns)