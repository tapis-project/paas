# Generated by Django 2.0 on 2020-12-15 22:38

import django.contrib.postgres.fields
import django.contrib.postgres.fields.jsonb
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='ManageTables',
            fields=[
                ('manage_table_id', models.AutoField(primary_key=True, serialize=False)),
                ('table_name', models.CharField(max_length=255)),
                ('root_url', models.CharField(max_length=255)),
                ('column_definition', django.contrib.postgres.fields.jsonb.JSONField()),
                ('validate_json_create', django.contrib.postgres.fields.jsonb.JSONField()),
                ('validate_json_update', django.contrib.postgres.fields.jsonb.JSONField()),
                ('endpoints', django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=255), size=None)),
                ('tenant_id', models.CharField(max_length=255)),
                ('primary_key', models.CharField(max_length=255)),
                ('special_rules', django.contrib.postgres.fields.jsonb.JSONField()),
                ('comments', models.TextField()),
                ('constraints', django.contrib.postgres.fields.jsonb.JSONField())
            ],
        ),
        migrations.CreateModel(
            name='ManageTablesTransition',
            fields=[
                ('manage_table_transition_id', models.AutoField(primary_key=True, serialize=False)),
                ('column_definition_tn', django.contrib.postgres.fields.jsonb.JSONField()),
                ('validate_json_create_tn', django.contrib.postgres.fields.jsonb.JSONField()),
                ('validate_json_update_tn', django.contrib.postgres.fields.jsonb.JSONField()),
                ('table_name_tn', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('manage_table', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='pgrest.ManageTables')),
            ]
        )
    ]
