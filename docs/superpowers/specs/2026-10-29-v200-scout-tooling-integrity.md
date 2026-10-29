# v200 — Scout tooling integrity: real alert times, stall exclusion, era split, gap names, two-sided merge

**Version:** ui 1.36.2 · bot 2.15.5
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-engineer

## Why

The 2026-10-21 and 2026-10-29 trade-scout slates sent no row onward. Most of
their noise came from defects in the tooling, not the book. The 10-29
quant-researcher panel (`docs/superpowers/results/2026-10-29-scout-slate.md`
§ Panel review) named them:

- **Alert hour is fake for most of the book.** `scripts/ops/export_book_rows.sh`
  exports `status_history[0].at` as `plan_first_status_at`.
  - Market-entry plans stamp that entry with `created_at`, a bar date
    (`swingbot/core/planning/builders.py:488,711`).
  - Non-market plans start with an empty history, so their first entry is the
    later fill or expiry (`plan_types.py:45,252-265`).
  - `_alert_hour` (`scripts/reports/autopsy/rows.py:125-132`) reads a
    date-only value as 00:00 UTC, which is 20:00 ET. In the 10-29 export,
    521 trade rows were date-only, 74 timestamped (fill times) and 236
    empty. The `alert_hour=20` cell (N 518) and the `after_close 613` tally
    are therefore artefacts.
  - Plans have carried a real wall-clock `issued_at` since 2026-09-16 (v87,
    `9afac464`; `swingbot/core/scanning/analyze.py:543`), but the export never
    reads it. Production on 2026-10-29: 0 of 373 Jul–Aug plans carry it, 96
    of 140 September plans and 204 of 204 October plans do.
- **The August stop-monitor stall is still in the stop cells.** The stall ran
  from 2026-08-03 16:18 UTC until the 08-04 18:55 and 08-05 15:34 catch-up
  batches (2026-10-21 slate § Stop-enforcement check).
- **No exit-model era split.** Exit and monitor changes landed on 2026-09-03,
  09-09, 09-10 (`f8c8eaad`) and 09-11 (`b4ef2e87`, `breakeven_trigger`).
- **The gap bucket names invert in readers' heads.** In `_gap`
  (`scripts/reports/autopsy/bars.py:128-137`), positive means the open is
  worse than the planned entry, so `favourable` means an open at a better
  price. Scouts misread it on 10-21 and again on 10-29.
- **The merge is one-sided and accepts evidence that is not known at entry.**
  `scripts/dev/scout_merge.py:294-300` keeps a row only if the Δ lower bound is
  above 0. It also accepts cells cut on the outcome, such as `exit_reason`,
  `weekend_hold` and `fomc_proximity` (which reads the exit date), and on the
  fill day, `open_gap_bucket`.

The fix makes the next slate trustworthy. It changes no entry, exit,
threshold or live alert.

## Goals

1. A trade's alert hour comes only from a real issue time (`issued_at`, live or
   backfilled from Discord). Otherwise it is unknown.
2. Plans issued before 2026-09-16 get their issue time back from Discord where
   exactly one one-to-one match exists.
3. Every trade open during the stall leaves the row set before any cell,
   complement, tally or pooled figure is computed, and is reported on a line
   of its own.
4. Every cell also reports `pre`, `straddle` and `post` era numbers.
5. Gap bucket names say which side of the planned entry the open was on.
6. The merge ranks *exploit* and *avoid* rows on one comparable scale. It
   rejects cells that are not known at entry.

## Non-goals and anti-goals

- No change to which plans are issued, filled, sized, stopped or closed.
- No new cut or hypothesis.
- No re-run of a closed pre-registration, and no claim drawn from a
  re-autopsied cell. q values from the 10-29 autopsy are never quoted against
  v200 ones, because N changes and every q moves.
- **Anti-goal:** a backfill that guesses. An ambiguous match stays unknown,
  and the match rate is reported.
- **Anti-goal:** a production write outside a committed revision shipped
  through a normal deploy.

## Design

### Part 1 — Alert time (partner choice: stamp going forward plus a Discord backfill)

1. **Export.** `export_book_rows.sh` adds `plan_issued_at`
   (`p.doc->>'issued_at'`) and `plan_issued_at_source`
   (`p.doc->>'issued_at_source'`) to the `trade` and `plan` branches of the
   `rows` UNION (lines 27-125), appended at the end of the column list.
   - `rejections` is a log grep with no plan doc, so it is unchanged.
   - The column list pinned at line 19 and `tests/scout/test_export_script.py`
     change together.
   - Older CSVs, which lack the columns, still parse, with the hour unknown.
