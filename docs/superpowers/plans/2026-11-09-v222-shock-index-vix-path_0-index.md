# v222 — Market-shock detector: index + VIX entry path — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch
**Edge:** none (integrity)
**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)

## Goal

v209's market-shock detector labels the market `NORMAL` / `SHOCK` /
`RECOVERY` from breadth and sector depth, and its own acceptance replay of
2026-11-05 failed: the detector stayed `NORMAL` at all 26 steps while SPY was
already −1.4 ATR and the VIX up more than 20 % at 15:00 UTC. That day was a
concentrated, semiconductor-led crash that dragged the index without a broad
sector selloff, so neither the depth path nor the fast path held for two
consecutive readings. v209 cannot release (V209-13) until its replay passes,
and the replay must not pass by tuning on that one day.

This plan adds a third entry path, `_index_path`: SPY down at least
`index_atr_k` ATR from the prior close **and** the VIX up at least
`index_vix_chg` percent on the same reading. It is a shadow-only label, it
never blocks a trade, and it is off (`index_atr_k = 0.0`) until the evidence
says otherwise. The cell is chosen **before** 2026-11-05 is looked at again,
in three stages: a daily screen over every year from the first common SPY/VIX
bar to 2026-11-04 (Stage 1), an intraday confirmation on 5 to 10 frozen
historical days built from Alpaca bars (Stage 2), then one pass/fail replay of
2026-11-05 with the frozen cell (Stage 3). A pass makes the frozen cell the
shipped default and commits v209's replay test unchanged; a fail is a measured
answer, reported to the partner, and never a reason to move the grid.

What it leaves alone: the depth, fast, exit, recovery and carry rules, the
open-settle and two-consecutive-reading rules, the `SHOCK` label, every stored
field and table, and every long and short plan (byte-identical with the path
off). Missing SPY or ATR, or a stale or proxy VIX, makes the new path false,
never partially true.

Success is measured as: the spec's `## Results` section holds Stage 1 (window,
16-cell table on both series, per-year episodes, the winner or NO-LIFT,
descriptive forward long-book results) and Stage 2 (frozen day list, per-day
step tables, survival per cell) before any default is set; the production tape
check shows whether a non-proxy `^VIX` row exists in market hours; the Stage 3
replay is run once and recorded; narrow test runs per task are green and CI is
green after the push.

## Architecture

- **Two trees.** All code lives in the v209 worktree
  `.claude/worktrees/2026-11-05-v209-market-shock-detector` (branch
  `2026-11-05-v209-market-shock-detector`) — `shock.py`, `shock_scan.py`, the
  `SHOCK_*` keys and every shock test exist only there. The spec, and so its
  `## Results` section, lives in the **main** tree
  (`E:/Documents/Private/Projects/Discord-Bot/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`);
  results edits are committed on `main` by the controller. Stage data lives in
  the main tree's gitignored `data/v222/` (absolute path passed to every script).
- **Stage 1 (Part 1).** `scripts/data/fetch_shock_index_daily.py` pulls daily
  SPY and `^VIX` from Yahoo (yfinance, `auto_adjust=True`, the live tape's
  source) to 2026-11-04 into `data/v222/SPY.csv` and `data/v222/VIX.csv` with a
  `provenance.json`. A dedicated directory, not `data/backtest_cache_ext/`:
  extending the cached `^VIX.csv` (ends 2019-12-31) would change a file v211's
  plan reads, and `backtest_cache.cache_path` would write `_VIX.csv` anyway
  (the naming trap). `scripts/backtest/shock_index_screen.py` holds the pure
  daily series (close and upper-bound), fire days, episodes, budget, winner
  rule and the Stage 2 day picker, plus a CLI writing JSON + markdown.
  `scripts/reports/shock_longbook_dump.py` (standalone, prod-side, read-only)
  and `scripts/backtest/shock_index_forward.py` give the descriptive forward
  long-book table with `week_cluster_bootstrap`.
