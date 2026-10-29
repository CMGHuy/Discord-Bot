# v200 — Scout tooling integrity: real alert times, stall exclusion, era split, gap names, two-sided merge

**Version:** ui 1.36.2 · bot 2.15.5
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer

## Why

The 2026-10-21 and 2026-10-29 trade-scout slates sent no row onward. Most of
their noise came from defects in the tooling, not from the book. The 10-29
quant-researcher panel (`docs/superpowers/results/2026-10-29-scout-slate.md`
§ Panel review) named them:

- **Alert hour is fake for most of the book.** `scripts/ops/export_book_rows.sh`
  exports `status_history[0].at` as `plan_first_status_at`. Market-entry plans
  stamp that entry with `created_at`, a bar date
  (`swingbot/core/planning/builders.py:488,711`). `_alert_hour`
  (`scripts/reports/autopsy/rows.py:125-132`) reads the date-only value as
  00:00 UTC, which is 20:00 ET. In the 10-29 export, 521 trade rows were
  date-only, 74 timestamped and 236 empty. The `alert_hour=20` cell (N 518)
  and the `after_close 613` tally are artefacts. Plans have carried a real
  wall-clock `issued_at` since 2026-09-16 (v87, `9afac464`;
  `swingbot/core/scanning/analyze.py:543`), but the export never reads it.
  The production count on 2026-10-29: 0 of 373 Jul–Aug plans carry it, 96 of
  140 September plans and 204 of 204 October plans do.
- **The August stop-monitor stall is still in the stop cells.** 32 trades
  closed in the 2026-08-04 18:55 and 2026-08-05 15:34 catch-up batches
  (2026-10-21 slate § Stop-enforcement check). 18 of them closed below
  −1.05R gross, and the worst at −6.03R. They feed `exit_reason=stop` and
  `gap_through_stop`.
- **No exit-model era split.** Exit changes landed on 2026-09-03, 09-09 and
  09-10, and a full-window cell mixes the eras.
- **The gap bucket names invert in readers' heads.** In `_gap`
  (`scripts/reports/autopsy/bars.py:128-137`) positive means the open is
  *worse* than the planned entry. `favourable` therefore means an open at a
  *better* price than planned, which for a stop-buy means the trigger was not
  reached. Scouts misread it on 10-21 and again on 10-29, after the 10-21
  panel had flagged it.
- **The merge is one-sided and accepts outcome-defined evidence.**
  `scripts/dev/scout_merge.py:294-300` keeps a row only if the Δ lower bound is
  above 0, so an idea that removes a losing cell can never rank. It also
  accepts cells cut on the outcome itself (`exit_reason`, `gap_through_stop`,
  `weekend_hold`, …). Such cells can only describe trades after the fact:
  `weekend_hold=yes` is survivorship, because 749 of the 756 non-weekend trades
  lasted under 3 calendar days.

The fix makes the next slate trustworthy. It changes no entry, exit,
threshold or live alert.

## Goals

1. Every closed trade's alert hour comes from a real timestamp or is reported
   unknown. A date-only stamp is never read as a time.
2. Plans issued before 2026-09-16 get their alert time back from Discord where
   one unambiguous match exists.
3. The autopsy reports the stall trades as their own line and excludes them
   from every cell.
4. Every cell row also carries its pre- and post-era numbers.
5. Gap bucket names say which side of the planned entry the open was on.
6. The merge ranks *exploit* and *avoid* rows symmetrically and rejects
   outcome-defined cells as evidence for either.

## Non-goals and anti-goals

- No change to which plans are issued, filled, sized, stopped or closed.
- No new cut or hypothesis. This spec makes existing cuts honest.
- No re-run of any closed pre-registration, and no claim drawn from a
  re-autopsied cell.
- **Anti-goal:** a backfill that guesses. An ambiguous or missing Discord match
  stays unknown, and the match rate is reported.
- **Anti-goal:** any write to production other than the one backfill revision.
  The Discord read is read-only.

