# v222 — Market-shock detector: index + VIX entry path — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** none (predicted bot patch; Stage 1 returned NO-LIFT at gate 1, nothing shipped)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md) (amended 1494eab1, panel applied d39b5d88)

> **Re-planned 2026-11-13** against the amended spec. The first plan (four
> parts, V222-1..V222-14 with V222-6/6b/6c) targeted v209's unmerged branch
> and a 2026-11-05 pass/fail gate; both are gone. Its part files were removed.
> V222-6c (archive the one-minute `^VIX` bars) is done on `main` (`b253ef36`)
> and has no row here.

## Goal

v209's market-shock detector is on `main` in shadow mode. Since Amendment A1
it reads the market as `SHOCK` when watchlist breadth or sector depth crosses
one of three bars (depth, majority, fast), and its one-shot acceptance passed:
it found 5 of 6 frozen shock days without false fires on calm days. But it
finds them late. On four of the five hits, 20 % or less of the day's SPY drop
was still ahead when the label flipped, and on 2026-11-05 it fired at 15:45 UTC
although SPY had been more than one ATR down since 14:45. A label that arrives
after the damage tells an alert-time trader little.

The index and the VIX often move before half the watchlist is one ATR down,
and both are already in every reading (`spy_atr_move`, `vix_chg_pct`). This plan
tests one pre-registered idea: a fourth entry path, `_index_path`, true when SPY
is at least `index_atr_k` ATR below the prior close **and** `^VIX` is up at least
`index_vix_chg` percent. Being an extra OR term, it can only make the first
`SHOCK` earlier or leave it where it is. The question is whether it does so out
of sample, often enough, without extra false fires. Once shipped, production's
shadow pass labels shock days earlier where the evidence says it can; nothing
else changes: the label still never blocks a trade, A1's three paths and their
thresholds are untouched, no stored field or table is added, and with the path
off every long and short plan is byte-identical.

The cell is chosen from data in two stages before any code changes. Stage 1
screens 16 frozen grid cells on daily SPY and `^VIX` bars from 1993 to
2026-11-04 against a budget of at most 6 episodes in every calendar year, and
picks the most sensitive cell whose grid neighbours also fit. Stage 2 replays
only that cell intraday on a frozen list of 16 days built from Alpaca bars
(8 counted shock days without an A1 fixture, 4 quiet, 4 near-miss) plus the 26
A1 fixtures, with the VIX half forced true so every gate is an upper bound. The
cell must survive on 6 of 8 shock days, stay silent on quiet days, fire on at
most 2 of 4 near-miss days, add no A1 false fire, and lead A1 by at least 30
minutes and 15 points of the drop on 5 of the 8 counted shock days. Any failure
closes the plan `no-lift/` and nothing ships. 2026-11-05 is in-sample and
decides nothing; it is reported once in Stage 3.

Success is measured as: the spec's `## Results` holds Stage 1 (window, the
16-cell table on both series, per-year episodes against the pre-registered
prior, the winner or NO-LIFT, descriptive arms) and Stage 2 (frozen day list,
per-day tables, the five gate rows and the lead table) before any default is
set; the production check reports the `^VIX` tape's presence, staleness, lag and
any explicit `SHOCK_INDEX_*` key; the frozen cell becomes the config `Field`
default only, with `tests/market/test_shock_acceptance_a1.py` passing unedited
with the same report; narrow runs are green per task and CI is green after the
push.

## Architecture

- **One worktree off `main`.** `.claude/worktrees/2026-11-09-v222-shock-index-vix-path`
  (branch `2026-11-09-v222-shock-index-vix-path`, the plan file stem per
  `document-lifecycle.md`), created by V222-1 before any Stage 1 work. Every
  code, fixture and test change is committed there. All plan paths are
  repo-relative; they resolve in the worktree (and, being tracked on `main`,
  from the main tree for `plan_lint.py`). The spec's `## Results` section lives
  in the **main** tree and is committed on `main` by the controller. Stage data
  lives in the main tree's gitignored `E:/Documents/Private/Projects/Discord-Bot/data/v222/`
  (absolute path passed to every script) so it outlives the worktree.
- **Stage 1 data (V222-1).** `scripts/data/fetch_backtest_data.py` already has
  a `^VIX` context fetch (`fetch_vix_context`, `vix_context_main`, pinned to
  2009..2019 for other screens; it refuses to overwrite without `--force`). A new
  `--shock-index` mode writes daily SPY (`1993-01-01`..) and, through the same
  `fetch_vix_context` (session check against that SPY file), `^VIX` to
  2026-11-04 into `data/v222/` with a `provenance.json`. It refuses the pinned
  caches `data/backtest_cache/` and `data/backtest_cache_ext/` outright, so no
  pinned file is ever overwritten.
- **Stage 1 screen (V222-1..V222-5).** `scripts/backtest/shock_index_screen.py`
  holds pure functions: daily close and upper-bound series (ATR14 and prior close
  from bars before the day), fire days, episodes, budget, the edge-aware winner
  rule, the prior check, the descriptive arms (SPY-only, gap/intraday split,
  macro days, VIX-high timing) and the Stage 2 day picker, plus a CLI writing
  JSON and markdown. `scripts/reports/shock_longbook_dump.py` (prod-side,
  read-only) and `scripts/backtest/shock_index_forward.py` give the descriptive
  forward long-book table with `week_cluster_bootstrap`.
