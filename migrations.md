# Migrations

This project uses Alembic to manage database schema changes for the SQLAlchemy models.

## How It Works

SQLAlchemy models describe the desired database tables in Python. Alembic stores schema changes as revision files in `alembic/versions/` and records which revisions have been applied in the database's `alembic_version` table.

The important files are:

- `core/db.py`: creates the SQLAlchemy `Base`, engine, and session factory.
- `core/models.py`: defines ORM models, starting with `Channel`.
- `alembic/env.py`: imports the models and points Alembic at `Base.metadata` so autogenerate can compare models to the current database schema.
- `alembic.ini`: configures the Alembic script directory and default database URL.
- `alembic/versions/`: contains migration revision files.

The default database is SQLite at `runtime/metaauto.db`, controlled by `DATABASE_URL` in `settings.py`.

## Common Commands

Install dependencies first if needed:

```bash
pip install -r requirements.txt
```

Apply all migrations:

```bash
alembic upgrade head
```

Show the currently applied migration:

```bash
alembic current
```

Show migration history:

```bash
alembic history
```

Roll back one migration:

```bash
alembic downgrade -1
```

## Adding A Model Change

1. Update or add SQLAlchemy models in `core/models.py`.
2. Generate a migration:

```bash
alembic revision --autogenerate -m "describe the schema change"
```

3. Review the generated file in `alembic/versions/`. Autogenerate is a helper, not a substitute for reviewing migrations.
4. Apply it:

```bash
alembic upgrade head
```

## Current Schema

The first migration creates the `channels` table with:

- `id`: channel ID and primary key.
- `name`: channel name.
- `enabled`: boolean flag for whether the channel is active.
