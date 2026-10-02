# v91 — Postgres import correctness

**Bump:** bot patch
**Edge:** none (integrity)

## Why

On 2026-09-16 the v67 schema was created on production for the first time
(`alembic upgrade head`, 17 revisions, now at `p6_000`), and every existing
importer was run against the live JSON. Four defects surfaced. They are
recorded here because each one is a silent-loss class, not a cosmetic one, and
because three of them sit directly on the path to the only two stores whose
migration carries a measurable performance win.

Production is unaffected throughout: `DB_STORES=''`, so nothing reads
PostgreSQL and JSON remains the sole source of truth. Every importer is
read-only against its JSON source, and every write is an idempotent upsert.

### Measured state after the first import

| store | source | imported | parity |
|---|---|---|---|
| `watchlist` | 77 | 77 | OK |
| `state` (signal_state) | 1170 | 1170 | OK |
| `account` | 10 keys + 814 history | 1 + 814 | OK |
| `starred_plans` | 0 | 0 | OK (empty source) |
| `plans` | 416 | 416 | **FAILED** — all 416 |
| `journal` | 609 | **517** | **FAILED** — 92 lost |
| `trades` | 802 | **0** | **FAILED** — total |

Database size 12 MB. Source files: `trades.json` 2.9 MB / 802 records,
`plans.json` 873 KB / 416, `journal.json` 401 KB / 609, `state.json` 128 KB /
1170 keys, `account.json` 164 KB, `watchlist.json` 77 tickers.

## The four defects

### D1 — `trades` does not import at all (802 of 802 lost)

```
codec.ReservedKeyError: record uses reserved key(s) ['id'];
rename the field because these names belong to infrastructure columns
```

`trades.json` records carry the trade identifier as `id`. The `trades` table
has an infrastructure `id BigInteger` primary key plus a separate
`trade_id Text` domain column (`core/db/schema.py:51-52`), and
`TradeRepository` keys on `trade_id` (`repositories/trades.py`). `split_doc`
therefore rejects the record at the boundary (`core/db/codec.py:23-28`), which
is correct behaviour — the caller is wrong.

**The translator already exists and is already in production use.**
`performance._db_record()` (`core/tracking/performance.py:438-442`) maps
`id → trade_id` and `horizon_key → horizon`, and the live dual-write path
calls it (`performance.py:507`). `import_trades.load_source` simply returns the
raw JSON and never applies it (`scripts/db/import_trades.py:14-15`).

**Fix:** map source records through `_db_record` in `import_trades.load_source`.
Reusing the dual-write translator is the point — an importer that shapes
records differently from the live writer would produce a database that passes
import and then diverges the moment dual-write starts.

### D2 — `journal` silently loses 92 of 609 rows

```
DETAIL: Token "NaN" is invalid.
CONTEXT: JSON data, line 1: ..."r_realized": -1.0, "mfe_r": NaN...
```

`json.dumps` emits bare `NaN` / `Infinity` for non-finite floats. That is
accepted by Python's own parser but is not valid JSON, and PostgreSQL's JSONB
rejects it. The affected records are journal entries whose `mfe_r` / `mae_r`
were never computed.

This is **not** a journal problem. Any store whose document payload can hold a
non-finite float has it; journal is merely the first to carry one. The fix
therefore belongs at the codec boundary, where every store crosses.

**Fix:** sanitise non-finite floats to `None` in `split_doc`, recursively
through nested containers.

**Decision — NaN becomes null, and that is a deliberate narrowing.** `NaN`
means "not computed" in every site that produces one here, and `None` is how
the JSON stores already spell that elsewhere. Round-tripping `NaN` back out of
the database is explicitly *not* a goal: parity must therefore compare a source
`NaN` as equal to a database `null`, which is the one place the comparator
needs to know about this rule.

### D3 — `plans` round-trip widens `created_at` (416 of 416)

- source: `'2026-08-11'` (date-only string)
- round-tripped: `'2026-08-11T00:00:00+00:00'`

`created_at` is a promoted `TIMESTAMP WITH TIME ZONE` column, so a date-only
string is parsed on write and rendered in full on read. No data is lost and no
instant moves. The contract does change: a consumer reading `created_at` after
`plans` flips to `db` receives a different string than it does today.

The other fields reported as differing during diagnosis — `badge_stats`,
`status_history`, `legs_realized`, `gate`, `cohort_stats` — are **not** real
differences. They were artefacts of comparing with `repr()`, which is
key-order sensitive; `record_checksum` serialises with `sort_keys=True`
(`scripts/db/import_common.py:11-13`). `created_at` alone accounts for all 416
mismatches, which is why the mismatch count equals the row count exactly.

