
# Change Log

All notable changes to this project will be documented in this file.

## 1.3.0 - 2023-03-09
### Breaking Changes:
- No Change.

### New features:
- No Change.

### Bug fixes:
- No Change.

## 1.2.3 - 2023-02-09
### Breaking Changes:
- No Change.

### New features:
- No Change.

### Bug fixes:
- Changed search and order parsing so they raise Exceptions, previously they did not and they would get muffled, errors are now converyed to user verbosely.
- Fixed syntax error in one test.


## 1.2.2 - 2023-02-03
### Breaking Changes:
- No Change.

### New features:
- Added materialized views, accessible by using `materialized_view_raw_sql` when creating views with the normal view endpoints.
- Added refresh materialized views endpoint. `/v3/pgrest/manage/views/<view_id>/refresh`, will complain if the view wasn't created with `materialized_view_raw_sql`.
- Added healthcheck

### Bug fixes:
- Previously a row in the manage_views table could not actually have a view in the database so when deleting it was impossible to get rid of the dangling manage_views row entry for the view. That is fixed as the query won't throw an error when view does not exist in database (applies for materialized views as well)


## 1.2.1 - 2023-01-23
### Breaking Changes:
- No Change.

### New features:
- DB Migrations at startup now start from api container during main exec. No longer a need for init container. Better stdout prints.
- entry.sh file takes care of migration only happening once per instance of API (even if there are 6 workers)
    - Added entry.sh, added db_init.py, updated Dockerfile, Makefile, Docker-Compose

### Bug fixes:
- No Change.

## 1.2.0 - 2022-06-03
### Breaking Changes:
- No change.

### New features:
- Bumping tag for Tapis 1.2.0 release.

### Bug fixes:
- No Change.


## 1.1.0 - 2022-01-07
### Breaking Changes:
- No Change.

### New features:
- Full 1.1.0 release of what was in 1.0.3.
- Replaced pycommon with tapisservice and tapipy (w/plugins). Now based off flaskbase-plugins image.

### Bug fixes:
- No Change.

## 1.0.3 - 2021-12-17 - (1.1.0 pre-release)
### Breaking Changes:
- Where parameters for tables and views are changed to match search spec.
    - No longer `where_col_one=val` format. Now `col_one.eq=val`.
- Changed how serial data type works. Users can now specify `serial_start` and `serial_increment` in table definition to modify the type.
- Changed how puts to `manage/table/table_id` work. Old methods are gone.
- Views and tables now default to having no return limit (previously row limit of 10).

### New features:
- Added support for `raw_sql` input when creating table views. This allows admins only to have greater view customization.
- Added support for bulk row posts to `data/table_url`. Keeps single dictionary inputs, but also allows lists of dictionaries (rows) as input.
- Where parameters for tables and views are changed to match search spec.
    - No longer `where_col_one=val` format. Now `col_one.eq=val`.
    - Added support for `.eq`, `.neq`, `.like`, `.nlike`, `.gt`, `.gte`, `.lt`, `.lte`, `.between`, `.nbetween`, `.in`, and `.nin`.
- Changed how serial data type works. Users can now specify `serial_start` and `serial_increment` in table definition to modify the type.
    - `serial_start` and `serial_increment` both default to 1.
    - Now using a Postgres 10+ identity data type to make the sequence possible.
- Added lots of operations to puts `manage/table/table_id` work. Meaning updates to tables are possible.
    - Check docs, new operations are `root_url`, `table_name`, `comments`, `endpoints`, `column_type`, `add_column`, `drop_column`, `drop_default`, and `set_default`.
    - Meaning no more having to delete and recreate tables.
- `data_utils` are now more universal. `do_transaction` and the like are functionalized for ease-of-use/updates.
- Rearranged dockerfile for faster compilations. (Code after package initialization)
- Service now grants all neccessary roles in enviroment, across tenants, at startup.
- Updated PgREST spec with newest features.
- New tests for all features.

### Bug fixes:
- Added better error messages for unique constraint names that collide during table creation.
- Fixed view names and table names colliding in a tenant.


## 1.0.2 - 2021-09-24
### Breaking Changes:
- Spec operationIds changed for readability. The following are the changes, "oldID: newID":
    - get_table: get_manage_table
    - list_in_collection: get_table
    - create_in_collection: add_table_row
    - update_multiple_in_collection: update_table_rows
    - get_in_collection: get_table_row
    - update_in_collection: update_table_row
    - delete_in_collection: delete_table_row
- Changed foreign key table definition variables. Now requires `on_event` and `event_action` rather than setting `on_delete` to event action. This allows for `ON UPDATE` event along with `ON DELETE` event.

### New features:
- Tenants are now completely separated with different postgres schemas.
- New role creation endpoints for users in `PGREST_ROLE_ADMIN` role.
- Expanded foreign key usability. Now allow new event type. Also allow new event actions.
- Added `PGREST_USER` role that can only get views that the user's permissions allow for.

### Bug fixes:
- Documentation fixed to point towards ReadTheDocs, which is now up to date with all new table, view, and role definitions.
- Updated Django and DjangoFlaskbase requirements to avoid security issues.
- Updated dependencies to pass Github Dependabot alerts.
- Updated PgREST spec, previously out-of-date, now organized and verbose.


## 1.0.1 - 2021-09-24
### Breaking Changes:
- ManageViews/ManageTables/ManageTableTransitions are now stored in each tenant, no longer service wide
- New folder containing tenant migration, `database_tenants`, create tenants func now stored there.

### New features:
- PgREST tenant seperation. New migrations, now using Django Tenants back-end. Switched Django Tenants to take Tapis v3 tenant_id.
- Added new role endpoints to allow for `PGREST_ROLE_ADMINS` above to create and manage roles for users.

### Bug fixes:
- Previously table_ids were serialized service wide, this meant that users could notice that there were more tables than the table view showed. Calling these tables resulted in an error, but with tenant seperation it is no longer an issue.


## 1.0.0 - 2021-09-24
### Breaking Changes:
- No Change.

### New features:
- Initial 1.0.0 changelog.

### Bug fixes:
- No Change.
