

from django.shortcuts import render
from rest_framework.views import APIView


class TableManagement(APIView):
    """
    GET: Returns information about all of the tables.
    POST: Creates a new table in ManageTables, and then a new table from thee
    json provided by the user.
    """
    def get(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Check for details=true. Decide what a brief description and a detailed description is.
        # Display information for each table based on details variable.
        pass

    def post(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Create row in table with json information.
        # Pull out:
        # 1) table_name
        # 2) column definitions
        # 3) desired endpoints (5 options)

        # With 1 & 2, generate a SQL statement to create a new postgres table.
        # With 3, just store in table and we check the endpoint is allowed

        # Will need to run migration for the new table. Automatically, or just makemigration and then run
        # migrations on a specific action. (Migrations can get tricky fast, here)

        # Also generates a JSON validation spec, store it in the table metadata, and will run it against user input
        # when users try to create a new entry.
        pass


# TODO how are we doing roles? I know we're doing a layered approach. Row pem > table pem > tenant pem.
# Trying to determine how to house these.

# These are endpoints to manage the tables and contains metadata for the tables.
class TableManagementById(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Generates SQL to list details for the specified table.
        # Returns in a JSON format.
        pass

    def put(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Generates SQL to update the structure of a table.
        # Will need to run migration for update - this may be rough.
        # Put have "actions" that will need to be included in the json. Either "add_column" - adds a column,
        # "update_column" - updates a column, "flush" - flush a table, "update_table" - updates the table.
        pass

    def delete(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Generates SQL to drop the specified table.
        # Will need to run migration for delete.
        pass


class TableManagementDump(APIView):
    """
    """
    def post(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Dumps data for the table(s) specified in the json. Results in a json form.
        pass


class TableManagementLoad(APIView):
    """
    """
    def post(self, request, *args, **kwargs):
        # Check role. Must be an admin.
        # Loads data for the table(s) specified in the json. Data must be provided in json form.
        pass


# For dynamic views, all end users will end up here. We will find the corresponding table
# based on the url to get here. We then will formulate a SQL statement to do the need actions.

# Once we figure out the table and row, these are just simple SQL crud operations.
class DynamicView(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # Checks role. Must be allowed to see table.
        # Allows users to view all rows in a table.
        pass

    def post(self, request, *args, **kwargs):
        # Checks role. Must be allowed to add to table.
        # Create a new row in the table.
        pass


class DynamicViewById(APIView):
    """
    """
    def get(self, request, *args, **kwargs):
        # Checks role. Must be allowed to view this row.
        pass

    def put(self, request, *args, **kwargs):
        # Checks role. Must be allowed to update this row.
        pass

    def delete(self, request, *args, **kwargs):
        # Checks role. Must be allowed to delete this row.
        pass