**Fix:** establish whether any consumer depends on the date-only form, then
either normalise in `_plans_from_repo_shape` or accept the widening and record
it. This is the one defect whose fix is not yet decided, and the plan must
resolve it by reading consumers, not by assuming.

### D4 — `run_import`'s inline verification cannot be trusted

`run_import` compares source records against `repo.list_all()` raw
(`scripts/db/import_common.py:85`) with neither the `from_repo_shape`
translation nor the `ignore_fields` set that `parity_report.py` carries per
store (`scripts/db/parity_report.py:106-121, 130`).

Consequences, both observed:

- **False alarm.** `watchlist` reported `VERDICT: FAILED` on all 77 tickers
  while authoritative parity reports OK. Its `added_at` is a generated stamp —
  `str` in source, `datetime` from the database, and stamped at a different
  instant on each call. `import_watchlist.py:18-19` documents that "parity
  explicitly ignores this generated field", but `run_import` has no
  `ignore_fields` parameter, so the documented intent was never implemented.
- **False confidence.** `state` and `starred_plans` reported OK from a
  comparison that happens to be shape-neutral. A store that passes this check
  has not been meaningfully checked.

A verifier that cries wolf on a healthy store and waves through an unchecked
one is worse than no verifier, because the operator stops reading it.

**Fix:** delete the ad-hoc comparison and have `run_import` delegate to
`parity_report`'s spec-driven `parity()`. One verifier, one registry of
per-store shapes and ignores, no second definition to drift.

## Scope

In scope:

1. D1 — `import_trades` uses `_db_record`.
2. D2 — non-finite floats sanitised at the codec boundary; parity treats source
   `NaN` as equal to database `null`.
3. D3 — resolve the `created_at` contract by reading consumers, then implement
   the chosen side.
4. D4 — `run_import` delegates to `parity_report.parity()`.
5. Re-import all seven stores on production and prove parity OK across all of
   them.
6. Flip `watchlist` and `state` to `dual` as the first live stage change.

Out of scope, deliberately:

- **Flipping `trades` or `plans` to `dual` or `db`.** Those carry the
  performance win and they are the ones these defects hit. They move in their
  own plan, after this one has proven the pipeline on two low-risk stores and
  after backups exist.
- The remaining v67 parts (P3-16…24 NOTIFY watcher, Parts 4–9).
- `scripts/db/import_all.py` (P6-06's orchestrator). Seven explicit importer
  invocations are adequate at this size, and the orchestrator's `ORDER` list
  names importers that do not exist yet.
- Any scan-path or API performance change. Those are real and separately
  motivated, but this plan is about not losing data.

## Order is a correctness requirement

`starred_plans.plan_id` is a foreign key into `plans` (revision `p2_006`), and
`account`'s balance is derived from realised P&L in `trades`. The import order
is therefore `watchlist, state, plans, starred, trades, account, journal` and
the plan states it once.

## Backups gate the stage flip, not the import

An import into a database nothing reads is reversible by dropping the volume.
A `dual` flip is not, in the same way: from that point PostgreSQL holds writes
that JSON also holds, and a later `db` flip trusts them. v67's P6-03 (nightly
`pg_dump`) and P6-04 (a restore exercised for real, once) are unbuilt.

**This plan flips `watchlist` and `state` to `dual` without them, and that is
an accepted, bounded risk:** both stores are small, both are fully
reconstructible from their JSON files, which `dual` keeps writing, and neither
is read from the database at this stage. Backups become a hard prerequisite
before any store reaches `db`, and before `trades` or `plans` reach `dual`.

## Verification

- Every fix lands with a test that fails first. D1 and D2 have natural
  regression tests — a trade record whose key is `id`, and a record carrying
  `float("nan")` — that fail against today's code for exactly the observed
  reason.
- Authoritative parity is `parity_report.py --all`, which must report OK for
  all seven stores against production data before the stage flip.
- The suite runs once, as the plan's own final verification task.

## Success criteria

1. `parity_report.py --all` reports OK for all seven stores on production.
2. `trades` imports 802 of 802; `journal` imports 609 of 609.
3. `run_import`'s verdict agrees with `parity_report`'s for every store — no
   store reports FAILED while parity reports OK, or the reverse.
4. `watchlist` and `state` run at `dual` on production for a full trading day
   with no divergence logged by `core/db/dual.py`.
5. JSON remains the read path throughout; no user-visible behaviour changes.
