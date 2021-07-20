Developer Quick-Start Guide
===========================
PgREST gives a friendly API to connect to a postgres backend. The API currently features tables and views. Tables are created with a table definition and then given rows after the table is initialized. Table creation and deletion are accessible via the `/manage/tables` endpoint. To access these tables and add rows, we use the `/data/{table_id}` endpoint. Views is similar, using `/manage/views` for creation and deletion. The get a view, you can use the `/views/{view_name}` endpoint. A description of tables and view definitions are below.

Once you understand table and view definitions, put it all to work by looking at our quick start Jupyter notebook here: [quick start notebook.](https://github.com/tapis-project/paas/blob/dev/quick-start-notebook.ipynb) This notebook contains all the code neccessary to work with PgREST, modify it to your wishes or copy and paste into whatever scripts you have.

Table Definitions and Features
------------------------------
The /manage/tables endpoints for PgREST expect a json formatted table definition. Each table definition can have the following rules.
 - table_name
   - This is a required rule.
   - The name of the table in question.
 - root_url
   - This is a required rule.
   - The root_url for PgRESTs /data endpoint.
   - Ex: root_url "table25" would be accessible via "http://pgrestURL/data/table25".
 - enums
   - Enum generation is done in table definitions.
   - Provide a dict of enums where the key is enum name and the value is the possible values for the enum.
   - Ex: {"accountrole": ["ADMIN", "USER"]} would create an "accountrole" enum that can have values of "ADMIN" or "USER"
   - Deletion/Updates are not currently supported. Speak to developer if you're interested in a delete/update endpoint.
 - comments
   - Field to allow for better readability of table json. Table comments are saved and outputted on /manage/tables/ endpoints.
 - constraints
   - Specification of Postgres table constraints. Currently only allows multi-column unique constraints
   - Constraints available:
     - unique
       - multi-column unique constraint that requires sets of column values to be unique.
       - Example: "constraints": {"unique": {"unique_col_one_and_two_pair": ["col_one", "col_two"]}}
         - This means that col_one and col_two cannot have pairs of values that are identical.
         - The constraint name can be specified as well
 - columns
   - This is a required rule. 
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
     - comments
       - Field to allow for better readability of table and column json. Column comments are not saved or used. They are for json readability only.
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
     - foreign_key
       - Weather or not this key should reference a key in another table, a "foreign key".
       - Can be true or false.
       - If foreign_key is set to true, columns arguments "reference_table", "reference_column", and "on_delete" must also be set.
         - reference_table
           - Only needed in the case that foreign_key is set to true.
           - Specifies the foreign table that the foreign_key is in.
           - Can be set to the table_name of any table.
         - reference_column
           - Only needed in the case that foreign_key is set to true.
           - Specifies the foreign column that the foreign_key is in.
           - Can be set to the key for any column in the reference_table.
         - on_delete
           - Only needed in the case that foreign_key is set to true.
           - Specifies the deletion strategy when referencing a foreign key.
           - Can be set to "CASCADE" or "SET NULL"
             - "CASCADE" deletes this column if the foreign key's column is deleted.
             - "SET NULL" set this column to null if the foreign key's column is deleted.

### Example of a table definition with many different column types.
```
{
  "table_name": "UserProfile",
  "root_url": "user-profile",
  "delete": false,
  "enums": {"accountrole": ["ADMIN",
                            "USER",
                            "GUEST"]},
  "comments": "This is the user profile table that keeps track of user profiles and data",
  "constraints": {"unique": {"unique_first_name_last_name_pair": ["first_name", "last_name"]}},
  "columns": {
    "user_profile_id": {
      "data_type": "serial",
      "primary_key": true
    },
    "username": {
      "unique": true,
      "data_type": "varchar",
      "char_len": 255
      "comments": "The username used by *** service"
    },
    "role": {
      "data_type": "accountrole"
    },
    "company": {
      "data_type": "varchar",
      "char_len": 255,
      "foreign_key": true,
      "reference_table": "Companys",
      "reference_column": "company_name",
      "on_delete": "CASCADE"
    },
    "employee_id": {
      "data_type": "integer",
      "foreign_key": true,
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

View Creation and Features
------------------------------
Views allow admins to create postgres views to cordone off data from users and give
users exactly what they need. These views allow for permission_rules which cross reference a users roles and if they own all roles the permission_rules state for the view, then they have access to view the view.
The /manage/views endpoints for PgREST expects a json formatted view definition. Each view definition can have the following rules.
 - view_name
   - This is a required rule.
   - The name of the view in question.
 - root_url
   - This is a required rule.
   - The root_url for PgRESTs /views endpoint.
   - Ex: root_url "view25" would be accessible via "http://pgrestURL/views/table25".
 - select_query
   - This is a required rule.
   - Query to select from the table specified with from_table
 - from_table
   - This is a required rule.
   - Table to read data from
 - where_query
   - Optional field that allows you to specify a postgres where clause for the view
 - comments
   - Field to allow for better readability of view json. Table comments are saved and outputted on /manage/views/ endpoints.
 - permission_rules
   - List of roles required to view this view.
   - If nothing is given, view is open to all.

### Example of a view definition.
```
{
  'view_name': 'test_view', 
  'root_url': 'just_a_cool_url',
  'select_query': '*',
  'from_table': 'initial_table_2',
  'where_query': 'col_one >= 90',
  'permission_rules': ['lab_6_admin', 'cii_rep],
  'comments': 'This is a cool test_view to view all of
               initial_table_2. Only users with the
               lab_6_admin and cii_rep role can view this.'
}
```


Local Development and Deployment
================================
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



# Old, Manual Instructions (Use the Makefile, it's better.)

Build the containers:
---------------------
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
