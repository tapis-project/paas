# docker-compose run api python manage.py test
import json

from django.test import TestCase

from rest_framework.test import APIClient

from proto import test_data

class ResponseTestCase(TestCase):

    def createTable(self):
        self.client.post('/manage-tables', data=json.dumps(test_data.simple_table),
                                    content_type='application/json')

    def setUp(self):
        self.client = APIClient()
        self.createTable()

    def test_list_tables(self):
        response = self.client.get('/manage-tables')
        print(response.json())
        self.assertEqual(response.status_code, 200)
