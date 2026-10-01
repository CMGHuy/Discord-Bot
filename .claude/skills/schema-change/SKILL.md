---
name: schema-change
description: Use when changing the Postgres schema, a store's read or write path, or a data migration -- every store is Postgres-only, so a shape change is an Alembic revision following docs/claude/schema-evolution.md. Not for reading data, not for analytics queries, and not for the few files under data/ that were never stores (snapshots, telemetry).
---

# Schema change

## Step 1 — Read the recipe and pick the operation

Read `docs/claude/schema-evolution.md` and pick one: add (a field in `doc`, no
migration), rename or drop (a data revision using `swingbot/core/db/doc_fields.py`),
or promote (a DDL revision plus a reason in `schema.PROMOTION_REASONS`). Never add
read-time upcasting for an old field name; the revision converts old rows.

## Step 2 — Read up before writing DDL

Confirm current Postgres DDL best practice for the change you're making
before you write it -- a schema change is not reversible the way an app-code
change is. A new revision's `down_revision` is the current head
(`python -m alembic heads`).

## Step 3 — The three contract tests

`tests/db/test_schema_contract.py`, `tests/db/test_unknown_field_round_trip.py`
and `tests/db/test_doc_fields.py` guard the hybrid layout (promoted columns plus
`doc`). Run them after any change to `schema.py`, a repository or a revision;
a migration that completes without raising has not been verified by that alone.

## Step 4 — Round-trip and downgrade

Write a record, read it back through the same repository, and compare --
against real data shape pulled from the store, not a fixture built to round-trip
cleanly. Run the revision's downgrade once against the test database.

## The gate

The contract tests green, the revision's downgrade run once against the test
database, and the round-trip committed as a test someone else can re-run. Before
a drop or rename runs on production, a point-in-time-rollback drill within the
last 7 days (`docs/deploy/DB_RESTORE.md`); the rollback is
`scripts/ops/rollback_to.sh`.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "The migration printed no errors" | A swallowed write failure also prints nothing -- silence is not success. |
| "The row counts match" | Counts matching says nothing about field content; a field can be dropped or mangled on every row while the count holds. |
| "I'll read the old field name too, just in case" | That is a second code path per field forever; the revision converts the rows once. |
| "A JSON file under data/ is a backup" | No store is backed by a file any more; the backup is `rollback_to.sh` and the `pg_dump` files. |

## Trigger table

Should fire: adding a column to a store's Postgres schema.
Should fire: changing which store a repository's writer targets.
Should fire: writing a script to migrate or backfill a store's data.
Should not fire: a read-only analytics query against already-migrated data.
Should not fire: a dashboard or admin-UI change that only reads from a store.
Should not fire: reading a `data/*.json` file for context, with no write.