- **Stage 2 (V222-6d..V222-8).** No builder rewrite: A1's
  `build_shock_replay_fixture.py --validation-days FILE --out-dir DIR` already
  builds any session (DST-aware) from Alpaca bars with a ramp VIX. The thin
  adapter `scripts/data/shock_stage2_days.py` turns the frozen day list into that
  file's `{"days": {iso: info}}` shape with `shock_validation_days.day_table`, and
  new fixtures go to `tests/fixtures/shock_replay_v222/`, never the frozen A1
  directory. `scripts/backtest/shock_index_intraday.py` replays fixtures through
  `shock.measure`, re-derives A1's first `SHOCK` (parity-tested against
  `shock.step` on all 26 A1 fixtures), adds the index half without touching
  `shock.py`, and applies the five gates. V222-6d derives a separate
  2026-11-05 fixture with real one-minute `^VIX` from the frozen one (non-VIX
  fields copied byte for byte) for Stage 3.
- **Detector (V222-9..V222-11).** `swingbot/core/market/shock.py`: two float
  fields appended to `ShockThresholds` (default `0.0`, staying `0.0` forever),
  `_index_path(reading, th)` with an `index_atr_k <= 0` guard, OR-ed into
  `entry_condition`. Two hot-reloadable `Field`s, two `THRESHOLD_ATTRS` rows, two
  `.env.example` lines and the config pins. No stored field, label or migration.
- **Release (V222-12..V222-14).** A read-only production check, the Stage 3
  in-sample and ramp-VIX reports, a partner gate, then the frozen cell becomes the
  config `Field` default (and its `CAST_DEFAULTS` pin and `.env.example` line).

**Tech stack:** Python 3.11, pandas/numpy, yfinance, pytest; no new dependency.

## Global Constraints

