# v222 — Market-shock detector: index + VIX entry path

**Version:** ui 1.40.3 · bot 2.17.3
**Bump:** bot patch (a third entry condition inside the shadow-only v209 detector; no new surface)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, quant-researcher, veteran-trader

## Why

v209 (`swingbot/core/market/shock.py`) labels the market `NORMAL` / `SHOCK` /
`RECOVERY` from breadth and sector depth. Its acceptance test is a replay of
**2026-11-05**: the first `SHOCK` must come at or before 15:00 UTC. V209-12
built that fixture from Alpaca (`tests/fixtures/shock_replay_2026_11_05.json`,
87 tickers, 26 steps, committed `eafc6eb8`), and V209-12b measured the result:
**the detector stayed `NORMAL` at all 26 steps (14:45 to 21:00 UTC).** The
replay test is written but uncommitted (3 of 5 tests fail with
`StopIteration`).

The fixture is real, not broken. At 15:00 UTC:

| Measure | Value | Rule | Result |
|---|---|---|---|
| Breadth (equities down more than 1 ATR) | 0.424 | enter at 0.40 | passes |
| Sectors down (median name down more than 1 ATR) | 1 of 8 | needs 5 (`sectors_frac` 0.6) | **fails** |
| Breadth speed | +0.129 | fast path needs the `speed_enter` jump with `breadth_fast` | fails |
| SPY | −1.65 % (−1.4 ATR) | not used by any entry path | n/a |
| QQQ | −3.6 % | not used | n/a |
| VIX (interpolated from the 15:20 tape: 21.13, +27.21 %) | +21 % to +27 % | not used by any entry path | n/a |
| Semiconductors (14 in the fixture) | all down 5 % to 14 % (SNDK −13.6, AMD −12.6, MU −10.6, NVDA −5.0) | n/a | n/a |

By 21:00 UTC SPY was −4.4 % and QQQ −6.4 %. The day was a semiconductor/AI-led
crash that dragged the index. Only Information Technology (27 of 30 names
down) cleared the sector rule; Consumer Discretionary, Financials,
Industrials and Health Care were mostly down but not a full ATR at the
median; 22 names with no sector (IREN, NBIS, RGTI, MSTR, ARM, SHOP and
similar) count toward breadth but never toward the sector rule.

So the breadth-plus-depth rule needs a broad sector selloff, and a
concentrated, index-dragging crash does not look like one. The index and the
VIX were already showing it. The partner's brief for v209 was "when the market
turns sharply, whether correction or news, across all sectors"; this spec
closes the gap for the crash that is led by one heavy sector.

## What changes

`shock.entry_condition` gains a third path next to `_depth_path` and
`_fast_path`:

- `_index_path(reading, th)`: true when `spy_atr_down >= th.index_atr_k` **and**
  `vix_chg_pct >= th.index_vix_chg`, both read from the same `ShockReading`.
  `spy_atr_down = (spy_prev_close - spy_last) / spy_atr14`. A missing SPY
  quote, a missing ATR, or a VIX reading older than `vix_max_age_s` makes the
  path false (it never fires on partial data).
- `entry_condition` returns `_depth_path or _fast_path or _index_path`.

Unchanged: the open-settle rule, the two-consecutive-reading rule, the `SHOCK`
label (so the stored rows and v210's notices and badge need no change), and
the exit, recovery and carry rules. Everything stays `shadow`: the label
never blocks a trade.

`ShockReading` carries `spy_last`, `spy_prev_close` and `vix_chg_pct`;
the SPY ATR is added to `ShockReading` as `spy_atr14` (a new field, see
Risks for the migration note). `ShockThresholds` gets `index_atr_k` and
`index_vix_chg`; the Market Shock config section gets matching keys
(`MARKET_SHOCK_INDEX_ATR_K`, `MARKET_SHOCK_INDEX_VIX_CHG`). The defaults
are **set only by Stage 1 below**, never from 2026-11-05.

## Stages

**Stage 1 — daily screen (before any threshold).** Over the longest daily SPY
and VIX history the cache holds (`scripts/data/fetch_backtest_data.py`
populates it), grid `index_atr_k` and `index_vix_chg`. For each cell report:
days that fire, distinct episodes (fires separated by a quiet gap), fires per
year, and what the long book would have done on the next 1, 3 and 5 sessions,
each with pooled `ExpR`, win rate and `N`, using `pooled-numbers` rules.
The result is a **daily proxy** for an intraday rule (a daily close cannot
show a 15:00 UTC reading) and the spec says so wherever it quotes it. It
records a fires-per-year **budget** before looking at any cell. The pre-
registered budget is **at most 6 firing episodes per year**.

**Stage 2 — intraday confirmation.** For the cells that survive Stage 1,
build 5 to 10 intraday replay fixtures with
`scripts/data/build_shock_replay_fixture.py` (parameterise the session
date), covering known shock days and quiet days. Only Alpaca fixtures count;
a synthetic one never confirms anything. Report for each day the first
`SHOCK` time and the per-step table.

**Stage 3 — replay and release.** 2026-11-05 is a replay check only, never a
tuning input: with the chosen cell the first `SHOCK` must be at or before
15:00 UTC, which is the earliest the settle and two-reading rules allow. If
no cell that passes Stages 1 and 2 also fires by 15:00 on 2026-11-05, that is
a measured answer: report the table, commit nothing that weakens the test,
and decide with the partner. Then the V209-12b replay test is committed
unchanged.

## Acceptance

- Stage 1 and 2 results are written to the spec's results section before any
  default is set.
- With the path off (`index_atr_k` unset) or the mode `off` / `shadow`,
  every long and short plan is byte-identical to before (the V209-8b pins
  extend to the new path).
- Missing SPY, missing ATR, stale or missing VIX: the path is false and the
  detector's other paths behave exactly as before.
- Every new function stays under cyclomatic complexity 15; unit tests cover
  boundary values at each threshold, partial-data cases, and the
  interaction with the settle and two-reading rules.

## Non-goals

- No change to the depth, fast, exit, recovery or carry rules.
- No new label, state machine or stored table.
- No notices, badge, trade blocking or short switching (v210 and later).
- No threshold chosen from a single day.
- The concentrated-sector path and sector reassignment of the 22 unsectored
  names are separate ideas, left for a follow-on if Stage 1 or 2 shows the
  index path is not enough.

## Risks

- **Stage 1 is a proxy.** Daily bars and a daily VIX change differ from a
  15:00 UTC intraday reading; Stage 2 exists for exactly that.
- **VIX source.** The live path reads the shared tape; a stale tape makes the
  path silent (safe) but could hide a real shock. v209's shadow rows show how
  often.
- **New `ShockReading` field.** `spy_atr14` extends the stored reading JSON;
  per `schema-evolution.md` a field added to a JSON document needs no table
  change, and rows without it read as `None` (path false).
- **False positives.** A one-day index drop with a VIX spike that recovers
  would label `SHOCK` for a session; the two-reading rule and the episode
  budget bound this, and `shadow` costs nothing.

## Order of work

v209's release (V209-13) waits on the partner's decision: the V209-12b replay
test stays uncommitted until Stage 3 here closes, so v209 does not meet its
own acceptance gate until then. v222 runs Stage 1 (read-only backtest data),
Stage 2 (Alpaca fetches), then implements the path, then Stage 3.
