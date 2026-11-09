# v222 — Market-shock detector: index + VIX entry path

**Version:** ui 1.40.3 · bot 2.17.3
**Bump:** bot patch (a third entry condition inside the shadow-only v209 detector; no new surface)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-researcher, veteran-trader

## Why

v209 (`swingbot/core/market/shock.py`, on the unmerged branch
`2026-11-05-v209-market-shock-detector`) labels the market `NORMAL` / `SHOCK` /
`RECOVERY` from breadth and sector depth. Its acceptance test is a replay of
**2026-11-05**: the first `SHOCK` must come at or before 15:00 UTC. V209-12
built that fixture from Alpaca (`tests/fixtures/shock_replay_2026_11_05.json`,
87 tickers, 26 steps, commit `eafc6eb8`), and V209-12b measured the result:
**the detector stayed `NORMAL` at all 26 steps (14:45 to 21:00 UTC).** The
replay test is written but uncommitted (3 of 5 tests fail with
`StopIteration`).

The fixture is real, not broken. Times below are UTC; US DST ended on
2026-11-01, so 15:00 UTC is 10:00 ET. Every row is the 15:00 UTC reading
unless it says otherwise.

| Measure at 15:00 UTC | Value | Rule | Result |
|---|---|---|---|
| Breadth (equities down more than 1 ATR) | 0.424 | enter at 0.40 | passes |
| Sectors down (median name down more than 1 ATR) | 1 of 8 | needs 5 (`sectors_frac` 0.6) | **fails**, so the depth path is false |
| Breadth speed | +0.129 | fast path needs breadth ≥ 0.25 and speed ≥ 0.10 | **passes on this one reading**, but the 14:45 reading has no speed (no previous reading) and breadth 0.294, so it does not qualify; the two-consecutive-reading rule (`_from_normal`) then needs 15:15, where speed is +0.024 and fails |
| SPY | −1.65 % (−1.4 ATR) | no entry path uses it | n/a |
| QQQ | −3.6 % | not used | n/a |
| VIX | +21 % to +27 % | not used | n/a |
| Semiconductors (14 in the fixture) | all down 5 % to 14 % (SNDK −13.6, AMD −12.6, MU −10.6, NVDA −5.0) | n/a | n/a |

By 21:00 UTC (the close) SPY was −4.4 % and QQQ −6.4 %: SPY lost about
another 2.75 % after the 15:00 reading. The day was a semiconductor/AI-led
crash that dragged the index. At 15:00 UTC only Information Technology (27 of
30 names down) cleared the sector rule; Consumer Discretionary, Financials,
Industrials and Health Care were mostly down at that time but not a full ATR
at the median; 22 names with no sector (IREN, NBIS, RGTI, MSTR, ARM, SHOP
and similar) count toward breadth but never toward the sector rule.

So no existing path holds for two consecutive readings: depth needs a broad
sector selloff, and the fast path needs a sustained breadth jump. A
concentrated, index-dragging crash does neither, while the index and the VIX
were already showing it. This is one day's lead, not evidence of an edge.

**VIX provenance in the fixture.** The fixture's VIX is a straight line from 0 % at
14:30 UTC to the 15:20 UTC tape reading (21.13, +27.21 %), then flat. The 15:00
value therefore uses a later observation and is **not point-in-time**. It is a
construction aid for the replay, never evidence.

## What changes

`shock.entry_condition` gains a third path next to `_depth_path` and
`_fast_path`:

- `_index_path(reading, th)`: true when `-reading.spy_atr_move >= th.index_atr_k`
  **and** `reading.vix_chg_pct >= th.index_vix_chg`. `spy_atr_move` already
  exists on `ShockReading` (`shock.py:90`), so **no new stored field**. A
  missing SPY quote or ATR, or a VIX reading older than `vix_max_age_s` or a
  proxy-tape row (`shock_scan.read_vix` returns no VIX for a proxy), makes the
  path false. It never fires on partial data.
- `entry_condition` returns `_depth_path or _fast_path or _index_path`.

