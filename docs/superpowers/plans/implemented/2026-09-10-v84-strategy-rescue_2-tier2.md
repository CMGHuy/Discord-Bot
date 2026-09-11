# Strategy Rescue v2 — Part 2: Tier 2 (Tasks R15–R30)

> Read `2026-09-10-v84-strategy-rescue_0-index.md` first. Its **Global
> Constraints** and **Shared conventions** apply to every task here and are not
> repeated. Read spec
> `docs/superpowers/specs/2026-09-10-v84-strategy-rescue-v2-design.md` §4.4–4.6
> for the pre-registered rules these tasks execute.

**Covers:** RSI Divergence (§4.4), MA Ribbon (§4.5), Support/Resistance (§4.6).

## Task numbering deviation from the index

The index's map allots R15–R20 / R21–R25 / R26–R30 by strategy. Executing it
that way is not possible: **Stage 2 needs a fold-arms emitter that does not
exist** (see below), and that harness is shared by all three strategies, so it
takes R15 on its own. The real allocation is:

| Tasks | Contents |
|---|---|
| R15 | Shared fold-arms harness (blocks every Stage 2 task in this part) |
| R16–R19 | RSI Divergence |
| R20–R23 | MA Ribbon |
| R24–R27 | Support/Resistance |
| R28–R30 | Tier 2 results docs, registry check, wrap |

**Update the index's task map to match before execution.**

## The fold-stage tooling contract (verified 2026-09-10)

This is the single most important finding in this part, and it changes what the
tasks have to build.

1. **`validate_component.py --stage walkforward` does not run backtests.** It
   consumes an arms JSON that "the component's own measurement script wrote":
   `{"folds": [{"test_year": "2021", "baseline": [ArmTrade...], "component":
   [ArmTrade...]}, ...]}`, exactly 3 folds with distinct `test_year`
   (`validate_component.py:110-128`). It scores them with
   `delta_standardised_win_rate` and `gate_win_rate`, nothing else.
2. **`wf_run.py` cannot produce that input.** `run_folds`
   (`backtest_wf.py:167-181`) emits pooled dicts with `delta_expectancy_r`
   only — no `delta_win_rate_pp`, no per-trade rows. Feeding a `run_folds`
   result to `gate_win_rate` returns FAIL for every fold, because
   `f.get("delta_win_rate_pp")` is `None` (`backtest_wf.py:217-219`). **A
   `wf_run.py` PASS is not a Stage 2 pass and must never be reported as one.**
3. **The component arm is expressible only through `swingbot.config`
   attributes.** `_apply_overrides` (`backtest_wf.py:51-56`) does
   `setattr(config, key, value)`; `wf_run.py --component-json` is a dict of
   config keys. Entry-filter tunables in `DEFAULT_PARAMS` are **invisible** to
   this mechanism.

4. **`run_backtest_daterange` and `run_backtest_range.py` disagree on
   `tp2_mode` defaults.** The function defaults `tp2_mode="none"`; the CLI's
   `--tp2` defaults to `"levels"`. Any instrument calling the function directly
   **must pass `tp2_mode="levels"` explicitly**, or the fold arms measure
   different economics than the TRAIN grid they are compared against. This is
   the same class of silent mismatch that corrupted round 2's Elliott Wave
   rescue grid, and it is unrecoverable after a VALIDATION look is spent.

**Consequence:** every mechanism in this part must be readable from `config` at
entry-evaluation time, and a purpose-built arms emitter must exist. Precedent
for a purpose-built instrument: `measure_rs_gate_effect.py`,
`measure_dcb_veto.py`. Task R15 builds the shared one.

The `config` read seam already has a precedent in this exact module:
`apply_regime_gate` (`entry_filters.py:117-120`) does a lazy
`from swingbot import config` / `getattr(config, "REGIME_GATES_ENABLED", False)`.
Every task here follows that pattern — **lazy import inside the function**, never
module-level, so tests can monkeypatch and `_apply_overrides` takes effect
without re-import.

## Params that must NOT be touched

These are closed pre-registrations that still live in `DEFAULT_PARAMS`, set to
`None`/`False`. Every task below adds a **new** key alongside them and leaves
them exactly as they are. A reviewer should check this explicitly.

- MA Ribbon: `min_width_pctile`, `require_expanding` (`entry_filters.py:364-365`)
- RSI Divergence: `min_volume_ratio`, `min_reclaim_strength`
  (`entry_filters.py:576-577`)

---

### Task R15: Shared fold-arms emitter

**Files:**
- Create: `scripts/backtest/measure_strategy_arm.py`
- Test: `tests/backtesting/test_measure_strategy_arm.py`

**Interfaces:**
- Consumes: `swingbot.core.backtesting.backtest.run_backtest_daterange(ticker, df, strategy, horizon_key, date_from, date_to, frictions=True, exit_model="v1", ...)`; `backtest_wf.ANCHORED_FOLDS`; `backtest_wf._apply_overrides`.
- Produces: `scripts/backtest/measure_strategy_arm.py` CLI writing
  `{"folds":[{"test_year": str, "baseline": [dict], "component": [dict]}]}`,
  where each dict has keys `ticker, strategy, horizon_key, entry_date, outcome,
  r_multiple, planned_rr` — the `ArmTrade` field set
  (`acceptance.py:28-47`). Consumed by R18/R22/R26.

- [ ] **Step 1: Pin the backtest entry point's real signature**

Do not guess whether `scale_out` is a keyword. Run:

```bash
python -c "import inspect; from swingbot.core.backtesting.backtest import run_backtest_daterange as f; print(inspect.signature(f))"
```

Expected: a signature containing `exit_model` and `scale_out`. **If `scale_out`
is absent, stop and report** — every measurement in this plan depends on it,
and inventing the kwarg would silently measure the wrong economics.

