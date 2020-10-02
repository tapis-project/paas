# docker-compose run api python manage.py

from django.conf.urls import url
from rest_framework.urlpatterns import format_suffix_patterns
from proto import views


urlpatterns = [

    # ---- table management --- #

    # POST
    url('^manage-tables/(?P<manage_table_id>.+)/load)', views.TableManagementLoad.as_view()),
    # POST
    url('^manage-tables/(?P<manage_table_id>.+)/dump)', views.TableManagementDump.as_view()),

    # GET SINGLE, PUT, DELETE
    url('^manage-tables/(?P<manage_table_id>.+)', views.TableManagementById.as_view()),
    # GET ALL, POST
    url('^manage-tables', views.TableManagement.as_view()),

    # ---- dynamic views --- #
    # GET SINGLE, PUT, DELETE
    url('^dv/(?P<root_url>.+)/(?P<primary_id>.+)', views.DynamicViewById.as_view()),
    # GET ALL, POST
    url('^dv/(?P<root_url>.+)', views.DynamicView.as_view()),

]
urlpatterns = format_suffix_patterns(urlpatterns)

