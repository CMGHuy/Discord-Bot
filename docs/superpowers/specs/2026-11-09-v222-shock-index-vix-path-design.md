# v222 — Market-shock detector: index + VIX entry path

**Version:** ui 1.40.3 · bot 2.17.3
**Bump:** bot patch (a third entry condition inside the shadow-only v209 detector; no new surface)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-researcher, veteran-trader

> **Amended 2026-11-13: rebased on the shipped A1 detector.** The first draft
> (2026-11-09) was written against v209's original two-path rule on its unmerged
> branch. Since then v209 shipped on `main` (bot 2.18.0, shadow-only, closed out
> in `62dd3d8f`) with **Amendment A1** (`b7b29020`), which replaced the entry
> rule. The 11-05 replay test that this draft gated on was deleted in favour of
> the A1 one-shot acceptance test (`b65e1c2b`, PASS). Partner decision: rewrite
> v222 against the A1 rule. The `Version:` line is the authoring stamp of the
> first draft (`main` is now ui 1.41.0 · bot 2.18.6). Read § Premise check first.

## Premise check (2026-11-13)

Every fact below was re-measured on `main` at `9566a326`, read-only.

**What shipped.** `shock.entry_condition` (`swingbot/core/market/shock.py`) is
now `_depth_path or _majority_path or _fast_path`:

- `_depth_path`: `depth_frac >= SHOCK_DEPTH_FRAC` (0.50, the share of sectored
  names that sit in down sectors) and `breadth_frac >= SHOCK_BREADTH_ENTER - relief`.
- `_majority_path`: `breadth_frac >= SHOCK_BREADTH_MAJORITY - relief` (0.50), no
  speed or depth needed.
- `_fast_path`: unchanged (breadth ≥ 0.25 and speed ≥ 0.10).

`SHOCK_SECTORS_FRAC` is gone. VIX still only gives relief (0.05 off the breadth
bars when VIX is up ≥ 15 %); it never fires a path. SPY never fires a path. The
open-settle and two-consecutive-reading rules are unchanged. The keys are mapped
in `shock_scan.THRESHOLD_ATTRS`.

**A1 already reaches `SHOCK` on 2026-11-05.** Replaying the frozen fixture
(`tests/fixtures/shock_replay_2026_11_05.json`, 87 names, 26 steps) through
`shock.measure` / `shock.step` with default thresholds:

| UTC | breadth | depth_frac | SPY ATR move | paths (depth / majority / fast) | label |
|---|---|---|---|---|---|
| 14:45 | 0.294 | 0.000 | −1.12 | – / – / – | NORMAL |
| 15:00 | 0.424 | 0.484 | −1.44 | – / – / fast | NORMAL |
| 15:15 | 0.447 | 0.484 | −1.88 | – / – / – | NORMAL |
| 15:30 | 0.506 | 0.565 | −2.22 | depth / majority / – | NORMAL (streak 1) |
| 15:45 | 0.529 | 0.565 | −2.49 | depth / majority / – | **SHOCK** |

It stays `SHOCK` to the close. The result is the same whether VIX comes from the
fixture's interpolated line or from the real one-minute bars
(`tests/fixtures/vix_2026_11_05_1m.csv`): relief is 0.05 from 15:00 either way.
`test_shock_acceptance_a1.py` reports the same thing: *"first SHOCK 15:45 UTC;
7 of 25 longs opened at/after 14:36 UTC came before it."*

This is **in-sample**. A1's own spec says its structure and its two 0.50 bars
were chosen after 2026-11-05 was read, to fit it. So the original v222 motivation
("no path fires on 2026-11-05") is **no longer true**. The day is now detected,
45 minutes after the 15:00 UTC point that the settle and two-reading rules allow.

**Where A1 is weak: timing, not recall.** In the A1 one-shot acceptance (frozen
validation days 2023–2025, PASS: recall 5/6, false fires calm 0/12, rotation 1/4,
hard 0/4), the share of each shock day's SPY drop (prior close to close) still
ahead at the first `SHOCK`:

