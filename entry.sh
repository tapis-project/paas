#!/bin/bash

# Set up database.
cd /home/tapis/pgrest; python3 -u /home/tapis/pgrest/db_init.py
# Run API
cd /home/tapis; /usr/local/bin/uwsgi --ini paas/uwsgi.ini

while true; do sleep 86400; done