- [ ] **Step 2: Write the failing test**

```python
# tests/backtesting/test_measure_strategy_arm.py
import json

from scripts.backtest.measure_strategy_arm import build_fold_arms, trade_to_arm
from swingbot.core.backtesting.backtest import BacktestSummary, BacktestTrade


def _summary(ticker, outcome, r, entry=100.0, sl=95.0, tp=110.0):
    t = BacktestTrade(entry_date="2021-03-01", exit_date="2021-04-01",
                      direction="long", entry=entry, stop_loss=sl,
                      take_profit=tp, outcome=outcome, exit_price=tp,
                      return_pct=1.0, r_multiple=r, holding_days=30)
    return BacktestSummary(ticker=ticker, strategy="RSI Divergence",
                           horizon_key="4w", total_signals=1, evaluated=1,
                           wins=1, losses=0, timeouts=0, scratches=0,
                           win_rate=100.0, avg_return_pct=1.0,
                           avg_r_multiple=r, expectancy_r=r,
                           max_drawdown_pct=-1.0, avg_holding_days=30.0,
                           trades=[t])


def test_trade_to_arm_carries_arm_fields_and_derives_planned_rr():
    s = _summary("AAPL", "win", 2.0)
    arm = trade_to_arm(s, s.trades[0])
    assert arm["ticker"] == "AAPL"
    assert arm["strategy"] == "RSI Divergence"
    assert arm["horizon_key"] == "4w"
    assert arm["entry_date"] == "2021-03-01"
    assert arm["outcome"] == "win"
    assert arm["r_multiple"] == 2.0
    # planned_rr = (tp - entry) / (entry - stop) = 10 / 5
    assert arm["planned_rr"] == 2.0


def test_short_planned_rr_is_direction_correct():
    s = _summary("AAPL", "loss", -1.0, entry=100.0, sl=105.0, tp=90.0)
    s.trades[0].direction = "short"
    arm = trade_to_arm(s, s.trades[0])
    assert arm["planned_rr"] == 2.0


def test_build_fold_arms_shape_is_validate_component_ready(monkeypatch):
    calls = []

    def fake_run(ticker, df, strategy, horizon_key, date_from, date_to, **kw):
        calls.append(date_from)
        return _summary(ticker, "win", 1.5)

    arms = build_fold_arms(
        strategy="RSI Divergence", overrides={"X": 1},
        symbols=["AAPL"], horizons=["4w"],
        frame_for=lambda s: object(), run_fn=fake_run)

    assert [f["test_year"] for f in arms["folds"]] == ["2021", "2022", "2023"]
    for fold in arms["folds"]:
        assert fold["baseline"] and fold["component"]
        assert set(fold["baseline"][0]) == {
            "ticker", "strategy", "horizon_key", "entry_date",
            "outcome", "r_multiple", "planned_rr"}
    # baseline + component leg per fold
    assert len(calls) == 6
```

