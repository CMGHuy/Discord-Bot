---
name: schema-change
description: Use when changing the Postgres schema, a store's read or write path, or a data migration -- the JSON-to-Postgres strangler is per-store and partially complete, so some stores are migrated and some are not. Not for reading data, not for analytics queries, and not for the JSON files under data/ that no longer back a migrated store.
---

# Schema change

## Step 1 — Establish which stores are migrated

The strangler runs per store, not as one cutover. Check the current state in
code, not from a plan doc: does `swingbot/core/db/repositories/` have a
repository class for the store you're touching, and does
`scripts/db/parity_report.py`'s `STORES` dict cover it. A plan can say a
store is migrated after the code has already moved past it, or before.

## Step 2 — Load the Postgres practices skill

Load `supabase:supabase-postgres-best-practices` before writing any DDL, per
its own trigger. This skill does not restate what it covers.

## Step 3 — `parity_report` is the only verifier to trust

Run `python scripts/db/parity_report.py` after any import or migration
touching a store. It diffs the JSON source against the Postgres table field
by field; an import that completes without raising has not been verified by
that alone.

## Step 4 — Round-trip before cutover

Before pointing a store's reads at Postgres, write a record, read it back
through the same repository, and compare -- against real data pulled from the
store you're migrating, not a fixture built to round-trip cleanly.

## The gate

`parity_report` clean on the store you touched, and the round-trip from Step
4 committed as a test someone else can re-run -- not one you ran once
locally and threw away.

## Known wrong turns

| Tempting | Reality |
|---|---|
| "The import printed no errors" | A swallowed write failure also prints nothing -- silence is not success. |
| "The row counts match" | Counts matching says nothing about field content; a field can be dropped or mangled on every row while the count holds. |
| "The JSON is still there as a backup" | It stays a backup only until a writer overwrites it -- check whether the write path already switched before trusting it. |

## Trigger table

Should fire: adding a column to a store's Postgres schema.
Should fire: changing which store a repository's writer targets.
Should fire: writing a script to migrate or backfill a store's data.
Should not fire: a read-only analytics query against already-migrated data.
Should not fire: a dashboard or admin-UI change that only reads from a store.
Should not fire: reading a `data/*.json` file for context, with no write.
