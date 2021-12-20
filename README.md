PgREST - Postgres as a RESTful API
========================================
The PgREST service provides an friendly HTTP-based API to a managed Postgres database. As with the other Tapis v3 service, PgREST utilizes a REST architecture. The API currently features tables, views, and roles. Tables, views, and roles are created with PgREST endpoints that are described in detail in our documentation.
  
**PgREST Documentation:** https://tapis.readthedocs.io/en/latest/technical/pgrest.html  
**PgREST Automated Live-Docs:** https://tapis-project.github.io/live-docs/#tag/user

Once you understand PgREST, put it all to work by looking at our quick-start Jupyter notebook. This notebook contains all the code neccessary to work with PgREST, modify it to your wishes or copy and paste code snippets into whatever scripts you have.

**Quick-Start Jupyter Notebook:** https://github.com/tapis-project/paas/blob/dev/notebook-quick-start.ipynb


Local Development
=================
Before You Begin:
1. Make sure you are on the TACC VPN.
2. Make sure you have updated ``service_password`` in the config-local.json with the PgREST
service password from the Tapis v3 Kuberenetes development environment. 
   
(If you don't know what these mean, [ask a friend](https://tacc-cloud.slack.com).) 


Makefile
--------
This repository has a Makefile to make your life easier. It creates needed variables and has
targets for any neccessary building or deployment steps.

To build and deploy locally:  
```
make local-deploy
```
The first time you start up the containers on a new machine, or any time you remove the
postgres volume (e.g., with `make down`), you need to add tenants to the Tenants configuration
table. Do that with the following command, once the API container and database are running:
```
make add-tenants
```

Speaking of which, to take down current containers and postgres volume:  
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
