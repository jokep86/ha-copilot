# Migrations

SQL migration files applied in version order by `Database.run_migrations()`.

## Naming convention

`NNN_description.sql` — where `NNN` is a zero-padded integer version (e.g. `001`, `002`).

The version number is extracted from the filename prefix. Applied versions are recorded in `schema_version`.

## Adding a new migration

1. Create `NNN_description.sql` with the next version number.
2. Write idempotent SQL (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).
3. Do not modify existing migration files — always add new ones.
4. Update `CHANGELOG.md` with the schema change.
