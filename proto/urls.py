# docker-compose run api python manage.py

from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns
from proto import views


urlpatterns = [

    # ---- table management --- #

    # POST
    url('^paas/manage-tables/load/(?P<manage_table_id>.+)', views.TableManagementLoad.as_view()),
    # POST
    url('^paas/manage-tables/dump/(?P<manage_table_id>.+)', views.TableManagementDump.as_view()),

    # GET SINGLE, PUT, DELETE
    url('^paas/manage-tables/(?P<manage_table_id>.+)', views.TableManagementById.as_view()),
    # GET ALL, POST
    url('^paas/manage-tables', views.TableManagement.as_view()),

    # ---- dynamic views --- #
    # GET SINGLE, PUT, DELETE
    url('^paas/(?P<root_url>.+)/(?P<primary_id>.+)', views.DynamicViewById.as_view()),
    # GET ALL, POST
    url('^paas/(?P<root_url>.+)', views.DynamicView.as_view()),

]
urlpatterns = format_suffix_patterns(urlpatterns)