- **Stage 2 (Part 2).** `scripts/data/build_shock_replay_fixture.py` gains a
  `SessionSpec` (DST-aware open/close from America/New_York, optional VIX
  anchor) and `--session` / `--vix-anchor`; its 2026-11-05 default output stays
  byte-identical. `scripts/backtest/shock_index_intraday.py` replays each
  frozen day through `shock.measure` and evaluates the SPY half of the rule on
  two consecutive settled readings; the VIX half is never confirmed by an
  interpolated or absent VIX.
- **Detector (Part 3).** `swingbot/core/market/shock.py`: two `float` fields
  appended to `ShockThresholds`, `_index_path(reading, th)` with an explicit
  `th.index_atr_k > 0` guard, `entry_condition` ORs it in. `shock_scan.py`
  `THRESHOLD_ATTRS` gains two rows; `swingbot/config.py` gains two
  hot-reloadable `Field`s in the Market Shock block; `.env.example` mirrors
  them. No stored field, table, label or migration.
- **Stage 3 (Part 3).** One run-once replay of the untracked
  `tests/market/test_shock_replay_2026_11_05.py` helpers with the frozen cell,
  then (on a pass only) the frozen cell becomes the `ShockThresholds`, config
  `Field` and `CAST_DEFAULTS` default and the replay test is committed unchanged.

**Tech stack:** Python 3.11, pandas/numpy, yfinance 0.2.66, pytest; no new dependency.

## Global Constraints

