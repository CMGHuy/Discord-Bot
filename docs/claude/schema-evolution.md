# Schema evolution — add, rename, drop, promote

Referenced from the root `CLAUDE.md`. **Read before changing a table's shape or
the fields a stored record carries.**

Every table is hybrid: a few **promoted** columns (keys, foreign keys, indexed
or NOT NULL fields) plus `doc JSONB NOT NULL DEFAULT '{}'` holding every other
field, and `updated_at TIMESTAMPTZ`. `split_doc`/`merge_doc`
(`swingbot/core/db/codec.py`) move a flat record across that boundary. The data
model changes about once per plan (v39, v50, v52, v58 reshaped trades and
plans); this layout is what keeps that cheap. Three tests keep it that way:

| Test | Guards |
|---|---|
| `tests/db/test_schema_contract.py` | every table has `doc` and `updated_at`; every promoted column has a one-line reason in `schema.PROMOTION_REASONS` |
| `tests/db/test_unknown_field_round_trip.py` | a field no code has seen, nested, survives every repository |
| `tests/db/test_doc_fields.py` | rename and drop run up and down |

## The four operations

| Operation | What you do | Migration? |
|---|---|---|
| **add** | Write the field. It lands in `doc`. | None. |
| **rename** | A data revision: `rename_doc_field(table, old, new)` in `upgrade()`, the same call with the names swapped in `downgrade()`. It refuses (`DocFieldConflict`) if any row carries both names. | Data revision. |
| **drop** | A data revision: `drop_doc_field(table, name)` in `upgrade()`, `restore_doc_field(table, name)` in `downgrade()`. The drop first snapshots every value into `dropped_doc_fields`, so the downgrade restores them exactly (explicit nulls included). | Data revision. |
| **promote** | `op.add_column`, a backfill `UPDATE t SET col = (doc->>'field')::type`, the column in `register(...)`'s tuple **and** a reason in `PROMOTION_REASONS`. Keep the `doc` copy: `merge_doc` lets a non-null column win, so both agree and a later demote is a column drop. | DDL revision. |

The helpers live in `swingbot/core/db/doc_fields.py`. Inside a revision they use
`alembic.op.get_bind()`; tests pass `conn=`.

## No read-time upcasting

A shape change is applied **once, by a revision**. Never add code that reads a
field under its old name "just in case": that is a second code path per field
forever, and it is how v58's `tp1_hit`/`target1_hit` confusion started. If old
rows exist, the revision converts them.

## Revision ids

`p[1-6]_NNN` for v67's parts, `v<plan>_NNN` for later plans (`v116_001`).
`tests/db/test_migrations.py` requires one of those shapes and exactly one
head. A new revision's `down_revision` is the current head
(`python -m alembic heads`).

## Before running a data revision on production

A drop or rename touches every row. Check the last PITR drill passed
(`docs/deploy/DB_RESTORE.md`) — the rollback is `scripts/ops/rollback_to.sh`
to the second before the revision ran.
