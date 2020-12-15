# docker-compose run api python manage.py test
# docker-compose run api python manage.py makemigrations
import json

from django.test import TestCase

from rest_framework.test import APIClient

from proto import test_data


class ResponseTestCase(TestCase):

    init_resp_1 = {}
    init_resp_2 = {}

    def createTable(self):
        init_resp_1 = self.client.post('/paas/manage-tables', data=json.dumps(test_data.init_table_1),
                                     content_type='application/json')
        self.init_resp_1 = init_resp_1.json()

        init_resp_2 = self.client.post('/paas/manage-tables', data=json.dumps(test_data.init_table_2),
                                       content_type='application/json')
        self.init_resp_2 = init_resp_2.json()

    def setUp(self):
        self.client = APIClient()
        self.createTable()

    def tearDown(self):
        self.client.delete(f'/paas/manage-tables/{self.init_resp_1["table_id"]}')
        self.client.delete(f'/paas/manage-tables/{self.init_resp_2["table_id"]}')


    #######################
    # MANAGE TABLES TESTS #
    #######################

    # ---- LIST ALL TABLES ---- #
    def test_list_tables(self):
        response = self.client.get('/paas/manage-tables')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].lower(), "application/json")

    def test_list_tables_details(self):
        response = self.client.get('/paas/manage-tables?details=true')
        self.assertEqual(response["Content-Type"].lower(), "application/json")
        try:
            response.json()[0]["columns"]
        except KeyError:
            self.fail("Details did not return columns")
        self.assertEqual(response.status_code, 200)

    def test_list_tables_for_correct_tenant_only(self):
        response = self.client.get('/paas/manage-tables')
        self.assertEqual(response["Content-Type"].lower(), "application/json")
        for resp in response.json():
            self.assertEqual(resp["tenant"], "public")

    # ---- CREATE TABLES ---- #
    def test_simple_create(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_1),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/paas/manage-tables/{response.json()["table_id"]}')

    def test_existing_root_url(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_2),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_existing_table(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_3),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_no_columns(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_4),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_char_len_required_on_varchar(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_5),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 400)

    # ---- DELETE TABLES ---- #
    def test_delete_existing_table(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_6),
                                    content_type='application/json')
        self.client.delete(f'/paas/manage-tables/{response.json()["table_id"]}')
        self.assertEqual(response.status_code, 200)

    def test_delete_nonexistent_table(self):
        response = self.client.delete('/paas/manage-tables/100000000000007473774')
        self.assertEqual(response.status_code, 404)

    # ---- LIST SINGLE TABLE ---- #
    def test_list_single_tables(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_6),
                                    content_type='application/json')
        self.client.get(f'/paas/manage-tables/{response.json()["table_id"]}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"].lower(), "application/json")
        self.client.delete(f'/paas/manage-tables/{response.json()["table_id"]}')

    def test_list_single_tables_detail(self):
        response = self.client.post('/paas/manage-tables', data=json.dumps(test_data.create_table_6),
                                    content_type='application/json')
        table_id = response.json()["table_id"]
        get_response = self.client.get(f'/paas/manage-tables/{table_id}?details=true')
        self.assertEqual(response["Content-Type"].lower(), "application/json")
        try:
            get_response.json()["columns"]
        except KeyError:
            self.fail("Details did not return columns")
        self.assertEqual(response.status_code, 200)
        self.client.delete(f'/paas/manage-tables/{response.json()["table_id"]}')

    def test_list_nonexistent_table(self):
        response = self.client.get('/paas/manage-tables/5999999993999999')
        self.assertEqual(response.status_code, 404)

    # ---- UPDATE TABLE ---- #

    #######################
    # DYNAMIC VIEWS TESTS #
    #######################