| Shock day | SPY | First SHOCK (UTC, open+) | Drop still ahead |
|---|---|---|---|
| 2024-08-05 | −2.91 % flush | 14:00, +30 m | −14 % (SPY closed above the reading) |
| 2024-12-18 | −2.98 % grind | 21:00, +390 m | 0 % (at the close) |
| 2025-03-10 | −2.66 % flush | 18:00, +270 m | −1 % |
| 2025-04-04 | −5.86 % grind | 14:30, +60 m | 35 % |
| 2025-04-21 | −2.38 % grind | never | – |
| 2025-10-10 | −2.70 % grind | 19:15, +345 m | 20 % |

On four of the five hits, A1 fired with 20 % or less of the drop still ahead.
It labels shock days, but mostly after the damage. The validation fixtures build
VIX from the daily open and close (the close is lookahead at intraday steps), so
these rows say nothing about a VIX-based rule. They show only A1's lag.

**What the index path still adds, and what it does not.**

- *Recall on 2026-11-05:* nothing. A1 already detects the day.
- *Lead time:* possibly. On 2026-11-05 SPY was already −1.12 ATR at 14:45 and
  −1.44 at 15:00, while breadth reached A1's bars only at 15:30. A rule on SPY
  and VIX can only make the first `SHOCK` earlier or leave it where it is (it is
  an extra OR term). Whether it is earlier on *out-of-sample* shock days without
  extra false fires is open. Stages 1 and 2 measure that. A new lead gate makes
  "adds nothing over A1" a NO-LIFT result (§ Frozen).
- *2026-11-05 as a gate:* gone. During this check the real one-minute VIX values
  and the SPY ATR readings at 14:45 and 15:00 were read. So it is now known which
  grid cells would hold on both readings. A blind run is no longer possible.
  Like A1, 2026-11-05 becomes an **in-sample report, never a gate**. This applies
  the A1 panel's BLOCKING ruling, which removed the 11-05 gate.

**Data point found during the check.** The real one-minute `^VIX` bars read 23.15
at 15:20 UTC. The live tape row that the first draft used read 21.13 (+27.2 %) at
the same time. The tape lagged the index by about 2 points during the fastest part
of the move. Production shadow rows (read-only, 2026-11-13) hold 221 readings over
2026-11-10..12. None has a null `vix_chg_pct`, and none reached `SHOCK` (quiet
days: SPY never beyond −0.64 ATR, breadth ≤ 0.08). That says the VIX feed is
present, not that it is timely or that it is the non-proxy `^VIX`. V222-12 still
checks both.

**Recommendation.** The idea is **not fully moot**: its remaining claim is lead
time. Proceed with the frozen grid and budget, with 2026-11-05 demoted and the
lead gate added. If Stage 1 has no cell inside the budget, or Stage 2 shows no
earlier first `SHOCK` than A1 on any frozen shock day, close `no-lift/`.

## Why

v209's detector (`swingbot/core/market/shock.py`, `swingbot/core/scanning/shock_scan.py`,
on `main`, `MARKET_SHOCK_MODE=shadow` in production) labels the market `NORMAL` /
`SHOCK` / `RECOVERY` from watchlist breadth and sector depth. After A1 it finds
shock days (recall 5/6 on the frozen set), but late (table above). The index and
VIX often move before half the watchlist is one ATR down, and they are already in
every reading (`spy_atr_move`, `vix_chg_pct`). v222 asks one question: does a
pre-registered SPY + VIX path move the first `SHOCK` earlier, out of sample,
within a false-fire budget? It is a labelling-integrity change (`Edge: none
(integrity)`). The label still never blocks a trade.

## What changes

`shock.entry_condition` gains a fourth path next to `_depth_path`,
`_majority_path` and `_fast_path`:

- `_index_path(reading, th)`: false when `th.index_atr_k <= 0` (off; without this
  guard a calm reading with `-spy_atr_move >= 0.0` and `vix_chg_pct >= 0.0`
  would fire). Otherwise true when `-reading.spy_atr_move >= th.index_atr_k`
  **and** `reading.vix_chg_pct >= th.index_vix_chg`. `spy_atr_move` and
  `vix_chg_pct` already exist on `ShockReading`, so **no new stored field**. A
  missing SPY quote or ATR, a VIX reading older than `vix_max_age_s`, or a
  proxy-tape row (`shock_scan.read_vix` returns no VIX for a proxy) makes the
  path false. It never fires on partial data. VIX relief does not apply to it
  (relief lowers breadth bars only).