- **Worktree.** Every code task runs in
  `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-09-v222-shock-index-vix-path`
  and its dispatch names that path. Never edit code in the main tree; check
  `git -C E:/Documents/Private/Projects/Discord-Bot status --short` after each
  task (only the spec's `## Results` edits may appear there). Never `cd` in Bash;
  use `git -C` and absolute paths.
- **Order (spec § Order of work): Stage 1, Stage 2, implementation, production
  check, Stage 3 release and reports.** No V222-9..V222-14 task starts before
  gate 2 has passed.
- **Human gates (partner, `AskUserQuestion`, one question, recommended option
  first):**
  - **Gate 1** ends V222-5: the partner reads Stage 1. No winner → NO-LIFT: the
    plan stops, nothing ships, it closes `no-lift/`.
  - **Gate 2** ends V222-8: the partner reads Stage 2 and confirms the frozen
    cell. Any failed gate → NO-LIFT, same as gate 1.
  - **Gate 3** ends V222-13: the partner reads the production check and the
    Stage 3 reports and approves the release (V222-14). A proxy-only production
    tape, or an explicit `SHOCK_INDEX_*` key in production's `.env`, is put to the
    partner here. No gate re-opens a frozen rule.
- **Frozen before any data is read (spec § Frozen; copied, never re-chosen):**
  - **Window.** First date both SPY and `^VIX` daily bars exist to 2026-11-04;
    both dates and the year count go into Results before any cell is read.
  - **Grid.** `index_atr_k` ∈ {1.0, 1.25, 1.5, 2.0} × `index_vix_chg` (percent) ∈
    {10, 15, 20, 25}. 16 cells.
  - **Episode.** Fires separated by fewer than **5 sessions** form one episode.
  - **Budget.** At most **6 episodes in every calendar year**, on the
    **upper-bound series**.
  - **Winner rule.** Among in-budget cells, the most sensitive (lowest
    `index_atr_k`, then lowest `index_vix_chg`) whose every existing neighbour
    (one grid step on one axis, either direction) is in budget; missing
    beyond-edge neighbours count neither for nor against. None → **NO-LIFT**.
  - **Prior.** Cells with `index_atr_k` ≤ 1.25 expected to break the cap in at
    least two years (2008 and 2020); a winner, if any, at `index_atr_k` ≥ 1.5;
    NO-LIFT more likely than not. Reported per cell beside the failing-year count.
  - **Stage 2 cell.** Only the Stage 1 winner; no neighbour, no fallback. A
    Stage 2 failure is NO-LIFT.
  - **Stage 2 day list.** From the winner cell's upper-bound series, sessions on
    or after the first Alpaca-buildable date (written down first), 2026-11-05
    excluded; representative session per episode = largest upper-bound SPY ATR
    move. **8 counted shock days** (highest-ranked episodes whose representative
    session has no A1 fixture); the **6 A1 shock fixtures** replayed and reported,
    never counted; **4 quiet days** (slots 1–4 from counted shock days 1–4: next
    calendar month, same weekday, nearest same day of month, no winner fire and
    none within 5 sessions; slot 3 → nearest early-close or post-holiday session,
    slot 4 → nearest first session after a US DST change, same no-fire
    condition); **4 near-miss days** (winner upper-bound fires the close series
    missed, smallest close-to-close SPY drop in ATR first, counted shock days
    excluded). An unbuildable day is replaced by the next in its ranking.
  - **Gates (VIX half forced true).** Survival: fires on ≥ **6 of 8** counted
    shock days, **0 of 4** quiet, ≤ **2 of 4** near-miss. A1-days false fires:
    on the 20 A1 non-shock fixtures, A1 + index adds **no** false-fire day in any
    class over A1's recorded row (calm 0/12, rotation 1/4, hard 0/4). Lead: a
    counted shock day leads when `t_idx` ≤ `t_A1` − **30 min** and drop still
    ahead at `t_idx` exceeds that at `t_A1` by ≥ **15 points**; A1 never firing
    means `t_A1` = close, share 0; neither firing does not lead; pass at ≥ **5 of
    8**. Drop still ahead at *t* = `(SPY at t − close) / (prior close − close)`
    (A1's `lead_share`).
- **Plan-time operational readings (fixed here, before any data is read; the
  spec leaves them open; the controller checks them):**
  - **Daily series (no lookahead).** Prior close = previous session's close;
    ATR14 = `swingbot.core.market.indicators.atr(bars_before_day, 14).iloc[-1]`
    on at least 15 completed bars dated before the session. Close series: SPY
    `(Close − prev)/ATR14`, VIX `(Close/prevClose − 1)·100`. Upper bound: SPY
    `(Low − prev)/ATR14`, VIX `(High/prevClose − 1)·100`. The gap part is
    `(Open − prev)/ATR14`. A bar is met with `1e-9` tolerance (`shock._meets`).
  - **"VIX half forced true"** = run with `index_vix_chg = FORCE_VIX_BAR = -1e9`
    while each step keeps its ramp `vix_chg_pct` (so A1's VIX relief is exactly
    what A1's recorded runs used). It needs a non-None `vix_chg_pct` on every
    settled reading; a fixture without one cannot be gated and counts as
    unbuildable (replaced from its ranking). The descriptive ramp run uses the
    cell's real `index_vix_chg`.
  - **What "fires" means per gate.** Survival, quiet and near-miss count the
    index path on its own (two consecutive settled readings with the index half
    true; insufficient readings hold the streak, as `shock.step` does). Lead and
    A1-days false fires compare the first `SHOCK` of A1 alone with A1 + index
    (shared streak, as the detector counts paths). A1 false fire = A1's
    `is_false_fire` (unbuildable, any insufficient reading, or a first `SHOCK`).
  - **First Alpaca-buildable date** = first row of
    `data/market_data_pit/daily/SPY.csv` (2016-01-04 today); V222-5 writes it
    into Results before the day list.
  - **Quiet-slot calendars.** Early close via `session.is_early_close(d)`;
    post-holiday = a session whose previous session is more than one weekday
    earlier, read from `session.nyse_calendar()` for dates on or after
    `NYSE_FIRST_DATE` (2018-01-01; the calendar ends 2030) and from the SPY daily
    session index before it; DST change days from `zoneinfo("America/New_York")`
    UTC-offset changes. "Nearest" = fewest calendar days from the base-rule date
    of that slot, ties to the earlier date; a month with no candidate rolls to the
    next month.
  - **Macro split (descriptive).** `market_events.FOMC_DECISION_DATES` is the
    only calendar: inside its first..last span a representative session is
    `yes` if it is an FOMC decision date or a first Friday (payrolls), else `no`;
    outside the span `unknown`. CPI is not used (the repo's CPI dates are
    approximations).
  - **Forward long-book (descriptive only).** Closed `bullish` main-ledger
    regular trades whose open session falls in the first 1, 3 or 5 sessions of an
    episode (session 1 = first fire day); N per trade and per episode, Total R
    beside ExpR, `week_cluster_bootstrap` intervals. Never cited for the release.
  - **Stage 3 VIX prior.** The derived 2026-11-05 fixture's prior VIX close is
    the 2026-11-04 close in `data/v222/^VIX.csv`, recorded in the fixture.
- **Data hygiene.** No SPY or VIX value of a candidate Stage 2 day is read
  before the day list is in Results. 2026-11-05 decides nothing; it is reported
  in Stage 1 (VIX-high timing) and Stage 3 only.
- **A1 is a closed record.** Never edit `tests/market/test_shock_acceptance_a1.py`,
  `tests/fixtures/shock_replay/` (incl. `validation_days.json`) or
  `tests/fixtures/shock_replay_2026_11_05.json`; never import helpers from the
  test. `ShockThresholds()` defaults never change. The A1 test passes unedited
  with the same report after V222-9 and V222-14.
- **Off is a float sentinel.** `index_atr_k = 0.0` / `index_vix_chg = 0.0`, never
  `None` (`thresholds_from_config` casts with `type(default)(...)`; a `None`
  silently stops the detector). Both keys carry `min=0`. `_index_path` returns
  False when `th.index_atr_k <= 0`, and when `spy_atr_move` or `vix_chg_pct` is None.
- **No stored field.** Never add `index_*` to `ShockReading` / `ShockState`; no
  Alembic revision. `shock.py` stays free of config/I/O imports.
- **Config pins.** `len(set(THRESHOLD_ATTRS.values()))` 18 → 20
  (`tests/scanning/test_shock_scan.py`); `len(V209_FIELDS)` 20 → 22 (test renamed);
  the Market Shock block stays contiguous after `DCB_VOLUME_RATIO` and directly
  before `DATABASE_URL`; each new `help` contains `v209` (and `v222`),
  `search_class` `"excluded"`, an exact `.env.example` line, `min <= default <= max`.
- **`DATA_READERS`** (`scripts/dev/select_tests.py`, first prefix match wins):
  rows for `data/v222/` (V222-1), `tests/fixtures/shock_replay_2026_11_05_vix1m.json`
  (V222-6d, extended by V222-13), `tests/fixtures/shock_replay_v222/` (V222-8);
  V222-7 appends its test to the existing `tests/fixtures/shock_replay/` row.
  Read `tests/dev/test_select_tests.py` coverage assertions before each edit.
- **Complexity < 15** for every new or changed function
  (`scripts/dev/complexity_gate.py`).
- **Tests:** narrow runs only (`python scripts/dev/testrun.py file <test>`); no
  task runs the full suite (CI does). New test files go in existing directories
  (`tests/backtest_scripts/` → suite `backtest-scripts`, `tests/scripts/` →
  `tooling`, `tests/market/` → `market-signals`, `tests/scanning/` → `scanning`).
  A task whose tests reach Postgres runs `/replicate-prod-db` first in the shared
  `swing-db` container.
- **Production** is read-only through `bash scripts/ops/ssh-hetzner.sh`; any VM
  change goes through `mirror-prod`, never `sed -i` on the bind-mounted `.env`.
  `.env` values (local or production) are never printed; the production key
  check reports presence only.
- **Commits:** several scoped commits per task on the v222 branch; Results edits
  on `main` by the controller. No merge, no deploy inside the plan.

## Review Focus

- Frozen values appear verbatim as code constants (`GRID_K`, `GRID_VIX`,
  `EPISODE_GAP`, `BUDGET_PER_YEAR`, `N_SHOCK`, `N_QUIET`, `N_NEAR`, `SURVIVAL_MIN`,
  `QUIET_MAX`, `NEAR_MISS_MAX`, `LEAD_MIN_MINUTES`, `LEAD_MIN_SHARE`,
  `LEAD_DAYS_MIN`, `A1_RECORDED`) and are pinned by tests.
- No lookahead in the daily series; the ramp VIX never decides a gate.
- `first_shock` parity with `shock.step` on all 26 A1 fixtures.
- The `index_atr_k > 0` guard; partial data never fires; the off path is byte-identical.

## Parallelisation

Sequential by design: the three gates and the stage order forbid most overlap.

- **Spine:** V222-1 → V222-1b → V222-2 → V222-3 → V222-3b → V222-4 → V222-4c → V222-5 (gate 1) → V222-8
  (gate 2) → V222-9 → V222-10 → V222-11 → V222-13 (gate 3) → V222-14. Each stage
  reads the previous stage's frozen results.
- **One module, sequential:** V222-1b creates `scripts/backtest/shock_index_screen.py`;
  V222-2, V222-3, V222-3b, V222-4 and V222-4c each extend it and its test file (V222-3b,
  V222-4 and V222-4c consume V222-3's `CellResult` and report dict; run 3b, then 4, then 4c).
- **V222-4b** (forward long-book) has disjoint files and no contract dependency (it
  re-states `cell_key`'s text rather than importing it) and may run beside
  V222-1b..V222-4c; V222-5 runs it on real data.
- **`scripts/dev/select_tests.py` is shared** by V222-1b, V222-6d, V222-7, V222-8
  and V222-13: never two of them at once.
- **V222-6d** needs `data/v222/^VIX.csv` from V222-1 (the prior close) and edits
  the builder and its test only; it may run beside V222-2..V222-5 (not beside
  another `select_tests.py` task). V222-13 consumes its fixture.
- **V222-7 → V222-7b → V222-7c:** one module and test file. V222-7 may start
  after V222-1 (disjoint code files); V222-8 needs V222-5's day list and V222-7c.
- **V222-7b needs V222-4 in the worktree:** `evaluate` imports `N_SHOCK`,
  `N_QUIET`, `N_NEAR` and `NEG_CLASSES` from `scripts/backtest/shock_index_screen.py`
  (a contract dependency, not a shared file), so V222-7b starts only after V222-4
  is committed on the v222 branch.
- **V222-9 → V222-10 → V222-11:** V222-10's `THRESHOLD_ATTRS` set-equality test
  needs V222-9's fields; V222-11 drives `thresholds_from_config` and
  `run_shock_pass`.
- **V222-12** needs the frozen cell (V222-8) only; disjoint from V222-9..V222-11
  and may run beside them.
- **V222-13** needs V222-9 (real `_index_path` in `shock.step`), V222-6d and
  V222-8. Gate 3 waits for V222-12 and V222-13.
- **V222-14** edits the same files as V222-10 (`swingbot/config.py`,
  `.env.example`, `tests/test_config_v209_keys.py`, `tests/scanning/test_shock_scan.py`)
  and runs last.

## Task ledger

| Id | Title | Part | Model | Files (C create / M modify) | Creates for later tasks |
|---|---|---|---|---|---|
| V222-1 | Worktree; daily SPY + `^VIX` to 2026-11-04 via `fetch_backtest_data.py --shock-index` | 1 | sonnet | M `scripts/data/fetch_backtest_data.py`; C `tests/backtest_scripts/test_fetch_shock_index.py`; data `data/v222/{SPY.csv,^VIX.csv,provenance.json}` (main tree) | worktree + branch `2026-11-09-v222-shock-index-vix-path`; `fetch_backtest_data.SHOCK_INDEX_END = "2026-11-04"`, `SHOCK_INDEX_SPY_START = "1993-01-01"`, `SHOCK_INDEX_VIX_START = "1990-01-01"`, `PINNED_CACHES = ("data/backtest_cache", "data/backtest_cache_ext")`, `SHOCK_INDEX_FILES = ("SPY.csv", "^VIX.csv", "provenance.json")`; `fetch_shock_index(cache_dir: Path, *, end: str = SHOCK_INDEX_END, fetcher=fetch) -> dict` (writes `SPY.csv`, `^VIX.csv` via `fetch_vix_context`, `provenance.json`; returns `{source, fetched_at, end, spy_first, spy_rows, vix_first, vix_rows}`; raises `ContextError` on a pinned cache); `shock_index_main(argv) -> int`, CLI `--shock-index --cache-dir DIR [--end] [--force]` (exit 2 on existing files without `--force` or a pinned dir) |
| V222-1b | Screen module readers, `DATA_READERS` row, the window, Results scaffold | 1 | sonnet | C `scripts/backtest/shock_index_screen.py`; C `tests/backtest_scripts/test_shock_index_screen.py`; M `scripts/dev/select_tests.py` (row `("data/v222/", ("tests/backtest_scripts/test_shock_index_screen.py",))`); M spec (main) `## Results` | `shock_index_screen.WINDOW_END = "2026-11-04"`, `OHLC`, `ROOT`; `read_daily(path: Path) -> pd.DataFrame` (Date index, `Open,High,Low,Close`); `common_window(spy, vix) -> dict` (`start, end, years, sessions`); Results `### Stage 1 — window` and the pending headings |
| V222-2 | Daily series, fire days, episodes (no lookahead) | 1 | opus | M `scripts/backtest/shock_index_screen.py`; M `tests/backtest_scripts/test_shock_index_screen.py` | `GRID_K = (1.0, 1.25, 1.5, 2.0)`; `GRID_VIX = (10.0, 15.0, 20.0, 25.0)`; `EPISODE_GAP = 5`; `BUDGET_PER_YEAR = 6`; `EPS = 1e-9`; `daily_moves(spy, vix) -> pd.DataFrame` (index sessions; cols `spy_close_atr, spy_low_atr, spy_open_atr, vix_close_chg, vix_high_chg`); `fire_days(moves, k: float, v: float, series: str) -> list[pd.Timestamp]` (`series` ∈ `"close"`, `"upper"`, `"spy_upper"` = upper SPY half only, `v` ignored); `episodes(fires, sessions: pd.DatetimeIndex, gap: int = EPISODE_GAP) -> list[list[pd.Timestamp]]`; `episodes_per_year(eps, years: range) -> dict[int, int]` (episode year = first fire's year); `representative(ep, moves) -> pd.Timestamp` (min `spy_low_atr`, ties earlier) |
| V222-3 | Grid, budget, edge-aware winner rule, prior check, report CLI | 1 | opus | M `scripts/backtest/shock_index_screen.py`; M `tests/backtest_scripts/test_shock_index_screen.py` | `CellResult` (frozen dataclass: `k, v, close_fires, close_episodes, upper_fires, upper_episodes, upper_episode_sessions, per_year_close: dict[int,int], per_year_upper: dict[int,int], years_over_cap: tuple[int,...], in_budget: bool`); `screen_grid(moves, years: range) -> list[CellResult]` (k outer, v inner); `neighbours(k, v) -> list[tuple[float, float]]`; `qualifying(cells) -> list[tuple[float, float]]` (most sensitive first); `pick_winner(cells) -> tuple[float, float] \| None`; `PRIOR = {"fail_k_max": 1.25, "fail_years_min": 2, "crisis_years": (2008, 2020), "winner_k_min": 1.5}`; `prior_report(cells, winner) -> dict`; `build_report(data_dir: Path) -> dict` (keys `window, cells, qualifying, winner, prior, episodes` with `episodes`: `"k,v" -> [[iso, ...], ...]` upper series); `render_md(report: dict) -> str`; `main(argv=None) -> int` CLI `--data-dir --out-json --out-md` |
| V222-3b | Descriptive arms: SPY-only, gap/intraday split, macro days, VIX-high timing | 1 | sonnet | M `scripts/backtest/shock_index_screen.py`; M `tests/backtest_scripts/test_shock_index_screen.py` | `spy_only_arm(moves, years: range) -> list[dict]` (per k: `k, upper_fires, upper_episodes, years_over_cap`); `macro_flag(d: date) -> str` (`"yes"`/`"no"`/`"unknown"`); `episode_splits(moves, eps) -> list[dict]` (`rep, total_atr, gap_atr, intraday_atr, gap_share, macro`); `vix_high_in_settle(vix_1m: pd.Series, open_utc: datetime, settle_min: int = 15) -> bool \| None`; `read_vix_1m(path: Path) -> pd.Series` (UTC bar start -> high, yfinance 3-header CSV); report keys `spy_only`, `splits` (winner cell, or `[]`), `vix_high_timing` (`{iso: bool \| None}`); CLI `--vix-1m PATH` (repeatable, `DAY=PATH`) |
| V222-4 | Stage 2 day picker, part 1: frozen constants, A1 days, Alpaca date, quiet slots | 2 | opus | M `scripts/backtest/shock_index_screen.py`; M `tests/backtest_scripts/test_shock_index_screen.py` | `N_SHOCK = 8`; `N_QUIET = 4`; `N_NEAR = 4`; `RESERVE = 3`; `EXCLUDE = (date(2026, 11, 5),)`; `A1_DAYS_FILE = Path("tests/fixtures/shock_replay/validation_days.json")`; `A1_SHOCK_DAYS` (six ISO days); `A1_FIXTURES = 26`; `QUIET_SLOTS`; `a1_fixture_days(path: Path) -> dict[str, list[date]]` (class -> days, all 26); `first_alpaca_date(pit_spy: Path) -> date`; `_eligible(day, alpaca_from) -> bool`; `quiet_days(moves, fires, ranked: list[date], sessions, *, alpaca_from=date.min) -> list[list[date]]` (4 slots, each `[pick, *reserves]`) |
| V222-4b | Forward long-book: prod dump and descriptive forward table | 2 | sonnet | C `scripts/reports/shock_longbook_dump.py`; C `scripts/backtest/shock_index_forward.py`; C `tests/scripts/test_shock_longbook_dump.py`; C `tests/backtest_scripts/test_shock_index_forward.py` | `shock_longbook_dump.longbook_record(trade: dict) -> dict \| None` (`{opened_at, r}`); `shock_index_forward.HORIZONS = (1, 3, 5)`; `forward_longbook(episodes: list[list[str]], trades: list[dict], sessions: list[str], horizons=HORIZONS) -> list[dict]` (per horizon `horizon, n_trades, n_episodes, exp_r, total_r, ci_low, ci_high`); CLI `--screen-json --longbook --data-dir --out-md` |
| V222-4c | Stage 2 day picker, part 2: shock ranking, near-miss, `stage2_days`, report and CLI | 2 | opus | M `scripts/backtest/shock_index_screen.py`; M `tests/backtest_scripts/test_shock_index_screen.py` | `rank_shock_days(moves, eps, *, alpaca_from: date, a1_days: set[date]) -> list[date]`; `near_miss_days(moves, k, v, counted: list[date], *, alpaca_from: date) -> list[date]`; `stage2_days(moves, winner, eps, *, a1_days, alpaca_from) -> dict` (`{"cell": [k, v], "alpaca_from": iso, "shock": [8 iso], "shock_reserve": [iso...], "quiet": [4 iso], "quiet_reserve": [[iso...] x4], "near_miss": [4 iso], "near_miss_reserve": [iso...], "a1_shock": [6 iso], "a1_negative": {class: [iso...]}}`); `stage2_section(moves, winner, a1_days, pit_spy) -> dict \| None`; report key `stage2_days`; CLI `--a1-days PATH --pit-spy PATH` |
| V222-5 | Run Stage 1, write Results, freeze the Stage 2 day list, gate 1 | 2 | sonnet | M spec (main) `## Results` § Stage 1, § Stage 2 day list; outputs `data/v222/{stage1.json,stage1.md,longbook.json,forward.md,stage2_days.json}` (main tree) | Results § Stage 1 (window, cells, prior, winner or NO-LIFT, arms) and § Stage 2 day list (alpaca_from written first); `data/v222/stage2_days.json` = `stage2_days(...)` dict |
| V222-6d | Derived 2026-11-05 fixture with real one-minute `^VIX` (new path, frozen file untouched) | 3 | sonnet | M `scripts/data/build_shock_replay_fixture.py`; M `tests/scripts/test_build_shock_replay_fixture.py`; C `tests/fixtures/shock_replay_2026_11_05_vix1m.json`; M `scripts/dev/select_tests.py` (row for the new fixture -> `tests/scripts/test_build_shock_replay_fixture.py`) | `VIX_BARS = Path("tests/fixtures/vix_2026_11_05_1m.csv")`; `VIX1M_OUT = Path("tests/fixtures/shock_replay_2026_11_05_vix1m.json")`; `VIX_BARS_SOURCE = "yfinance_1m"`; `load_vix_bars(path: Path) -> list[tuple[datetime, float]]` (UTC bar start, close); `vix_from_bars(bars, t: datetime, prior: float) -> dict` (`{"level", "chg_pct"}` from the last bar finished by `t`; both None when none); `derive_vix1m_fixture(frozen: dict, bars, prior: float) -> dict` (only `vix` per step and the header flags change: `vix_interpolated: false`, `vix_source`, `vix_prior`); CLI `--vix-bars PATH --vix-prior LEVEL [--out]` (reads `DEFAULT_OUT`, refuses `--out DEFAULT_OUT`, exit 2) |
| V222-7 | Intraday evaluator: readings, A1 first-`SHOCK` replica, index half, lead rule | 3 | opus | C `scripts/backtest/shock_index_intraday.py`; C `tests/backtest_scripts/test_shock_index_intraday.py`; M `scripts/dev/select_tests.py` (append the new test to the `tests/fixtures/shock_replay/` row) | `FORCE_VIX_BAR = -1e9`; `SURVIVAL_MIN = 6`; `QUIET_MAX = 0`; `NEAR_MISS_MAX = 2`; `LEAD_MIN_MINUTES = 30`; `LEAD_MIN_SHARE = 0.15`; `LEAD_DAYS_MIN = 5`; `A1_RECORDED = {"calm": 0, "rotation": 1, "hard": 0}`; `readings(fx: dict, th: ShockThresholds = ShockThresholds()) -> list[ShockReading]`; `index_half(reading, k: float, vbar: float) -> bool`; `first_shock(rs, th=ShockThresholds(), k: float = 0.0, vbar: float = FORCE_VIX_BAR) -> datetime \| None`; `index_first_fire(rs, k: float, vbar: float = FORCE_VIX_BAR, th=ShockThresholds()) -> datetime \| None`; `require_vix(rs, th) -> None` (ValueError on a settled reading with `vix_chg_pct is None`); `drop_ahead(rs, t: datetime \| None, spy_daily: dict) -> float \| None`; `DayLead` (frozen: `day, t_a1, t_idx, ahead_a1, ahead_idx, leads`); `lead_day(fx, k: float, vbar: float = FORCE_VIX_BAR) -> DayLead` |
| V222-7b | Stage 2 `evaluate`: survival, quiet, near-miss, A1-days false fires, lead, ramp run | 3 | opus | M `scripts/backtest/shock_index_intraday.py`; M `tests/backtest_scripts/test_shock_index_intraday.py` | `fixture_status(fx: dict) -> str` (`"ok"`, `"unbuildable"`, `"synthetic"`, `"no_vix"`); `a1_false_fire(fx: dict, rs, first: datetime \| None) -> bool`; `load_fixtures(days: dict, v222_dir: Path, a1_dir: Path) -> dict[str, dict]`; `evaluate(days: dict, fixtures: dict[str, dict]) -> dict` (keys `cell, complete, missing, survival, quiet, near_miss, a1_false_fires, lead, a1_shock_report, ramp, verdict` ∈ `"PASS"`/`"NO-LIFT"`/`"INCOMPLETE"`, `frozen: [k, v] \| None`); raises when A1-alone counts differ from `A1_RECORDED` |
| V222-7c | Day-list adapter for the builder; Stage 2 report and CLI | 3 | sonnet | C `scripts/data/shock_stage2_days.py`; C `tests/scripts/test_shock_stage2_days.py`; M `scripts/backtest/shock_index_intraday.py`; M `tests/backtest_scripts/test_shock_index_intraday.py` | `shock_stage2_days.stage2_info(stage2: dict, isos: list[str]) -> dict` (`{"days": {iso: info}}`, info via `shock_validation_days.day_table` / `_day_row`, class `shock`/`quiet`/`near_miss`); CLI `--stage2-json --out [--only iso,...]`; `shock_index_intraday.render_md(result: dict) -> str`; `main(argv=None) -> int` CLI `--days-json --v222-dir --a1-dir --out-json --out-md` (exit 0 complete, 3 incomplete, 2 bad input) |
| V222-8 | Build Stage 2 fixtures, run, write Results, freeze the cell, gate 2 | 3 | sonnet | C `tests/fixtures/shock_replay_v222/days.json` (copy of `stage2_days.json`) and `tests/fixtures/shock_replay_v222/<iso>.json.gz`; M `tests/backtest_scripts/test_shock_index_intraday.py` (committed-fixture shape test); M `scripts/dev/select_tests.py` (row `("tests/fixtures/shock_replay_v222/", ("tests/backtest_scripts/test_shock_index_intraday.py",))`); M spec (main) `## Results` § Stage 2; outputs `data/v222/{stage2_info.json,stage2.json,stage2.md}` | Results § Stage 2: frozen cell `FROZEN_K, FROZEN_V` (= the Stage 1 winner) or NO-LIFT |
| V222-9 | `ShockThresholds` index fields, `_index_path`, `entry_condition` | 4 | sonnet | M `swingbot/core/market/shock.py`; M `tests/market/test_shock_step_entry.py` | `ShockThresholds.index_atr_k: float = 0.0`, `.index_vix_chg: float = 0.0` (appended after `quote_max_age_s`); `shock._index_path(reading: ShockReading, th: ShockThresholds) -> bool` |
| V222-10 | Config keys, `THRESHOLD_ATTRS` rows, `.env.example`, config pins | 4 | sonnet | M `swingbot/config.py`; M `swingbot/core/scanning/shock_scan.py`; M `.env.example`; M `tests/scanning/test_shock_scan.py`; M `tests/test_config_v209_keys.py` | `SHOCK_INDEX_ATR_K` (float, default `"0.0"`, min 0, max 5.0, step 0.25) and `SHOCK_INDEX_VIX_CHG` (float, default `"0.0"`, min 0, max 200, step 1), placed after `SHOCK_VIX_RELIEF`; `THRESHOLD_ATTRS["index_atr_k"] = "SHOCK_INDEX_ATR_K"`, `["index_vix_chg"] = "SHOCK_INDEX_VIX_CHG"` |
| V222-11 | Pipeline tests: partial data, stale/proxy VIX, SPY chunk room, off is byte-identical | 4 | sonnet | C `tests/scanning/test_shock_index_path.py`; M `tests/scanning/test_shock_plans_byte_identical.py` | none (tests only) |
| V222-12 | Production check (read-only): `^VIX` tape, staleness, lag, `spy_atr_move` nulls, explicit keys, shadow fire rate | 5 | sonnet | C `scripts/reports/shock_vix_check.py`; C `tests/scripts/test_shock_vix_check.py`; M spec (main) `## Results` § Production check | `shock_vix_check.tape_status(entry: dict, now: datetime, max_age_s: int = 600) -> dict`; `COVERAGE_SQL`; `coverage(rows: list[dict], max_age_s: int = 600) -> dict`; `lag_points(rows: list[dict], vix_1m: pd.Series) -> list[dict]`; `shadow_fire_rate(rows: list[dict], k: float, v: float) -> dict`; `ENV_KEYS = ("SHOCK_INDEX_ATR_K", "SHOCK_INDEX_VIX_CHG")`; `env_presence(counts: dict[str, int]) -> dict[str, bool]` |
| V222-13 | Stage 3 reports: 2026-11-05 in-sample and A1 days with ramp VIX, gate 3 | 5 | sonnet | C `scripts/backtest/shock_index_stage3.py`; C `tests/backtest_scripts/test_shock_index_stage3.py`; M `scripts/dev/select_tests.py` (append the new test to the vix1m and `shock_replay/` rows); M spec (main) `## Results` § Stage 3 | `replay_labels(fx: dict, th: ShockThresholds) -> list[tuple[ShockReading, str]]` (real `shock.step`); `in_sample_1105(fx: dict, k: float, v: float) -> dict` (first `SHOCK` with/without, longs opened before each; refuses `vix_interpolated: true`); `a1_ramp_report(a1_dir: Path, k: float, v: float) -> dict` (recall, false fires per class, lead share, beside A1's row); CLI `--fixture --a1-dir --k --v --out-md` |
| V222-14 | Release: frozen cell becomes the config `Field` default | 5 | sonnet | M `swingbot/config.py`; M `.env.example`; M `tests/test_config_v209_keys.py`; M `tests/scanning/test_shock_scan.py` | `SHOCK_INDEX_ATR_K` / `SHOCK_INDEX_VIX_CHG` defaults = `FROZEN_K` / `FROZEN_V` (help: VIX half never tested intraday on a shock day); `ShockThresholds()` stays `0.0` (pinned) |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-09-v222-shock-index-vix-path_1-stage1-screen.md` | V222-1, V222-1b, V222-2, V222-3, V222-3b | worktree, daily data, daily screen, winner rule, prior, descriptive arms |
| 2 | `2026-11-09-v222-shock-index-vix-path_2-stage1-picker-run.md` | V222-4, V222-4b, V222-4c, V222-5 | Stage 2 day picker, forward long-book, Stage 1 run and gate 1 |
| 3 | `2026-11-09-v222-shock-index-vix-path_3-stage2-intraday.md` | V222-6d, V222-7, V222-7b | 11-05 one-minute fixture, intraday evaluator, gates and `evaluate` |
| 3b | `2026-11-09-v222-shock-index-vix-path_3b-stage2-run.md` | V222-7c, V222-8 | day-list adapter, Stage 2 report and CLI, Stage 2 fixtures, run and gate 2 (part 3 split at a task boundary: it passed 1500 lines) |
| 4 | `2026-11-09-v222-shock-index-vix-path_4-detector.md` | V222-9..V222-11 | `_index_path`, config keys and pins, pipeline tests |
| 5 | `2026-11-09-v222-shock-index-vix-path_5-release.md` | V222-12..V222-14 | production check, Stage 3 reports, gate 3, release |
