
Local Development
=================
Before You Begin:
1. Make sure you are on the TACC VPN.
2. Make sure you have updated ``service_password`` in the config-local.json with the PgREST
service password from the Tapis v3 Kuberenetes development environment. 
   
(If you don't know what these mean, [ask a friend](https://tacc-cloud.slack.com).) 



Makefile
--------
This repository has a Makefile to make your life easier.  
To build and deploy locally:  
```
make local-deploy
```
The first time you start up the containers on a new machine, or any time you remove the
postrges volume (e.g., with "make down"), you need to add tenants to the Tenants configuration
table. Do that with the following command, once the API container and database are running:
```
make add-tenants
```

Speaking of whcih, to take down current containers and postgres volume:  
```
make down-volumes
```

The repository has a set of tests, but they require a valid Tapis v2 OAuth token for a user
with the admin role. You must populate the ``test_token`` attribute in the config-local.json file
with such a token in order to run the tests.

Once the token is in place, to run the tests:  
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



# Old, Manual Instructions (You Probably Want to Use the Makefile)

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

Run the tests
-------------

1) Add a real token to the test_token variable in config-local.json.

2) Run all the tests: `docker-compose run api python manage.py test`

3) Run just the createTable test: `docker-compose run api python manage.py test pgrest.tests.ResponseTestCase.createTable`