- `entry_condition` returns `_depth_path or _majority_path or _fast_path or _index_path`.

Unchanged: the open-settle rule, the two-consecutive-reading rule (readings from
different paths count toward the same streak, as they already do for A1's three
paths), the `SHOCK` label (so stored rows and v210's notices and badge need no
change), and the exit, recovery, re-entry and carry rules. Everything stays
`shadow`: the label never blocks a trade.

**Config.** `ShockThresholds` gets `index_atr_k: float = 0.0` and
`index_vix_chg: float = 0.0`. Keys follow the existing section:
`SHOCK_INDEX_ATR_K` and `SHOCK_INDEX_VIX_CHG`, declared in `swingbot/config.py`
(hot-reloaded on SIGHUP), each with a matching `THRESHOLD_ATTRS` row in
`shock_scan.py`, or they never reach `ShockThresholds`
(`thresholds_from_config` converts with `type(default)(...)`), and pinned in
`tests/test_config_v209_keys.py` (`V209_FIELDS`, `CAST_DEFAULTS`).
**"Off" is `index_atr_k = 0.0`** (a float sentinel, as `DCB_VOLUME_RATIO` does).
A `None` default would make `thresholds_from_config` raise on every pass;
`run_shock_pass` would swallow it, and the whole detector would silently stop
taking readings. `SHOCK_INDEX_ATR_K` carries `min=0` (unlike `SHOCK_ATR_K`,
`min=0.25`).

**Where the frozen cell lives (changed by this amendment).** The
`ShockThresholds` dataclass default **stays `0.0`**. Default `ShockThresholds()`
is what `test_shock_acceptance_a1.py` replays. That test is the record of a
closed one-shot pre-registration, and turning the index path on in it would
silently change A1's recorded verdict. On a Stage 3 release, the frozen cell
becomes the **config `Field` default** (and its `CAST_DEFAULTS` pin and
`.env.example`), so production's shadow pass reads it through
`thresholds_from_config`. The v222 tests pass the cell explicitly. Stage results
go in a `## Results` section of this spec.

## Frozen before any data is read

Nothing in this section changes after Stage 1 opens its data. The grid, budget
and winner rule are exactly the first draft's. The amendment adds one gate and
demotes 2026-11-05. No stage has run.

- **Window.** From the first date both SPY and ^VIX daily bars exist to
  2026-11-04 (the day before 2026-11-05). The cache does not reach that far
  today (`data/backtest_cache_ext/^VIX.csv` covers 2009-06-01 to 2019-12-31;
  SPY daily ends 2025-12-30 there), so Stage 1 first extends both series to
  2026-11-04. Both dates and the year count are written into the results
  section before any cell is read.
- **Grid.** `index_atr_k` ∈ {1.0, 1.25, 1.5, 2.0} × `index_vix_chg` (percent) ∈
  {10, 15, 20, 25}. 16 cells.
- **Episode.** A fire is a session on which the daily rule holds. Fires
  separated by fewer than **5 sessions** form one episode.
- **Budget.** At most **6 episodes in every calendar year** of the window, so one
  crisis year cannot carry the rest. It is evaluated on the **upper-bound
  series** below.
- **Winner rule.** Among cells inside the budget, take the *most sensitive*
  (lowest `index_atr_k`, then lowest `index_vix_chg`) whose neighbours on both
  axes are also inside the budget. If none qualifies, the result is
  **NO-LIFT** and nothing ships.
- **Intraday survival (Stage 2).** A cell survives when it fires (two
  consecutive settled readings) on at least 75 % of the frozen shock days and on
  none of the frozen quiet days.
- **Lead over A1 (Stage 2, added 2026-11-13).** On the same fixtures, compare the
  first `SHOCK` of the shipped A1 detector alone with A1 plus the index path at
  the surviving cell. The cell must make the first `SHOCK` **strictly earlier on
  at least one frozen shock day**. Otherwise the index path adds nothing over A1,
  and the result is **NO-LIFT**. Because Stage 2 confirms only the SPY half where
  intraday VIX is interpolated, this comparison is an **upper bound** on the lead.
  It can fail the idea but never prove the lead. Per shock day the results report
  both first-`SHOCK` times and the share of the SPY drop still ahead at each.
