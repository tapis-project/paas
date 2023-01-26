"""
WSGI config for paas project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/wsgi/
"""

import os
import time
import sys

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'paas.settings')

# Running migration step.
import subprocess

# Running makemigrations.
print("\n\n\n\n\nMigration -- Running makemigrations before app start.")
i = 0
while i < 40:
    result = subprocess.run("python /home/tapis/manage.py makemigrations", shell=True, capture_output=True)
    if result.stderr:
        print(f"Error running makemigrations, try {i} of 10. stderr:\n {result.stderr.decode('utf-8')}\n\n")
        i = i + 1
        time.sleep(3)
        continue
    print("Migration -- Successfully ran makemigrations.")
    break
else:
    msg = f"Error connecting to the database, giving up"
    print(msg)
    raise Exception(msg)


# Running migrate_schemas.
print("\n\n\n\n\nMigration -- Running migrate_schemas before app start.")
result = subprocess.run("python /home/tapis/manage.py migrate_schemas --shared", shell=True, capture_output=True)
if result.stderr:
    msg = f"Error running migrate_schemas. stderr: {result.stderr}"
    print(msg)
    raise Exception(msg)
print("Application -- Successfully ran migrate_schemas, running app.")

application = get_wsgi_application()
