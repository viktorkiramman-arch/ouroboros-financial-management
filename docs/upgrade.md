# Upgrade Guide

## Backup First

Before upgrading an existing installation, stop the app and copy the database file.

SQLite default:

```powershell
Copy-Item instance/ouroboros.db instance/ouroboros.backup.db
```

For PostgreSQL, use `pg_dump` and store the dump outside the application directory.

## Local SQLite Upgrade

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run migrations:

```powershell
$env:FLASK_APP = "wsgi.py"
$env:AUTO_CREATE_DB = "false"
python -m flask db upgrade
```

Local development may still use `AUTO_CREATE_DB=true`, but production should use migrations.

## Existing SQLite Databases

If an existing database was created before migrations, stamp the baseline after backing up:

```powershell
$env:FLASK_APP = "wsgi.py"
python -m flask db stamp 0001_legacy_baseline
python -m flask db upgrade
```

The `0002_currency_integrity` migration backfills legacy transactions from the user's previous reporting currency setting. It does not rewrite historical amounts.

## PostgreSQL Production

Set:

```text
DATABASE_URL=postgresql://user:password@host:5432/finance
LOCAL_ONLY=false
AUTO_CREATE_DB=false
SECRET_KEY=<at least 32 random characters>
SESSION_COOKIE_SECURE=true
```

Then run:

```powershell
$env:FLASK_APP = "wsgi.py"
python -m flask db upgrade
```

## Rollback

Rollback requires a tested backup restore. For financial data, prefer restoring the database backup rather than downgrading destructive schema changes in place.

## Verification

After upgrade:

```powershell
python -m ruff check .
python -m pytest
python -m compileall ouroboros_financial_management tests migrations
```