- **Stage 2 day list.** 5 to 10 days, written into the results section **before**
  any replay is built: the shock days are the largest Stage 1 episodes by SPY
  ATR move, the quiet days are matched by date in other months. **2026-11-05 is
  excluded.** Where a chosen day already has an A1 validation fixture
  (`tests/fixtures/shock_replay/<day>.json.gz`), that fixture is reused as is.
  The choice of days never looks at it.
- **2026-11-05 (in-sample, never gated).** Its outcome inputs were read during
  the premise check, so it decides nothing (§ Stage 3).

## Stages

**Stage 1 — daily screen.**
- **Data.** `scripts/data/fetch_backtest_data.py` does not carry VIX today, so
  Stage 1 begins by adding daily `^VIX` (the same Yahoo source the live tape
  uses) to the cache. The results record the source and fetch date.
- **Two series.** A *close* series (SPY close vs prior close, VIX daily change)
  and an *upper-bound* series (SPY daily low vs prior close, VIX daily high vs
  prior close). The live rule can fire on any of 26 intraday readings, so a day
  that breaks the threshold and recovers fires live but not on the close. The
  close series is therefore a **lower bound** on the live rate, and the budget
  is judged on the upper-bound series. Neither series can show the
  two-consecutive-reading rule.
- **Report per cell.** Fire days, distinct episodes, episodes per year (each
  year, not only pooled).
- **Forward long-book results (1, 3, 5 sessions)** are **descriptive only**: they
  decide no cell and no gate. Report N per episode as well as per trade (trades
  inside one episode are not independent), Total R beside ExpR, and
  `week_cluster_bootstrap` intervals (`swingbot/core/backtesting/instrument/stats.py`).
  A shock can be followed by a bounce, so no pass/fail direction is claimed.

**Stage 2 — intraday confirmation and lead.** For the cells that pass Stage 1,
replay one fixture per frozen day. Days without an A1 fixture are built with
`scripts/data/build_shock_replay_fixture.py`. Its A1 `build_day_fixture` /
`--validation-days` mode is already parameterised by session date (DST-aware) and
draws VIX as a ramp from the daily open change to the close change. That ramp
uses the close, so it is not point-in-time, and it never confirms the VIX half:
each day confirms only the SPY half, and the results say so. Only Alpaca fixtures
count; a synthetic or unbuildable one confirms nothing. Report the first `SHOCK`
time and the per-step table for each day, then apply the survival rule and the
lead-over-A1 gate (§ Frozen). One cell is frozen from Stages 1 and 2 alone.

