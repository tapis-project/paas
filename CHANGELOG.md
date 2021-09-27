
# Change Log

All notable changes to this project will be documented in this file.


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