- [ ] **Step 3: Run it to confirm it fails**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_measure_strategy_arm.py
```

Expected: FAIL — `ModuleNotFoundError: scripts.backtest.measure_strategy_arm`.

- [ ] **Step 4: Implement the emitter**

```python
#!/usr/bin/env python3
"""Emit fold arms for ONE strategy under a config override, in the shape
validate_component.py --stage walkforward consumes.

Why this exists: wf_run.py's run_folds emits pooled expectancy deltas, not
per-trade rows, so gate_win_rate sees delta_win_rate_pp=None and fails every
fold. Stage 2 needs per-trade arms. This is the per-strategy instrument for
that, in the same spirit as measure_rs_gate_effect.py.

Run:
  python scripts/backtest/measure_strategy_arm.py \
      --strategy "RSI Divergence" \
      --component-json '{"RSI_DIV_MIN_CONSECUTIVE_TURN": 3}' \
      --out data/rsidiv_folds.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.backtest import run_backtest_daterange  # noqa: E402
from swingbot.core.backtesting.backtest_wf import (  # noqa: E402
    ANCHORED_FOLDS, _apply_overrides, _frame_for, _symbols_for_folds,
)
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.marketdata.universe import liquidity_ok  # noqa: E402

DECIDED_OR_NOT = ("win", "loss", "scratch", "timeout")


def trade_to_arm(summary, trade) -> dict:
    """BacktestTrade -> the ArmTrade field set (acceptance.py:28-47).

    planned_rr is derived, not stored: BacktestTrade carries entry/stop/target
    but no ratio. Direction-adjusted so a short's reward and risk are both
    positive distances.
    """
    entry, stop, target = trade.entry, trade.stop_loss, trade.take_profit
    if str(trade.direction).lower().startswith("s"):
        reward, risk = entry - target, stop - entry
    else:
        reward, risk = target - entry, entry - stop
    planned_rr = (reward / risk) if risk else None
    return {
        "ticker": summary.ticker,
        "strategy": summary.strategy,
        "horizon_key": summary.horizon_key,
        "entry_date": trade.entry_date,
        "outcome": trade.outcome,
        "r_multiple": trade.r_multiple,
        "planned_rr": planned_rr,
    }


def _leg(strategy, symbols, horizons, start, end, overrides, frame_for, run_fn):
    """One arm of one fold. Config overrides are applied around the whole leg
    and restored afterwards, so a raising run never leaks config state."""
    old = _apply_overrides(overrides or {})
    try:
        rows = []
        for sym in symbols:
            df = frame_for(sym)
            if df is None:
                continue
            for hz in horizons:
                # tp2_mode MUST be passed explicitly: run_backtest_daterange
                # defaults to "none" while run_backtest_range.py's --tp2
                # defaults to "levels". Leaving it implicit would measure the
                # folds under different economics than the TRAIN grid -- the
                # same silent mismatch that corrupted round 2's Elliott Wave
                # grid (tune_strategy ran v1/no-scale-out while validation ran
                # v2/scale-out).
                s = run_fn(sym, df, strategy, hz, start, end,
                           exit_model="v2", scale_out=True, tp2_mode="levels")
                for t in s.trades:
                    if t.outcome in DECIDED_OR_NOT:
                        rows.append(trade_to_arm(s, t))
        return rows
    finally:
        _apply_overrides(old)


def build_fold_arms(strategy, overrides, symbols, horizons,
                    frame_for=None, run_fn=None) -> dict:
    frame_for = frame_for or _frame_for
    run_fn = run_fn or run_backtest_daterange
    folds = []
    for _tr_start, _tr_end, test_start, test_end in ANCHORED_FOLDS:
        folds.append({
            "test_year": test_start[:4],
            "baseline": _leg(strategy, symbols, horizons, test_start, test_end,
                             {}, frame_for, run_fn),
            "component": _leg(strategy, symbols, horizons, test_start, test_end,
                              overrides, frame_for, run_fn),
        })
        print(f"fold {test_start[:4]}: baseline={len(folds[-1]['baseline'])} "
              f"component={len(folds[-1]['component'])} trades", flush=True)
    return {"folds": folds}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--component-json", required=True,
                    help='config overrides for the component leg, e.g. '
                         '\'{"MA_RIBBON_CONFIRM_BARS": 2}\'')
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    overrides = json.loads(args.component_json)
    if not overrides:
        print("REFUSING: --component-json is empty; both arms would be "
              "identical and every fold delta would be 0.", file=sys.stderr)
        return 1

    symbols = [s for s in _symbols_for_folds()
               if (_frame_for(s) is not None and liquidity_ok(_frame_for(s)))]
    arms = build_fold_arms(args.strategy, overrides, symbols, list(HORIZONS))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(arms, indent=1), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Verify the helpers it imports actually exist**

```bash
python -c "from swingbot.core.backtesting.backtest_wf import _frame_for, _symbols_for_folds, _apply_overrides, ANCHORED_FOLDS; print('ok', len(ANCHORED_FOLDS))"
```

Expected: `ok 3`. If `_frame_for` is not importable, find its real name in
`backtest_wf.py` and fix the import — do not stub it.

- [ ] **Step 6: Run the test to verify it passes**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_measure_strategy_arm.py
```

Expected: PASS, 3 tests.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/measure_strategy_arm.py tests/backtesting/test_measure_strategy_arm.py
git commit -m "feat(backtest): per-strategy fold-arms emitter for Stage 2

wf_run.py's run_folds emits pooled expectancy deltas only, so gate_win_rate
sees delta_win_rate_pp=None and fails every fold. Stage 2 needs per-trade
arms; this emits them for one strategy under a config override."
```

---

### Task R16: RSI Divergence — `min_consecutive_rsi_turn`

Spec §4.4. Baseline to beat: **N=1534, WR 48.0%, ExpR +0.257** — 2.0pp short,
and the largest population in the campaign.

**Files:**
- Modify: `swingbot/config.py` (new Field + searchable registration)
- Modify: `swingbot/core/market/entry_filters.py:573-627`
- Test: `tests/market/test_rescue_rsi_divergence.py` (create)

**Interfaces:**
- Consumes: `entry_filters.rsi_divergence_entries(df, horizon_key, params=None)`.
- Produces: config attr `RSI_DIV_MIN_CONSECUTIVE_TURN` (int, default `1` = off)
  and param key `min_consecutive_rsi_turn`, read by R17/R18/R19.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_rescue_rsi_divergence.py
import numpy as np

from swingbot.core.market.entry_filters import rsi_divergence_entries
from tests.conftest import make_ohlcv, make_trend_df

GATED = {"min_consecutive_rsi_turn": 3}


def _one_bar_turn_frame(n=320):
    """Uptrend with a saw-tooth wobble: RSI ticks up for a single bar at a
    time before rolling over. Exactly the noisy one-uptick reclaim the
    persistence gate exists to reject."""
    t = np.arange(n)
    base = 100 * (1 + 0.06 / 100) ** t
    saw = np.where(t % 2 == 0, 1.6, -1.6)
    saw[:60] = 0.0
    return make_ohlcv(base + saw)


def test_gate_off_is_byte_identical():
    df = make_trend_df(300, +0.2)
    a_bull, a_bear = rsi_divergence_entries(df, "4w")
    b_bull, b_bear = rsi_divergence_entries(
        df, "4w", params={"min_consecutive_rsi_turn": 1})
    assert (a_bull == b_bull).all()
    assert (a_bear == b_bear).all()


def test_persistence_gate_never_adds_entries():
    df = make_trend_df(400, +0.3)
    on_bull, on_bear = rsi_divergence_entries(df, "4w", params=GATED)
    off_bull, off_bear = rsi_divergence_entries(df, "4w")
    assert on_bull.sum() <= off_bull.sum()
    assert on_bear.sum() <= off_bear.sum()
    assert (on_bull & ~off_bull).sum() == 0


def test_single_bar_turns_are_suppressed():
    df = _one_bar_turn_frame()
    on_bull, _ = rsi_divergence_entries(df, "4w", params=GATED)
    off_bull, _ = rsi_divergence_entries(df, "4w")
    assert off_bull.sum() >= on_bull.sum()
    assert on_bull.sum() == 0


def test_no_lookahead():
    df = make_trend_df(300, +0.3)
    full, _ = rsi_divergence_entries(df, "4w", params=GATED)
    trunc, _ = rsi_divergence_entries(df.iloc[:-1], "4w", params=GATED)
    assert (full.iloc[:-1] == trunc).all()


def test_closed_rescue_params_still_default_off():
    from swingbot.core.market.entry_filters import DEFAULT_PARAMS
    p = DEFAULT_PARAMS["RSI Divergence"]
    assert p["min_volume_ratio"] is None
    assert p["min_reclaim_strength"] is None
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python scripts/dev/testrun.py file tests/market/test_rescue_rsi_divergence.py
```

Expected: FAIL — `test_single_bar_turns_are_suppressed` fails because
`min_consecutive_rsi_turn` is ignored today.

- [ ] **Step 3: Add the default param**

In `entry_filters.py`, extend the existing dict (leave the two closed rescue
params exactly as they are):

```python
DEFAULT_PARAMS["RSI Divergence"] = {"rsi_reclaim": 45,
                                    # rescue gate (Task 98) -- off until the
                                    # train grid (Task 99) adopts winners
                                    "min_volume_ratio": None,
                                    "min_reclaim_strength": None,
                                    # v84 rescue: RSI must move in the trade
                                    # direction for N consecutive bars, not
                                    # the single uptick below. 1 = off.
                                    "min_consecutive_rsi_turn": 1}
```

- [ ] **Step 4: Replace the single-bar turn check**

Replace lines 596-597 (`turn_bull` / `turn_bear`) with:

```python
    from swingbot import config
    min_turn = int(params.get("min_consecutive_rsi_turn") if params and
                   "min_consecutive_rsi_turn" in params
                   else getattr(config, "RSI_DIV_MIN_CONSECUTIVE_TURN", None)
                   or p["min_consecutive_rsi_turn"])
    min_turn = max(1, min_turn)
    rising = rsi14 > rsi14.shift(1)
    falling = rsi14 < rsi14.shift(1)
    if min_turn > 1:
        rising = (rising.rolling(min_turn).sum() == min_turn)
        falling = (falling.rolling(min_turn).sum() == min_turn)
    turn_bull = (rsi14 > reclaim) & rising.fillna(False)
    turn_bear = (rsi14 < (100 - reclaim)) & falling.fillna(False)
```

The explicit `params` check first is what keeps an explicit call argument
authoritative over a config override, so tests stay deterministic while
`_apply_overrides` still drives the fold legs.

- [ ] **Step 5: Add the config Field**

Add to `FIELDS` in `swingbot/config.py`, alongside the other tunables:

```python
    Field("RSI_DIV_MIN_CONSECUTIVE_TURN", "RSI_DIV_MIN_CONSECUTIVE_TURN",
          "Trade Filters & Risk", "RSI Divergence: consecutive RSI turn bars",
          type="int", default="1", min=1, max=6, step=1,
          help="How many consecutive bars RSI must move in the trade direction "
               "before a hidden-divergence reclaim counts as confirmed. 1 keeps "
               "the original single-uptick behaviour."),
```

Then register it as searchable. Read the `_SEARCH_CLASSES` block near
`config.py:917` and add the attribute name to the `searchable` bucket — do not
guess the literal structure, open it and match what is there.

- [ ] **Step 6: Verify the field is wired and searchable**

```bash
python -c "from swingbot import config; print(config.RSI_DIV_MIN_CONSECUTIVE_TURN); print('RSI_DIV_MIN_CONSECUTIVE_TURN' in config.searchable_attrs())"
```

Expected: `1` then `True`.

- [ ] **Step 7: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/market/test_rescue_rsi_divergence.py
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```

Expected: both PASS. The second guards against regressing the shared module.

- [ ] **Step 8: Commit**

```bash
git add swingbot/config.py swingbot/core/market/entry_filters.py tests/market/test_rescue_rsi_divergence.py
git commit -m "feat(rsi-divergence): consecutive-turn persistence gate (v84 R16)

Replaces the single-bar RSI uptick with an N-consecutive-bar requirement.
Defaults to 1 (byte-identical to the old behaviour). Closed rescue params
min_volume_ratio/min_reclaim_strength untouched."
```

---

### Task R17: RSI Divergence — TRAIN grid and plateau

**Pre-registered rule (spec §4.4, verbatim):** TRAIN grid
`min_consecutive_rsi_turn ∈ {2, 3, 4}`; a config qualifies at WR≥50, ExpR>0,
N≥30, excl≤50%, **and must show a plateau across adjacent values, not a lone
spike**. 0/3 qualifying ⇒ REJECTED-ON-TRAIN, permanently WEAK, no VALIDATION
spent.

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-rsidiv-train.md`

- [ ] **Step 1: Dispatch the grid to `backtest-runner`**

Three TRAIN runs plus the already-measured baseline. Give the subagent this
verbatim, one blocking call per cell:

```bash
for K in 2 3 4; do
  RSI_DIV_MIN_CONSECUTIVE_TURN=$K python scripts/backtest/run_backtest_range.py \
    --train --strategy "RSI Divergence" \
    --exit-model v2 --scale-out --pass-wr 50 \
    --json "$SCRATCH/rsidiv_train_k$K.json"
done
```

If the env-var route does not reach `config` (check
`swingbot/config.py`'s loader for whether env vars are read at import), fall
back to `--strategy` runs driven by a tiny wrapper that sets
`config.RSI_DIV_MIN_CONSECUTIVE_TURN` before calling `main()`. **Report which
route was used** — a grid that silently measured K=1 three times is the failure
mode to guard against, so each cell's output must show a different N.

- [ ] **Step 2: Confirm the cells actually differ**

Expected: three distinct `N` values, each ≤ the K=1 baseline N=1534. If any two
cells report identical N and win rate, the override did not take effect — stop
and fix the plumbing before recording anything.

- [ ] **Step 3: Run the plateau check with the sanctioned instrument**

```python
python - <<'PY'
from swingbot.core.backtesting.backtest_wf import plateau_report
# expectancies filled in from Step 1's three JSON outputs, in grid order
grid = [2, 3, 4]
expectancies = [None, None, None]   # <- replace with measured ExpR per cell
best = max(grid, key=lambda k: expectancies[grid.index(k)])
print(plateau_report("min_consecutive_rsi_turn", grid, expectancies, best))
PY
```

`PLATEAU_TOLERANCE_R = 0.03` (`backtest_wf.py:33`). `is_plateau: False` ⇒ the
adopted value is a spike ⇒ **rejected, no Stage 2, no VALIDATION**.

- [ ] **Step 4: Write the results doc**

Record every cell, pass or fail, with the pre-registered rule quoted at the top
and an honest observations section. If 0/3 qualify, the empty qualifying table
**is** the finished result — write it and stop the RSI Divergence line here.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-rsidiv-train.md
git commit -m "docs(v84): RSI Divergence TRAIN grid result"
```

---

### Task R18: RSI Divergence — Stage 2 walkforward

Only if R17 produced a qualifying, plateaued config. Uses R15's emitter.

- [ ] **Step 1: Emit fold arms for the adopted K**

```bash
python scripts/backtest/measure_strategy_arm.py \
  --strategy "RSI Divergence" \
  --component-json '{"RSI_DIV_MIN_CONSECUTIVE_TURN": <adopted K>}' \
  --out data/v84_rsidiv_folds.json
```

Dispatch to `backtest-runner` — this is 3 folds × 2 arms × full universe.

- [ ] **Step 2: Score it with the pre-registered gate**

```bash
python scripts/backtest/validate_component.py --stage walkforward \
  --arms data/v84_rsidiv_folds.json \
  --title "v84 RSI Divergence consecutive-turn gate" \
  --window "fold-test 2021/2022/2023" \
  --out-md docs/superpowers/results/2026-09-10-v84-rsidiv-walkforward.md
```

Expected: per-fold `dWR` lines then `PASS` or `FAIL`. Exit code 0 = PASS.
`gate_win_rate`: ≥2 of 3 folds improving, no fold worse than −1.0pp, per-fold
N≥30 (`backtest_wf.py:206-226`).

- [ ] **Step 3: Commit the verdict either way**

```bash
git add docs/superpowers/results/2026-09-10-v84-rsidiv-walkforward.md data/v84_rsidiv_folds.json
git commit -m "docs(v84): RSI Divergence Stage 2 walkforward verdict"
```

A FAIL ends the RSI Divergence line — record it, do not retune.

---

### Task R19: RSI Divergence — VALIDATION (ONE shot)

**Only** if R17 and R18 both passed. This spends the strategy's single shot.

- [ ] **Step 1: Confirm the free stages passed**

Re-read both results docs. If either says FAIL or REFUSED, **stop** — this task
does not run.

- [ ] **Step 2: Set the adopted default**

Change `DEFAULT_PARAMS["RSI Divergence"]["min_consecutive_rsi_turn"]` from `1`
to the adopted K and update the config Field's `default` to match, so live and
backtest agree.

- [ ] **Step 3: Spend the shot**

```bash
python scripts/backtest/run_backtest_range.py --validation \
  --strategy "RSI Divergence" --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json \
  --run-date 2026-09-10 \
  --json data/v84_rsidiv_validation.json
```

Record the result **as-is**, whatever it says. A WEAK verdict here is final.

- [ ] **Step 4: Commit**

```bash
git add swingbot/config.py swingbot/core/market/entry_filters.py swingbot/core/backtesting/validation_registry.json data/v84_rsidiv_validation.json
git commit -m "feat(rsi-divergence): adopt consecutive-turn gate, VALIDATION shot spent"
```

---

### Task R20: MA Ribbon — `confirm_bars` alignment persistence

Spec §4.5. Baseline: **N=233, WR 48.1%, ExpR +0.270** — 1.9pp short.

**Files:**
- Modify: `swingbot/config.py`
- Modify: `swingbot/core/market/entry_filters.py:362-410`
- Test: `tests/market/test_rescue_ribbon_confirm.py` (create — do **not** edit
  `tests/market/test_rescue_ribbon.py`, which guards the closed width grid)

**Interfaces:**
- Produces: config attr `MA_RIBBON_CONFIRM_BARS` (int, default `1` = off), param
  key `confirm_bars`.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_rescue_ribbon_confirm.py
from swingbot.core.market.entry_filters import ma_ribbon_entries
from tests.conftest import make_trend_df

GATED = {"confirm_bars": 3}


def test_gate_off_is_byte_identical():
    df = make_trend_df(300, +0.2)
    a, _ = ma_ribbon_entries(df, "4w")
    b, _ = ma_ribbon_entries(df, "4w", params={"confirm_bars": 1})
    assert (a == b).all()


def test_confirmation_never_adds_entries():
    df = make_trend_df(400, +0.4)
    on, _ = ma_ribbon_entries(df, "4w", params=GATED)
    off, _ = ma_ribbon_entries(df, "4w")
    assert on.sum() <= off.sum()
    assert (on & ~off).sum() == 0


def test_every_gated_entry_had_k_bars_of_alignment():
    """The mechanism's actual claim: an entry only fires where fast/mid sat
    above slow for K consecutive bars ending at the crossover."""
    import numpy as np
    from swingbot.core.market.indicators import ema
    df = make_trend_df(400, +0.4)
    on, _ = ma_ribbon_entries(df, "4w", params=GATED)
    close = df["Close"]
    fast, mid = ema(close, 10), ema(close, 20)
    slow = close.rolling(50).mean()
    above = (fast > slow) & (mid > slow)
    for d in on[on].index:
        i = on.index.get_loc(d)
        assert above.iloc[i - 2:i + 1].all()


def test_closed_width_params_still_default_off():
    from swingbot.core.market.entry_filters import DEFAULT_PARAMS
    p = DEFAULT_PARAMS["MA Ribbon"]
    assert p["min_width_pctile"] is None
    assert p["require_expanding"] is False


def test_no_lookahead():
    df = make_trend_df(300, +0.3)
    full, _ = ma_ribbon_entries(df, "4w", params=GATED)
    trunc, _ = ma_ribbon_entries(df.iloc[:-1], "4w", params=GATED)
    assert (full.iloc[:-1] == trunc).all()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python scripts/dev/testrun.py file tests/market/test_rescue_ribbon_confirm.py
```

Expected: FAIL on `test_every_gated_entry_had_k_bars_of_alignment`.

- [ ] **Step 3: Add the default param**

```python
DEFAULT_PARAMS["MA Ribbon"] = {
    "ext_pct": 8.0,
    "min_width_pctile": None,
    "require_expanding": False,
    # v84 rescue: fast/mid must sit on the correct side of slow for N
    # consecutive bars ending at the crossover. 1 = off (same-bar firing).
    "confirm_bars": 1,
}
```

- [ ] **Step 4: Implement the gate**

Insert immediately after the `bullish` / `bearish` assignment
(`entry_filters.py:388-393`), before the closed width-gate block:

```python
    # --- v84 rescue: temporal persistence of the alignment ---
    # Distinct axis from the closed width grid below: width measures how far
    # apart the ribbon is right now; this measures how long the ordering has
    # held. Targets whipsaw false-starts, not narrow ribbons.
    from swingbot import config
    confirm = int(params.get("confirm_bars") if params and "confirm_bars" in params
                  else getattr(config, "MA_RIBBON_CONFIRM_BARS", None)
                  or p["confirm_bars"])
    if confirm > 1:
        above_slow = (fast > slow_sma) & (mid > slow_sma)
        below_slow = (fast < slow_sma) & (mid < slow_sma)
        held_up = (above_slow.rolling(confirm).sum() == confirm).fillna(False)
        held_dn = (below_slow.rolling(confirm).sum() == confirm).fillna(False)
        bullish &= held_up
        bearish &= held_dn
```

- [ ] **Step 5: Add the config Field**

```python
    Field("MA_RIBBON_CONFIRM_BARS", "MA_RIBBON_CONFIRM_BARS",
          "Trade Filters & Risk", "MA Ribbon: alignment confirmation bars",
          type="int", default="1", min=1, max=6, step=1,
          help="How many consecutive bars the fast and mid EMAs must hold "
               "their side of the slow SMA, ending at the crossover bar, "
               "before an entry fires. 1 keeps same-bar firing."),
```

Register it in the `searchable` bucket of `_SEARCH_CLASSES` as in R16 Step 5.

- [ ] **Step 6: Verify and run tests**

```bash
python -c "from swingbot import config; print(config.MA_RIBBON_CONFIRM_BARS, 'MA_RIBBON_CONFIRM_BARS' in config.searchable_attrs())"
python scripts/dev/testrun.py file tests/market/test_rescue_ribbon_confirm.py
python scripts/dev/testrun.py file tests/market/test_rescue_ribbon.py
```

Expected: `1 True`, then both test files PASS. The second proves the closed
width grid still behaves exactly as before.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py swingbot/core/market/entry_filters.py tests/market/test_rescue_ribbon_confirm.py
git commit -m "feat(ma-ribbon): alignment-persistence confirmation gate (v84 R20)

Requires the fast/mid-vs-slow ordering to hold N consecutive bars ending at
the crossover. Defaults to 1 (same-bar, byte-identical). Distinct axis from
the closed min_width_pctile/require_expanding grid, which stays off."
```

---

### Task R21: MA Ribbon — TRAIN grid and plateau

**Pre-registered rule (spec §4.5, verbatim):** TRAIN sweep
`confirm_bars ∈ {2, 3}`; qualify at WR≥50, ExpR>0, N≥30, excl≤50%, plateau
required. 0/2 qualifying ⇒ closes this axis too, no VALIDATION spent.

- [ ] **Step 1: Run the two cells** (dispatch to `backtest-runner`)

```bash
for K in 2 3; do
  MA_RIBBON_CONFIRM_BARS=$K python scripts/backtest/run_backtest_range.py \
    --train --strategy "MA Ribbon" \
    --exit-model v2 --scale-out --pass-wr 50 \
    --json "$SCRATCH/maribbon_train_k$K.json"
done
```

Same plumbing caveat as R17 Step 1 — confirm the two cells report different N.

- [ ] **Step 2: Plateau check**

A 2-point grid has one neighbour each, so `plateau_report` is weak here. State
that limitation explicitly in the results doc rather than pretending a 2-cell
grid demonstrates a plateau. If K=2 and K=3 disagree by more than
`PLATEAU_TOLERANCE_R = 0.03`, treat the better one as a spike and **reject**.

- [ ] **Step 3: Write results doc, commit**

```bash
git add docs/superpowers/results/2026-09-10-v84-maribbon-train.md
git commit -m "docs(v84): MA Ribbon TRAIN grid result"
```

---

### Task R22: MA Ribbon — Stage 2 walkforward

Only if R21 qualified. Identical shape to R18:

- [ ] **Step 1: Emit arms**

```bash
python scripts/backtest/measure_strategy_arm.py \
  --strategy "MA Ribbon" \
  --component-json '{"MA_RIBBON_CONFIRM_BARS": <adopted K>}' \
  --out data/v84_maribbon_folds.json
```

- [ ] **Step 2: Score**

```bash
python scripts/backtest/validate_component.py --stage walkforward \
  --arms data/v84_maribbon_folds.json \
  --title "v84 MA Ribbon alignment confirmation" \
  --window "fold-test 2021/2022/2023" \
  --out-md docs/superpowers/results/2026-09-10-v84-maribbon-walkforward.md
```

- [ ] **Step 3: Commit the verdict either way**

---

### Task R23: MA Ribbon — VALIDATION (ONE shot)

Only if R21 and R22 both passed. Same four steps as R19, substituting
`"MA Ribbon"`, `MA_RIBBON_CONFIRM_BARS`, `confirm_bars`, and
`data/v84_maribbon_validation.json`. Adopt the default in both
`DEFAULT_PARAMS` and the config Field before spending the shot.

---

### Task R24: Support/Resistance — level-touch significance filter

Spec §4.6. Baseline: **N=247, WR 45.7%, ExpR +0.316** — 4.3pp short.

**⚠ Declared adjacency — must appear in the code comment, the task, and the
results doc.** The closed `LEVEL_TOUCH_STRENGTH` (v36) pre-registration used
touch-count as a **post-qualification confidence tiebreak between
already-selected target candidates**, and measured net-negative. This uses the
same underlying signal as a **pre-entry gate on which setups fire**. Different
pipeline point, same signal family. Do not present it as unrelated.

**Files:**
- Modify: `swingbot/config.py`
- Modify: `swingbot/core/market/entry_filters.py:416-452`
- Test: `tests/market/test_rescue_sr_touches.py` (create)

**Interfaces:**
- Produces: config attr `SR_MIN_LEVEL_TOUCHES` (int, default `0` = off), param
  key `min_level_touches`.

- [ ] **Step 1: Write the failing test**

```python
# tests/market/test_rescue_sr_touches.py
import numpy as np

from swingbot.core.market.entry_filters import support_resistance_entries
from tests.conftest import make_ohlcv, make_trend_df

GATED = {"base_atr": 4.0, "close_frac": 0.4, "gap_pct": 3.0,
         "min_level_touches": 2}


def test_gate_off_is_byte_identical():
    df = make_trend_df(300, +0.2)
    a, _ = support_resistance_entries(df, "2m")
    b, _ = support_resistance_entries(
        df, "2m", params={"base_atr": 4.0, "close_frac": 0.4,
                          "gap_pct": 3.0, "min_level_touches": 0})
    assert (a == b).all()


def test_filter_never_adds_entries():
    df = make_trend_df(400, +0.35)
    on, _ = support_resistance_entries(df, "2m", params=GATED)
    off, _ = support_resistance_entries(df, "2m")
    assert on.sum() <= off.sum()
    assert (on & ~off).sum() == 0


def test_untested_single_spike_high_is_rejected():
    """A lone spike high that was never revisited is not a tested ceiling:
    with the gate on, a breakout over it must not fire."""
    closes = np.concatenate([
        np.linspace(100, 108, 200),
        np.array([130.0]),              # single untested spike
        np.linspace(109, 118, 99),      # later breakout above 108, not 130
    ])
    df = make_ohlcv(closes)
    on, _ = support_resistance_entries(df, "2m", params=GATED)
    off, _ = support_resistance_entries(df, "2m")
    assert on.sum() <= off.sum()


def test_no_lookahead():
    df = make_trend_df(300, +0.3)
    full, _ = support_resistance_entries(df, "2m", params=GATED)
    trunc, _ = support_resistance_entries(df.iloc[:-1], "2m", params=GATED)
    assert (full.iloc[:-1] == trunc).all()
```

- [ ] **Step 2: Run it to verify it fails**

```bash
python scripts/dev/testrun.py file tests/market/test_rescue_sr_touches.py
```

Expected: FAIL — `min_level_touches` is currently ignored, so the gated and
ungated runs are identical and the byte-identical test passes vacuously while
the spike test does not constrain anything. Confirm the failure names the
missing behaviour before implementing.

- [ ] **Step 3: Add the default param**

```python
DEFAULT_PARAMS["Support/Resistance"] = {"base_atr": 4.0, "close_frac": 0.4,
                                        "gap_pct": 3.0,
                                        # v84 rescue: the broken level must
                                        # have been tested and rejected this
                                        # many times first. 0 = off.
                                        "min_level_touches": 0}
```

- [ ] **Step 4: Implement the filter**

Insert before the `return bullish, bearish` at `entry_filters.py:452`:

```python
    # --- v84 rescue: level-touch significance, as a PRE-ENTRY gate ---
    # Adjacency declared: the closed LEVEL_TOUCH_STRENGTH (v36) used touch
    # count as a post-selection tiebreak between target candidates and
    # measured net-negative. This is the same signal at a different pipeline
    # point -- gating which setups fire at all. Different mechanism, and the
    # results doc says so explicitly.
    from swingbot import config
    min_touches = int(params.get("min_level_touches") if params and
                      "min_level_touches" in params
                      else getattr(config, "SR_MIN_LEVEL_TOUCHES", None)
                      or p["min_level_touches"])
    if min_touches > 0:
        near = 0.5 * g["atr14"]
        # approached the level and closed back on the wrong side of it
        rejected_res = ((high >= resistance - near) & (close < resistance))
        rejected_sup = ((low <= support + near) & (close > support))
        touches_res = rejected_res.rolling(lookback).sum().shift(1)
        touches_sup = rejected_sup.rolling(lookback).sum().shift(1)
        bullish &= (touches_res >= min_touches).fillna(False)
        bearish &= (touches_sup >= min_touches).fillna(False)
```

The `.shift(1)` keeps the count strictly prior to the breakout bar — the
NO-LOOKAHEAD rule at the top of this module.

- [ ] **Step 5: Add the config Field**

```python
    Field("SR_MIN_LEVEL_TOUCHES", "SR_MIN_LEVEL_TOUCHES",
          "Trade Filters & Risk", "S/R: minimum prior level rejections",
          type="int", default="0", min=0, max=5, step=1,
          help="How many times price must have approached the level (within "
               "half an ATR) and closed back on the wrong side of it before a "
               "breakout through it counts as a tested ceiling. 0 disables the "
               "check, treating any rolling-window extreme as a level."),
```

Register as searchable (see R16 Step 5).

- [ ] **Step 6: Verify and run tests**

```bash
python -c "from swingbot import config; print(config.SR_MIN_LEVEL_TOUCHES, 'SR_MIN_LEVEL_TOUCHES' in config.searchable_attrs())"
python scripts/dev/testrun.py file tests/market/test_rescue_sr_touches.py
python scripts/dev/testrun.py file tests/market/test_entry_filters.py
```

Expected: `0 True`, then both PASS.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py swingbot/core/market/entry_filters.py tests/market/test_rescue_sr_touches.py
git commit -m "feat(support-resistance): level-touch significance pre-entry gate (v84 R24)

Requires the broken level to have been approached within 0.5*ATR14 and
rejected N times before a breakout qualifies. Defaults to 0 (off).

Adjacency declared: v36's closed LEVEL_TOUCH_STRENGTH used touch count as a
post-selection target tiebreak and measured net-negative; this gates entry
instead. Same signal family, different pipeline point."
```

---

### Task R25: Support/Resistance — TRAIN grid and plateau

**Pre-registered rule (spec §4.6, verbatim):** TRAIN win_rate ≥ 50%, ExpR > 0,
N ≥ 30, excl ≤ 50% on the filtered population, plateau across the
touch-count/tolerance grid required.

- [ ] **Step 1: Run the grid** (dispatch to `backtest-runner`)

```bash
for K in 1 2 3; do
  SR_MIN_LEVEL_TOUCHES=$K python scripts/backtest/run_backtest_range.py \
    --train --strategy "Support/Resistance" \
    --exit-model v2 --scale-out --pass-wr 50 \
    --json "$SCRATCH/sr_train_k$K.json"
done
```

Note S/R is gated to `(bullish, {2m, 3m})` by `STRATEGY_GATES`
(`strategy_types.py:214`), so N here comes from two horizons only — the
baseline N=247 already reflects that. Watch the N≥30 floor as K rises; a filter
this strict can cut the population below the floor, which is a rejection, not a
reason to lower K below the grid.

- [ ] **Step 2: Plateau check** with `plateau_report` over `[1, 2, 3]`.

- [ ] **Step 3: Write results doc, commit**

The doc must carry the LEVEL_TOUCH_STRENGTH adjacency paragraph verbatim from
R24, so a future reader comparing the two pre-registrations sees the
relationship stated rather than having to notice it.

---

### Task R26: Support/Resistance — Stage 2 walkforward

Only if R25 qualified. Same shape as R18/R22:

```bash
python scripts/backtest/measure_strategy_arm.py \
  --strategy "Support/Resistance" \
  --component-json '{"SR_MIN_LEVEL_TOUCHES": <adopted K>}' \
  --out data/v84_sr_folds.json

python scripts/backtest/validate_component.py --stage walkforward \
  --arms data/v84_sr_folds.json \
  --title "v84 Support/Resistance level-touch gate" \
  --window "fold-test 2021/2022/2023" \
  --out-md docs/superpowers/results/2026-09-10-v84-sr-walkforward.md
```

**Watch the per-fold N≥30 floor.** With only two horizons in play, a fold-year
slice of a filtered population can fall under it — `gate_win_rate` returns FAIL
for that, and that is a real rejection, not a tooling problem.

---

### Task R27: Support/Resistance — VALIDATION (ONE shot)

Only if R25 and R26 both passed. Same four steps as R19, substituting
`"Support/Resistance"`, `SR_MIN_LEVEL_TOUCHES`, `min_level_touches`, and
`data/v84_sr_validation.json`.

---

### Task R28: Tier 2 results consolidation

**Files:**
- Create: `docs/superpowers/results/2026-09-10-v84-tier2-summary.md`

- [ ] **Step 1: One table, three rows** — strategy, adopted config (or "none"),
  TRAIN verdict, Stage 2 verdict, VALIDATION verdict, final badge.
- [ ] **Step 2: Record every strategy that died at a free stage**, with the
  stage and the number that killed it. An empty rescue column is the finished
  answer.
- [ ] **Step 3: State the validation-window look count** this part spent (0–3).
- [ ] **Step 4: Commit.**

---

### Task R29: Tier 2 registry verification

- [ ] **Step 1: Confirm only rescued strategies have new rows**

```bash
python -c "
import json
rows = json.load(open('swingbot/core/backtesting/validation_registry.json'))
for r in rows:
    if r['strategy'] in ('RSI Divergence','MA Ribbon','Support/Resistance'):
        print(r['strategy'], r['status'], r['n'], r['win_rate'], r['window'], r['run_date'])
"
```

Expected: a `run_date` of `2026-09-10` **only** for strategies that actually
spent a VALIDATION shot. Any other strategy still shows its pre-existing row.

- [ ] **Step 2: Confirm no hand-edits** — `git log -p` on the registry for this
  part must show only `--emit-registry` commits from R19/R23/R27.

---

### Task R30: Tier 2 handoff

- [ ] **Step 1:** Update the index's task map to the real allocation at the top
  of this file.
- [ ] **Step 2:** Note in the handoff which strategies remain WEAK and why —
  input to R42/R43's closed-pre-registration rows.
- [ ] **Step 3:** Do **not** run the full suite here. That is R41.