2. **Source tag.** `TradePlanV2` gains `issued_at_source: str | None = None`
   (an **add**, `docs/claude/schema-evolution.md` § The four operations).
   - `analyze.py:543` sets it to `"live"` only on the `issued_at is None`
     branch, where it stamps the wall clock. Replay passes `issued_at`
     (`qualify.py:59,95`; `scan_replay.py:213`) and leaves it `None`.
   - The comment at `plan_types.py:123-129` is updated to say that
     `discord`-sourced values exist for pre-v87 records.
   - A test pins that the field round-trips through `plan_from_dict`.
3. **Autopsy hour.** `_alert_hour` uses `plan_issued_at` only. Neither
   `plan_first_status_at` (a fill or expiry time for non-market plans, which
   would be lookahead) nor `created_at` (a bar date by design,
   `builders.py:452,696`) is an hour source any more. The report prints
   alert-hour coverage by source (`live`, `discord`, unknown) beside every
   `alert_hour*` cell and tally.
4. **Discord backfill.** Two steps. Nothing is generated on the VM.
   - **a. Read (dry run).** `scripts/ops/backfill_issued_at_discord.py` runs
     in the bot container.
     - **Access:** a REST-only HTTP client (`discord.http` / `Client.login`
       without `connect`), so no gateway session races the live bot. The
       token comes from the container environment and is never printed.
     - **Source:** `DISCORD_CHANNEL_TRADES_ID` only, never the
       `DISCORD_CHANNEL_TRADES_SIMPLE_ID` mirror (`swingbot/config.py:111-114`).
       History from 2026-07-01 to 2026-09-16 inclusive, bot-authored
       messages only.
     - **Match key:** ticker, direction, strategy, `horizon_key`, and an
       Eastern date equal to the plan's `created_at` date or the next trading
       day.
     - **One-to-one:** a plan matches when it has exactly one candidate
       message and that message has exactly one candidate plan. Otherwise
       every plan involved stays unknown.
     - **Output:** a CSV with plan_id, candidate counts both ways, message id,
       message time (UTC ISO), and the lag in hours from the bar date. It
       also prints the match rate and the lag distribution. It writes
       nothing.
     - **Script docstring:** the embed fields used for matching (read from
       `swingbot/core/scanning/alert_embeds.py` and sampled messages of the
       period).
   - **b. Revision (committed).** The CSV comes back to this machine. The
     matched `plan_id → (issued_at, "discord")` pairs are pinned in a
     committed data revision, `swingbot/core/db/migrations/versions/v200_001_…`,
     whose `down_revision` is the current head
     (`schema-evolution.md` § Revision ids). It follows the
     `v173_001_manual_bulk_retag.py:1-60` contract:
     - It locks rows with `SELECT … FOR UPDATE`.
     - It refuses (raises) when only some of the pinned plans exist, or when
       a pinned plan already carries `issued_at`.
     - It logs and writes nothing when none of the pinned ids exist, so the
       test DB, a fresh install and the local replica still upgrade.
     - It sets the two doc fields only.
     - `downgrade()` removes both fields from exactly the pinned ids.
   - **c. Ship.**
     - The partner sees the dry-run match rate before the revision is
       written.
     - The revision is verified up and down on the shared `swing-db` replica
       (`/replicate-prod-db` first).
     - The last PITR drill is checked (`schema-evolution.md` § Before
       running a data revision on production; the rollback is
       `scripts/ops/rollback_to.sh`).
     - It ships via the normal deploy (`alembic upgrade head`,
       `docs/deploy/DEPLOY_HETZNER.md`).
     - The UPDATE fires the `plans` NOTIFY trigger (`swingbot/core/db/events.py:8`)
       once per touched row, so the admin UI's SSE stream sees a burst. That
       is expected, and the run note says so.

### Part 2 — The August stall exclusion

`scripts/reports/autopsy/exclusions.json` holds
`{"stall_2026_08": {"reason": …, "rule": …, "windows": [...], "trade_ids": [...]}}`.

- **Rule:** exclude every trade **open at any moment** in a stall window.
  That means opened before the window's end and not closed before its
  start, whatever the close reason or time. Selecting on the catch-up close
  alone would keep the lucky survivors.
- **Windows:**
  - from `2026-08-03 16:18:02` UTC (the last close before the gap) to
    `2026-08-04 18:55:43` UTC;
  - the 08-05 gap ending at `15:34:08` UTC, with its start set from the last
    close before that batch.
  - The builder derives both from the production export and records them in
    the file.
- **Placement:** the exclusion is applied right after rows load, before
  `cut_cells`. Excluded trades leave cells, complements, tallies, give-back
  (`exits.py:92`) and the header's pooled figures.