## Design

### Part 1 — Alert time (partner choice: stamp going forward plus a Discord backfill)

1. **Export.** `export_book_rows.sh` adds two columns, `plan_issued_at`
   (`p.doc->>'issued_at'`) and `plan_issued_at_source`
   (`p.doc->>'issued_at_source'`), to both the `rows` and the `rejections`
   queries. Existing columns keep their names and positions; the new ones go
   at the end, so older CSVs still parse.
2. **Source tag.** `TradePlanV2` gains `issued_at_source: str | None = None`
   (an **add** per `docs/claude/schema-evolution.md` § The four operations: no
   migration). The live path in `analyze.py:543` sets it to `"live"` whenever
   it stamps the wall clock. A replay that passes `issued_at` leaves it `None`.
   The field must exist on the dataclass, or `plan_from_dict` drops it and the
   next save loses it.
3. **Autopsy.** `_alert_hour` takes `plan_issued_at` first. Next it takes a
   `plan_first_status_at` or `created_at` value only if that value carries a
   time component, judged by the raw string, not by 00:00 UTC. Otherwise the
   hour is `None`. A 10-character date is never parsed as a time.
   `alert_hour_session` and any other consumer of the hour follow the same
   rule. The report states how many rows were covered by each source (`live`,
   `discord`, timestamped status, unknown).
4. **Discord backfill.** This is a one-off script,
   `scripts/ops/backfill_issued_at_discord.py`, run inside the bot container
   on the VM. It reads, never posts.
   - It logs in with the bot token from the container's environment, never
     printing it. It walks the history of the alert channels the bot posts
     plans to, from 2026-07-01 to 2026-09-16 inclusive, and keeps only
     messages authored by the bot.
   - It matches each plan that has no `issued_at` to a message by ticker,
     direction, strategy, and an Eastern calendar date equal to the plan's
     `created_at` date or the next trading day. The builder reads the
     embed or content fields that carry these from
     `swingbot/core/scanning/alert_embeds.py` and the embed history of that
     period.
   - **One candidate** gives `issued_at = message.created_at` (UTC ISO) and
     `issued_at_source = "discord"`. **Zero or several candidates** leave the
     plan untouched, and the plan is listed in the dry-run report.
   - Default mode is `--dry-run`. It writes a CSV of plan_id, candidate count,
     chosen message time and match key into a scratch path, and prints the
     match rate. `--apply` writes the matched values as an Alembic **data
     revision** (an `UPDATE` setting the two doc fields only where `issued_at`
     is absent). Its `downgrade()` removes both fields from the rows it
     touched, keyed by `issued_at_source = 'discord'`. The pre-run check in
     `schema-evolution.md` § Before running a data revision on production
     applies.
   - The partner sees the dry-run match rate before `--apply` runs.

### Part 2 — The August stall exclusion

The exclusion is a committed, versioned list:
`scripts/reports/autopsy/exclusions.json` holds `{"stall_2026_08": {"reason": …,
"rule": …, "trade_ids": [...]}}`. The rule closes trades in
`[2026-08-04 18:55:00, 18:56:00)` UTC or `[2026-08-05 15:34:00, 15:35:00)` UTC
whose close reason is the price monitor. The ids are derived once from the
production export by that rule and committed, so the list is reproducible from
the rule and auditable. The autopsy drops these trades from every cell, prints
one line with N, gross ExpR and worst R for the excluded set, and records the
exclusion file's SHA-256 in its manifest.

### Part 3 — Exit-era split

An era boundary constant is set at `2026-09-10` (the last exit-model change).
A trade belongs to `pre` if `opened_at` (Eastern date) is ≤ 2026-09-10,
otherwise to `post`. *(My call: era by entry, since the exit model in force
at entry decided the targets.)* Every cell row in the markdown table and the
JSON gains `pre` and `post` sub-objects with N, WR and net ExpR (no CI and no
q: the BH family stays the full-window cells, unchanged). If a cell's sign
differs between eras, the cell's notes column says `era sign flip`. The merge
does not read the era fields. They exist for the panel and the partner.