**Stage 3 — release and in-sample report.** No stage-3 gate remains on
2026-11-05. With the frozen cell:
- **2026-11-05, reported once.** Run on a *separate* fixture built from the real
  one-minute `^VIX` bars (each step reads the close of the last bar finished by
  the step, against the tape's prior close, `vix_interpolated: false`). It is
  written to a new path. The frozen `shock_replay_2026_11_05.json` stays
  untouched, because the A1 acceptance test pins its shape
  (`vix_interpolated is True`). Report the first `SHOCK` time with and without
  the index path and the longs-opened-before line. It is labelled in-sample and
  decides nothing.
- **A1 validation days, reported.** Replay the 26 frozen A1 fixtures with A1
  plus the index path at the frozen cell. Report recall, false fires per class
  and lead share next to A1's recorded row, with the caveat that their VIX ramp
  uses the daily close. Reported, never gated: those days were not chosen for
  v222, and their VIX is not point-in-time.
- **Release.** After the V222-12 production check, the frozen cell becomes the
  config `Field` default (`ShockThresholds` stays `0.0`, § Config). The A1
  acceptance test is not edited.

## Acceptance

- Stage 1 and 2 results, including the lead-over-A1 table, are in the spec's
  results section before any default is set.
- With `index_atr_k = 0.0`, or mode `off` / `shadow`, every long and short plan
  is byte-identical to before (the V209-8b pins extend to the new path), and
  A1's three paths and the readings are unchanged.
- `tests/market/test_shock_acceptance_a1.py` passes unedited and prints the same
  report as on `main` before v222.
- Missing SPY or ATR, a stale or proxy VIX: the path is false, and the other
  paths behave exactly as before.
- Production check before the release (read-only): a non-proxy `^VIX` tape row
  exists during market hours (the tape maps `^VIX=VIXY` as a proxy fallback; if
  production only has the proxy, the path can never fire and the spec says so).
  Also report how often the tape VIX is missing or older than `vix_max_age_s` in
  the shadow rows that now exist (221 at 2026-11-13).
- Every new function stays under cyclomatic complexity 15. Unit tests cover
  boundary values at each threshold, partial-data cases, the `0.0` off value,
  and the interaction with the settle and two-reading rules (including a streak
  built from one A1 path and the index path).

## Non-goals

- No change to the depth, majority, fast, exit, recovery or carry rules, or to
  any A1 threshold.
- No new label, state machine, stored field or table.
- No edit to the A1 acceptance test, its day list or its fixtures, and no re-run
  of A1 as a gate.
- No notices, badge, trade blocking or short switching (v210 and later). The
  label is information; this spec does not decide what an alert-time trader or
  v210 does with it. It first fires at about 10:00 ET, after the open, so it
  cannot protect resting orders placed before the open.
- No threshold chosen from a single day, and none from 2026-11-05.
- The concentrated-sector path and the sector assignment of the 22 unsectored
  names are separate ideas. A1's weighted depth covers part of the first.

## Risks

- **The budget is a floor on false positives.** Even the upper-bound series
  cannot show a 10:00 ET fire on a day that recovers by noon, or the
  two-reading rule. The real intraday rate comes from the shadow rows: 221 so
  far, all quiet days, so no rate yet.
- **The lead gate is one-sided.** With the VIX half unconfirmed on historical
  days, passing it shows that SPY moved before breadth, not that the full rule
  would have fired. The shadow rows are the only test of the VIX half.
- **VIX as a percent change.** +20 % is about 2.4 points at a VIX of 12 and
  about 6 at 30. No minimum VIX level is in the grid (YAGNI). If the shadow
  rows show low-level noise, a floor is a follow-on.
- **VIX source and lag.** The live path reads Yahoo `^VIX` with a 600 s age gate.
  On 2026-11-05 the tape read about 2 points below the real index at 15:20 UTC
  (premise check), so a lagging tape delays the VIX half exactly when it matters.
  A stale tape silences the path: safe, but late.
- **Gap days.** A gap fires against the prior close at the first settled reading.
  The two-reading rule is the only guard. 2024-08-05 shows A1 alone already
  firing at +30 m on a flush that closed above the reading.

## Order of work

**Branch.** v209 is on `main`, so v222's implementation takes a **fresh worktree
off `main`** (named per `document-lifecycle.md`). The old instruction to stack on
the v209 branch is void: that branch and worktree are gone. Stages 1 and 2 are
read-only analysis and need no code branch. Order: Stage 1, Stage 2,
implementation, production check, Stage 3 release and reports.

**Plan impact (the plan files are not edited by this amendment; re-plan before
implementing).**
- Part 1 (V222-1..V222-5, Stage 1 daily screen): survives unchanged.
- Part 2a: V222-6 and V222-6b (builder parameterised by session date, CLI and
  per-session outputs) are **dropped**. A1 already ships `build_day_fixture`
  and `--validation-days`, and at most a thin adapter for the Stage 2 day list
  remains. V222-6c (archive the one-minute VIX bars) is **done** on `main`
  (`b253ef36`). V222-6d survives **changed**: the `--vix-bars` build writes a
  *new* 2026-11-05 fixture path and never overwrites the frozen one.
- Part 2b (V222-7, V222-7b, V222-8): survive, **extended** with the
  A1-alone vs A1+index comparison and the lead gate, and reuse of existing A1
  fixtures.
- Part 3: V222-9 (`_index_path` beside `_majority_path`; `ShockThresholds`
  default stays 0.0), V222-10 (keys, `THRESHOLD_ATTRS`, `test_config_v209_keys.py`
  pins), V222-11 (pipeline tests) and V222-12 (production `^VIX` check) survive
  with small edits. V222-13 (11-05 one-shot pass/fail) is **replaced** by the
  in-sample report plus the A1-validation-days report. V222-14 ("frozen cell
  becomes the `ShockThresholds` default; commit the replay test unchanged") is
  **replaced**: the cell goes to the config `Field` default only, and the replay
  test it names no longer exists.

## Panel review

First draft (2026-11-09). Rows naming the V209-12b replay test or the 11-05
gate are superseded by the 2026-11-13 amendment (§ Premise check); the rest
still hold. The amendment itself has not had a panel. Rerun `/panel` on this
spec before re-planning.

staff-engineer (opus), 8 advisories, no blockers:
- staff-engineer: "off" via unset would crash `thresholds_from_config` silently -- applied (0.0 sentinel, Config).
- staff-engineer: `spy_atr14` redundant with `spy_atr_move` -- applied (field dropped).
- staff-engineer: rows without the new field raise in `_from_row` -- applied (no new field, so moot).
- staff-engineer: VIX-source risk measured on shadow rows that do not exist -- applied (Risks, Acceptance production check for a non-proxy ^VIX row).
- staff-engineer: which branch v222 builds on and the stale Version line -- applied (Order of work; amended 2026-11-13: fresh worktree off main).
- staff-engineer: key naming and `THRESHOLD_ATTRS` row -- applied (`SHOCK_INDEX_*`, Config).
- staff-engineer: fixture VIX provenance for Stage 2 days -- applied (Stage 2).
- staff-engineer: daily VIX history source unnamed -- applied (Stage 1 Data).

quant-researcher (opus), 3 BLOCKING, 5 advisory:
- quant-researcher BLOCKING: grid values and winner rule not frozen -- applied (Frozen section: grid, winner rule).
- quant-researcher BLOCKING: 2026-11-05 could act as a tuning input -- applied (cell frozen before one pass/fail run; 11-05 excluded from Stage 2). Amended 2026-11-13: 11-05 is in-sample and never gated.
- quant-researcher BLOCKING: episode gap length undefined -- applied (5 sessions, every calendar year).
- quant-researcher: daily proxy biased low, report an upper bound -- applied (two series, budget on the upper bound).
- quant-researcher: forward-return population, role, N, bootstrap -- applied (descriptive only, N per episode, `week_cluster_bootstrap`).
- quant-researcher: Stage 2 day list and survival criterion -- applied (Frozen section).
- quant-researcher: window not fixed -- applied (Frozen section, per-year reporting).
- quant-researcher: `_from_row` / `spy_atr14` -- applied (see staff-engineer).

veteran-trader (sonnet), 7 advisories, no blockers:
- veteran-trader: fast-path row described wrongly -- applied (first draft's table; superseded by the A1 table in § Premise check).
- veteran-trader: interpolated VIX uses the 15:20 reading, so the 15:00 gate is partly a tuning target -- applied (real one-minute bars; amended 2026-11-13: the gate is gone).
- veteran-trader: daily budget biased low, a floor only -- applied (Risks, Stage 1 two series).
- veteran-trader: timeline ambiguity -- applied (UTC/ET and per-row times).
- veteran-trader: `spy_atr14` redundant -- applied.
- veteran-trader: VIX proxy tape, percent scale, minimum level -- applied for the proxy and scale (Acceptance, Risks); a minimum VIX level in the grid -- rejected: YAGNI, a follow-on if shadow rows show noise.
- veteran-trader: how the label is used by an alert-time trader -- applied (Non-goals; forward returns descriptive only).

Plan-writing finding (2026-11-09): the interpolated VIX made Stage 3 fail in every cell by
construction (14:45 reads +8.2 % < 10) -- applied then: real one-minute `^VIX` bars for the
2026-11-05 fixture. Amended 2026-11-13: that fixture is now a separate in-sample report, and
historical Stage 2 days keep the SPY-half-only rule, since yfinance holds intraday bars only for
recent sessions.
