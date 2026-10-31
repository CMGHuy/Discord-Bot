# Scout tooling integrity implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [Scout tooling integrity](../specs/2026-10-29-v200-scout-tooling-integrity.md)

**Goal:**

The 2026-10-21 and 2026-10-29 trade-scout slates sent nothing onward, and the
10-29 quant-researcher panel traced most of their noise to the tooling, not
the book. The alert hour is fake for most trades: the export reads
`status_history[0].at`, which is a bar date for market plans and a fill or
expiry time for the rest, so the `alert_hour=20` cell (N 518) and the
`after_close 613` tally are artefacts. The August stop-monitor stall still sits
inside every stop cell. Cells mix exit-model eras across the 09-03..09-11
changes. The gap bucket names (`favourable`, `adverse_*`) are read backwards by
scouts. And `scout_merge.py` keeps only cells whose Δ lower bound is above
zero while accepting cells cut on the outcome or the fill day, which a scout
can never act on at entry.

Once shipped, the alert hour comes only from a real issue time:
`issued_at` stamped live (now tagged `issued_at_source = "live"`), or, for
plans issued before v87 (2026-09-16), recovered from the Discord alert message
by an exact `plan_id` match or a one-to-one key match, pinned in a committed
data revision `v200_001`. Everything else is `unknown`, and the report says how
much of each it has. Trades open at any moment during the August stall leave
the row set before any figure is computed and are reported on one line. Every
cell gains `pre` / `straddle` / `post` era numbers around the production deploy
time of `b4ef2e87`. Gap buckets become `open_better` / `flat` /
`open_worse_small` / `open_worse_large`. The merge becomes two-sided
(`exploit` keeps a positive lower bound, `avoid` a negative upper bound), each
cut carries `defined_at` (`entry` / `fill` / `outcome`), and a schema-2 autopsy
bans `fill`- and `outcome`-defined cells; a schema-1 autopsy re-merges under the
old rule with a banner.

Left alone: which plans are issued, filled, sized, stopped or closed; every
threshold; the BH family (all cells stay in one pass); past autopsies and
slates; every closed pre-registration. `swingbot/core/` changes only by the
`issued_at_source` field, its one live stamp and its comment. Production sees
read-only exports and a read-only Discord REST read; the one write is the
committed revision, shipped by the partner's normal deploy after they have seen
the dry-run match rate. That deploy is not a plan task.

Success is the spec's Verification: an autopsy on a fresh export reports
alert-hour coverage by source with no hour from a date-only or fill stamp and
prints the stall line; the 10-29 scout rows, re-merged with `direction`, drop
`exit_reason=stop`, `gap_through_stop` and both `open_gap_bucket` rows as not
known at entry; the 10-29 JSON re-merges under the legacy rule with its banner;
the partner has seen the backfill match rate before `v200_001` was written; the
full suite is green once. q values from the 10-29 autopsy are never compared
with v200 ones.

**Architecture:** Five strands over the scout tooling (`scripts/ops/`,
`scripts/reports/autopsy/`, `scripts/dev/scout_merge.py`, the scout skills),
plus one plan-doc field in `swingbot/core/planning/plan_types.py` and one
Alembic data revision copied from the `v173_001` contract. Production facts the
code needs (the `b4ef2e87` deploy time, the two stall windows) are read once,
read-only, in V200-1 and recorded in a committed results file that later tasks
copy constants from. The Discord backfill is a read-only dry-run script, then a
human checkpoint, then the pinned revision, then a replica up/down check.

**Tech stack:** Python 3.11, bash/psql (export), discord.py REST client
(`Client.login` without `connect`), SQLAlchemy/Alembic, pytest;
`scripts/dev/sync_codex.py` for skill/agent mirrors.

## Global Constraints