- **Worktree.** Every code task runs in
  `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v209-market-shock-detector`
  and names it in its dispatch. Never edit code in the main tree; check
  `git -C E:/Documents/Private/Projects/Discord-Bot status --short` after each
  task (only the spec's `## Results` edits may appear there). Never `cd` in
  Bash; use `git -C` and absolute paths. In part files, every `- Create:` /
  `- Modify:` path carries the full prefix
  `.claude/worktrees/2026-11-05-v209-market-shock-detector/` so `plan_lint.py`
  resolves it from the main tree.
- **Order (spec § Order of work): Stage 1, Stage 2, implementation, Stage 3.**
  No Part 3 task starts before Stage 1 and Stage 2 results are in the spec's
  `## Results` section and the partner has passed gate 2.
- **Human gates (partner, `AskUserQuestion`, recommended option first):**
  - **Gate 1** ends V222-5: the partner reads the Stage 1 results. NO-LIFT
    (no winner) stops the plan: nothing ships, the plan goes to `no-lift/`, and
    the partner decides v209's release separately.
  - **Gate 2** ends V222-8: the partner reads the Stage 2 results and confirms
    the frozen cell. No cell survives → NO-LIFT, same as gate 1.
  - **Gate 3** ends V222-13 on a Stage 3 fail: report the table, commit
    nothing that weakens the replay test, V222-14 does not run; the partner
    decides. A fail is never a reason to move the grid, the rule or the cell.
- **Frozen before any data is read (spec § Frozen, copied verbatim; never re-chosen):**
  - **Window.** From the first date both SPY and ^VIX daily bars exist to
    2026-11-04 (the day before the replay). Both dates and the year count are
    written into the results section before any cell is read.
  - **Grid.** `index_atr_k` ∈ {1.0, 1.25, 1.5, 2.0} × `index_vix_chg` (percent) ∈
    {10, 15, 20, 25}. 16 cells.
  - **Episode.** A fire is a session on which the daily rule holds. Fires
    separated by fewer than **5 sessions** form one episode.
  - **Budget.** At most **6 episodes in every calendar year** of the window, so
    one crisis year cannot carry the rest. It is evaluated on the
    **upper-bound series**.
  - **Winner rule.** Among cells inside the budget, take the *most sensitive*
    (lowest `index_atr_k`, then lowest `index_vix_chg`) whose neighbours on both
    axes are also inside the budget. If none qualifies, the result is
    **NO-LIFT** and nothing ships.
  - **Intraday survival (Stage 2).** A cell survives when it fires (two
    consecutive settled readings) on at least 75 % of the frozen shock days and
    on none of the frozen quiet days.
  - **Stage 2 day list.** 5 to 10 days, written into the results section
    **before** any replay is built: the shock days are the largest Stage 1
    episodes by SPY ATR move, the quiet days are matched by date in other
    months. **2026-11-05 is excluded** from the list.
- **Plan-time operational readings (fixed here, before any data is read; the
  spec leaves them open; the controller checks them, see OPEN):**
  - A neighbour is a grid cell one step away on one axis; a cell on the grid's
    edge has only the neighbours that exist.
  - "Cells that pass Stage 1" = cells that satisfy the winner rule's
    condition (in budget **and** every neighbour in budget). The frozen cell is
    the most sensitive of them that survives Stage 2.
  - Day list: 5 shock days + 5 quiet days. Shock days: the winner cell's
    upper-bound episodes whose dates have Alpaca 15-minute bars (on or after
    2016-01-04), ranked by the most negative upper-bound SPY ATR move inside
    the episode; the day is that session. Quiet day per shock day: the session
    nearest the same day of month in the previous calendar month (next month
    when the previous month is outside the window), on which the most
    sensitive grid cell (1.0, 10) does not fire on the upper-bound series and no
    fire of it lies within 5 sessions. Fewer than 3 shock days available → stop
    at gate 1 and ask.
  - Daily series (no lookahead): prior close = the previous session's close,
    ATR14 = `swingbot.core.market.indicators.atr(bars_before_day, 14).iloc[-1]`
    on completed bars dated before the session (as `shock_scan._name_row` does
    live, at least 15 completed bars). Close series: SPY `(Close − prev)/ATR14`,
    VIX `(Close/prevClose − 1)·100`. Upper bound: SPY `(Low − prev)/ATR14`, VIX
    `(High/prevClose − 1)·100`. A comparison meets its bar with `1e-9`
    tolerance, as `shock._meets` does.
  - Stage 2 judges the **SPY half** (`−spy_atr_move ≥ index_atr_k` on two
    consecutive readings with `minutes_since_open ≥ 15`); no real intraday VIX
    exists for historical days, so every day reports "VIX half unconfirmed"
    (spec Stage 2). Only `source == "alpaca"` fixtures count.
  - Forward long-book (descriptive only): closed `bullish` main-ledger regular
    trades whose open session falls within the first 1, 3, 5 sessions of an
    episode (session 1 = the episode's first fire day).
- **Off is a float sentinel.** `index_atr_k = 0.0` and `index_vix_chg = 0.0`
  defaults until V222-14; never `None` (`thresholds_from_config` casts with
  `type(default)(...)`; a `None` silently stops the detector).
  `SHOCK_INDEX_ATR_K` carries `min=0`. `_index_path` returns False when
  `th.index_atr_k <= 0`.
- **No stored field.** Never add `index_*` to `ShockReading` / `ShockState`;
  no Alembic revision. `shock.py` stays import-free of config/I/O
  (`test_shock_measure.py` ast walk).
- **Config tests.** New `Field` help strings contain `v209` and `v222`;
  `V209_FIELDS` dict order equals FIELDS order; the block stays contiguous
  between `DCB_VOLUME_RATIO` and `DATABASE_URL`; `THRESHOLD_ATTRS` count
  17 → 19; `V209_FIELDS` 19 → 21.
- **Complexity < 15** for every new or changed function
  (`scripts/dev/complexity_gate.py`); nothing touched is near it today.
- **Tests:** narrow runs only (`python scripts/dev/testrun.py file <test>`); no
  task runs the full suite (CI does). None of the shock tests reaches the DB;
  no `/replicate-prod-db` needed. Production access is read-only through
  `bash scripts/ops/ssh-hetzner.sh` (standing permission); nothing is changed
  on the VM.
- **`.env`** may be read by scripts (Alpaca keys for the builder); never print
  its values.
- **Commits:** several scoped commits per task on the v209 branch; results
  edits on `main`. Do not merge, do not release; V209-13 owns the release.

## Review Focus

- Frozen values appear verbatim in code constants (`GRID_K`, `GRID_VIX`,
  `EPISODE_GAP`, `BUDGET_PER_YEAR`, `SURVIVAL_SHOCK_SHARE`) and are pinned by
  tests; nothing reads 2026-11-05 before V222-13.
- No lookahead in the daily series (ATR and prior close from bars before the day).
- The `index_atr_k > 0` guard; partial data never fires; the off path is
  byte-identical.

## Parallelisation

Sequential by design; the human gates and the stage order forbid most overlap.

- **V222-1 → V222-5 → V222-8 → (V222-9..12) → V222-13 → V222-14** is the spine:
  each Stage reads the previous Stage's frozen results (gate 1, gate 2, gate 3).
- **V222-2 → V222-3:** same module `scripts/backtest/shock_index_screen.py`
  (V222-3 consumes `daily_moves`, `fire_days`, `episodes`, `episodes_per_year`).
- **V222-4** may run in parallel with V222-2/3 (disjoint files); it consumes
  `episodes` only at run time in V222-5, so its tests stub episodes.
- **V222-6 and V222-7** may run in parallel with Part 1 code tasks (disjoint
  files, no contract dependency), but V222-8 needs V222-5's frozen day list.
- **V222-9 → V222-10:** V222-10's `THRESHOLD_ATTRS` set-equality test needs the
  two `ShockThresholds` fields from V222-9.
- **V222-11** needs V222-9 and V222-10 (it drives `run_shock_pass` through
  `thresholds_from_config`). **V222-12** is disjoint from V222-9..11 and may run
  beside them.
- **V222-13 → V222-14:** V222-14 runs only on a Stage 3 pass and edits the
  same files as V222-9/V222-10.

## Task ledger

All file paths are relative to the v209 worktree
`.claude/worktrees/2026-11-05-v209-market-shock-detector/`, except the spec
(main tree).

| Id | Title | Part | Model | Files (C create / M modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V222-1 | Daily SPY + ^VIX to 2026-11-04, provenance, Results scaffold and frozen window | 1 | sonnet | C `scripts/data/fetch_shock_index_daily.py`; C `tests/scripts/test_fetch_shock_index_daily.py`; M spec (main) `## Results` | `fetch_shock_index_daily.WINDOW_END = date(2026, 11, 4)`; `fetch_daily(symbol: str, end: date, *, download=None) -> pd.DataFrame` (Date index, `Open,High,Low,Close`); `read_daily(path: Path) -> pd.DataFrame`; `common_window(spy, vix) -> dict` keys `start, end, years, sessions`; files `data/v222/SPY.csv`, `data/v222/VIX.csv`, `data/v222/provenance.json` (main tree) |
| V222-2 | Daily series, fire days and episodes (no lookahead) | 1 | opus | C `scripts/backtest/shock_index_screen.py`; C `tests/backtest_scripts/test_shock_index_screen.py` | `GRID_K = (1.0, 1.25, 1.5, 2.0)`; `GRID_VIX = (10.0, 15.0, 20.0, 25.0)`; `EPISODE_GAP = 5`; `BUDGET_PER_YEAR = 6`; `EPS = 1e-9`; `daily_moves(spy, vix) -> pd.DataFrame` (index sessions; cols `spy_close_atr, spy_low_atr, vix_close_chg, vix_high_chg`); `fire_days(moves, k: float, v: float, series: str) -> list[pd.Timestamp]` (`series` in `"close"`, `"upper"`); `episodes(fires, sessions: pd.DatetimeIndex, gap: int = EPISODE_GAP) -> list[list[pd.Timestamp]]`; `episodes_per_year(eps, years: range) -> dict[int, int]` |
| V222-3 | Grid, budget, winner rule, Stage 2 day picker, report CLI | 1 | opus | M `scripts/backtest/shock_index_screen.py`; M `tests/backtest_scripts/test_shock_index_screen.py` | `CellResult` (frozen dataclass: `k, v, close_fires, close_episodes, upper_fires, upper_episodes, per_year_close, per_year_upper, in_budget`); `screen_grid(moves) -> list[CellResult]`; `neighbours(k, v) -> list[tuple[float, float]]`; `qualifying(cells) -> list[tuple[float, float]]` (most sensitive first); `pick_winner(cells) -> tuple[float, float] \| None`; `stage2_days(moves, winner, *, alpaca_from=date(2016, 1, 4), n_shock=5, exclude=(date(2026, 11, 5),)) -> dict` (`{"shock": [iso...], "quiet": [iso...]}`); CLI `--data-dir --out-json --out-md`; JSON keys `window, cells, qualifying, winner, episodes` (`episodes`: `"k,v" -> [[iso...]...]` upper series), `stage2_days` |
| V222-4 | Forward long-book: prod dump and descriptive forward table | 1 | sonnet | C `scripts/reports/shock_longbook_dump.py`; C `scripts/backtest/shock_index_forward.py`; C `tests/scripts/test_shock_longbook_dump.py`; C `tests/backtest_scripts/test_shock_index_forward.py` | `shock_longbook_dump.longbook_record(trade: dict) -> dict \| None` (`{opened_at, r}`); `shock_index_forward.HORIZONS = (1, 3, 5)`; `forward_longbook(episodes: list[list[str]], trades: list[dict], sessions: list[str], horizons=HORIZONS) -> list[dict]` (per horizon: `horizon, n_trades, n_episodes, exp_r, total_r, ci_low, ci_high`); CLI `--screen-json --longbook --data-dir --out-md` |
| V222-5 | Run Stage 1, write Results, freeze the Stage 2 day list, gate 1 | 1 | sonnet | M spec (main) `## Results` § Stage 1; outputs `data/v222/stage1.json`, `data/v222/stage1.md`, `data/v222/longbook.json`, `data/v222/forward.md` (main tree) | Results § Stage 1 (winner cell or NO-LIFT, qualifying cells) and § Stage 2 day list; `data/v222/stage2_days.json` (`{"shock": [...], "quiet": [...], "cells": [[k, v]...]}`) |
| V222-6 | Fixture builder parameterised by session date (DST, optional VIX anchor) | 2 | sonnet | M `scripts/data/build_shock_replay_fixture.py`; M `tests/scripts/test_build_shock_replay_fixture.py` | `VixAnchor(at: datetime, level: float, chg_pct: float)`; `SessionSpec(day, open_utc, close_utc, turn_utc, daily_start, vix_anchor)`; `session_spec(day: date, vix_anchor: VixAnchor \| None = None, daily_start: date \| None = None) -> SessionSpec`; `DEFAULT_SPEC`; `spec=DEFAULT_SPEC` kwarg on `step_times, vix_path, fixture_step, load_or_fetch, long_entries, build_fixture`; CLI `--session YYYY-MM-DD`, `--vix-anchor HH:MM,LEVEL,CHG`; non-default outputs `market_data/shock_replay_<yyyy_mm_dd>.json` and cache `market_data/shock_replay_<yyyy_mm_dd>/` |
| V222-6b | Builder CLI `--session` / `--vix-anchor` and per-session output paths | 2 | sonnet | M `scripts/data/build_shock_replay_fixture.py`; M `tests/scripts/test_build_shock_replay_fixture.py` | `parse_anchor(text: str, day: date) -> VixAnchor`; `resolve_spec(args) -> SessionSpec`; `default_paths(spec) -> tuple[Path, Path]`; CLI `--session`, `--vix-anchor`, `--out`, `--cache-dir`; bad anchor exits 2 |
| V222-7 | Intraday SPY-half evaluator and survival rule | 2 | opus | C `scripts/backtest/shock_index_intraday.py`; C `tests/backtest_scripts/test_shock_index_intraday.py` | `SURVIVAL_SHOCK_SHARE = 0.75`; `step_readings(fx: dict, th=ShockThresholds()) -> list[ShockReading]`; `spy_half_first_fire(readings, k: float, open_settle_min: int = 15) -> datetime \| None`; `day_table(readings, k: float) -> list[dict]`; `survives(shock_fired: list[bool], quiet_fired: list[bool]) -> bool` |
| V222-7b | Stage 2 day list, fixture checks, evaluate, report and CLI | 2 | opus | M `scripts/backtest/shock_index_intraday.py`; M `tests/backtest_scripts/test_shock_index_intraday.py` | `load_days`, `fixture_path`, `fixture_status`, `evaluate(days, fixtures) -> {complete, days, cells, survivors, frozen}`, `render_md`; CLI `--days-json --fixtures-dir --out-json --out-md`, exit 0/3/2 |
| V222-8 | Build Stage 2 fixtures, run, write Results, freeze the cell, gate 2 | 2 | sonnet | M spec (main) `## Results` § Stage 2; outputs `data/v222/stage2/*.json`, `data/v222/stage2.json`, `data/v222/stage2.md` (main tree) | Results § Stage 2 frozen cell `(index_atr_k, index_vix_chg)` = `FROZEN_K, FROZEN_V`, or NO-LIFT |
| V222-9 | `ShockThresholds` index fields, `_index_path`, `entry_condition` | 3 | sonnet | M `swingbot/core/market/shock.py`; M `tests/market/test_shock_step_entry.py` | `ShockThresholds.index_atr_k: float = 0.0`, `.index_vix_chg: float = 0.0` (appended after `quote_max_age_s`); `shock._index_path(reading: ShockReading, th: ShockThresholds) -> bool` |
| V222-10 | Config keys, `THRESHOLD_ATTRS` rows, `.env.example`, config pins | 3 | sonnet | M `swingbot/config.py`; M `swingbot/core/scanning/shock_scan.py`; M `.env.example`; M `tests/scanning/test_shock_scan.py`; M `tests/test_config_v209_keys.py` | config `SHOCK_INDEX_ATR_K` (float, default `"0.0"`, min 0, max 5.0, step 0.25), `SHOCK_INDEX_VIX_CHG` (float, default `"0.0"`, min 0, max 200, step 1), placed after `SHOCK_VIX_RELIEF`; `THRESHOLD_ATTRS["index_atr_k"] = "SHOCK_INDEX_ATR_K"`, `["index_vix_chg"] = "SHOCK_INDEX_VIX_CHG"` |
| V222-11 | Pipeline tests: partial data, stale/proxy VIX, off is byte-identical | 3 | sonnet | C `tests/scanning/test_shock_index_path.py`; M `tests/scanning/test_shock_plans_byte_identical.py` | none (tests only) |
| V222-12 | Production `^VIX` tape check and VIX-coverage query (read-only) | 3 | sonnet | C `scripts/reports/shock_vix_check.py`; C `tests/scripts/test_shock_vix_check.py`; M spec (main) `## Results` § Production VIX | `shock_vix_check.tape_status(entry, now: datetime, max_age_s: int = 600) -> dict`; `COVERAGE_SQL` |
| V222-13 | Stage 3: replay 2026-11-05 once with the frozen cell, gate 3 | 3 | sonnet | C `scripts/backtest/shock_index_replay_once.py`; M spec (main) `## Results` § Stage 3 | `replay_table(fx: dict, th: ShockThresholds) -> list[dict]`; Results § Stage 3 PASS/FAIL |
| V222-14 | Frozen cell becomes the default; commit the replay test unchanged | 3 | sonnet | M `swingbot/core/market/shock.py`; M `swingbot/config.py`; M `.env.example`; M `tests/test_config_v209_keys.py`; M `tests/market/test_shock_step_entry.py`; add `tests/market/test_shock_replay_2026_11_05.py` (unchanged) | defaults `index_atr_k = FROZEN_K`, `index_vix_chg = FROZEN_V` |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-09-v222-shock-index-vix-path_1-stage1-screen.md` | V222-1..V222-5 | daily data, daily screen, winner rule, forward long-book, Stage 1 results and gate 1 |
| 2 | `2026-11-09-v222-shock-index-vix-path_2-stage2-intraday.md` | V222-6..V222-8 | builder by session date, intraday evaluator, Stage 2 results and gate 2 |
| 3 | `2026-11-09-v222-shock-index-vix-path_3-detector-release.md` | V222-9..V222-14 | `_index_path`, config, pipeline pins, production VIX check, Stage 3 replay and default |
