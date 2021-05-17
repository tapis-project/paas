
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



Table Definitions and Features
------------------------------
The /manage endpoints for PgREST expect a json formatted table definition. Each table definition requires the following.
 - table_name
   - The name of the table in question.
 - root_url
   - The root_url for PgRESTs /data endpoint.
   - Ex: root_url "table25" would be accessible via "http://pgrestURL/data/table25".
 - enums
   - Enum generation is done in table definitions.
   - Provide a dict of enums where the key is enum name and the value is the possible values for the enum.
   - Ex: {"accountrole": ["ADMIN", "USER"]} would create an "accountrole" enum that can have values of "ADMIN" or "USER"
   - Deletion/Updates are not currently supported. Speak to developer if you're interested in a delete/update endpoint.
 - columns
   - Column definitions in the form of a dict. Dict key would be column, value would be column definition.
   - Ex: {"username": {"unique": true, "data_type": "varchar", "char_len": 255}
   - Columns arguments are as follows.
     - data_type
       - This field is required.
       - Specifies the data type for values in this column.
       - Can be varchar, datetime, {enumName}, text, timestamp, serial, varchar[], boolean, integer, integer[].
         - Note: varchar requires the char_len column definition.
         - Note: Setting a timestamp data_type column to default to "UPDATETIME" or "CREATETIME" has special properties.
           - "CREATETIME" sets the field to the UTC time at creation. It is then not changed later.
           - "UPDATETIME" sets the filed to the UTC time at creation. It is updated to the update time when it is updated.
     - char_len
       - Additional argument for varchar data_types. Required to set max value size.
       - Can be any value from 1 to 255.
     - unique
       - Determines whether or not each value in this column is unique.
       - Can be true or false.
     - null
       - States whether or not a value can be "null".
       - Can be true or false.
     - default
       - Sets default value for column to fallback on if no value is given.
       - Must follow the data_type for the column.
       - Note: Setting a timestamp data_type column to default to "UPDATETIME" or "CREATETIME" has special properties.
          - "CREATETIME" sets the field to the UTC time at creation. It is then not changed later.
          - "UPDATETIME" sets the filed to the UTC time at creation. It is updated to the update time when it is updated.
     - primary_key
       - Specifies primary_key for the table.
       - This can only be used for one column in the table.
       - This primary_key column will be the value users can use to *get* a row in the table.
       - If this is not specified in a table, primary_key defaults to "{table_name}_id".
         - Note that this default cannot be modified and is of data_type=serial.
     - FK
       - Weather or not this key should reference a key in another table, a "foreign key".
       - Can be true or false.
       - If FK is set to true, columns arguments "reference_table", "reference_column", and "on_delete" must also be set.
         - reference_table
           - Only needed in the case that FK is set to true.
           - Specifies the foreign table that the foreign_key is in.
           - Can be set to the table_name of any table.
         - reference_column
           - Only needed in the case that FK is set to true.
           - Specifies the foreign column that the foreign_key is in.
           - Can be set to the key for any column in the reference_table.
         - on_delete
           - Only needed in the case that FK is set to true.
           - Specifies the deletion strategy when referencing a foreign key.
           - Can be set to "CASCADE" or "SET NULL"
             - "CASCADE" deletes this column if the foreign key's column is deleted.
             - "SET NULL" set this column to null if the foreign key's column is deleted.

Example of a table definition with many different column types.
```
{
  "table_name": "UserProfile",
  "root_url": "user-profile",
  "delete": false,
  "enums": {"accountrole": ["ADMIN",
                            "USER",
                            "GUEST"]},
  "columns": {
    "user_profile_id": {
      "data_type": "serial",
      "primary_key": true
    },
    "username": {
      "unique": true,
      "data_type": "varchar",
      "char_len": 255
    },
    "role": {
      "data_type": "accountrole"
    },
    "company": {
      "data_type": "varchar",
      "char_len": 255,
      "FK": true,
      "reference_table": "Companys",
      "reference_column": "company_name",
      "on_delete": "CASCADE"
    },
    "employee_id": {
      "data_type": "integer",
      "FK": true,
      "reference_table": "Employees",
      "reference_column": "employee_id",
      "on_delete": "CASCADE"
    }
    "first_name": {
      "null": true,
      "data_type": "varchar",
      "char_len": 255
    },
    "last_name": { 
      "null": true,
      "data_type": "varchar",
      "char_len": 255
    },
    "created_at": {
      "data_type": "timestamp",
      "default": "CREATETIME"
    },
    "last_updated_at": {
      "data_type": "timestamp",
      "default": "UPDATETIME"
    }
  }
}
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