- `Bump: bot patch` — applied at `/close-out`, not by any task. No `VERSION.json` edit in a task.
- Implement in a worktree under `.claude/worktrees/` (name per `document-lifecycle.md`). Every command uses absolute paths or `git -C <wt>`; never `cd`. Stage explicit paths only; never `git add -A`.
- `swingbot/core/` changes only in V200-2: `TradePlanV2.issued_at_source`, its `"live"` stamp on the `issued_at is None` branch of `analyze.attach_plan_v2`, and the field comment. No other core file, no entry/exit/threshold/sizing/live-alert change.
- Hour sources: `plan_issued_at` only. `plan_first_status_at` and `plan_created_at` are never an hour source again (lookahead / bar-date artefact; spec Part 1.3).
- An ambiguous Discord match stays unknown. No guessed backfill. The backfill script writes nothing (CSV to stdout, summary to stderr). Never the `DISCORD_CHANNEL_TRADES_SIMPLE_ID` mirror channel. REST only (no gateway `connect`). Never print, echo or log the token or any `.env` value.
- Production: read-only only (`scripts/ops/ssh-hetzner.sh`, never raw ssh). No task deploys, runs `alembic upgrade` on the VM, or writes to the production DB. The `v200_001` revision is never generated on the VM. Raw export CSVs and the dry-run CSV stay in the scratchpad, never committed (the revision's pinned mapping and the stall fixture's id/timestamp extract are the only committed derivatives).
- Stall rule: exclude a trade when `opened_at < window.end` and `closed_at >= window.start` (open at any moment in the window), whatever its close reason. Applied before cells, complements, tallies, give-back and header pooled figures.
- Era rule: `pre` = closed before the boundary; `post` = opened after it and not on the boundary's Eastern date; `straddle` = everything else with both timestamps (opened before or on the boundary day, closed after). Era numbers carry no CI and no q; the merge never reads them.
- BH family unchanged: every cell (fill- and outcome-defined included) stays in the single BH pass, over trades with the stall trades removed.
- Every new or changed function stays below cyclomatic complexity 15 (`python -m radon cc -s -n C <files>` prints nothing; `python scripts/dev/complexity_gate.py`). Table-drive new branches in `scout_merge.py`.
- Every `.claude/skills/*` or `.claude/agents/*` edit ships its Codex mirror in the same commit: `python <wt>/scripts/dev/sync_codex.py`, then `python <wt>/scripts/dev/sync_codex.py --check` prints `Codex mirror is current.`
- Tests: scout/autopsy/merge/export/backfill-script tests go in `tests/scout/` (suite `scout`, no `suites.toml` change); the revision test goes in `tests/db/`. Per-task verification is the narrow run `python <wt>/scripts/dev/testrun.py file <test>`; the one full-suite run is V200-18. A task that runs database tests (V200-7, V200-8, V200-18) runs `/replicate-prod-db` first into the shared `swing-db` container when the replica has not been synced this session.
- Past autopsies (`docs/superpowers/results/*-book-autopsy.*`) and slates are never rewritten.

## Review Focus

- An old export CSV without `plan_issued_at` / `plan_issued_at_source` (every CSV before V200-3): it must load, with every hour `unknown`, and a CSV missing any *other* column is still refused. Pinned in V200-3 (`test_an_old_csv_without_the_issued_columns_loads_with_unknown_hours`, `test_a_wrong_header_is_still_refused_naming_the_gap`).
- A plan carrying `issued_at` written before V200-2 (no `issued_at_source`): it counts as `live`, not `unknown`. Pinned in V200-3 (`test_issued_at_without_a_source_counts_as_live`).
- A trade opened before a stall window and closed by the catch-up batch with a *win*, or closed manually inside the window: excluded all the same; a trade closed one second before the window start is kept. Pinned in V200-9 (`test_open_at_any_moment_is_excluded_whatever_the_close`, `test_closed_just_before_the_window_is_kept`).
- A Discord message that matches two plans by key, or two messages that match one plan: every plan involved stays unknown; a plan with an exact `plan_id` message is matched by that message and leaves the key pool before key matching. Pinned in V200-5 (`test_a_two_way_key_collision_leaves_every_plan_unknown`, `test_an_exact_plan_id_match_wins_over_key_candidates`).
- A two-value cut offered both as "avoid X" and "exploit not-X" by two roles, and a schema-2 cell without `defined_at`: one rule kept, and the merge fails loudly. Pinned in V200-15 (`test_avoid_x_and_exploit_not_x_dedupe_by_cut`, `test_schema_2_cell_without_defined_at_fails_loudly`).

## Parallelisation

At most 2 implementers at once (`CLAUDE.md`). Edges:

- **V200-1** (production read) has no code dependency; it must land before V200-9 (stall windows) and V200-11 (era boundary), which copy its recorded values.
- **V200-2** (`swingbot/core` field) is disjoint from everything else and may run with any task.
- **V200-3 → V200-4:** both edit the row/report path; V200-4 consumes `BookRow.hour_source` from V200-3.
- **V200-5 → V200-6 → (partner go) → V200-7 → V200-8:** V200-6 runs V200-5's script; V200-7 pins V200-6's CSV and **may not start before the partner has seen V200-6's match rate**; V200-8 verifies V200-7 on the replica. V200-5 may run beside V200-3/V200-4 (disjoint files).
- **V200-9 → V200-10 → V200-11 → V200-12 → V200-13:** each edits `scripts/reports/autopsy/report.py` (and V200-9/V200-11 consume `BookRow.opened_at_utc` / `closed_at_utc` from V200-3; V200-10 builds on V200-4's header). V200-12 and V200-13 both edit `bars.py`.
- **V200-12 → V200-14:** both edit the three scout role `SKILL.md` files and `.claude/agents/scout.md` and run `sync_codex.py`, which regenerates every mirror; two in flight would commit each other's mirrors.
- **V200-13, V200-14 → V200-15 → V200-16:** V200-15 reads `defined_at` / `autopsy_schema` (V200-13) and `ScoutRow.direction` (V200-14); V200-16 edits the same `scout_merge.py` functions after V200-15.
- **V200-17** follows every task through V200-16 (it runs the whole tool chain on fresh data). **V200-18** is last.

## Task ledger

| ID | Title | Part | Model | Files | Cross-task contract |
|---|---|---|---|---|---|
| V200-1 | Read the `b4ef2e87` deploy time and the stall windows from production | 1 | sonnet | Create `docs/superpowers/results/2026-10-29-v200-prod-reads.md` | Records, each with its source command: `era_boundary_utc` (ISO UTC, to the second) + `era_boundary_source`; `stall_windows` = two `{start, end}` UTC ISO pairs (window 1 `2026-08-03T16:18:02Z`..`2026-08-04T18:55:43Z` confirmed; window 2 start = last `closed_at` before the 08-05 batch, end `2026-08-05T15:34:08Z` confirmed); last PITR drill date. Read-only; no code |
| V200-2 | `TradePlanV2.issued_at_source` and the live stamp | 1 | opus | Modify `swingbot/core/planning/plan_types.py`, `swingbot/core/scanning/analyze.py`; create `tests/planning/test_issued_at_source.py`; modify `tests/backtesting/test_backtest_scenarios.py` | `TradePlanV2.issued_at_source: str \| None = None`, joins `_OMIT_WHEN_NONE`; values `"live"` (set only when `attach_plan_v2(..., issued_at=None)`) and `"discord"` (written only by `v200_001`); replay leaves `None`; round-trips through `plan_to_dict`/`plan_from_dict` |
| V200-3 | Export the issue time; hour from `issued_at` only; tolerant header | 1 | opus | Modify `scripts/ops/export_book_rows.sh`, `scripts/reports/autopsy/rows.py`, `tests/scout/test_export_script.py`, `tests/scout/test_autopsy_rows.py`, `tests/scout/test_book_autopsy.py`, `tests/scout/test_autopsy_exits.py` | Export columns appended at the end of both UNION branches: `plan_issued_at`, `plan_issued_at_source`. `rows.EXPORT_COLUMNS` (38 names) ends with them; `rows.LEGACY_EXPORT_COLUMNS = EXPORT_COLUMNS[:-2]` also accepted by `_check_header`. `rows._alert_hour(issued_at: str \| None) -> int \| None`. `BookRow` gains `hour_source: str = "unknown"` (`"live"` / `"discord"` / `"unknown"`: issued_at present and source `discord` → `discord`; present otherwise → `live`), `opened_at_utc: dt.datetime \| None = None`, `closed_at_utc: dt.datetime \| None = None` (tz-aware UTC from `opened_at`/`closed_at`) |
| V200-4 | Alert-hour coverage by source in the report | 1 | sonnet | Modify `scripts/reports/autopsy/exits.py`, `scripts/reports/autopsy/report.py`, `tests/scout/test_autopsy_exits.py`, `tests/scout/test_book_autopsy.py` | `exits.HOUR_SOURCES = ("live", "discord", "unknown")`; `exits.hour_coverage(rows) -> dict[str, int]` (all three keys, zeros kept); header `alert_hour_coverage = {"trades": {...}, "plans": {...}}`; JSON cells whose cut starts `alert_hour` carry `"hour_coverage"` (trades), tallies whose name starts `alert_hour` carry `"hour_coverage"` (plans); markdown line `alert-hour coverage (trades): live a, discord b, unknown c` above the cell table and `(plans)` above the tallies |
| V200-5 | Discord backfill dry-run script (pure matching + REST read) | 1 | opus | Create `scripts/ops/backfill_issued_at_discord.py`, `tests/scout/test_backfill_issued_at_discord.py` | `PlanKey(plan_id, ticker, direction, strategy, horizon_key, created_date: dt.date)`; `AlertKey(message_id, posted_at: dt.datetime, plan_id: str \| None, ticker, direction, strategy, horizon_key)`; `HORIZON_LABEL_TO_KEY` (from `strategy_types.HORIZONS`); `alert_key(message: dict) -> AlertKey \| None`; `match(plans, alerts) -> list[MatchRow]` with `MatchRow(plan_id, plan_candidates, message_candidates, message_id, issued_at, lag_hours, method)` (`method` in `exact`/`key`/`none`); `summary_lines(rows) -> list[str]`; CSV columns `plan_id,plan_candidates,message_candidates,message_id,issued_at,lag_hours,method`. Run: `docker compose exec -T bot python - [--sample N] < scripts/ops/backfill_issued_at_discord.py` |
| V200-6 | Production dry-run, then STOP for the partner | 1 | sonnet | Create `docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md`; modify `scripts/ops/backfill_issued_at_discord.py`, `tests/scout/test_backfill_issued_at_discord.py` only if the sampled embed layout differs | Dry-run CSV saved to `<scratchpad>/v200_backfill.csv` (never committed); results file records match rate, exact vs key counts, lag distribution, ambiguous count. Task ends `STATUS: CHECKPOINT` — V200-7 waits for the partner |
| V200-7 | Data revision `v200_001` pinning the Discord issue times | 1 | opus | Create `swingbot/core/db/migrations/versions/v200_001_discord_issued_at.py`, `tests/db/test_v200_discord_issued_at.py`; modify `tests/db/test_v173_002_preregistration_verdicts.py` | `revision = "v200_001"`, `down_revision = "v173_002"`; `PINNED_ISSUED_AT: dict[str, str]` (plan_id → UTC ISO); `stamp(docs, pins) -> dict[str, dict]` and `unstamp(docs, pins)` pure, raising `RuntimeError` naming ids; `apply_upgrade(conn) -> int`, `apply_downgrade(conn) -> int`; sets/removes `issued_at` + `issued_at_source = "discord"` only; heads assertion becomes `["v200_001"]` |
| V200-8 | Verify `v200_001` up and down on the replica; deploy note | 1 | sonnet | Modify `docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md` (append `## Replica verification`, `## Deploy note`) | Records counts before/after upgrade and downgrade on `swing-db`, the PITR drill date, the expected `plans` NOTIFY burst. No deploy |
| V200-9 | Stall exclusion rule and `exclusions.json` | 2 | sonnet | Create `scripts/reports/autopsy/exclusions.py`, `scripts/reports/autopsy/exclusions.json`, `tests/scout/fixtures/stall_2026_08_trades.csv`, `tests/scout/test_autopsy_exclusions.py` | `EXCLUSIONS_PATH = Path(__file__).with_name("exclusions.json")`; `Window(start: dt.datetime, end: dt.datetime)`; `Exclusion(key, reason, rule, windows: tuple[Window, ...], trade_ids: frozenset[str])`; `load_exclusions(path=EXCLUSIONS_PATH) -> list[Exclusion]`; `open_in_window(opened, closed, window) -> bool`; `rebuild_trade_ids(rows, windows) -> list[str]` (sorted); CLI `python scripts/reports/autopsy/exclusions.py <rows.csv>` prints the rebuilt ids as JSON. File shape `{"stall_2026_08": {"reason", "rule", "windows": [{"start","end"}], "trade_ids": [...]}}` |
| V200-10 | Apply the exclusion in the report; stall line; test routing | 2 | sonnet | Modify `scripts/reports/autopsy/report.py`, `scripts/reports/book_autopsy.py`, `scripts/dev/select_tests.py`, `tests/scout/test_book_autopsy.py`, `tests/scout/test_scout_routing.py`; create `tests/scout/test_autopsy_stall_report.py` | `exclusions.apply_exclusions(rows, exclusions) -> tuple[list, list]` (kept rows, excluded trade rows); `build_report(..., exclusions_path: Path \| None = EXCLUSIONS_PATH)`; header `stall_exclusions = [{"key", "n", "gross_expr", "worst_r"}]`; exclusions.json SHA-256 in `header["input_fingerprints"]`; markdown line `stall exclusion stall_2026_08: N n, gross ExpR x, worst R y`; `DATA_READERS` routes `scripts/reports/autopsy/exclusions.json` to `tests/scout/` |
| V200-11 | Exit-model era split per cell | 2 | sonnet | Create `scripts/reports/autopsy/eras.py`, `tests/scout/test_autopsy_eras.py`; modify `scripts/reports/autopsy/cells.py`, `scripts/reports/autopsy/report.py`, `tests/scout/test_book_autopsy.py` | `ERA_BOUNDARY_UTC: dt.datetime`, `ERA_BOUNDARY_SOURCE: str` (from V200-1); `ERAS = ("pre", "straddle", "post")`; `era_of(row, boundary=ERA_BOUNDARY_UTC) -> str \| None`; `era_stats(members) -> dict[str, dict]` (`{"n", "win_rate", "net_expr"}` per era, `None` figures at n 0); `CellStats.eras: dict \| None = None` in `to_json` as `"eras"`; `CellStats.notes` gains `"era sign flip"` when pre and post net_expr signs differ; header `era_boundary = {"utc", "source"}` |
| V200-12 | Gap bucket names and the sign note | 2 | haiku | Modify `scripts/reports/autopsy/bars.py`, `scripts/reports/autopsy/report.py` (`NOTES`), `tests/scout/test_autopsy_bars.py`, `tests/scout/test_book_autopsy.py`, `.claude/skills/exit-harvester/SKILL.md`, `.claude/skills/setup-scout/SKILL.md`, `.claude/skills/regime-desk/SKILL.md`, `.claude/agents/scout.md`, `.claude/skills/setup-scout/references/playbook.md`; regenerate their `.agents/` / `.codex/` mirrors | `_open_gap_bucket` returns `open_better` / `flat` / `open_worse_small` / `open_worse_large` (thresholds unchanged); `bars.GAP_SIGN_NOTE` (one sentence, verbatim in every listed doc) |
| V200-13 | `defined_at` per cut and `autopsy_schema: 2` | 3 | opus | Modify `scripts/reports/autopsy/cuts.py`, `scripts/reports/autopsy/bars.py`, `scripts/reports/autopsy/exits.py`, `scripts/reports/autopsy/report.py`, `scripts/reports/autopsy/cells.py`; create `tests/scout/test_autopsy_defined_at.py` | `DEFINED_AT_TAGS = ("entry", "fill", "outcome")`; `cuts.CATEGORICAL_DEFINED_AT`, `bars.BAR_DEFINED_AT`, `exits.EXIT_DEFINED_AT`: `dict[str, str]` cut name → tag; `report.cut_defined_at(sector_of) -> dict[str, str]` (every cut in `_all_cuts`); cell JSON `"defined_at"`; header `"autopsy_schema": 2` (`report.AUTOPSY_SCHEMA = 2`) |
| V200-14 | Scout row field `direction` | 3 | sonnet | Modify `scripts/dev/scout_merge.py`, `.claude/skills/{exit-harvester,regime-desk,setup-scout}/SKILL.md`, `.claude/skills/trade-scout/SKILL.md`, `.claude/agents/scout.md`, `tests/scout/test_scout_merge.py`, `tests/scout/test_scout_merge_parse.py`, `tests/scout/test_generator_roles.py`, `tests/scout/test_trade_scout_skill.py`; regenerate mirrors | `ROW_FIELDS` gains `"direction"` after `"edge"`; `DIRECTIONS = ("exploit", "avoid")`; `ScoutRow.direction: str`; missing → drop `missing direction`; other value → drop `direction must be exploit or avoid` |
| V200-15 | Two-sided known-at-entry screen; schema-1 legacy rule | 3 | opus | Modify `scripts/dev/scout_merge.py`, `tests/scout/test_scout_merge.py`; create `tests/scout/test_scout_merge_two_sided.py` | `autopsy_schema(header) -> int` (absent → 1); `screen_rows(rows, *, closed, ledger, cells, schema: int = 1)`; drop texts `cell <id> is <tag>-defined (not known at entry)`, `cell <id> Δ upper bound <x> is at or above zero or unavailable`; `class SchemaError(ValueError)` raised for a schema-2 cell without `defined_at`; dedupe key `(cut, value-or-complement)` per two-value cut |
| V200-16 | Ranking by bound and projected pooled change; legacy banner | 3 | sonnet | Modify `scripts/dev/scout_merge.py`, `tests/scout/test_scout_merge.py`, `tests/scout/test_scout_merge_two_sided.py` | `projected_pooled_change(cell, header, direction) -> float \| None` (exploit: `cell.net_expr - pooled_net_expr`; avoid: exact complement ExpR from `n`, `header.n`, `pooled_net_expr` minus pooled); `_rank_key` bound term `-lower` (exploit) / `+upper` (avoid); `LEGACY_BANNER = "legacy autopsy (schema 1): no known-at-entry check"` first line under the slate title when schema 1 |
| V200-17 | End-to-end verification on fresh data | 3 | sonnet | Create `docs/superpowers/results/2026-10-29-v200-verification.md` | Records the spec's Verification items 1-2 with counts; raw CSVs and rows file stay in the scratchpad |
| V200-18 | Full suite | 3 | sonnet | Fix observed defects in the owning task's files only | `python <wt>/scripts/dev/testrun.py full`: `0 failed`, `0 xfailed`; `complexity_gate.py`; `sync_codex.py --check` |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-29-v200-scout-tooling-integrity_1-alert-time.md` | V200-1 … V200-8 | Production reads, `issued_at_source`, export and hour rule, coverage, Discord backfill through the replica check |
| 2 | `2026-10-29-v200-scout-tooling-integrity_2-stall-era-gap.md` | V200-9 … V200-12 | Stall exclusion, era split, gap bucket names |
| 3 | `2026-10-29-v200-scout-tooling-integrity_3-merge-verification.md` | V200-13 … V200-18 | `defined_at`, `direction`, two-sided merge, ranking, verification, full suite |

## Cross-task contracts

- **Production facts file** (`docs/superpowers/results/2026-10-29-v200-prod-reads.md`, V200-1): a fenced `json` block holding exactly `{"era_boundary_utc": "...Z", "era_boundary_source": "...", "stall_windows": [{"start": "...Z", "end": "...Z"}, {...}], "pitr_last_drill": "YYYY-MM-DD" | null}`, followed by the commands and raw output lines each value came from. V200-9 copies `stall_windows` into `exclusions.json`; V200-11 copies `era_boundary_*` into `eras.py`; V200-8 re-checks `pitr_last_drill`. If V200-1 cannot find a deploy record for `b4ef2e87` with a clock time, it returns `BLOCKED:` (the commit time is forbidden as the boundary).
- **Hour source vocabulary:** `"live"`, `"discord"`, `"unknown"` everywhere (`TradePlanV2.issued_at_source` stores only the first two; `BookRow.hour_source` and coverage use all three).
- **UTC timestamps on rows:** `BookRow.opened_at_utc` / `closed_at_utc` (V200-3) are the only inputs to the stall rule (V200-9) and the era rule (V200-11); the Eastern-date fields stay as they are.
- **Autopsy JSON** keeps exactly four top-level keys `{"header", "cells", "tallies", "giveback"}`. New header keys: `alert_hour_coverage` (V200-4), `stall_exclusions` (V200-10), `era_boundary` (V200-11), `autopsy_schema` (V200-13). New cell keys: `hour_coverage` (alert_hour cuts, V200-4), `eras`, `notes` (V200-11), `defined_at` (V200-13). Markdown stays within `report.MD_MAX_LINES = 150`.
- **Merge input:** `scout_merge.py` reads `header.autopsy_schema`, `header.n`, `header.pooled_net_expr`, and per cell `id`, `cut`, `value`, `n`, `net_expr`, `delta`, `ci`, `q`, `thin`, `defined_at`. It never reads `eras`.
