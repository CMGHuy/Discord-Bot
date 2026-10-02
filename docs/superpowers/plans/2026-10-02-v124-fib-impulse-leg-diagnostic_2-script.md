# Fibonacci impulse-leg instrument and anchor diagnostic — implementation plan, part 2 (Phases 2–3)

> Part of v124. Header, global constraints, file map, the arm 4 identification route, review focus and `## Parallelisation` live in `2026-10-02-v124-fib-impulse-leg-diagnostic_0-index.md`; read it and the spec (`docs/superpowers/specs/2026-10-02-v124-fib-impulse-leg-diagnostic-design.md`) with any task here.

# Phase 2 — The diagnostic script

### Task V124-3: Window guards, bucket arithmetic, verdicts, reproduction

**Files:** Create `scripts/backtest/measure_fib_anchor_diagnostic.py`, `tests/scripts/test_measure_fib_anchor_diagnostic.py`.

**Interfaces:**
- Consumes: `funnel.MIN_N_TRAIN`, `funnel.pooled`, `funnel.dir_rows`; `measure_fib_confluence.TRAIN_EXT`, `Progress`, `_load_frames`, `_write`, `require_ext_cache`.
- Produces: `DIRECTIONS`, `DIAG_WINDOW = ("2015-01-01", "2025-12-31")`, `REPRO_WINDOW = TRAIN_EXT`, `TOL_ATR = 0.25`, `DIVISORS = (4, 6, 8)`, `PRIMARY_DIVISOR = 6`, `MIN_BUCKET_N = 30`, `MIN_SIGN_DIVISORS = 2`, `REFERENCE`, `REFERENCE_UNIVERSE_N = 73`, `EXIT_RULE`; `require_diagnostic_window(window) -> window` (raises `SystemExit` for a start before 2015-01-01 or an end after 2025-12-31); `require_repro_window(window) -> tuple` (raises unless the window is exactly `REPRO_WINDOW`); `bucket(rows, favourable) -> {"favourable": stats, "rest": stats}`; `split_passes(buckets) -> bool`; `wr_sign_positive(buckets) -> bool`; `divisor_buckets(rows, cell_key) -> {"4"|"6"|"8": buckets}` (reads `row["d<divisor>"][cell_key]`); `leg_arm_verdict(by_divisor) -> {"primary_passes", "wr_sign_divisors", "proceeds"}`; `single_split_verdict(buckets) -> {"primary_passes", "proceeds"}`; `describe(rows, key) -> {label: stats}`; `quintile_key(rows, value_key) -> callable`; `reproduction(rows, direction, universe_n, reference=None) -> dict` (`None` reads the module's `REFERENCE` at call time).

- [ ] **Step 0: Precondition** as in V124-1 Step 0.
- [ ] **Step 1: Write the failing tests.**

```python
# tests/scripts/test_measure_fib_anchor_diagnostic.py
"""v124 diagnostic: refusals, bucket arithmetic, features, identification, report. No backtests."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def _module():
    import measure_fib_anchor_diagnostic
    return measure_fib_anchor_diagnostic


def trade(outcome, r, direction="bullish", **flags):
    """A hand-labelled trade row; flags land in every divisor cell (d4/d6/d8)."""
    cell = {"has_leg": True, "anchored": False, "zone_confluence": False, "fib_on_leg": False,
            "zone_touch": False, "close_in_zone": False, "broke_structure": None, "leg_atr": 1.0}
    cell.update({key: value for key, value in flags.items() if key in cell})
    row = {"ticker": "AAA", "horizon_key": "4w", "direction": direction, "entry_date": "2015-06-01",
           "outcome": outcome, "r_multiple": r, "confirm_close": flags.get("confirm_close", False),
           "confirm_wick": False, "anchor_fractal": True, "tested_ratio": 0.5,
           "rolling_level_confluence": False, "identified": True, "has_fib": True}
    row.update({f"d{d}": dict(cell) for d in (4, 6, 8)})
    return row


def group(wins, losses, win_r=2.0, **flags):
    return [trade("win", win_r, **flags) for _ in range(wins)] + [trade("loss", -1.0, **flags) for _ in range(losses)]


GOOD = dict(anchored=True, zone_confluence=True, fib_on_leg=True, confirm_close=True)


@pytest.mark.parametrize("window", [("2014-12-31", "2025-12-31"), ("2015-01-01", "2026-01-02"),
                                    ("2010-01-01", "2023-12-31"), ("2026-01-02", "2026-06-30")])
def test_diagnostic_window_outside_2015_2025_is_refused(window):
    with pytest.raises(SystemExit, match="diagnostic window"):
        _module().require_diagnostic_window(window)


@pytest.mark.parametrize("window", [("2015-01-01", "2025-12-31"), ("2015-01-01", "2015-12-31")])
def test_diagnostic_window_inside_2015_2025_is_accepted(window):
    assert _module().require_diagnostic_window(window) == window


def test_reproduction_window_is_exactly_v103s():
    module = _module()
    assert module.require_repro_window(["2010-01-01", "2023-12-31"]) == ("2010-01-01", "2023-12-31")
    for window in (("2010-01-01", "2025-12-31"), ("2015-01-01", "2023-12-31")):
        with pytest.raises(SystemExit, match="reproduction runs on 2010-01-01..2023-12-31"):
            module.require_repro_window(window)


def test_bucket_arithmetic_on_hand_labelled_rows():
    module = _module()
    rows = group(20, 20, anchored=True) + group(12, 28)
    buckets = module.bucket(rows, lambda row: row["d6"]["anchored"])
    fav, rest = buckets["favourable"], buckets["rest"]
    assert (fav["n"], rest["n"]) == (40, 40)
    assert fav["win_rate"] == pytest.approx(50.0) and rest["win_rate"] == pytest.approx(30.0)
    assert fav["expectancy_r"] == pytest.approx(0.5) and rest["expectancy_r"] == pytest.approx(-0.1)
    assert module.split_passes(buckets) is True


def test_split_needs_n_30_in_each_bucket():
    module = _module()
    buckets = module.bucket(group(15, 14, anchored=True) + group(12, 28), lambda row: row["d6"]["anchored"])
    assert buckets["favourable"]["n"] == 29
    assert module.split_passes(buckets) is False


def test_split_needs_expr_no_lower_and_accepts_equal():
    module = _module()
    lower = module.bucket(group(20, 20, win_r=0.5, anchored=True) + group(12, 28),
                          lambda row: row["d6"]["anchored"])
    assert module.split_passes(lower) is False                         # WR 50 > 30 but ExpR -0.25 < -0.1
    equal = module.bucket(group(20, 20, win_r=0.75, anchored=True) + group(10, 30, win_r=2.5),
                          lambda row: row["d6"]["anchored"])
    assert equal["favourable"]["expectancy_r"] == equal["rest"]["expectancy_r"] == -0.125
    assert module.split_passes(equal) is True


def test_equal_win_rate_does_not_pass():
    module = _module()
    buckets = module.bucket(group(15, 15, anchored=True) + group(15, 15), lambda row: row["d6"]["anchored"])
    assert module.split_passes(buckets) is False
    assert module.wr_sign_positive(buckets) is False


def test_scratch_only_bucket_is_not_a_pass_and_never_raises():
    module = _module()
    rows = [trade("scratch", 0.0, anchored=True) for _ in range(40)] + group(12, 28)
    buckets = module.bucket(rows, lambda row: row["d6"]["anchored"])
    assert buckets["favourable"]["win_rate"] is None
    assert module.split_passes(buckets) is False
    assert module.wr_sign_positive(buckets) is False


def _per_divisor(flags_by_divisor):
    """A (20W/20L) and B (12W/28L); flags_by_divisor[d] names which group is favourable at d."""
    rows = group(20, 20) + group(12, 28)
    for index, row in enumerate(rows):
        in_a = index < 40
        for divisor, favoured in flags_by_divisor.items():
            row[f"d{divisor}"]["anchored"] = in_a if favoured == "A" else not in_a
    return rows


def test_leg_arm_needs_primary_and_two_divisor_signs():
    module = _module()
    passing = module.leg_arm_verdict(module.divisor_buckets(_per_divisor({4: "A", 6: "A", 8: "B"}), "anchored"))
    assert passing == {"primary_passes": True, "wr_sign_divisors": 2, "proceeds": True}
    failing = module.leg_arm_verdict(module.divisor_buckets(_per_divisor({4: "B", 6: "A", 8: "B"}), "anchored"))
    assert failing == {"primary_passes": True, "wr_sign_divisors": 1, "proceeds": False}
    no_primary = module.leg_arm_verdict(module.divisor_buckets(_per_divisor({4: "A", 6: "B", 8: "A"}), "anchored"))
    assert no_primary["proceeds"] is False


def test_single_split_verdict():
    module = _module()
    buckets = module.bucket(group(20, 20, confirm_close=True) + group(12, 28), lambda row: row["confirm_close"])
    assert module.single_split_verdict(buckets) == {"primary_passes": True, "proceeds": True}


def test_describe_and_quintiles():
    module = _module()
    rows = group(5, 5)
    for index, row in enumerate(rows):
        row["d6"]["leg_atr"] = float(index + 1)
    rows += [trade("loss", -1.0, leg_atr=None)]
    label = module.quintile_key(rows, lambda row: row["d6"]["leg_atr"])
    groups = module.describe(rows, label)
    assert set(groups) == {"Q1", "Q2", "Q3", "Q4", "Q5", "no leg"}
    assert groups["no leg"]["n"] == 1
    assert sum(stats["n"] for stats in groups.values()) == 11


def test_reproduction_compares_n_wr_expr_and_universe():
    module = _module()
    rows = group(20, 20)
    reference = {"bullish": {"n": 40, "win_rate": 50.0, "expectancy_r": 0.5}}
    assert module.reproduction(rows, "bullish", 73, reference)["matches"] is True
    assert module.reproduction(rows, "bullish", 72, reference)["matches"] is False
    assert module.reproduction(rows[:-1], "bullish", 73, reference)["matches"] is False


def test_reference_is_the_v103_arm():
    module = _module()
    assert module.REFERENCE["bullish"] == {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219}
    assert module.REFERENCE["bearish"] == {"n": 169, "win_rate": 23.67, "expectancy_r": -0.1269}
    assert module.REFERENCE_UNIVERSE_N == 73
    assert module.REPRO_WINDOW == ("2010-01-01", "2023-12-31")
    assert module.DIAG_WINDOW == ("2015-01-01", "2025-12-31")
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement.**

```python
#!/usr/bin/env python3
"""v124: Fibonacci impulse-leg anchor diagnostic -- read-only.

Spec: docs/superpowers/specs/2026-10-02-v124-fib-impulse-leg-diagnostic-design.md
Extended cache only: run with BACKTEST_CACHE_DIR=data/backtest_cache_ext.

Two windows. The diagnostic reads entries 2015-01-01..2025-12-31 (DIAG_WINDOW,
partner decision 2026-10-02); a trade still open at 2025-12-31 may resolve on
2026 bars (outcome resolution only). First, the v103 reference arm is
re-collected on its own window 2010-01-01..2023-12-31 (REPRO_WINDOW) to prove
the instrument matches v103; the 2015/2025 bounds do not apply to that check.
2026 is the holdout. No VALIDATION budget is spent.

It measures whether each of four Fibonacci-handbook claims shows any signal
in the bot's own trades. It gates nothing. Each arm has one primary split,
fixed in the spec, and an exit rule (EXIT_RULE) that decides only whether the
arm earns its own spec.

Commands (from the repo root):
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_anchor_diagnostic.py \\
      collect-repro --direction bullish --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_anchor_diagnostic.py \\
      collect-fib --direction bullish --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_anchor_diagnostic.py \\
      collect-confluence --tickers A,B,C --out <json>
  python scripts/backtest/measure_fib_anchor_diagnostic.py reproduce --repro <bull json> <bear json>
  python scripts/backtest/measure_fib_anchor_diagnostic.py report --repro <bull> <bear> --fib <bull> <bear> \\
      --confluence <json> [<json> ...] --out <json> --md <md> [--reproduction-note <md>]
"""
from __future__ import annotations

import argparse
import collections
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

from funnel import MIN_N_TRAIN, dir_rows, pooled  # noqa: E402
from measure_fib_confluence import TRAIN_EXT, Progress, _load_frames, _write, require_ext_cache  # noqa: E402

DIRECTIONS = ("bullish", "bearish")
DIAG_WINDOW = ("2015-01-01", "2025-12-31")   # entries + features (partner decision, 2026-10-02)
REPRO_WINDOW = TRAIN_EXT                     # v103's own window, for the reproduction check only
# --- frozen in the spec ---
TOL_ATR = 0.25            # one tolerance, arms 1, 2 and 4
DIVISORS = (4, 6, 8)      # leg-dependent splits reported at every divisor
PRIMARY_DIVISOR = 6       # == fib_leg.ORIGIN_DIVISOR (pinned by a test in V124-4)
MIN_BUCKET_N = MIN_N_TRAIN
MIN_SIGN_DIVISORS = 2
REFERENCE = {"bullish": {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219},
             "bearish": {"n": 169, "win_rate": 23.67, "expectancy_r": -0.1269}}
REFERENCE_UNIVERSE_N = 73
EXIT_RULE = ("An arm proceeds to its own spec only if, on the bullish side, the favourable bucket "
             "has a higher win rate and an ExpR no lower than the rest, with N >= 30 in each bucket. "
             "Arms 1, 2 and 4 must also keep the win-rate sign at two of the three divisors.")


def require_diagnostic_window(window):
    """Refuse a diagnostic window starting before 2015-01-01 or ending after 2025-12-31."""
    start, end = window
    if start < DIAG_WINDOW[0] or end > DIAG_WINDOW[1]:
        raise SystemExit(f"v124 diagnostic window is {DIAG_WINDOW[0]}..{DIAG_WINDOW[1]}: got {start}..{end}")
    return window


def require_repro_window(window):
    """The v103 reproduction runs on exactly REPRO_WINDOW, nothing else."""
    if tuple(window) != REPRO_WINDOW:
        raise SystemExit(f"the v103 reproduction runs on {REPRO_WINDOW[0]}..{REPRO_WINDOW[1]} only: got {window}")
    return tuple(window)


def bucket(rows, favourable) -> dict:
    fav, rest = [], []
    for row in rows:
        (fav if favourable(row) else rest).append(row)
    return {"favourable": pooled(fav), "rest": pooled(rest)}


def _comparable(stats) -> bool:
    return (stats["n"] >= MIN_BUCKET_N and stats["win_rate"] is not None
            and stats["expectancy_r"] is not None)


def split_passes(buckets) -> bool:
    """Spec exit rule for one split: higher WR, ExpR no lower, N >= 30 in each bucket."""
    fav, rest = buckets["favourable"], buckets["rest"]
    if not (_comparable(fav) and _comparable(rest)):
        return False
    return fav["win_rate"] > rest["win_rate"] and fav["expectancy_r"] >= rest["expectancy_r"]


def wr_sign_positive(buckets) -> bool:
    fav, rest = buckets["favourable"]["win_rate"], buckets["rest"]["win_rate"]
    return fav is not None and rest is not None and fav > rest


def divisor_buckets(rows, cell_key) -> dict:
    return {str(d): bucket(rows, lambda row, d=d: bool(row[f"d{d}"][cell_key])) for d in DIVISORS}


def leg_arm_verdict(by_divisor) -> dict:
    primary = split_passes(by_divisor[str(PRIMARY_DIVISOR)])
    signs = sum(wr_sign_positive(by_divisor[str(d)]) for d in DIVISORS)
    return {"primary_passes": primary, "wr_sign_divisors": signs,
            "proceeds": primary and signs >= MIN_SIGN_DIVISORS}


def single_split_verdict(buckets) -> dict:
    primary = split_passes(buckets)
    return {"primary_passes": primary, "proceeds": primary}


def describe(rows, key) -> dict:
    """Description only: pooled stats per label. Never feeds a verdict."""
    groups = collections.defaultdict(list)
    for row in rows:
        groups[str(key(row))].append(row)
    return {name: pooled(members) for name, members in sorted(groups.items())}


def quintile_key(rows, value_key):
    """Label function: Q1..Q5 over this population's own values, 'no leg' for None."""
    values = [value for value in map(value_key, rows) if value is not None]
    if not values:
        return lambda row: "no leg"
    edges = np.quantile(values, [0.2, 0.4, 0.6, 0.8])

    def label(row):
        value = value_key(row)
        return "no leg" if value is None else f"Q{int(np.searchsorted(edges, value, side='right')) + 1}"
    return label


def reproduction(rows, direction, universe_n, reference=None) -> dict:
    """v103 reference arm on REPRO_WINDOW: N exact, WR at 2 dp, ExpR at 4 dp, universe exact."""
    observed, want = pooled(dir_rows(rows, direction)), (reference or REFERENCE)[direction]
    same = (observed["n"] == want["n"] and observed["win_rate"] is not None
            and observed["expectancy_r"] is not None
            and round(observed["win_rate"], 2) == want["win_rate"]
            and round(observed["expectancy_r"], 4) == want["expectancy_r"])
    return {"observed": observed, "reference": want, "universe_n": universe_n,
            "reference_universe_n": REFERENCE_UNIVERSE_N,
            "matches": bool(same and universe_n == REFERENCE_UNIVERSE_N)}
```

- [ ] **Step 4: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect PASS. Run `python -m radon cc -s -n C scripts/backtest/measure_fib_anchor_diagnostic.py tests/scripts/test_measure_fib_anchor_diagnostic.py` and expect no output.
- [ ] **Step 5: Commit.**

```bash
git add scripts/backtest/measure_fib_anchor_diagnostic.py tests/scripts/test_measure_fib_anchor_diagnostic.py
git commit -m "feat(v124): diagnostic and reproduction window guards, bucket arithmetic, verdicts"
```

### Task V124-4: Arms 1–3 features, the Fibonacci collector and the reproduction collector

**Files:** Modify `scripts/backtest/measure_fib_anchor_diagnostic.py`, `tests/scripts/test_measure_fib_anchor_diagnostic.py`.

**Interfaces:**
- Consumes (V124-1/2): `fib_leg.ORIGIN_DIVISOR`, `leg_at`, `origin_strength`, `PRICE_COLUMNS`; (V124-3) `require_diagnostic_window`, `require_repro_window`, `DIAG_WINDOW`, `REPRO_WINDOW`, `TOL_ATR`, `DIVISORS`, `Progress`, `_load_frames`, `_write`, `require_ext_cache`; (existing) `measure_fib_v103.collect_trades`, `measure_fib_diagnostic.fib_level`/`tested_ratio`, `run_backtest_range._build_asof_map`, `levels.collect_candidate_levels`/`strategy_family`, `structure.PIVOT_K`/`pivot_confirmations`, `indicators.atr`, `HORIZONS`, `config.AVWAP_LEVELS_ENABLED`.
- Produces: `ZONE_FAMILIES`; `atr_at(prefix) -> float`; `near(a, b, atr_value) -> bool`; `rolling_anchor(prefix, lookback) -> dict | None` (`low`, `low_pos`, `high`, `high_pos`, first occurrence); `anchored_split(anchor, leg, atr_value, direction) -> bool`; `anchor_is_fractal(prefix, anchor, direction) -> bool | None`; `zone_confluence(candidates, leg, atr_value) -> bool`; `level_confluence(candidates, level, atr_value) -> bool`; `close_in_zone(leg, close) -> bool`; `confirm_close(prefix, direction) -> bool`; `confirm_wick(prefix, direction) -> bool`; `tri(value) -> bool | None`; `num(value) -> float | None`; `leg_cell(...) -> dict` (keys `has_leg`, `anchored`, `zone_confluence`, `zone_touch`, `close_in_zone`, `broke_structure`, `leg_atr`); `fib_trade_features(frame, horizon_key, direction, entry_date, *, candidates_fn=collect_candidate_levels) -> dict` (keys `confirm_close`, `confirm_wick`, `anchor_fractal`, `tested_ratio`, `rolling_level_confluence`, `d4`, `d6`, `d8`); `collect_fib(frames, asof_map, direction, window=DIAG_WINDOW, *, run_fn=None, progress=None, candidates_fn=collect_candidate_levels) -> list[dict]`; `collect_repro(frames, asof_map, direction, *, run_fn=None, progress=None) -> list[dict]` (trade rows only, on `REPRO_WINDOW`); `_frames_and_asof(args)`, `_cmd_collect_fib(args)`, `_cmd_collect_repro(args)`.

- [ ] **Step 0: Precondition** as in V124-1 Step 0.
- [ ] **Step 1: Write the failing tests.** Append. On `CLEAN[:17]` with horizon `2w` (`fib_lookback` 15, so `origin_strength` is 3 at every divisor), the rolling window is bars 2..16. Its low is bar 7 (8.5) and its high is bar 13 (15.5), the leg's own origin and end. Bar 16 has Open = Close = 13, Low 12.5, High 13.5, so the lower wick is exactly half the range.

```python
from types import SimpleNamespace as NS

from tests.market.fib_leg_fixtures import CLEAN, MIRROR, path_frame

SIDES = [(False, "bullish"), (True, "bearish")]


def _entry(mirror):
    frame = path_frame(CLEAN[:17], mirror=mirror)
    return frame, str(frame.index[16].date())


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_fib_trade_features_on_the_clean_leg(mirror, direction):
    module = _module()
    frame, date = _entry(mirror)
    zone_price = MIRROR - 11.5 if mirror else 11.5            # inside the 0.5-0.618 zone
    label = "Anchored VWAP (swing low)" if mirror else "Volume Profile HVN"
    out = module.fib_trade_features(frame, "2w", direction, date,
                                    candidates_fn=lambda df, h, price: [(zone_price, label), (zone_price, "EMA20")])
    assert out["anchor_fractal"] is True
    assert out["confirm_close"] is False                       # Close 13 is not above the prior High 14
    assert out["confirm_wick"] is True                         # wick 0.5 of range 1.0
    assert out["tested_ratio"] == 0.382                        # nearest level 12.826 to Close 13
    assert out["rolling_level_confluence"] is False            # 11.5 is > 0.25 ATR from 12.826
    for divisor in (4, 6, 8):
        cell = out[f"d{divisor}"]
        assert cell["has_leg"] is True and cell["anchored"] is True and cell["zone_confluence"] is True
        assert cell["zone_touch"] is False and cell["close_in_zone"] is False
        assert cell["broke_structure"] is True and cell["leg_atr"] > 0


def test_zone_ignores_other_families_and_missing_legs():
    module = _module()
    frame, date = _entry(False)
    out = module.fib_trade_features(frame, "2w", "bullish", date,
                                    candidates_fn=lambda df, h, price: [(11.5, "EMA20"), (14.0, "Volume Profile HVN")])
    assert out["d6"]["zone_confluence"] is False
    nan_leg = dict.fromkeys(("level_500", "level_618", "origin_price", "end_price"), float("nan"))
    assert module.zone_confluence([(11.5, "Volume Profile HVN")], nan_leg, 1.0) is False
    assert module.close_in_zone(nan_leg, 11.5) is False


def test_short_history_has_no_rolling_anchor():
    module = _module()
    prefix = path_frame(CLEAN[:10])
    assert module.rolling_anchor(prefix, 15) is None
    assert module.anchored_split(None, {"origin_price": 8.5, "end_price": 15.5}, 1.0, "bullish") is False
    assert module.anchor_is_fractal(prefix, None, "bullish") is None


def test_anchor_that_is_not_a_fractal():
    module = _module()
    prefix = path_frame(CLEAN[:9])                             # bar 7 needs bar 10 to confirm
    anchor = module.rolling_anchor(prefix, 9)
    assert anchor["low_pos"] == 7
    assert module.anchor_is_fractal(prefix, anchor, "bullish") is False


@pytest.mark.parametrize("mirror,direction", SIDES)
def test_confirmation_close_beyond_prior_bar(mirror, direction):
    module = _module()
    prefix = path_frame([10, 12], mirror=mirror)               # Close 12 > prior High 10.5
    assert module.confirm_close(prefix, direction) is True
    assert module.confirm_close(path_frame([10, 10.2], mirror=mirror), direction) is False
    assert module.confirm_close(path_frame([10], mirror=mirror), direction) is False


def test_near_needs_finite_values_and_positive_atr():
    module = _module()
    assert module.near(10.0, 10.2, 1.0) is True
    assert module.near(10.0, 10.3, 1.0) is False
    assert module.near(10.0, float("nan"), 1.0) is False
    assert module.near(10.0, 10.0, float("nan")) is False
    assert module.near(10.0, 10.0, 0.0) is False


def test_primary_divisor_is_the_fib_leg_default():
    from swingbot.core.market.fib_leg import ORIGIN_DIVISOR
    assert _module().PRIMARY_DIVISOR == ORIGIN_DIVISOR


def _explode(*args, **kwargs):
    raise AssertionError("run_fn must not be called")


@pytest.mark.parametrize("window", [("2015-01-01", "2026-03-01"), ("2010-01-01", "2023-12-31")])
def test_collect_fib_refuses_a_window_outside_2015_2025_before_running(window):
    with pytest.raises(SystemExit, match="diagnostic window"):
        _module().collect_fib({}, {}, "bullish", window, run_fn=_explode)


def test_collect_fib_stamps_features_on_reference_trades():
    module = _module()
    frame, date = _entry(False)

    def run_fn(ticker, df, strategy, horizon, **kwargs):
        assert strategy == "Fibonacci"
        trades = [NS(entry_date=date, direction="bullish", outcome="win", r_multiple=1.5)] if horizon == "2w" else []
        return NS(trades=trades)

    rows = module.collect_fib({"AAA": frame}, {}, "bullish", module.DIAG_WINDOW, run_fn=run_fn,
                              candidates_fn=lambda df, h, price: [])
    assert len(rows) == 1
    row = rows[0]
    assert (row["ticker"], row["horizon_key"], row["outcome"], row["r_multiple"]) == ("AAA", "2w", "win", 1.5)
    assert row["d6"]["anchored"] is True and row["d6"]["zone_confluence"] is False


def test_collect_repro_runs_the_reference_arm_on_v103s_window_without_features():
    module = _module()
    frame, date = _entry(False)
    seen = []

    def run_fn(ticker, df, strategy, horizon, **kwargs):
        trades = [NS(entry_date=date, direction="bullish", outcome="loss", r_multiple=-1.0),
                  NS(entry_date="2024-02-01", direction="bullish", outcome="win", r_multiple=2.0)]
        seen.append(horizon)
        return NS(trades=trades if horizon == "2w" else [])

    rows = module.collect_repro({"AAA": frame}, {}, "bullish", run_fn=run_fn)
    assert [row["entry_date"] for row in rows] == [date]       # the 2024 entry is outside 2010-2023
    assert "d6" not in rows[0] and seen
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect the new tests to FAIL (`AttributeError`).
- [ ] **Step 3: Implement.** Add to the import block, after the `measure_fib_confluence` import:

```python
import pandas as pd  # noqa: E402

import measure_fib_v103  # noqa: E402
from measure_fib_diagnostic import fib_level, tested_ratio  # noqa: E402
from run_backtest_range import _build_asof_map  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.market.fib_leg import leg_at, origin_strength  # noqa: E402
from swingbot.core.market.indicators import atr  # noqa: E402
from swingbot.core.market.levels import collect_candidate_levels, strategy_family  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.market.structure import PIVOT_K, pivot_confirmations  # noqa: E402
```

Append the arm 1–3 feature block and the collector:

```python
ZONE_FAMILIES = frozenset({"Volume Profile", "AVWAP"})   # Rolling S/R closed by v102; Zigzag redundant (v49)


def atr_at(prefix) -> float:
    return float(atr(prefix).iloc[-1]) if len(prefix) else float("nan")


def near(a, b, atr_value) -> bool:
    return bool(np.isfinite(a) and np.isfinite(b) and atr_value > 0 and abs(a - b) <= TOL_ATR * atr_value)


def rolling_anchor(prefix, lookback):
    """The swing low/high fibonacci_entries draws at the last bar: min Low / max
    High over the trailing ``lookback`` bars (first occurrence). None when short."""
    if len(prefix) < lookback:
        return None
    lows = prefix["Low"].to_numpy(float)[-lookback:]
    highs = prefix["High"].to_numpy(float)[-lookback:]
    base = len(prefix) - lookback
    return {"low": float(lows.min()), "low_pos": base + int(np.argmin(lows)),
            "high": float(highs.max()), "high_pos": base + int(np.argmax(highs))}


def anchored_split(anchor, leg, atr_value, direction) -> bool:
    """Arm 1 primary: the rolling origin-side extreme within 0.25 ATR of the leg
    origin AND the other extreme within 0.25 ATR of the leg end."""
    if anchor is None:
        return False
    origin, end = (anchor["low"], anchor["high"]) if direction == "bullish" else (anchor["high"], anchor["low"])
    return near(origin, leg["origin_price"], atr_value) and near(end, leg["end_price"], atr_value)


def anchor_is_fractal(prefix, anchor, direction):
    """Arm 1 described: is the rolling origin-side extreme a k=3 fractal confirmed by now?"""
    if anchor is None:
        return None
    sh, sl = pivot_confirmations(prefix, PIVOT_K)
    flags, pos = (sl, anchor["low_pos"]) if direction == "bullish" else (sh, anchor["high_pos"])
    confirm = pos + PIVOT_K
    return bool(confirm < len(prefix) and flags[confirm])


def _zone_prices(candidates):
    return [price for price, label in candidates if strategy_family(label) in ZONE_FAMILIES]


def zone_confluence(candidates, leg, atr_value) -> bool:
    """Arm 2 primary: a Volume Profile or AVWAP price inside the leg's 0.5-0.618
    zone widened by 0.25 ATR each side. False when there is no leg."""
    lo, hi = sorted((leg["level_500"], leg["level_618"]))
    if not (np.isfinite(lo) and atr_value > 0):
        return False
    pad = TOL_ATR * atr_value
    return any(lo - pad <= price <= hi + pad for price in _zone_prices(candidates))


def level_confluence(candidates, level, atr_value) -> bool:
    """Arm 2 described: the same families within 0.25 ATR of the rolling tested level."""
    return any(near(price, level, atr_value) for price in _zone_prices(candidates))


def close_in_zone(leg, close) -> bool:
    lo, hi = sorted((leg["level_500"], leg["level_618"]))
    return bool(np.isfinite(lo) and lo <= close <= hi)


def confirm_close(prefix, direction) -> bool:
    """Arm 3 primary: Close[t] > High[t-1] (bullish) / Close[t] < Low[t-1] (bearish)."""
    if len(prefix) < 2:
        return False
    close, prior = float(prefix["Close"].iloc[-1]), prefix.iloc[-2]
    return close > float(prior["High"]) if direction == "bullish" else close < float(prior["Low"])


def confirm_wick(prefix, direction) -> bool:
    """Arm 3 described: rejection wick (lower bullish / upper bearish) >= half the range."""
    bar = prefix.iloc[-1]
    high, low = float(bar["High"]), float(bar["Low"])
    body_lo, body_hi = sorted((float(bar["Open"]), float(bar["Close"])))
    span = high - low
    if not span > 0:
        return False
    wick = body_lo - low if direction == "bullish" else high - body_hi
    return wick >= 0.5 * span


def tri(value):
    return None if not np.isfinite(value) else bool(value)


def num(value):
    return round(float(value), 6) if np.isfinite(value) else None


def leg_cell(leg, anchor, candidates, atr_value, direction, close) -> dict:
    return {"has_leg": bool(np.isfinite(leg["origin_price"])),
            "anchored": anchored_split(anchor, leg, atr_value, direction),
            "zone_confluence": zone_confluence(candidates, leg, atr_value),
            "zone_touch": tri(leg["zone_touch"]),
            "close_in_zone": close_in_zone(leg, close),
            "broke_structure": tri(leg["broke_structure"]),
            "leg_atr": num(leg["leg_atr"])}


def _rolling_tested(anchor, close, direction):
    if anchor is None:
        return None, None
    ratio = tested_ratio(close, anchor["high"], anchor["low"], direction)
    return ratio, fib_level(anchor["high"], anchor["low"], ratio, direction)


def fib_trade_features(frame, horizon_key, direction, entry_date, *, candidates_fn=collect_candidate_levels) -> dict:
    """Arm 1-3 features at the entry bar t, from frame.iloc[:t+1] only."""
    t = frame.index.get_loc(pd.Timestamp(entry_date))
    prefix = frame.iloc[:t + 1]
    close, atr_value, h = float(prefix["Close"].iloc[-1]), atr_at(prefix), HORIZONS[horizon_key]
    anchor = rolling_anchor(prefix, h["fib_lookback"])
    candidates = candidates_fn(prefix, h, close)
    ratio, tested_level = _rolling_tested(anchor, close, direction)
    out = {"confirm_close": confirm_close(prefix, direction), "confirm_wick": confirm_wick(prefix, direction),
           "anchor_fractal": anchor_is_fractal(prefix, anchor, direction), "tested_ratio": ratio,
           "rolling_level_confluence": tested_level is not None and level_confluence(candidates, tested_level, atr_value)}
    for divisor in DIVISORS:
        leg = leg_at(prefix, direction, origin_strength(horizon_key, divisor))
        out[f"d{divisor}"] = leg_cell(leg, anchor, candidates, atr_value, direction, close)
    return out


def collect_repro(frames, asof_map, direction, *, run_fn=None, progress=None) -> list:
    """The v103 reference arm (b=0) on REPRO_WINDOW, trade rows only: the
    instrument check. The diagnostic window's 2015/2025 bounds do not apply."""
    window = require_repro_window(REPRO_WINDOW)
    return measure_fib_v103.collect_trades("A", frames, asof_map, 0.0, window, directions=(direction,),
                                           run_fn=run_fn, progress=progress)


def collect_fib(frames, asof_map, direction, window=DIAG_WINDOW, *, run_fn=None, progress=None,
                candidates_fn=collect_candidate_levels) -> list:
    """Today's Fibonacci trades (the v103 reference arm, b=0) with features.
    Bearish is unmasked inside v103's collector through gate_override."""
    require_diagnostic_window(window)
    rows = measure_fib_v103.collect_trades("A", frames, asof_map, 0.0, window, directions=(direction,),
                                           run_fn=run_fn, progress=progress)
    ticks, out = Progress(len(rows)), []
    for row in rows:
        ticks.tick(f"features {direction} {row['ticker']} {row['entry_date']}")
        out.append({**row, **fib_trade_features(frames[row["ticker"]], row["horizon_key"], direction,
                                                row["entry_date"], candidates_fn=candidates_fn)})
    return out


def _frames_and_asof(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    return frames, _build_asof_map(list(frames), frames, args.universe)


def _cmd_collect_repro(args):
    started = time.monotonic()
    frames, asof_map = _frames_and_asof(args)
    rows = collect_repro(frames, asof_map, args.direction)
    _write(args.out, {"kind": "repro", "direction": args.direction, "window": REPRO_WINDOW,
                      "universe_n": len(frames), "rows": rows,
                      "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_collect_fib(args):
    require_diagnostic_window(DIAG_WINDOW)
    started = time.monotonic()
    frames, asof_map = _frames_and_asof(args)
    rows = collect_fib(frames, asof_map, args.direction, DIAG_WINDOW)
    _write(args.out, {"kind": "fib", "direction": args.direction, "window": DIAG_WINDOW,
                      "universe_n": len(frames), "avwap_levels_enabled": bool(config.AVWAP_LEVELS_ENABLED),
                      "rows": rows, "elapsed_s": round(time.monotonic() - started, 1)})
```

- [ ] **Step 4: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect PASS. Run `python -m radon cc -s -n C scripts/backtest/measure_fib_anchor_diagnostic.py` and expect no output.
- [ ] **Step 5: Commit.**

```bash
git add scripts/backtest/measure_fib_anchor_diagnostic.py tests/scripts/test_measure_fib_anchor_diagnostic.py
git commit -m "feat(v124): arm 1-3 entry-bar features, Fibonacci and v103-reproduction collectors"
```

### Task V124-5: Arm 4 identification and the confluence collector

**Files:** Modify `scripts/backtest/measure_fib_anchor_diagnostic.py`, `tests/scripts/test_measure_fib_anchor_diagnostic.py`.

**Interfaces:**
- Consumes (V124-4): `near`, `atr_at`, `leg_at`, `origin_strength`, `collect_candidate_levels`, `strategy_family`, `HORIZONS`, `config`; (V124-3) `require_diagnostic_window`, `DIAG_WINDOW`, `DIVISORS`, `Progress`, `_load_frames`, `_write`, `require_ext_cache`; (existing) `backtest_scenarios.LEVEL_REFRESH_BARS`, `levels_asof`, `replay_scenarios`; `strategy_types.MIN_BARS`; `confluence_engine.SKIPPED`; `plan_engine.simulate_exit`; `builders._clamp_stop_to_hard_cap`; `levels.Level`; `strategy_types.LEGACY_HORIZONS`.
- Produces: `FIB_FAMILY`, `LEG_PRICE_KEYS`, `ALL_HZ`; `bucket_bar(index, horizon_key) -> int`; `scenario_levels(ticker, frame, index, horizon_key, direction, *, levels_fn=levels_asof) -> (stop_level, target_level) | None`; `is_identified(plan, stop_level) -> bool`; `fib_labels(pair) -> set[str]`; `fib_candidate_prices(candidates, labels) -> list[float]`; `arm4_cell(leg, prices, atr_value) -> {"has_leg", "fib_on_leg"}`; `confluence_row(ticker, frame, horizon_key, index, plan, result, *, levels_fn, candidates_fn) -> dict` (trade keys plus `identified`, `has_fib`, and `d4`/`d6`/`d8` only when `has_fib`); `confluence_trades(ticker, frame, horizon_key, window, *, replay_fn, exit_fn) -> [(index, plan, result)]`; `collect_confluence(frames, window=DIAG_WINDOW, *, horizons=ALL_HZ, replay_fn, exit_fn, levels_fn, candidates_fn) -> list[dict]`; `_cmd_collect_confluence(args)`.

- [ ] **Step 0: Precondition** as in V124-1 Step 0.
- [ ] **Step 1: Write the failing tests.** Append. On `RESTART` (26 bars) at index 25 with `2w` (`MIN_BARS` 20), the bucket bar is 25. The leg is origin 11.0, end 16.5, size 5.5, so `level_500` is 13.75.

```python
from swingbot.core.market.levels import Level
from tests.market.fib_leg_fixtures import RESTART


@pytest.mark.parametrize("index,horizon_key,expected", [
    (132, "3m", 130), (137, "3m", 135), (131, "3m", 130), (128, "2w", 125), (21, "2w", 20), (20, "2w", 20)])
def test_bucket_bar_is_the_replays_first_visit(index, horizon_key, expected):
    assert _module().bucket_bar(index, horizon_key) == expected


def test_scenario_levels_rebuilds_the_map_and_resplits_at_this_close():
    module = _module()
    frame = path_frame([10.0] * 30)                            # Close 10 everywhere
    calls = []

    def levels_fn(ticker, df, bar, horizon_key, cache):
        calls.append(bar)
        return ([Level(9.0, ["Fib 61.8%"]), Level(8.0, ["EMA20"])],
                [Level(9.2, ["Rolling resistance"]), Level(12.0, ["Swing high"])])   # 9.2 is below 10 now

    stop, target = module.scenario_levels("AAA", frame, 27, "2w", "bullish", levels_fn=levels_fn)
    assert calls == [25]
    assert (stop.price, target.price) == (9.2, 12.0)
    stop, target = module.scenario_levels("AAA", frame, 27, "2w", "bearish", levels_fn=levels_fn)
    assert (stop.price, target.price) == (12.0, 9.2)
    one_sided = module.scenario_levels("AAA", frame, 27, "2w", "bullish",
                                       levels_fn=lambda *a: ([Level(9.0, ["EMA20"])], []))
    assert one_sided is None


def test_is_identified_matches_the_replays_clamped_stop():
    from swingbot.core.planning.builders import _clamp_stop_to_hard_cap
    module = _module()
    level = Level(95.0, ["Fib 61.8%"])
    clamped = _clamp_stop_to_hard_cap(100.0, 95.0, True)
    assert module.is_identified(NS(trigger_price=100.0, stop_loss=clamped, direction="bullish"), level) is True
    assert module.is_identified(NS(trigger_price=100.0, stop_loss=clamped - 0.01, direction="bullish"), level) is False
    assert module.is_identified(NS(trigger_price=100.0, stop_loss=None, direction="bullish"), level) is False


def test_fib_labels_and_prices():
    module = _module()
    pair = (Level(9.0, ["Fib 61.8%", "EMA20"]), Level(12.0, ["Swing high", "Rolling resistance"]))
    labels = module.fib_labels(pair)
    assert labels == {"Fib 61.8%", "Swing high"}
    candidates = [(9.0, "Fib 61.8%"), (12.0, "Swing high"), (9.1, "EMA20"), (8.0, "Fib 50.0%")]
    assert module.fib_candidate_prices(candidates, labels) == [9.0, 12.0]


def _restart_case(stop_loss_offset=0.0, levels=None):
    from swingbot.core.planning.builders import _clamp_stop_to_hard_cap
    module = _module()
    frame = path_frame(RESTART)                               # Close[25] = 14.8
    stop_level = Level(13.7, ["Fib 50.0%", "EMA20"])
    levels = levels or ([stop_level], [Level(16.0, ["Rolling resistance"])])
    plan = NS(direction="bullish", trigger_price=14.8,
              stop_loss=_clamp_stop_to_hard_cap(14.8, 13.7, True) + stop_loss_offset)
    return module.confluence_row("AAA", frame, "2w", 25, plan, NS(outcome="win", r_total=1.2),
                                 levels_fn=lambda *a: levels,
                                 candidates_fn=lambda df, h, price: [(13.75, "Fib 50.0%"), (13.6, "EMA20")])


def test_confluence_row_finds_the_fib_candidate_on_the_leg():
    row = _restart_case()
    assert (row["identified"], row["has_fib"]) == (True, True)
    assert (row["outcome"], row["r_multiple"], row["direction"]) == ("win", 1.2, "bullish")
    for divisor in (4, 6, 8):
        assert row[f"d{divisor}"] == {"has_leg": True, "fib_on_leg": True}   # 13.75 == level_500


def test_confluence_row_without_fib_source_has_no_cells():
    row = _restart_case(levels=([Level(13.7, ["EMA20"])], [Level(16.0, ["Rolling resistance"])]))
    assert (row["identified"], row["has_fib"]) == (True, False)
    assert "d6" not in row


def test_confluence_row_with_a_mismatched_stop_is_unidentified():
    row = _restart_case(stop_loss_offset=0.05)
    assert (row["identified"], row["has_fib"]) == (False, False)


def test_confluence_trades_window_and_skips():
    module = _module()
    frame = path_frame(RESTART)
    seen = {}

    def replay_fn(ticker, df, horizon_key):
        seen["last"] = str(df.index[-1].date())
        return [(20, NS(direction="bullish")), (24, NS(direction="bullish")), (25, NS(direction="bullish"))]

    def exit_fn(df, index, plan, scale_out):
        assert scale_out is True
        return NS(outcome="not_triggered" if index == 24 else "win", r_total=1.0)

    start = str(frame.index[21].date())
    end = str(frame.index[25].date())
    trades = module.confluence_trades("AAA", frame, "2w", (start, end), replay_fn=replay_fn, exit_fn=exit_fn)
    assert [index for index, _, _ in trades] == [25]           # 20 before start, 24 skipped
    assert seen["last"] == end
    for window in (("2010-01-01", "2023-12-31"), ("2015-01-01", "2026-01-02")):
        with pytest.raises(SystemExit, match="diagnostic window"):
            module.confluence_trades("AAA", frame, "2w", window, replay_fn=replay_fn, exit_fn=exit_fn)
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect the new tests to FAIL (`AttributeError`).
- [ ] **Step 3: Implement.** Add `import math` to the stdlib imports at the top, extend the `strategy_types` import to `from swingbot.core.market.strategy_types import HORIZONS, LEGACY_HORIZONS, MIN_BARS  # noqa: E402`, and add after the existing imports:

```python
from swingbot.core.backtesting.arms.confluence_engine import SKIPPED  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import (  # noqa: E402
    LEVEL_REFRESH_BARS, levels_asof, replay_scenarios)
from swingbot.core.planning.builders import _clamp_stop_to_hard_cap  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402
```

Append:

```python
FIB_FAMILY = "Fibonacci"
LEG_PRICE_KEYS = ("origin_price", "level_382", "level_500", "level_618", "end_price")
ALL_HZ = tuple(LEGACY_HORIZONS)


def bucket_bar(index, horizon_key) -> int:
    """The bar replay_scenarios built its cached level map at: the first bar of
    index's LEVEL_REFRESH_BARS bucket the replay visited (never before warm-up)."""
    return max(MIN_BARS[horizon_key], (index // LEVEL_REFRESH_BARS) * LEVEL_REFRESH_BARS)


def scenario_levels(ticker, frame, index, horizon_key, direction, *, levels_fn=levels_asof):
    """(stop-side level, target-1 level) the replay's scenario at ``index`` was
    built from: the same as-of map, re-split against Close[index] as the replay does."""
    supports, resistances = levels_fn(ticker, frame, bucket_bar(index, horizon_key), horizon_key, {})
    price = float(frame["Close"].iloc[index])
    ordered = sorted(supports + resistances, key=lambda level: level.price)
    below = [level for level in ordered if level.price < price][::-1]
    above = [level for level in ordered if level.price > price]
    if not below or not above:
        return None
    return (below[0], above[0]) if direction == "bullish" else (above[0], below[0])


def is_identified(plan, stop_level) -> bool:
    """The rebuild is right only if it reproduces the plan's own (clamped) stop."""
    if plan.stop_loss is None:
        return False
    expected = _clamp_stop_to_hard_cap(plan.trigger_price, stop_level.price, plan.direction == "bullish")
    return math.isclose(plan.stop_loss, expected, rel_tol=1e-9, abs_tol=1e-12)


def fib_labels(pair) -> set:
    return {label for level in pair for label in level.sources if strategy_family(label) == FIB_FAMILY}


def fib_candidate_prices(candidates, labels) -> list:
    return [float(price) for price, label in candidates if label in labels]


def arm4_cell(leg, prices, atr_value) -> dict:
    """Arm 4 primary: a Fibonacci candidate within 0.25 ATR of a leg price."""
    return {"has_leg": bool(np.isfinite(leg["origin_price"])),
            "fib_on_leg": any(near(price, leg[key], atr_value) for price in prices for key in LEG_PRICE_KEYS)}


def _fib_prices_at(frame, index, horizon_key, labels, candidates_fn):
    prefix = frame.iloc[:bucket_bar(index, horizon_key) + 1]
    candidates = candidates_fn(prefix, HORIZONS[horizon_key], float(prefix["Close"].iloc[-1]))
    return fib_candidate_prices(candidates, labels)


def _arm4_cells(prefix, horizon_key, direction, prices) -> dict:
    atr_value = atr_at(prefix)
    return {f"d{d}": arm4_cell(leg_at(prefix, direction, origin_strength(horizon_key, d)), prices, atr_value)
            for d in DIVISORS}


def confluence_row(ticker, frame, horizon_key, index, plan, result, *, levels_fn=levels_asof,
                   candidates_fn=collect_candidate_levels) -> dict:
    row = {"ticker": ticker, "horizon_key": horizon_key, "direction": plan.direction,
           "entry_date": str(frame.index[index].date()), "outcome": result.outcome,
           "r_multiple": result.r_total}
    pair = scenario_levels(ticker, frame, index, horizon_key, plan.direction, levels_fn=levels_fn)
    row["identified"] = pair is not None and is_identified(plan, pair[0])
    labels = fib_labels(pair) if row["identified"] else set()
    row["has_fib"] = bool(labels)
    if labels:
        prices = _fib_prices_at(frame, index, horizon_key, labels, candidates_fn)
        row.update(_arm4_cells(frame.iloc[:index + 1], horizon_key, plan.direction, prices))
    return row


def confluence_trades(ticker, frame, horizon_key, window, *, replay_fn=replay_scenarios,
                      exit_fn=simulate_exit) -> list:
    """Mirror of ConfluenceEngine.run_ticker that keeps (index, plan, result)."""
    start, end = require_diagnostic_window(window)
    out = []
    for index, plan in replay_fn(ticker, frame.loc[:end], horizon_key):
        if str(frame.index[index].date()) < start:
            continue
        result = exit_fn(frame, index, plan, scale_out=True)
        if result.outcome not in SKIPPED:
            out.append((index, plan, result))
    return out


def collect_confluence(frames, window=DIAG_WINDOW, *, horizons=ALL_HZ, replay_fn=replay_scenarios,
                       exit_fn=simulate_exit, levels_fn=levels_asof,
                       candidates_fn=collect_candidate_levels) -> list:
    require_diagnostic_window(window)
    progress, rows = Progress(len(frames) * len(horizons)), []
    for ticker, frame in sorted(frames.items()):
        for horizon_key in horizons:
            progress.tick(f"confluence {ticker} {horizon_key}")
            for index, plan, result in confluence_trades(ticker, frame, horizon_key, window,
                                                         replay_fn=replay_fn, exit_fn=exit_fn):
                rows.append(confluence_row(ticker, frame, horizon_key, index, plan, result,
                                           levels_fn=levels_fn, candidates_fn=candidates_fn))
    return rows


def _cmd_collect_confluence(args):
    require_diagnostic_window(DIAG_WINDOW)
    require_ext_cache()
    started = time.monotonic()
    frames = _load_frames(args.universe, args.tickers)
    rows = collect_confluence(frames, DIAG_WINDOW)
    _write(args.out, {"kind": "confluence", "window": DIAG_WINDOW, "tickers": sorted(frames),
                      "universe_n": len(frames), "avwap_levels_enabled": bool(config.AVWAP_LEVELS_ENABLED),
                      "rows": rows, "elapsed_s": round(time.monotonic() - started, 1)})
```

- [ ] **Step 4: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect PASS. Run `python -m radon cc -s -n C scripts/backtest/measure_fib_anchor_diagnostic.py` and expect no output.
- [ ] **Step 5: Smoke identification check (real data; counts only).** This needs the extended CSV cache, which already exists locally (`data/backtest_cache_ext/SPY.csv`). If it is missing, stop and ask; do not fetch. The window is one diagnostic-window year (2015) and one horizon. Print only counts, never pooled outcomes, so no bucket is read.

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python - <<'EOF'
import sys, time
sys.path[:0] = ["scripts/backtest", "."]
import measure_fib_anchor_diagnostic as m
from measure_fib_confluence import _load_frames
started = time.monotonic()
rows = m.collect_confluence(_load_frames(None, "SPY"), ("2015-01-01", "2015-12-31"), horizons=("4w",))
print("trades", len(rows), "unidentified", sum(not r["identified"] for r in rows),
      "with_fib", sum(r["has_fib"] for r in rows), "seconds", round(time.monotonic() - started, 1))
EOF
```

Expect `unidentified 0`. Record the seconds figure: the after-plan run uses it to size the confluence chunks. A non-zero `unidentified` means the rebuild does not reproduce the replay. Stop and report it before V124-6. Do not loosen `is_identified`.
- [ ] **Step 6: Commit.**

```bash
git add scripts/backtest/measure_fib_anchor_diagnostic.py tests/scripts/test_measure_fib_anchor_diagnostic.py
git commit -m "feat(v124): arm 4 level-map identification and the confluence collector"
```

### Task V124-6: Report, markdown tables, reproduction gate, CLI

**Files:** Modify `scripts/backtest/measure_fib_anchor_diagnostic.py`, `tests/scripts/test_measure_fib_anchor_diagnostic.py`.

**Interfaces:**
- Consumes (V124-3): `bucket`, `divisor_buckets`, `leg_arm_verdict`, `single_split_verdict`, `describe`, `quintile_key`, `reproduction`, `require_diagnostic_window`, `require_repro_window`, `EXIT_RULE`, `DIVISORS`, `PRIMARY_DIVISOR`; (V124-4/5) row shapes, `_cmd_collect_repro`, `_cmd_collect_fib`, `_cmd_collect_confluence`.
- Produces: `fib_tables(rows, direction) -> dict` (`arm1`, `arm1_described`, `arm2`, `arm2_described`, `arm3`, `arm3_described`); `confluence_tables(rows) -> dict` (`population`, `unidentified`, `fib_population_n`, `measurable`, `arm4`); `verdicts(fib, confluence) -> {"arm1".."arm4"}`; `build_report(fib_payloads, confluence_payloads, repro_payloads) -> dict` (diagnostic payloads must lie inside `DIAG_WINDOW`, repro payloads must be exactly `REPRO_WINDOW`; reproduction is computed from the repro payloads only); `render_markdown(report) -> str`; `main(argv=None) -> int` with commands `collect-repro`, `collect-fib`, `collect-confluence`, `reproduce`, `report`.

- [ ] **Step 0: Precondition** as in V124-1 Step 0.
- [ ] **Step 1: Write the failing tests.** Append:

```python
import json


DIAG = ["2015-01-01", "2025-12-31"]
REPRO = ["2010-01-01", "2023-12-31"]


def _payloads(confluence_rows=None):
    bull = group(20, 20, **GOOD) + group(12, 28)
    bear = [dict(row, direction="bearish") for row in group(5, 10)]
    fib = [{"kind": "fib", "direction": "bullish", "window": DIAG, "universe_n": 73,
            "avwap_levels_enabled": True, "rows": bull},
           {"kind": "fib", "direction": "bearish", "window": DIAG, "universe_n": 73,
            "avwap_levels_enabled": True, "rows": bear}]
    rows = confluence_rows if confluence_rows is not None else group(20, 20, **GOOD) + group(12, 28)
    confluence = [{"kind": "confluence", "window": DIAG, "tickers": ["AAA"],
                   "universe_n": 1, "avwap_levels_enabled": True, "rows": rows}]
    repro = [{"kind": "repro", "direction": "bullish", "window": REPRO, "universe_n": 73, "rows": group(20, 20)},
             {"kind": "repro", "direction": "bearish", "window": REPRO, "universe_n": 73,
              "rows": [dict(row, direction="bearish") for row in group(5, 10)]}]
    return fib, confluence, repro


REPRO_MATCH = {"bullish": {"n": 40, "win_rate": 50.0, "expectancy_r": 0.5},
               "bearish": {"n": 15, "win_rate": 33.33, "expectancy_r": 0.0}}


def test_report_verdicts_follow_the_exit_rule():
    module = _module()
    report = module.build_report(*_payloads())
    assert report["exit_rule"] == module.EXIT_RULE
    assert report["avwap_levels_enabled"] == [True]
    assert {arm: v["proceeds"] for arm, v in report["verdicts"].items()} == {
        "arm1": True, "arm2": True, "arm3": True, "arm4": True}
    assert report["fib"]["bearish"]["arm1"]["6"]["rest"]["n"] == 15        # described, not judged
    assert report["reproduction"]["bullish"]["observed"]["n"] == 40         # from the repro payload
    assert report["reproduction"]["bullish"]["matches"] is False            # 40 trades, not 815


def test_one_unidentified_confluence_trade_makes_arm4_not_measurable():
    module = _module()
    rows = group(20, 20, **GOOD) + group(12, 28)
    rows[0] = dict(rows[0], identified=False)
    report = module.build_report(*_payloads(rows))
    assert report["confluence"]["unidentified"] == 1
    assert report["verdicts"]["arm4"] == {"proceeds": False, "not_measurable": True}
    assert "not measurable with this instrument" in module.render_markdown(report)


def test_report_refuses_a_diagnostic_payload_outside_2015_2025():
    module = _module()
    fib, confluence, repro = _payloads()
    fib[0]["window"] = ["2010-01-01", "2025-12-31"]
    with pytest.raises(SystemExit, match="diagnostic window"):
        module.build_report(fib, confluence, repro)


def test_report_refuses_a_repro_payload_not_on_v103s_window():
    module = _module()
    fib, confluence, repro = _payloads()
    repro[0]["window"] = DIAG
    with pytest.raises(SystemExit, match="reproduction runs on"):
        module.build_report(fib, confluence, repro)


def test_markdown_carries_the_exit_rule_and_every_divisor():
    module = _module()
    text = module.render_markdown(module.build_report(*_payloads()))
    assert module.EXIT_RULE in text
    for divisor in (4, 6, 8):
        assert f"d={divisor} favourable" in text
    assert "Fibonacci bearish (description only)" in text


def _write_inputs(tmp_path):
    fib, confluence, repro = _payloads()
    paths = []
    for name, payload in (("bull", fib[0]), ("bear", fib[1]), ("conf", confluence[0]),
                          ("rbull", repro[0]), ("rbear", repro[1])):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        paths.append(str(path))
    return paths


def test_report_command_needs_a_note_when_the_baseline_does_not_reproduce(tmp_path):
    module = _module()
    bull, bear, conf, rbull, rbear = _write_inputs(tmp_path)
    out, md = tmp_path / "report.json", tmp_path / "report.md"
    argv = ["report", "--repro", rbull, rbear, "--fib", bull, bear, "--confluence", conf,
            "--out", str(out), "--md", str(md)]
    with pytest.raises(SystemExit, match="does not reproduce"):
        module.main(argv)
    assert not out.exists() and not md.exists()
    note = tmp_path / "note.md"
    note.write_text("difference explained", encoding="utf-8")
    assert module.main(argv + ["--reproduction-note", str(note)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["verdicts"]["arm1"]["proceeds"] is True
    assert md.read_text(encoding="utf-8").startswith("# v124")


def test_report_command_needs_no_note_when_the_baseline_reproduces(tmp_path, monkeypatch):
    module = _module()
    monkeypatch.setattr(module, "REFERENCE", REPRO_MATCH)
    bull, bear, conf, rbull, rbear = _write_inputs(tmp_path)
    out, md = tmp_path / "report.json", tmp_path / "report.md"
    assert module.main(["report", "--repro", rbull, rbear, "--fib", bull, bear, "--confluence", conf,
                        "--out", str(out), "--md", str(md)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["reproduction"]["bullish"]["matches"] is True


def test_reproduce_command_prints_only_the_baseline(tmp_path, capsys):
    module = _module()
    _, _, _, rbull, rbear = _write_inputs(tmp_path)
    assert module.main(["reproduce", "--repro", rbull, rbear]) == 0
    printed = capsys.readouterr().out
    assert '"matches": false' in printed and "arm1" not in printed
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect the new tests to FAIL (`AttributeError`).
- [ ] **Step 3: Implement.** Add `import json` to the stdlib imports and append:

```python
def _primary(row):
    return row[f"d{PRIMARY_DIVISOR}"]


def fib_tables(rows, direction) -> dict:
    rows = dir_rows(rows, direction)
    leg_atr = quintile_key(rows, lambda row: _primary(row)["leg_atr"])
    return {
        "arm1": divisor_buckets(rows, "anchored"),
        "arm1_described": {"rolling_origin_is_fractal": describe(rows, lambda row: row["anchor_fractal"]),
                           "broke_structure": describe(rows, lambda row: _primary(row)["broke_structure"]),
                           "leg_atr_quintile": describe(rows, leg_atr)},
        "arm2": divisor_buckets(rows, "zone_confluence"),
        "arm2_described": {"zone_touch": describe(rows, lambda row: _primary(row)["zone_touch"]),
                           "close_in_zone": describe(rows, lambda row: _primary(row)["close_in_zone"]),
                           "tested_ratio": describe(rows, lambda row: row["tested_ratio"]),
                           "rolling_level_confluence": describe(rows, lambda row: row["rolling_level_confluence"])},
        "arm3": bucket(rows, lambda row: row["confirm_close"]),
        "arm3_described": {"rejection_wick_half_range": describe(rows, lambda row: row["confirm_wick"])},
    }


def confluence_tables(rows) -> dict:
    unidentified = sum(not row["identified"] for row in rows)
    population = [row for row in rows if row["has_fib"]]
    return {"population": {d: pooled(dir_rows(rows, d)) for d in DIRECTIONS},
            "unidentified": unidentified, "fib_population_n": len(population),
            "measurable": bool(rows) and unidentified == 0,
            "arm4": {d: divisor_buckets(dir_rows(population, d), "fib_on_leg") for d in DIRECTIONS}}


def verdicts(fib, confluence) -> dict:
    bull = fib["bullish"]
    arm4 = (leg_arm_verdict(confluence["arm4"]["bullish"]) if confluence["measurable"]
            else {"proceeds": False, "not_measurable": True})
    return {"arm1": leg_arm_verdict(bull["arm1"]), "arm2": leg_arm_verdict(bull["arm2"]),
            "arm3": single_split_verdict(bull["arm3"]), "arm4": arm4}


def _by_direction(payloads, kind):
    found = {payload["direction"]: payload for payload in payloads}
    missing = [d for d in DIRECTIONS if d not in found]
    if missing:
        raise SystemExit(f"no {kind} payload for {', '.join(missing)}")
    return found


def reproductions(repro_payloads) -> dict:
    """Reproduction on REPRO_WINDOW only; refuses a payload from any other window."""
    for payload in repro_payloads:
        require_repro_window(payload["window"])
    found = _by_direction(repro_payloads, "collect-repro")
    return {d: reproduction(found[d]["rows"], d, found[d]["universe_n"]) for d in DIRECTIONS}


def build_report(fib_payloads, confluence_payloads, repro_payloads) -> dict:
    for payload in fib_payloads + confluence_payloads:
        require_diagnostic_window(tuple(payload["window"]))
    by_direction = _by_direction(fib_payloads, "collect-fib")
    fib = {d: fib_tables(by_direction[d]["rows"], d) for d in DIRECTIONS}
    confluence = confluence_tables([row for payload in confluence_payloads for row in payload["rows"]])
    return {"window": list(DIAG_WINDOW), "repro_window": list(REPRO_WINDOW), "exit_rule": EXIT_RULE,
            "avwap_levels_enabled": sorted({p["avwap_levels_enabled"] for p in fib_payloads + confluence_payloads}),
            "reproduction": reproductions(repro_payloads),
            "fib": fib, "confluence": confluence, "verdicts": verdicts(fib, confluence)}


# --- markdown ---------------------------------------------------------------

ARM_SECTIONS = (("arm1", "Arm 1 anchored entry", True), ("arm2", "Arm 2 zone + confluence", True),
                ("arm3", "Arm 3 confirmation", False))


def _stats_line(name, stats) -> str:
    wr = "n/a" if stats["win_rate"] is None else f"{stats['win_rate']:.2f}%"
    exp = "n/a" if stats["expectancy_r"] is None else f"{stats['expectancy_r']:+.3f}"
    return f"| {name} | {stats['n']} | {wr} | {exp} |"


def _table(title, named_stats) -> list:
    lines = [f"#### {title}", "", "| bucket | N | WR | ExpR |", "|---|---|---|---|"]
    return lines + [_stats_line(name, stats) for name, stats in named_stats.items()] + [""]


def _divisor_rows(by_divisor) -> dict:
    return {f"d={d} {side}": by_divisor[str(d)][side] for d in DIVISORS for side in ("favourable", "rest")}


def _arm_lines(tables, key, title, by_divisor) -> list:
    primary = _divisor_rows(tables[key]) if by_divisor else tables[key]
    lines = _table(f"{title} -- primary split", primary)
    for name, groups in tables[f"{key}_described"].items():
        lines += _table(f"{title} -- described: {name}", groups)
    return lines


def _reproduction_lines(reproductions) -> list:
    lines = ["## Baseline reproduction (v103 reference arm, b=0, on 2010-01-01..2023-12-31)", "",
             "| direction | N | WR | ExpR | universe | reference N / WR / ExpR / universe | matches |",
             "|---|---|---|---|---|---|---|"]
    for direction, item in reproductions.items():
        obs, ref = item["observed"], item["reference"]
        wr = "n/a" if obs["win_rate"] is None else f"{obs['win_rate']:.2f}%"
        exp = "n/a" if obs["expectancy_r"] is None else f"{obs['expectancy_r']:+.4f}"
        lines.append(f"| {direction} | {obs['n']} | {wr} | {exp} | {item['universe_n']} | "
                     f"{ref['n']} / {ref['win_rate']}% / {ref['expectancy_r']:+.4f} / "
                     f"{item['reference_universe_n']} | {item['matches']} |")
    return lines + [""]


def _verdict_lines(verdict_map) -> list:
    lines = ["## Verdicts (bullish only)", "", "| arm | primary passes | WR-sign divisors | proceeds |",
             "|---|---|---|---|"]
    for arm, item in verdict_map.items():
        primary = "not measurable" if item.get("not_measurable") else item["primary_passes"]
        lines.append(f"| {arm} | {primary} | {item.get('wr_sign_divisors', '-')} | {item['proceeds']} |")
    return lines + [""]


def _confluence_lines(confluence) -> list:
    lines = ["## Confluence (arm 4)", ""] + _table("Whole confluence population (described)",
                                                   confluence["population"])
    lines += [f"Unidentified trades: {confluence['unidentified']}. "
              f"Trades with a Fibonacci-family source: {confluence['fib_population_n']}.", ""]
    if not confluence["measurable"]:
        return lines + ["Arm 4 is **not measurable with this instrument**.", ""]
    for direction in DIRECTIONS:
        lines += _table(f"Arm 4 {direction} -- primary split", _divisor_rows(confluence["arm4"][direction]))
    return lines


def render_markdown(report) -> str:
    start, end = report["window"]
    lines = ["# v124 Fibonacci anchor diagnostic -- generated tables", "",
             f"Diagnostic window {start}..{end} (entries and features; 2026 is the holdout). "
             f"AVWAP_LEVELS_ENABLED: {report['avwap_levels_enabled']}.", "",
             "## Exit rule (fixed in the spec)", "", f"> {report['exit_rule']}", ""]
    lines += _reproduction_lines(report["reproduction"]) + _verdict_lines(report["verdicts"])
    for direction in DIRECTIONS:
        suffix = " (description only)" if direction == "bearish" else ""
        lines += [f"## Fibonacci {direction}{suffix}", ""]
        for key, title, by_divisor in ARM_SECTIONS:
            lines += _arm_lines(report["fib"][direction], key, title, by_divisor)
    lines += _confluence_lines(report["confluence"])
    return "\n".join(lines) + "\n"


# --- CLI ----------------------------------------------------------------------

def _load(paths) -> list:
    return [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]


def _cmd_reproduce(args):
    print(json.dumps(reproductions(_load(args.repro)), indent=1), flush=True)


def _cmd_report(args):
    report = build_report(_load(args.fib), _load(args.confluence), _load(args.repro))
    note = args.reproduction_note
    if not report["reproduction"]["bullish"]["matches"] and not (note and Path(note).is_file()):
        raise SystemExit("bullish baseline does not reproduce v103 on 2010-01-01..2023-12-31 "
                         "(N=815, WR 36.81%, ExpR +0.2219, universe 73): "
                         "explain the difference in a committed note, then pass --reproduction-note <path>")
    report["reproduction_note"] = note
    _write(args.out, report)
    Path(args.md).write_text(render_markdown(report), encoding="utf-8")


def _parser():
    parser = argparse.ArgumentParser(description="v124 Fibonacci impulse-leg anchor diagnostic (2015-2025)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    repro = sub.add_parser("collect-repro")
    fib = sub.add_parser("collect-fib")
    for command in (repro, fib):
        command.add_argument("--direction", required=True, choices=DIRECTIONS)
    confluence = sub.add_parser("collect-confluence")
    for command in (repro, fib, confluence):
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated subset: chunks and smoke runs")
    reproduce = sub.add_parser("reproduce")
    reproduce.add_argument("--repro", nargs=2, required=True)
    report = sub.add_parser("report")
    report.add_argument("--repro", nargs=2, required=True)
    report.add_argument("--fib", nargs=2, required=True)
    report.add_argument("--confluence", nargs="+", required=True)
    report.add_argument("--out", required=True)
    report.add_argument("--md", required=True)
    report.add_argument("--reproduction-note")
    return parser


COMMANDS = {"collect-repro": _cmd_collect_repro, "collect-fib": _cmd_collect_fib,
            "collect-confluence": _cmd_collect_confluence,
            "reproduce": _cmd_reproduce, "report": _cmd_report}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v124 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect PASS. Run `python -m radon cc -s -n C scripts/backtest/measure_fib_anchor_diagnostic.py tests/scripts/test_measure_fib_anchor_diagnostic.py` and expect no output. Run `python scripts/backtest/measure_fib_anchor_diagnostic.py --help` and expect the five commands.
- [ ] **Step 5: Commit.**

```bash
git add scripts/backtest/measure_fib_anchor_diagnostic.py tests/scripts/test_measure_fib_anchor_diagnostic.py
git commit -m "feat(v124): diagnostic report, markdown tables and reproduction gate"
```

# Phase 3 — Verification

### Task V124-7: Lookahead review, complexity, full suite

**Files:** None created. Fixes only if a check fails; each fix goes in its own commit.

- [ ] **Step 1: `no-lookahead` review.** Invoke the `no-lookahead` skill on `swingbot/core/market/fib_leg.py` and on the script's feature code (`rolling_anchor`, `anchor_is_fractal`, `fib_trade_features`, `scenario_levels`, `bucket_bar`, `_fib_prices_at`, `_arm4_cells`). Confirm that every read is bounded by `iloc[:t+1]` or by the bucket bar `<= t`; that pivot lag lives only in `structure.py`; and that `o.prior` positions used for `broke_structure` are `< origin`, so they are confirmed by `t`. Write down any finding and fix it test-first before Step 2.
- [ ] **Step 2: Complexity.** `python -m radon cc -s -n C swingbot/core/market/fib_leg.py scripts/backtest/measure_fib_anchor_diagnostic.py tests/market/test_fib_leg.py tests/market/fib_leg_fixtures.py tests/scripts/test_measure_fib_anchor_diagnostic.py`. Expect no output.
- [ ] **Step 3: Scope check.** `git diff --stat main...HEAD` lists only the five files in the file map. `git grep -n "fib_leg" -- swingbot bot.py admin_ui.py` hits only `swingbot/core/market/fib_leg.py`. `VERSION.json` is unchanged (`Bump: none`).
- [ ] **Step 4: Full suite, once.** Dispatch the `test-runner` subagent for `python scripts/dev/testrun.py full`, with the worktree named. Green means `0 failed` and `0 xfailed`. A changed pass count alone is not a failure (`testing-cost.md`).
- [ ] **Step 5: Hand back** to the controller for the whole-branch review and the merge. The measurement run happens after the merge (below), not in this task.
