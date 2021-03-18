
Local Development
=================
Before You Begin:
1. Make sure you are on the TACC VPN.
2. Make sure you have updated the service_password and dbpassword in the config-local.json


Build the containers:
--------------------
```
docker-compose build
```


Create initial DB structure:
---------------------------
from within the pgrest directory:
```
docker-compose run api python manage.py makemigrations
docker-compose run api python manage.py migrate
```


Start the API container
-----------------------
```
docker-compose up -d api
```


Add Tenants
-----------
Once the API container is running, exec into the container to add tenants:
```
docker exec -it pgrest-api bash
```
from within the container:
```
python manage.py shell
```
from within the python shell enter the following:
```
from pgrest import models

# add tenants
models.Tenants.objects.create(tenant_name="dev", db_instance_name="local")
models.Tenants.objects.create(tenant_name="admin", db_instance_name="local")

# list tenants
models.Tenants.objects.all().values()
```


Makefile
--------
This repository has a Makefile to make your life easier.  
To build and deploy locally:  
```
make local-deploy
```

To take down current containers and postgres volume:  
```
make down-volumes
```

To run the tests:  
```
make test
```

It's also useful to bring it all together to rebuild and test all at once:  
```
make down-volumes local-deploy test
```


Manual Testing
--------------
Get a v2 token from the tacc tenant (api.tacc.utexas.edu) representing a user with admin role:
```
export tok=<???>
```
Create a table:
```
curl -H "tapis-v2-token: $tok" -H "Content-type: application/json" -d "@sample.json" localhost:5000/v3/pgrest/manage/tables
```
Add some rows:
```
curl -H "tapis-v2-token: $tok" -H "Content-type: application/json" -d '{"data": {"col_one": "col 1 value", "col_two": 3, "col_three": 8, "col_four": false}}' localhost:5000/v3/pgrest/data/init

curl -H "tapis-v2-token: $tok" -H "Content-type: application/json" -d '{"data": {"col_one": "another col 1 value", "col_two": 47, "col_three": -9, "col_four": true, "col_five": "hi"}}' localhost:5000/v3/pgrest/data/init
```
List the data:
```
curl -H "tapis-v2-token: $tok" localhost:5000/v3/pgrest/data/init
```


Run the tests
-------------

1) Add a real token to the test_token variable in config-local.json.

2) Run all the tests: `docker-compose run api python manage.py test`

3) Run just the createTable test: `docker-compose run api python manage.py test pgrest.tests.ResponseTestCase.createTable`
