# Baseline migration for the users app.
# The users app manages Django's built-in User model (handled by
# django.contrib.auth migrations). This migration establishes the users
# app in the migration history so future model migrations apply cleanly.

from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
    ]
