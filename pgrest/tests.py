# docker-compose run api python manage.py test
# docker-compose run api python manage.py makemigrations
import json

from django.test import TestCase
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from pgrest import test_data
from pgrest.pycommon.config import conf

# SET YOUR HEADERS! Either way, user needs ADMIN role in SK.
# V3
#auth_headers = {'HTTP_X_TAPIS_TOKEN': conf.test_token}
# V2
auth_headers = {'HTTP_TAPIS_V2_TOKEN': conf.test_token}

# TESTS TO WRITE
#
# TO DO
# - Raw SQL endpoint
# DONE
# - Alter tables tests
# - Bulk row done by other tests.
# - Serial data type
# - Where support (table and view)


class ResponseTestCase(TenantTestCase):

    init_resp_1 = {}
    init_resp_2 = {}
    init_resp_3 = {}
    init_resp_4 = {}
    init_resp_5 = {}

    @classmethod
    def setup_tenant(cls, tenant):
        """
        Add any additional setting to the tenant before it get saved. This is required if you have
        required fields.
        """
        tenant.schema_name = "dev"
        tenant.tenant_name = "dev"
        tenant.db_instance_name = "default"
        return tenant

    @classmethod
    def get_test_schema_name(cls):
        return 'dev'

    def createTable(self):
        init_resp_1 = self.client.post('/v3/pgrest/manage/tables',
                                       data=json.dumps(test_data.init_table_1),
                                       content_type='application/json',
                                       **auth_headers)
        self.init_resp_1 = init_resp_1.json()

        init_resp_2 = self.client.post('/v3/pgrest/manage/tables',
                                       data=json.dumps(test_data.init_table_2),
                                       content_type='application/json',
                                       **auth_headers)
        self.init_resp_2 = init_resp_2.json()

        init_resp_3 = self.client.post('/v3/pgrest/manage/tables',
                                       data=json.dumps(test_data.init_table_3),
                                       content_type='application/json',
                                       **auth_headers)
        self.init_resp_3 = init_resp_3.json()

        init_resp_4 = self.client.post('/v3/pgrest/manage/tables',
                                       data=json.dumps(test_data.init_table_4),
                                       content_type='application/json',
                                       **auth_headers)
        self.init_resp_4 = init_resp_4.json()

        init_resp_5 = self.client.post('/v3/pgrest/manage/tables',
                                       data=json.dumps(test_data.init_table_5),
                                       content_type='application/json',
                                       **auth_headers)
        self.init_resp_5 = init_resp_5.json()


    def setUp(self):
        super().setUp()
        self.c = TenantClient(self.tenant)
        self.createTable()

    def tearDown(self):
        self.client.delete(f'/v3/pgrest/manage/tables/{self.init_resp_1["result"]["table_id"]}', **auth_headers)
        self.client.delete(f'/v3/pgrest/manage/tables/{self.init_resp_2["result"]["table_id"]}', **auth_headers)
        self.client.delete(f'/v3/pgrest/manage/tables/{self.init_resp_3["result"]["table_id"]}', **auth_headers)
        self.client.delete(f'/v3/pgrest/manage/tables/{self.init_resp_4["result"]["table_id"]}', **auth_headers)
        self.client.delete(f'/v3/pgrest/manage/tables/{self.init_resp_5["result"]["table_id"]}', **auth_headers)

    #######################
    # MANAGE TABLES TESTS #
    #######################

    # ---- LIST ALL TABLES ---- #
    def test_list_tables(self):
        response = self.client.get('/v3/pgrest/manage/tables', **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].lower(), "application/json")

    def test_list_tables_details(self):
        response = self.client.get('/v3/pgrest/manage/tables?details=true', **auth_headers)
        self.assertEqual(response["Content-Type"].lower(), "application/json")
        try:
            response.json()["result"][0]["columns"]
        except KeyError:
            self.fail("Details did not return columns")
        self.assertEqual(response.status_code, 200)

    def test_list_tables_for_correct_tenant_only(self):
        response = self.client.get('/v3/pgrest/manage/tables', **auth_headers)
        self.assertEqual(response["Content-Type"].lower(), "application/json")
        for resp in response.json()["result"]:
            self.assertIn(resp["tenant"], ["dev", "admin"])

    # ---- CREATE TABLES ---- #
    def test_simple_create(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_1),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_create_table_with_serial_data_type(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_7),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_create_table_with_serial_data_type_complex(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_11),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        table_id = response.json()["result"]["table_id"]
        root_url = response.json()['result']['root_url']

        # Add multiple new rows to check on status of col_two serial data type.
        data = [{"col_one": "hello", "col_three": 90, "col_four": False, "col_five": "hehe"}]

        # Check serial_start is 511
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'][0]['col_two'], 511)

        # Check serial_increment works and changes val to 1500 (511 + 989)
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'][0]['col_two'], 1500)

        self.client.delete(f'/v3/pgrest/manage/tables/{table_id}', **auth_headers)

    def test_create_table_with_serial_data_type_with_null_fails(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_8),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_existing_root_url(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_2),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_existing_table(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_3),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_no_columns(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_4),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_char_len_required_on_varchar(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_5),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_create_with_foreign_key(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_9),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_create_with_foreign_key_no_nulls_with_delete_set_null_400(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_10),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

    # ---- DELETE TABLES ---- #
    def test_delete_existing_table(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_6),
                                    content_type='application/json',
                                    **auth_headers)
        del_resp = self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}',
                                      **auth_headers)
        self.assertEqual(del_resp.status_code, 200)

    def test_delete_nonexistent_table(self):
        response = self.client.delete('/v3/pgrest/manage/tables/100000000000007473774', **auth_headers)
        self.assertEqual(response.status_code, 404)

    # ---- LIST SINGLE TABLE ---- #
    def test_list_single_tables(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_6),
                                    content_type='application/json',
                                    **auth_headers)

        response = self.client.get(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].lower(), "application/json")

        del_resp = self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}',
                                      **auth_headers)

    def test_list_single_tables_detail(self):
        response = self.client.post('/v3/pgrest/manage/tables',
                                    data=json.dumps(test_data.create_table_6),
                                    content_type='application/json',
                                    **auth_headers)
        table_id = response.json()["result"]["table_id"]
        get_response = self.client.get(f'/v3/pgrest/manage/tables/{table_id}?details=true', **auth_headers)
        self.assertEqual(get_response["Content-Type"].lower(), "application/json")
        try:
            get_response.json()["result"]["columns"]
        except KeyError:
            self.fail("Details did not return columns")
        self.assertEqual(get_response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{get_response.json()["result"]["table_id"]}', **auth_headers)

    def test_list_nonexistent_table(self):
        response = self.client.get('/v3/pgrest/manage/tables/5999999993999999', **auth_headers)
        self.assertEqual(response.status_code, 404)

    # ---- UPDATE TABLE ---- #

    #######################
    # DYNAMIC VIEWS TESTS #
    #######################

    # ---- LIST ALL ROWS ---- #
    def test_list_table_contents(self):
        root_url = self.init_resp_1["result"]["root_url"]
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(response.status_code, 200)

    def test_list_nonexistent_table_contents(self):
        response = self.client.get(f'/v3/pgrest/data/nope', **auth_headers)
        self.assertEqual(response.status_code, 404)

    # ---- CREATE ROW ---- #
    def test_create_object_in_table(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)

    def test_create_object_in_table_nulls_no_needed(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)

    def test_create_object_in_table_without_required_field_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_create_object_in_table_wrong_data_type_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_one": 50, "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_create_object_in_nonexistent_table_400(self):
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/nah',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    # ---- UPDATE ROW ---- #
    def test_update_row(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    **auth_headers,
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, update
        data = {"col_two": 30}
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.put(f'/v3/pgrest/data/{root_url}/{row_id}',
                                   **auth_headers,
                                   data=json.dumps({"data": data}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_update_row_wrong_data_type_400(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, update
        data = {"col_two": "haha"}
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.put(f'/v3/pgrest/data/{root_url}/{row_id}',
                                   **auth_headers,
                                   data=json.dumps({"data": data}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_update_row_nonexistent_row_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_two": 100}
        response = self.client.put(f'/v3/pgrest/data/{root_url}/898989',
                                   **auth_headers,
                                   data=json.dumps({"data": data}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_update_row_nonexistent_column_400(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]

        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, update
        data = {"col_where": 30}
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.put(f'/v3/pgrest/data/{root_url}/{row_id}',
                                   **auth_headers,
                                   data=json.dumps({"data": data}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 400)

    # ---- DELETE ROW ---- #
    def test_delete_row(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]

        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    **auth_headers,
                                    data=json.dumps({"data": data}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, delete
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.delete(f'/v3/pgrest/data/{root_url}/{row_id}', **auth_headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.delete(f'/v3/pgrest/data/{root_url}/{row_id}', **auth_headers)
        self.assertEqual(response.status_code, 400)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 0)

    def test_delete_nonexistent_row_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        response = self.client.delete(f'/v3/pgrest/data/{root_url}/89898989', **auth_headers)
        self.assertEqual(response.status_code, 400)

    # ---- LIST SINGLE ROW ---- #
    # first, we need to create row
    def test_list_single_row(self):
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, list the row
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.get(f'/v3/pgrest/data/{root_url}/{row_id}', **auth_headers)
        self.assertEqual(response.status_code, 200)

    def test_list_nonexistent_row_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        response = self.client.get(f'/v3/pgrest/data/{root_url}/9090290392032', **auth_headers)
        self.assertEqual(response.status_code, 400)

    # ---- FILTER ROWS ON LISTING ---- #
    # first, we need to create rows
    def test_filter_by_one_column(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?col_one.eq=hi', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

    def test_filter_by_two_columns(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?col_one.eq=goodbye&col_three.eq=95', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

    def test_filter_by_two_columns_one_boolean(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 5)
        response = self.client.get(f'/v3/pgrest/data/{root_url}?col_one.eq=goodbye&col_four.eq=True', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

    def test_order_by(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 80,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 94,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 60,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 80)
        self.assertEqual(response.json()["result"][4]["col_three"], 60)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?order=col_three', **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 60)
        self.assertEqual(response.json()["result"][4]["col_three"], 95)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?order=col_three,DESC', **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 95)
        self.assertEqual(response.json()["result"][4]["col_three"], 60)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?order=col_three,ASC', **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 60)
        self.assertEqual(response.json()["result"][4]["col_three"], 95)

    def test_order_by_with_filters(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 80,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 94,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 60,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?col_one.eq=goodbye', **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 95)
        self.assertEqual(response.json()["result"][1]["col_three"], 94)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?col_one.eq=goodbye&order=col_three,ASC', **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 94)
        self.assertEqual(response.json()["result"][1]["col_three"], 95)

    # ---- UPDATING MULTIPLE ROWS ---- #
    def test_update_entire_table(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        # now, update
        data = {"col_five": "omg"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}',
                                   **auth_headers,
                                   data=json.dumps({"data": data}),
                                   content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            self.assertEqual(resp["col_five"], "omg")

    def test_update_nonexistent_rows_in_table(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        # now, update
        data = {"col_where": "omg"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}',
                                   data=json.dumps({"data": data}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_update_rows_with_wrong_data_type_400(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        # now, update
        data = {"col_five": 40}
        response = self.client.put(f'/v3/pgrest/data/{root_url}',
                                   data=json.dumps({"data": data}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 400)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            self.assertEqual(resp["col_five"], "hehe")

    def test_update_rows_with_filter_string(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "haha"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "haha"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        # now, update
        where_clause = {"col_five": {"operator": "eq", "value": "haha"}}
        data = {"col_one": "lata"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}',
                                   data=json.dumps({
                                       "data": data,
                                       "where": where_clause
                                   }),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            if resp["col_five"] == 'hehe':
                self.assertNotEqual(resp["col_one"], "lata")
            else:
                self.assertEqual(resp["col_one"], "lata")

    def test_update_rows_with_filter_int(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "haha"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 96,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "haha"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        where_clause = {"col_three": {"operator": "gte", "value": 95}}
        data = {"col_one": "lata"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}',
                                   data=json.dumps({
                                       "data": data,
                                       "where": where_clause
                                   }),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            if resp["col_three"] < 95:
                self.assertNotEqual(resp["col_one"], "lata")
            else:
                self.assertEqual(resp["col_one"], "lata")

    def test_update_rows_with_filter_incorrect_data_type(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "haha"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 96,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "haha"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        where_clause = {"col_three": {"operator": "gte", "value": 95}}

        data = {"col_one": 90}
        response = self.client.put(f'/v3/pgrest/data/{root_url}',
                                   data=json.dumps({
                                       "data": data,
                                       "where": where_clause
                                   }),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 400)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            self.assertNotEqual(resp["col_one"], 90)

    ###############
    # ENUMS TESTS #
    ###############

    # ---- CHECK ROW CREATION ---- #
    def test_create_complex_row_with_enum(self):
        # Note this also tests comments and unique constraints.
        root_url = self.init_resp_2["result"]["root_url"]
        data = {"col_one": "hello", "col_two": "cat", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)

    def test_create_row_with_enum_error(self):
        # We should get a 400 from this as enum's won't match up.
        root_url = self.init_resp_2["result"]["root_url"]
        data = {"col_one": "hello", "col_two": "NotInEnum", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

    #####################
    # ALTER TABLE TESTS #
    #####################
    # Change root_url
    def test_change_root_url(self):
        table_id = self.init_resp_4["result"]["table_id"]
        new_url = "alter_root_url_test"
        # Alter root_url
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"root_url": new_url}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Check that root_url was changed.
        response = self.client.get(f'/v3/pgrest/manage/tables/{table_id}', **auth_headers)
        self.assertEqual(response.json()['result']['root_url'], new_url)

        # Test new root_url works.
        data = {"col_one": "hello", "col_two": 323, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{new_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

    # Change table_name
    def test_change_table_name(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        new_table_name = "alter_table_name_table_name"
        # Alter table_name
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"table_name": new_table_name}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Check that table_name was changed.
        response = self.client.get(f'/v3/pgrest/manage/tables/{table_id}', **auth_headers)
        self.assertEqual(response.json()['result']['table_name'], new_table_name)

        # Test table still works.
        data = {"col_one": "hello", "col_two": "cat", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

    # Add comments
    def test_add_comments(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        new_comment = "This is my brand new comment for my table."
        # Add comments
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"comments": new_comment}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Check that comments was changed.
        response = self.client.get(f'/v3/pgrest/manage/tables/{table_id}', **auth_headers)
        self.assertEqual(response.json()['result']['comments'], new_comment)

        # Test table still works.
        data = {"col_one": "hello", "col_two": "cat", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

    # Change endpoints
    def test_change_endpoints(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        # Set endpoints to NONE
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"endpoints": ["NONE"]}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Check that endpoints was changed.
        response = self.client.get(f'/v3/pgrest/manage/tables/{table_id}', **auth_headers)
        self.assertEqual(response.json()['result']['endpoints'], [])

        # Test table no longer works.
        data = {"col_one": "hello", "col_two": "cat", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

        # Set endpoints to ALL
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"endpoints": ["ALL"]}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Test table works again.
        data = {"col_one": "hello", "col_two": "cat", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

    # Change column_type
    def test_change_column_type(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        # Change col_two from type TEXT to VARCHAR
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"column_type": "col_two, varchar"}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Test table still works.
        data = {"col_one": "hello", "col_two": "cat", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

    # Add column
    def test_add_column(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        # Add col_six
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"add_column": {
                                       "col_six": {
                                           "data_type": "integer"
                                       }
                                   }}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Test table still works.
        data = {
            "col_one": "hello",
            "col_two": "cat",
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe",
            "col_six": 9999
        }
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

    # Drop column
    def test_drop_column(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        # Drop col_five
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"drop_column": "col_five"}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Test that you can't use col_five anymore.
        data = {"col_one": "hello", "col_two": "cat", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

    # Drop default
    def test_drop_default(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        # Drop default from col_three
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"drop_default": "col_three"}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Test col_three isn't created with default of 888 (or 777, if set_default fn already ran) Should default to None.
        data = {"col_one": "hello", "col_two": "cat", "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.json()['result'][0]['col_three'], None)

    # Set default
    def test_set_default(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        # Set default for col_three, set to 777.
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"set_default": "col_three, 777"}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Test col_three is now defaulting to 777.
        data = {"col_one": "hello", "col_two": "cat", "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.json()['result'][0]['col_three'], 777)

    # Ensure table PUTS error out correctly.
    def test_alter_errors(self):
        table_id = self.init_resp_3["result"]["table_id"]
        root_url = self.init_resp_3["result"]["root_url"]
        # Should result in 400.
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"set_default": "col_three, "}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 400)
        # Should result in 400.
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"set_default": "col_three"}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 400)
        # Should result in 400.
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"set_default": "col_fourty, 777"}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 400)
        # Should result in 200 (no operation given).
        response = self.client.put(f'/v3/pgrest/manage/tables/{table_id}',
                                   data=json.dumps({"fake_oper": "col_three, "}),
                                   content_type='application/json',
                                   **auth_headers)
        self.assertEqual(response.status_code, 200)


    ###############
    # VIEWS TESTS #
    ###############

    # Create view
    def test_create_view(self):
        response = self.client.post(f'/v3/pgrest/manage/views', **auth_headers,
                                    data=json.dumps({'view_name': 'test_view', 
                                                     'root_url': 'just_a_cool_url',
                                                     'select_query': '*',
                                                     'from_table': 'initial_table_2'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/manage/views', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)

    # Check that all search parameters work on views too.
    def test_all_search_parameters(self):
        # Add data to init_table_5
        root_url = self.init_resp_5["result"]["root_url"]
        data = [{
            "col_one": "hello",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "hi",
            "col_two": 100,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 100,
            "col_three": 95,
            "col_four": False,
            "col_five": "hehe"
        }, {
            "col_one": "goodbye",
            "col_two": 120,
            "col_three": 90,
            "col_four": True,
            "col_five": "hehe"
        }, {
            "col_one": "bye",
            "col_two": 200,
            "col_three": 90,
            "col_four": False,
            "col_five": "hehe"
        }]
        response = self.client.post(f'/v3/pgrest/data/{root_url}',
                                    data=json.dumps({"data": data}),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        
        # create view off of init_table_5
        response = self.client.post(f'/v3/pgrest/manage/views',
                                    data=json.dumps({
                                        'view_name': 'test_view_search',
                                        'root_url': 'view_search_test_url',
                                        'select_query': '*',
                                        'from_table': 'initial_table_5'
                                    }),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result']['root_url'], 'view_search_test_url')
        view_root_url = 'view_search_test_url'
        
        # Get view and check if there's result.
        response = self.client.get(f'/v3/pgrest/manage/views', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        
        # eq and gte
        # Check for goodbye and 95 in col_one and col_three.
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_one.eq=goodbye&col_three.gte=95', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

        # neq
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_one.neq=goodbye', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 3)
        self.assertEqual(response.status_code, 200)

        # lte
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_two.lte=120', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 4)
        self.assertEqual(response.status_code, 200)

        # gt
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_two.gt=120', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

        # lt
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_two.lt=120', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 3)
        self.assertEqual(response.status_code, 200)

        # in and nin
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_two.in=120,100&col_three.nin=95', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 3)
        self.assertEqual(response.status_code, 200)
        
        # between and nbetween
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_two.between=0,150&col_three.nbetween=94,96', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 3)
        self.assertEqual(response.status_code, 200)

        # Ensure no results when query doesn't match
        response = self.client.get(f'/v3/pgrest/views/{view_root_url}?col_one.eq=chocolate', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 0)
        self.assertEqual(response.status_code, 200)

    # Nonexistence checks
    def test_get_nonexistent_view(self):
        response = self.client.get(f'/v3/pgrest/views/this_view_does_not_exist', **auth_headers)
        print(response)
        self.assertEqual(response.status_code, 404)

    def test_get_nonexistent_manage_view(self):
        response = self.client.get(f'/v3/pgrest/manage/views/22', **auth_headers)
        print(response)
        self.assertEqual(response.status_code, 404)

    def test_delete_nonexistent_view(self):
        response = self.client.delete(f'/v3/pgrest/manage/views/22', **auth_headers)
        print(response)
        self.assertEqual(response.status_code, 404)
        
    def test_raw_sql_view_creation(self):
        response = self.client.post(f'/v3/pgrest/manage/views', **auth_headers,
                                    data=json.dumps({'view_name': 'test_view_raw_sql',
                                                     'raw_sql': 'AS SELECT * FROM dev.initial_table_2;',
                                                     'comments': 'An example of creating a view with raw_sql.'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/views/test_view_raw_sql', **auth_headers)
        self.assertEqual(response.status_code, 200)

    def test_broken_raw_sql_view_creation(self):
        # raw_sql views don't allow select_query or from_table or where_query to also be provided.
        response = self.client.post(f'/v3/pgrest/manage/views', **auth_headers,
                                    data=json.dumps({'view_name': 'test_view', 
                                                     'raw_sql': 'AS SELECT * FROM dev.initial_table_2;',
                                                     'from_table': 'initial_table_2'}),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)


    ###############
    # ROLES TESTS #
    ###############

    # PGREST_TEST is deleted at startup of PgREST everytime.
    # Ensures it's fresh during tests and ensures no one can "overwrite" our permission to it between runs.
    def test_get_roles(self):
        response = self.client.get(f'/v3/pgrest/manage/roles', **auth_headers)
        self.assertEqual(response.status_code, 200)

    def test_roles(self):
        # Create role
        response = self.client.post(f'/v3/pgrest/manage/roles',
                                    data=json.dumps({
                                        'role_name': 'PGREST_TEST',
                                        'description': 'PgREST testing role. Do not delete, do not touch.'
                                    }),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Get role info after role created
        response = self.client.get(f'/v3/pgrest/manage/roles/PGREST_TEST', **auth_headers)
        self.assertEqual(response.status_code, 200)
        res_dict = response.json()
        self.assertEqual(res_dict['result']['name'], 'PGREST_TEST')
        self.assertEqual(res_dict['result']['owner'], 'pgrest')

        # Create role when it was already created
        response = self.client.post(f'/v3/pgrest/manage/roles',
                                    data=json.dumps({
                                        'role_name': 'PGREST_TEST',
                                        'description': 'PgREST testing role. Do not delete, do not touch.'
                                    }),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 400)

        # Grant role
        response = self.client.post(f'/v3/pgrest/manage/roles/PGREST_TEST',
                                    data=json.dumps({
                                        'method': 'grant',
                                        'username': 'cgarcia'
                                    }),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Grant role when already granted
        response = self.client.post(f'/v3/pgrest/manage/roles/PGREST_TEST',
                                    data=json.dumps({
                                        'method': 'grant',
                                        'username': 'cgarcia'
                                    }),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        res_dict = response.json()
        self.assertEqual(res_dict['result'], 'No changes made. User already has role')

        # Get role_info after grant
        # role info should return usernames that have the role, 'cgarcia' should now have the role
        response = self.client.get(f'/v3/pgrest/manage/roles/PGREST_TEST', **auth_headers)
        self.assertEqual(response.status_code, 200)
        res_dict = response.json()
        self.assertIn('cgarcia', res_dict['result']['usersInRole'])

        # Revoke role
        response = self.client.post(f'/v3/pgrest/manage/roles/PGREST_TEST',
                                    data=json.dumps({
                                        'method': 'revoke',
                                        'username': 'cgarcia'
                                    }),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)

        # Revoke role when already revoked
        response = self.client.post(f'/v3/pgrest/manage/roles/PGREST_TEST',
                                    data=json.dumps({
                                        'method': 'revoke',
                                        'username': 'cgarcia'
                                    }),
                                    content_type='application/json',
                                    **auth_headers)
        self.assertEqual(response.status_code, 200)
        res_dict = response.json()
        self.assertEqual(res_dict['result'], "No changes made. User already didn't have role")
