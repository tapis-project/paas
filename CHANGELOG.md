
# Change Log

All notable changes to this project will be documented in this file.


## 1.0.0 - 2021-09-24

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

- Initial 1.0.0 changelog.
- Tenants are now completely separated with different postgres schemas.
- New role creation endpoints for users in `PGREST_ROLE_ADMIN` role.
- Expanded foreign key usability. Now allow new event type. Also allow new event actions.
- Added `PGREST_USER` role that can only get views that the user's permissions allow for.

### Bug fixes:

- Documentation fixed to point towards ReadTheDocs, which is now up to date with all new table, view, and role definitions.
- Updated Django and DjangoFlaskbase requirements to avoid security issues.
