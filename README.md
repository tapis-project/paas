Local Development
=================

Before You Begin:
1. Make sure you are on the TACC VPN.
2. Make sure you have updated the service_password and dbpassword in the config-local.json
3. If running test, make sure you have update the test_token in config-local.json with a v2 password for a user which is also in v3

Build the containers:
--------------------

docker-compose build


Create initial DB structure:
---------------------------
from within the pgrest directory:
1. docker-compose run api python manage.py makemigrations
2. docker-compose run api python manage.py migrate



Start the API container
-----------------------
$ docker-compose up -d api

Add Tenants
-----------
Once the API container is running, exec into the container to add tenants:
1) docker exec -it pgrest-api bash

from within the container:
2) python manage.py shell

from within the python shell:
3) Enter the following:

from pgrest import models

(add tenants)

models.Tenants.objects.create(tenant_name="dev", db_instance_name="local")
models.Tenants.objects.create(tenant_name="admin", db_instance_name="local")

(list tenants)

models.Tenants.objects.all().values()

Manual Testing
--------------
1) get a v2 token from the tacc tenant (api.tacc.utexas.edu) representing a user with admin role:

export tok=<???>

2) Create a table:

curl -H "tapis-v2-token: $tok" -H "Content-type: application/json" -d "@sample.json" localhost:5000/v3/pgrest/manage/tables

3) Add some rows:

curl -H "tapis-v2-token: $tok" -H "Content-type: application/json" -d '{"data": {"col_one": "col 1 value", "col_two": 3, "col_three": 8, "col_four": false}}' localhost:5000/v3/pgrest/data/init

curl -H "tapis-v2-token: $tok" -H "Content-type: application/json" -d '{"data": {"col_one": "another col 1 value", "col_two": 47, "col_three": -9, "col_four": true, "col_five": "hi"}}' localhost:5000/v3/pgrest/data/init

4) List the data:

curl -H "tapis-v2-token: $tok" localhost:5000/v3/pgrest/data/init
   

Run the tests
-------------

1) Add a real token to the b_token variable in pgrest.tests.py. Note: don't push an image build with this token in it (TODO -- this step will change.)

2) Run all the tests: docker-compose run api python manage.py test

3) Run just the createTable test: docker-compose run api python manage.py test pgrest.tests.ResponseTestCase.createTable