- **Report:** one line with N, gross ExpR and worst R for the excluded set.
  The manifest records the file's SHA-256.
- **Tests:**
  - the `trade_ids` are rebuilt from the rule against a fixture export and
    match exactly;
  - no complement contains an excluded id.
- **Test routing:** `scripts/dev/select_tests.py` `DATA_READERS` gains a row
  routing `exclusions.json` to the autopsy tests.

### Part 3 — Exit-era split

- **Boundary:** the production **deploy time** of the last exit/monitor
  change, `b4ef2e87`. The commit date is not used. The builder reads it from
  the deploy record (`version_history.json` or the VM's deploy log) and
  records the value and its source in the autopsy manifest.
- **Eras:** `pre` means closed before the boundary, `post` means opened after
  it, and `straddle` means opened before and closed after. A boundary-day
  entry counts as `straddle`, because the change landed intraday.
- **Report:** every cell row in the markdown and JSON gains `pre`,
  `straddle` and `post` sub-objects with N, WR and net ExpR. Era numbers
  carry no CI and no q. A cell whose `pre` and `post` signs differ is noted
  `era sign flip`.
- **Merge:** the merge does not read the era fields.

### Part 4 — Gap bucket names

- **Rename:** `_open_gap_bucket` returns `open_better`, `flat`,
  `open_worse_small` and `open_worse_large`. Thresholds are unchanged.
- **Sign note:** the same sentence on the sign goes into `_gap`'s docstring,
  the autopsy notes, the three scout role skills, `.claude/agents/scout.md`
  and `.claude/skills/setup-scout/references/playbook.md`.
- **Past documents:** past autopsies and slates are not rewritten.

### Part 5 — Two-sided merge with a known-at-entry rule (partner choice)

1. **Schema marker.** The autopsy JSON header gains `"autopsy_schema": 2`. It
   is absent, which means 1, in every older file
   (`scripts/reports/autopsy/report.py:100-105`).
2. **`defined_at` per cut.** It is one of `entry`, `fill` or `outcome`, set
   in `cuts.py` beside each cut.
   - `outcome` covers any cut reading something after the fill: `exit_date`,
     `closed_at`, `exit_price`, `close_reason`, `mfe_r`, `mae_r`,
     `holding_days`, or bar fields computed after the fill. It includes at
     least `exit_reason`, `near_tp_close`, `gap_through_stop`,
     `holding_bucket`, `weekend_hold` and `fomc_proximity`.
   - `fill` covers cuts measured on the bar the fill selected, at least
     `open_gap_bucket`, because whether that bar is the fill day depends on
     its later high or low.
   - `gapped_through_entry` stays `entry`, because the fill happens at the
     open.
   - A test lists every cut and asserts that its tag matches the fields it
     reads.
3. **Row field.** Scout rows gain `direction: exploit | avoid` after `edge:`.
   The three role skills' `## Row format`, `.claude/agents/scout.md`, the
   trade-scout skill's merge description and the parser change together.
   Every one of these skill and agent edits ships its Codex mirror
   (`python scripts/dev/sync_codex.py`) in the same commit. A row without
   the field is dropped as `missing direction`.
4. **Rule (schema 2).**
   - `exploit` keeps a row when the Δ lower bound is above 0.
   - `avoid` keeps a row when the Δ upper bound is below 0.
   - Both still need q ≤ 0.10.
   - A cell whose cut is `fill` or `outcome` drops with
     `cell <id> is <tag>-defined (not known at entry)`.
   - In a two-value cut (`friday_entry`, `gapped_through_entry`, …), "avoid
     X" and "exploit not-X" count as one rule, deduplicated by cut.
5. **Ranking.**
   - **Display:** each row shows its projected pooled change. For exploit,
     keeping only the cell gives cell ExpR minus pooled ExpR. For avoid,
     dropping the cell gives about (1 − share) · Δ. Both come from the JSON.
   - **Sort:** the key stays the bound. The exploit key is `-lower`
     ascending, as today, and the avoid key is `+upper` ascending.
6. **Schema 1 (legacy).** An older autopsy re-merges under the old one-sided
   rule with no ban. The slate says `legacy autopsy (schema 1): no
   known-at-entry check` at the top. That settles the old conflict between
   backward compatibility and the loud failure: the merge fails loudly only
   when a schema-2 JSON lacks `defined_at` on a cut.
7. **BH family.** It is unchanged. Every cell, outcome and fill ones
   included, stays in the single BH pass, with the stall trades excluded.
   Removing cells would shrink the family and lower q unasked.

## Constraints

- Every touched function stays under complexity 15
  (`scripts/dev/complexity_gate.py`).
- Tests ship with each part, edge and empty cases included. Part 1 ships the
  export column pin and the round-trip test. Part 2 ships the rule rebuild
  and the complement test. Part 5 ships the cut tag audit.
- `swingbot/core/` changes only in the `issued_at_source` field, its one live
  stamp and the comment.
- Production touches:
  - a read-only export;
  - a read-only REST history read;
  - one committed data revision, shipped through a normal deploy after the
    partner has seen the dry-run.
  - Everything is mirrored into the repo (`docs/claude/working-conventions.md`).

## Left to the builder

- Which embed fields carry ticker, direction, strategy and horizon in
  July–September messages.
- The exact start of the 08-05 stall window, and the deploy timestamp of
  `b4ef2e87`. Both values and their sources are recorded.
- The column layout of the era sub-objects in the markdown table.

## Verification

1. Run the autopsy on a fresh export with the new columns. Check that it
   reports alert-hour coverage by source, that no hour comes from a
   date-only or fill stamp, and that the stall line appears.
2. Re-merge the 10-29 scout rows with `direction` added.
   - `exit_reason=stop`, `gap_through_stop` and the two `open_gap_bucket`
     rows drop as not known at entry.
   - The 10-29 JSON (schema 1) re-merges under the legacy rule and carries
     the banner.
3. The partner sees the backfill dry-run match rate before the revision is
   written.
4. The full suite runs green once, as the plan's final task.

## Panel review

Run 2026-10-29 over `8309e024` (staff-engineer, quant-engineer, both on opus).
All findings applied.

- staff-engineer [BLOCKING]: the revision must not be generated on the VM, or
  the next `alembic upgrade head` breaks — **applied**: the dry-run CSV is
  pinned in a committed revision shipped by normal deploy (Part 1.4b-c).
- staff-engineer [BLOCKING]: no refusal or no-op contract on a trading-store
  write — **applied**: the v173_001 contract (Part 1.4b).
- staff-engineer [ADVISORY]: the mirror channel would double every candidate
  — **applied**: `DISCORD_CHANNEL_TRADES_ID` only.
- staff-engineer [ADVISORY]: horizon is missing from the match key —
  **applied**, with one-to-one matching.
- staff-engineer [ADVISORY]: a gateway login would race the live bot —
  **applied**: REST-only.
- staff-engineer [ADVISORY]: `rejections` is a log grep, and the column pin
  test is affected — **applied** (Part 1.1).
- staff-engineer [ADVISORY]: the legacy re-merge contradicts the loud failure
  — **applied**: `autopsy_schema` (Part 5.1, 5.6).
- staff-engineer [ADVISORY]: the Codex mirror is needed for Part 5's skill
  edits, `scout.md` and trade-scout too — **applied** (Part 5.3).
- staff-engineer [ADVISORY]: `exclusions.json` needs a `DATA_READERS` row —
  **applied** (Part 2).
- staff-engineer [ADVISORY]: `issued_at_source` belongs on the `None` branch,
  and the field comment needs updating — **applied** (Part 1.2).
- staff-engineer [ADVISORY]: the PITR check, the replica verification and the
  NOTIFY burst were unwritten — **applied** (Part 1.4c).
- quant-engineer [BLOCKING]: a timestamped `plan_first_status_at` is a fill
  or expiry time, which is lookahead — **applied**: the hour comes from
  `issued_at` only.
- quant-engineer [BLOCKING]: `open_gap_bucket` is measured on the
  fill-selected bar — **applied**: tagged `fill` and banned (Part 5.2).
- quant-engineer [ADVISORY]: `fomc_proximity` reads `exit_date` —
  **applied**: listed, and the rule is widened to derived fields.
- quant-engineer [ADVISORY]: a stall rule keyed on close time keeps the
  survivors — **applied**: every trade open in a window is excluded, and a
  rule-rebuild test is added.
- quant-engineer [ADVISORY]: era by commit date and by entry mislabels trades
  — **applied**: boundary at the deploy time of `b4ef2e87`, plus a `straddle`
  bucket.
- quant-engineer [ADVISORY]: `created_at` as an hour source revives the
  artefact — **applied**: dropped.
- quant-engineer [ADVISORY]: the Discord match needs a one-to-one check and
  the lag recorded — **applied**.
- quant-engineer [ADVISORY]: the exclusion must also cover complements and
  pooled figures — **applied** (Part 2).
- quant-engineer [ADVISORY]: BH family membership was unstated — **applied**:
  unchanged (Part 5.7), and 10-29 q values are never quoted against v200
  ones.
- quant-engineer [ADVISORY]: the schema marker, mirrored duplicates and the
  incomparable ranking — **applied** (Part 5.1, 5.4, 5.5).