### Part 4 — Gap bucket names

`_open_gap_bucket` returns `open_better`, `flat`, `open_worse_small` and
`open_worse_large` in place of `favourable`, `flat`, `adverse_small` and
`adverse_large`. Thresholds are unchanged. `_gap`'s docstring and the autopsy
markdown's notes gain one sentence stating the sign. The scout role skills
(`exit-harvester`, `setup-scout`, `regime-desk`) and
`.claude/skills/setup-scout/references/playbook.md` gain the same sentence,
with the Codex mirror via `scripts/dev/sync_codex.py` in the same commit.
Past autopsies and slates are not rewritten. The merge accepts the old cell
ids only when reading an autopsy JSON whose manifest predates v200, so
re-merging an old slate still works.

### Part 5 — Two-sided merge with an outcome ban (partner choice)

1. **Row field.** Scout rows gain a required `direction: exploit | avoid` line,
   placed after `edge:`. The three role skills' `## Row format` sections and
   the parser in `scout_merge.py` change together. A row without it is dropped
   with reason `missing direction`.
2. **Rule.** For `exploit`, keep when the Δ lower bound is above 0. For `avoid`,
   keep when the Δ upper bound is below 0. Both still need q ≤ 0.10, unchanged.
   The drop reason names the bound that failed and the direction.
3. **Outcome ban.** Each cut in the autopsy JSON gains
   `defined_at: entry | outcome`. Outcome cuts are those whose value depends on
   anything after the fill: `exit_reason`, `near_tp_close`, `gap_through_stop`,
   `holding_bucket`, `weekend_hold`, and any other cut the builder finds reading
   `closed_at`, `exit_price`, `close_reason`, `mfe_r`, `mae_r` or
   `holding_days`. The merge drops a row citing an outcome cut with reason
   `cell <id> is outcome-defined (descriptive only)`. Its decision reads
   `defined_at` from the JSON and never keeps a hard-coded list. An autopsy
   JSON without `defined_at` fails the merge loudly, instead of passing every
   cell.
4. **Ranking.** For avoid rows, ranking uses `−upper` where exploit rows use
   `lower`, so both sort by distance from zero.

## Constraints

- Every function touched stays under complexity 15
  (`scripts/dev/complexity_gate.py`).
- Tests ship with each part, edge and empty cases included:
  - a date-only stamp gives hour `None`
  - the backfill gives 0, 1 and 2 candidates
  - the stall list is applied and its line printed
  - the era split includes the sign-flip note
  - the merge covers avoid/exploit at both bounds, a missing direction, an
    outcome cell, and missing `defined_at`
  - `issued_at_source` round-trips through `plan_from_dict`
- No change to `swingbot/core/` beyond the `issued_at_source` field and its
  one live stamp.
- The production steps are a read-only export, a read-only Discord history
  read, and one data revision after the partner has seen the dry-run.
  Everything is mirrored into the repo per `docs/claude/working-conventions.md`.

## Left to the builder

- The exact embed fields used for matching. These are read from
  `alert_embeds.py` and a sample of July–September messages, and recorded in
  the script's docstring.
- How the backfill finds the alert channel ids (config or `.env`, never
  hard-coded).
- The layout of the `pre`/`post` columns in the markdown table, which must stay
  readable at the current table width.

## Verification

1. Run the autopsy against the 2026-10-29 export and new export columns. It
   reports alert-hour coverage by source, and no hour-20 cell built from
   date-only stamps.
2. Re-merge the 10-29 scout rows (with `direction` added). The `exit_reason=stop`
   and `gap_through_stop` rows drop as outcome-defined. The two `open_better`
   rows (fill-day open, known before any outcome, so `entry`) are judged by
   the avoid rule.
3. The backfill dry-run match rate goes to the partner before `--apply`.
4. The full suite runs green once, as the plan's final task.
