"""Restore crop harvest-date columns removed by an out-of-band migration.

Some development databases were migrated with a ``0002_remove_harvest_fields``
migration that deleted the ``expected_harvest_date`` and
``actual_harvest_date`` columns from ``tblcrops``. Those migrations are not
part of this repository, but the current ``Crop`` model still uses both
fields, so the columns must be restored. The migration checks the actual
table before adding anything, which keeps it safe on databases where the
columns already exist.
"""

from django.db import migrations, models


CROP_TABLE = 'tblcrops'

CROP_DATE_FIELDS = (
    ('expected_harvest_date', 'expected harvest date'),
    ('actual_harvest_date', 'actual harvest date'),
)


def _table_columns(schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(
            cursor, CROP_TABLE
        )
    return {column.name for column in description}


def restore_crop_harvest_dates(apps, schema_editor):
    """Add any missing crop harvest-date columns without touching existing data."""
    existing_columns = _table_columns(schema_editor)
    Crop = apps.get_model('crops', 'Crop')

    for name, verbose_name in CROP_DATE_FIELDS:
        if name in existing_columns:
            continue

        field = models.DateField(
            blank=True,
            null=True,
            verbose_name=verbose_name,
        )
        field.set_attributes_from_name(name)
        schema_editor.add_field(Crop, field)


class Migration(migrations.Migration):

    # MySQL/MariaDB cannot roll back DDL statements, so run outside a
    # transaction. The operation is idempotent and checks for existing
    # columns before adding them.
    atomic = False

    dependencies = [
        ('crops', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            restore_crop_harvest_dates,
            migrations.RunPython.noop,
        ),
    ]
