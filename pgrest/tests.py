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


class ResponseTestCase(TenantTestCase):

    init_resp_1 = {}
    init_resp_2 = {}

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

    def setUp(self):
        super().setUp()
        self.c = TenantClient(self.tenant)
        self.createTable()

    def tearDown(self):
        self.client.delete(f'/v3/pgrest/manage/tables/{self.init_resp_1["result"]["table_id"]}', **auth_headers)
        self.client.delete(f'/v3/pgrest/manage/tables/{self.init_resp_2["result"]["table_id"]}', **auth_headers)


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
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_1),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_create_table_with_serial_data_type(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_7),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_create_table_with_serial_data_type_with_null_fails(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_8),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_existing_root_url(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_2),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_existing_table(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_3),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_no_columns(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_4),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_char_len_required_on_varchar(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_5),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_create_with_foreign_key(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_9),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_create_with_foreign_key_no_nulls_with_delete_set_null_400(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_10),
                                    content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 400)


    # ---- DELETE TABLES ---- #
    def test_delete_existing_table(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_6),
                                    content_type='application/json', **auth_headers)
        del_resp = self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}',
                                      **auth_headers)
        self.assertEqual(del_resp.status_code, 200)

    def test_delete_nonexistent_table(self):
        response = self.client.delete('/v3/pgrest/manage/tables/100000000000007473774', **auth_headers)
        self.assertEqual(response.status_code, 404)

    # ---- LIST SINGLE TABLE ---- #
    def test_list_single_tables(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_6),
                                    content_type='application/json', **auth_headers)

        response = self.client.get(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].lower(), "application/json")

        del_resp = self.client.delete(f'/v3/pgrest/manage/tables/{response.json()["result"]["table_id"]}', **auth_headers)

    def test_list_single_tables_detail(self):
        response = self.client.post('/v3/pgrest/manage/tables', data=json.dumps(test_data.create_table_6),
                                    content_type='application/json', **auth_headers)
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
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)

    def test_create_object_in_table_nulls_no_needed(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)

    def test_create_object_in_table_without_required_field_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_create_object_in_table_wrong_data_type_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_one": 50, "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_create_object_in_nonexistent_table_400(self):
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/nah', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    # ---- UPDATE ROW ---- #
    def test_update_row(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": data}),
                                    **auth_headers, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, update
        data = {"col_two": 30}
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.put(f'/v3/pgrest/data/{root_url}/{row_id}', **auth_headers,
                                   data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 200)

    def test_update_row_wrong_data_type_400(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]
        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, update
        data = {"col_two": "haha"}
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.put(f'/v3/pgrest/data/{root_url}/{row_id}', **auth_headers,
                                   data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_update_row_nonexistent_row_400(self):
        root_url = self.init_resp_1["result"]["root_url"]
        data = {"col_two": 100}
        response = self.client.put(f'/v3/pgrest/data/{root_url}/898989', **auth_headers,
                                   data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_update_row_nonexistent_column_400(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]

        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)
        # now, update
        data = {"col_where": 30}
        row_id = response.json()["result"][0]['_pkid']
        response = self.client.put(f'/v3/pgrest/data/{root_url}/{row_id}', **auth_headers,
                                   data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    # ---- DELETE ROW ---- #
    def test_delete_row(self):
        # first, we need to create row
        root_url = self.init_resp_1["result"]["root_url"]
        table_name = self.init_resp_1["result"]["table_name"]

        data = {"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
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
        response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": data}),
                                    content_type='application/json', **auth_headers)
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

        data = [{"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?where_col_one=hi', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

    def test_filter_by_two_columns(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?where_col_one=goodbye&where_col_three=95',
                                   **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

    def test_filter_by_two_columns_one_boolean(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 5)
        response = self.client.get(f'/v3/pgrest/data/{root_url}?where_col_one=goodbye&where_col_four=True',
                                   **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)
        self.assertEqual(response.status_code, 200)

    def test_order_by(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 80, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 94, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 60, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
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

        data = [{"col_one": "hello", "col_two": 100, "col_three": 80, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 94, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 60, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?where_col_one=goodbye', **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 95)
        self.assertEqual(response.json()["result"][1]["col_three"], 94)

        response = self.client.get(f'/v3/pgrest/data/{root_url}?where_col_one=goodbye&order=col_three,ASC',
                                   **auth_headers)
        self.assertEqual(response.json()["result"][0]["col_three"], 94)
        self.assertEqual(response.json()["result"][1]["col_three"], 95)

    # ---- UPDATING MULTIPLE ROWS ---- #
    def test_update_entire_table(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        # now, update
        data = {"col_five": "omg"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                   data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            self.assertEqual(resp["col_five"], "omg")

    def test_update_nonexistent_rows_in_table(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        # now, update
        data = {"col_where": "omg"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": data}),
                                   content_type='application/json', **auth_headers)
        self.assertEqual(response.status_code, 400)

    def test_update_rows_with_wrong_data_type_400(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        # now, update
        data = {"col_five": 40}
        response = self.client.put(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                   data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            self.assertEqual(resp["col_five"], "hehe")

    def test_update_rows_with_filter_string(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "haha"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "haha"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        # now, update
        where_clause = {"col_five": {
            "operator": "=",
            "value": "haha"
        }}
        data = {"col_one": "lata"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                   data=json.dumps({"data": data, "where": where_clause}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            if resp["col_five"] == 'hehe':
                self.assertNotEqual(resp["col_one"], "lata")
            else:
                self.assertEqual(resp["col_one"], "lata")

    def test_update_rows_with_filter_int(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "haha"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 96, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "haha"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        where_clause = {"col_three": {
            "operator": ">=",
            "value": 95
        }}
        data = {"col_one": "lata"}
        response = self.client.put(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                   data=json.dumps({"data": data, "where": where_clause}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        for resp in response.json()["result"]:
            if resp["col_three"] < 95:
                self.assertNotEqual(resp["col_one"], "lata")
            else:
                self.assertEqual(resp["col_one"], "lata")

    def test_update_rows_with_filter_incorrect_data_type(self):
        root_url = self.init_resp_1["result"]["root_url"]

        data = [{"col_one": "hello", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "hehe"},
                {"col_one": "hi", "col_two": 100, "col_three": 95, "col_four": False, "col_five": "haha"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 96, "col_four": False, "col_five": "hehe"},
                {"col_one": "goodbye", "col_two": 100, "col_three": 90, "col_four": True, "col_five": "hehe"},
                {"col_one": "bye", "col_two": 100, "col_three": 90, "col_four": False, "col_five": "haha"}]
        for dt in data:
            response = self.client.post(f'/v3/pgrest/data/{root_url}', data=json.dumps({"data": dt}),
                                        content_type='application/json', **auth_headers)
            self.assertEqual(response.status_code, 200)

        where_clause = {"col_three": {
            "operator": ">=",
            "value": 95
        }}

        data = {"col_one": 90}
        response = self.client.put(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                   data=json.dumps({"data": data, "where": where_clause}), content_type='application/json')
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
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        response = self.client.get(f'/v3/pgrest/data/{root_url}', **auth_headers)
        self.assertEqual(len(response.json()["result"]), 1)

    def test_create_row_with_enum_error(self):
        # We should get a 400 from this as enum's won't match up.
        root_url = self.init_resp_2["result"]["root_url"]
        data = {"col_one": "hello", "col_two": "NotInEnum", "col_three": 90, "col_four": False, "col_five": "hehe"}
        response = self.client.post(f'/v3/pgrest/data/{root_url}', **auth_headers,
                                    data=json.dumps({"data": data}), content_type='application/json')
        self.assertEqual(response.status_code, 400)


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