Unchanged: the open-settle rule, the two-consecutive-reading rule, the `SHOCK`
label (so stored rows and v210's notices and badge need no change), and the
exit, recovery and carry rules. Everything stays `shadow`: the label never
blocks a trade.

**Config.** `ShockThresholds` gets `index_atr_k: float` and
`index_vix_chg: float`. Keys follow the existing section:
`SHOCK_INDEX_ATR_K` and `SHOCK_INDEX_VIX_CHG`, declared in `swingbot/config.py`
(hot-reloaded on SIGHUP) with a matching `THRESHOLD_ATTRS` row in
`shock_scan.py`, or they never reach `ShockThresholds`
(`thresholds_from_config` converts with `type(default)(...)`).
**"Off" is `index_atr_k = 0.0`** (a float sentinel, as `DCB_VOLUME_RATIO` does);
a `None` default would make `thresholds_from_config` raise on every pass,
`run_shock_pass` would swallow it, and the whole detector would silently stop
taking readings. The shipped default is `0.0` until Stage 1 freezes a cell.

## Frozen before any data is read

Nothing in this section is changed after Stage 1 opens its data.

- **Window.** From the first date both SPY and ^VIX daily bars exist in the
  cache to 2026-11-04 (the day before the replay). Both dates and the year
  count are written into the results section before any cell is read.
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
- **Stage 2 day list.** 5 to 10 days, written into the results section **before**
  any replay is built: the shock days are the largest Stage 1 episodes by SPY
  ATR move, the quiet days are matched by date in other months. **2026-11-05 is
  excluded** from the list.

## Stages

**Stage 1 — daily screen.**
- **Data.** `scripts/data/fetch_backtest_data.py` does not carry VIX today, so
  Stage 1 begins by adding daily `^VIX` (the same Yahoo source the live tape
  uses) to the cache, and records the source and fetch date in the results.
- **Two series.** A *close* series (SPY close vs prior close, VIX daily change)
  and an *upper-bound* series (SPY daily low vs prior close, VIX daily high vs
  prior close). The live rule can fire on any of 26 intraday readings, so a day
  that breaks the threshold and recovers fires live but not on the close; the
  close series is therefore a **lower bound** on the live rate and the
  upper-bound series is the one the budget is judged on. Neither can show the
  two-consecutive-reading rule.
- **Report per cell.** Fire days, distinct episodes, episodes per year (each
  year, not only pooled).
- **Forward long-book results (1, 3, 5 sessions)** are **descriptive only**: they
  decide no cell and no gate. Report N per episode as well as per trade (trades
  inside one episode are not independent), Total R beside ExpR, and
  `week_cluster_bootstrap` intervals (`swingbot/core/backtesting/instrument/stats.py`).
  A shock can be followed by a bounce, so no pass/fail direction is claimed.

**Stage 2 — intraday confirmation.** For the cells that pass Stage 1, build one
fixture per frozen day with `scripts/data/build_shock_replay_fixture.py`
(parameterised by session date). The builder interpolates VIX from a single
tape reading, so each day's VIX provenance is recorded. Where no real intraday
VIX exists, that day confirms only the SPY half of the rule, and the results
say so; an interpolated VIX never counts as confirming the VIX half. Only
Alpaca fixtures count; a synthetic one never confirms anything. Report the
first `SHOCK` time and the per-step table for each day.

**Stage 3 — replay and release.** One cell is frozen from Stages 1 and 2 alone.
2026-11-05 is then run **once** as pass/fail: the first `SHOCK` must be at or
before 15:00 UTC, which is the earliest the settle and two-reading rules allow.
If it is later, that is a measured answer: report the table, commit nothing
that weakens the replay test, and decide with the partner. It is never a reason
to move the grid, the rule or the cell. On a pass, the V209-12b replay test is
committed unchanged.

## Acceptance

- Stage 1 and 2 results are in the spec's results section before any default
  is set.
- With `index_atr_k = 0.0`, or mode `off` / `shadow`, every long and short plan
  is byte-identical to before (the V209-8b pins extend to the new path), and
  the detector's other paths and readings are unchanged.
- Missing SPY or ATR, a stale or proxy VIX: the path is false and the other
  paths behave exactly as before.
- Production check before the release (V209-13): a non-proxy `^VIX` tape row
  exists during market hours (the tape maps `^VIX=VIXY` as a proxy fallback; if
  production only has the proxy, the path can never fire and the spec says so).
  The shadow rows log how often VIX is missing or stale.
- Every new function stays under cyclomatic complexity 15; unit tests cover
  boundary values at each threshold, partial-data cases, the `0.0` off value,
  and the interaction with the settle and two-reading rules.

## Non-goals

- No change to the depth, fast, exit, recovery or carry rules.
- No new label, state machine, stored field or table.
- No notices, badge, trade blocking or short switching (v210 and later). The
  label is information; this spec does not decide what an alert-time trader or
  v210 does with it. It first fires at about 10:00 ET, after the open, so it
  cannot protect resting orders placed before the open.
- No threshold chosen from a single day.
- The concentrated-sector path and the sector assignment of the 22 unsectored
  names are separate ideas, left for a follow-on if the index path is not
  enough.

## Risks

- **The budget is a floor on false positives.** Even the upper-bound series
  cannot show a 10:00 ET fire on a day that recovers by noon, or the
  two-reading rule. The real intraday rate comes from v209's shadow rows once
  live. None exist yet.
- **VIX as a percent change.** +20 % is about 2.4 points at a VIX of 12 and
  about 6 at 30. No minimum VIX level is in the grid (YAGNI); if the shadow
  rows show low-level noise, a floor is a follow-on.
- **VIX source.** The live path reads Yahoo `^VIX` with a 600 s age gate. A stale
  tape silences the path, which is safe but is exactly when a real shock needs
  it; the shadow rows count how often.
- **Gap days.** A gap fires against the prior close at the first settled reading;
  the two-reading rule is the only guard.

## Order of work

**Branch.** `shock.py` exists only on the v209 branch, so v222's implementation
stacks on `2026-11-05-v209-market-shock-detector` (resume that worktree; do not
branch from `main`). Stages 1 and 2 are read-only analysis and need no code
branch. The `Version:` line above is `main`'s and does not include v209's bump.
v209's release (V209-13) waits on the partner's decision: the V209-12b replay
test stays uncommitted until Stage 3 closes, so v209 does not meet its own
acceptance gate until then. Order: Stage 1, Stage 2, implementation, Stage 3.

## Panel review

staff-engineer (opus), 8 advisories, no blockers:
- staff-engineer: "off" via unset would crash `thresholds_from_config` silently -- applied (0.0 sentinel, Config).
- staff-engineer: `spy_atr14` redundant with `spy_atr_move` -- applied (field dropped).
- staff-engineer: rows without the new field raise in `_from_row` -- applied (no new field, so moot).
- staff-engineer: VIX-source risk measured on shadow rows that do not exist -- applied (Risks, Acceptance production check for a non-proxy ^VIX row).
- staff-engineer: which branch v222 builds on and the stale Version line -- applied (Order of work).
- staff-engineer: key naming and `THRESHOLD_ATTRS` row -- applied (`SHOCK_INDEX_*`, Config).
- staff-engineer: fixture VIX provenance for Stage 2 days -- applied (Stage 2).
- staff-engineer: daily VIX history source unnamed -- applied (Stage 1 Data).

quant-researcher (opus), 3 BLOCKING, 5 advisory:
- quant-researcher BLOCKING: grid values and winner rule not frozen -- applied (Frozen section: grid, winner rule).
- quant-researcher BLOCKING: 2026-11-05 could act as a tuning input -- applied (cell frozen before one pass/fail run; 11-05 excluded from Stage 2).
- quant-researcher BLOCKING: episode gap length undefined -- applied (5 sessions, every calendar year).
- quant-researcher: daily proxy biased low, report an upper bound -- applied (two series, budget on the upper bound).
- quant-researcher: forward-return population, role, N, bootstrap -- applied (descriptive only, N per episode, `week_cluster_bootstrap`).
- quant-researcher: Stage 2 day list and survival criterion -- applied (Frozen section).
- quant-researcher: window not fixed -- applied (Frozen section, per-year reporting).
- quant-researcher: `_from_row` / `spy_atr14` -- applied (see staff-engineer).

veteran-trader (sonnet), 7 advisories, no blockers:
- veteran-trader: fast-path row described wrongly -- applied (table row: passes one reading, fails persistence; verified against `_from_normal`).
- veteran-trader: interpolated VIX uses the 15:20 reading, so the 15:00 gate is partly a tuning target -- applied (provenance paragraph, Stage 2, Stage 3 run-once).
- veteran-trader: daily budget biased low, a floor only -- applied (Risks, Stage 1 two series).
- veteran-trader: timeline ambiguity -- applied (UTC/ET and per-row times).
- veteran-trader: `spy_atr14` redundant -- applied.
- veteran-trader: VIX proxy tape, percent scale, minimum level -- applied for the proxy and scale (Acceptance, Risks); a minimum VIX level in the grid -- rejected: YAGNI, a follow-on if shadow rows show noise.
- veteran-trader: how the label is used by an alert-time trader -- applied (Non-goals; forward returns descriptive only).
