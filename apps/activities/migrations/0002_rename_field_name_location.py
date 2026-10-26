from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activities', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='farmactivity',
            old_name='field_name',
            new_name='location',
        ),
        migrations.AlterField(
            model_name='farmactivity',
            name='location',
            field=models.CharField(
                help_text='Location or area where the activity will take place '
                          '(e.g. North Field, Block A).',
                max_length=255,
                verbose_name='location',
            ),
        ),
    ]
