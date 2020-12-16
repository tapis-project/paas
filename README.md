
Create initial DB structure:
from within proto:
1. docker-compose run api python manage.py makemigrations
2. docker-compose run api python manage.py migrate

Create a table:
curl -H "Content-type: application/json" -d "@table-def.json" localhost:8000/paas/manage-tables

Add a row:
curl -H "Content-type: application/json" -d '{"data": {"name": "sprok", "count": 3, "gizmo": "fuzz"}}' localhost:8000/paas/sprokets