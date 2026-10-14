# MySQL setup

The `projectv3/mysql` directory is a local XAMPP installation and database
store. Do not commit it: it contains server binaries and local database files.
The database schema is created from the Django migrations, so no database dump
or existing user data is needed.

## Create the database

Create an empty MySQL or MariaDB database, for example:

```sql
CREATE DATABASE bsitcrud CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Install the MySQL Python driver in the project environment:

```powershell
pip install mysqlclient
```

Set the connection details in PowerShell before starting Django:

```powershell
$env:DB_ENGINE = "django.db.backends.mysql"
$env:DB_NAME = "bsitcrud"
$env:DB_USER = "root"
$env:DB_PASSWORD = "<your-local-password>"
$env:DB_HOST = "127.0.0.1"
$env:DB_PORT = "3306"
```

Create the schema and run the application:

```powershell
python manage.py migrate
python manage.py runserver
```

The settings continue to use SQLite by default when `DB_ENGINE` is not set.
Keep database passwords in local environment variables; do not commit them.
