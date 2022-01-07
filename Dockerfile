# Core image for PgREST project - Includes files for testing.
# Image: pgrest-api/core

FROM tapis/flaskbase-plugins:latest

ENV PYTHONUNBUFFERED 1
ENV DJANGO_ENV dev
ENV DOCKER_CONTAINER 1
ENV TAPIS_API pgrest-api

## FILE INITIALIZATION
COPY ./requirements.txt /home/tapis/requirements.txt

# Installs
RUN pip install -r /home/tapis/requirements.txt

## CODE
COPY configschema.json /home/tapis/configschema.json
COPY ./manage.py /home/tapis/manage.py
COPY pgrest /home/tapis/service/pgrest
COPY pgrest /home/tapis/pgrest
COPY database_tenants /home/tapis/service/database_tenants
COPY database_tenants /home/tapis/database_tenants
COPY paas /home/tapis/service/paas
COPY paas /home/tapis/paas
RUN mkdir /home/tapis/databases
RUN touch /home/tapis/pgrest.log


WORKDIR /home/tapis/

#USER tapis

CMD ["/usr/local/bin/uwsgi", "--ini", "paas/uwsgi.ini", ]

EXPOSE 5000