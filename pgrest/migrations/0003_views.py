import django.contrib.postgres.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pgrest', '0002_tenants'),
    ]

    operations = [
        migrations.CreateModel(
            name='ManageViews',
            fields=[
                ('manage_view_id', models.AutoField(primary_key=True, serialize=False)),
                ('view_name', models.CharField(max_length=255)),
                ('root_url', models.CharField(max_length=255)),
                ('view_definition', django.contrib.postgres.fields.jsonb.JSONField()),
                ('permission_rules', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=255), null=True, blank=True, size=None)),
                ('tenant_id', models.CharField(max_length=255)),
                ('endpoints', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=255), size=None)),
                ('comments', models.TextField(null=True))
            ]
        )
    ]
