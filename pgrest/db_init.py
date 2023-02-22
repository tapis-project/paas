""" Database migration and connection checker/loop.
Try to make migrations for the db. Try 40 times, every 3 seconds in the case of 
postgres taking a bit to turn on. Then try migrate_schemas. Once complete can start API.
Only needs to happen in the case of new tenants or a fresh DB.
"""

import time

# Running migration step.
import subprocess

# Running makemigrations.
print("\n\n\n\n\nMigration -- Running makemigrations before app start.")
idx = 0
while idx < 40:
    result = subprocess.run("python /home/tapis/manage.py makemigrations", shell=True, capture_output=True)
    if result.stderr:
        print(f"Error running makemigrations, try {i} of 10. stderr:\n {result.stderr.decode('utf-8')}\n\n")
        idx += 1
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

