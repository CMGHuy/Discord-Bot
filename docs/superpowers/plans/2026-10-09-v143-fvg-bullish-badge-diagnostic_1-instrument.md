# v143 FVG (bullish) badge diagnostic: Implementation Plan, part 1 — the instrument

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Header, Global Constraints, Frozen readings, Review Focus and Parallelisation live in [`_0-index`](2026-10-09-v143-fvg-bullish-badge-diagnostic_0-index.md); every task here implicitly includes them. Work only in the worktree `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v143-fvg-bullish-badge-diagnostic`.

**Spec:** [`docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md`](../specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md)

# Phase 1 — The module `swingbot/core/backtesting/fvg_diagnostic.py`

**Sequential throughout:** all four tasks edit the same file and each consumes the previous task's symbols.

Every code block in this part was assembled into one module and run against its tests before the plan was written (52 tests across the plan's six test files passed; radon's worst score is 12; pyflakes and pycodestyle clean). Type it as printed.

### Task V143-1: Worktree, features, gap matching, replay quality, import guard

**Files:**
- Create: `swingbot/core/backtesting/fvg_diagnostic.py`
- Test: `tests/backtesting/test_fvg_diagnostic_features.py`
- Test: `tests/backtesting/test_fvg_diagnostic_import_guard.py`

**Interfaces:**
- Consumes (existing): `fvg.find_fair_value_gaps_detailed(df) -> list[dict]` (keys `bottom`, `top`, `mid`, `bar_index`, `direction`), `fvg.is_displacement_gap(df, gap, k) -> bool`, `fvg.DEFAULT_DISPLACEMENT_ATR_K` (1.5), `indicators.atr(df, period) -> Series`, `earnings_calendar.next_reaction_distance(asof_pos, reaction_positions) -> int | None`, `levels.count_confirming_strategies(df, h, current_price, target_price, tolerance_pct) -> (count, families)`, `strategy_types.HORIZONS[horizon_key]`, `quality.score_plan(*, direction, regime, htf_bias, confluence_count, volume_ratio, atr_pct, trigger_distance_pct, badge_status, rs_percentile=None, breadth=None, ...) -> QualityResult` (`.score`), `quality.atr_percentile(df) -> float | None`, `scanning.regime.get_htf_bias(df, horizon_key) -> dict | None` (key `bias`; reads `config.HTF_CONFLUENCE_ENABLED`). Test helpers: `tests.market.fvg_frames` (`FLAT`, `STRONG_BULL`, `WEAK_BULL`, `BULL_THIRD`, `bar_frame`), `tests.planning.test_exit_sim_single._plan(**kw) -> TradePlanV2`.
- Produces: constants `STRATEGY`, `TRAIN`, `SMA_BARS`, `ROLE_TARGET` / `ROLE_STOP` / `ROLE_NONE`, `GAP_FEATURES`; the frozen dataclass `SignalContext(target, target_sources, stop, stop_sources, tolerance_pct, map_bar=None, earnings_distance=None, confluence_count=None)` (the scenario's clustered target and stop levels with their source labels, the live confluence tolerance in percent, the bar the replay's level map was built on, and the driver's two per-trade readings); functions `atr14_at(df, i) -> float | None`, `match_gap(gaps, ctx) -> (gap | None, role)` (index, frozen reading 4), `gap_is_open(gaps, gap) -> bool`, `map_gaps(df, i, ctx) -> list` (the finder on the window ending at `min(ctx.map_bar, i)`), `gap_features(df, i, gap, atr_val) -> dict`, `entry_reference(plan) -> float`, `trend_aligned(df, i, direction) -> bool | None`, `target_confluence_count(df, i, horizon_key, target, tolerance_pct) -> int`, `volume_ratio(window) -> float | None`, `quality_inputs(df, i, plan, confluence_count) -> dict`, `replay_quality(df, i, plan, confluence_count) -> int | None`, `plan_features(df, i, plan, atr_val, confluence_count=None) -> dict`, `earnings_distance(signal_pos, reaction_positions) -> int | None`, `features(df, i, plan, ctx) -> dict`. The `features` dict has exactly these keys: `fvg_role`, `gap_age`, `gap_height_atr`, `displacement`, `gap_open`, `stop_atr`, `quality`, `trend_aligned`, `volatility`, `earnings_distance`; `None` means not computable. `quality` is the replay quality score, and is `None` whenever `ctx.confluence_count` is `None`.

- [ ] **Step 0: Create the worktree and load the lookahead rules**

Invoke the `worktree-lifecycle` skill, then from the main tree:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot worktree add -b 2026-10-09-v143-fvg-bullish-badge-diagnostic .claude/worktrees/2026-10-09-v143-fvg-bullish-badge-diagnostic main
```

Invoke the `no-lookahead` skill before writing any code in this task.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_fvg_diagnostic_features.py`:

```python
"""v143 features: each value at a known bar, the gap match and its tolerance,
and that no feature reads a bar after the signal bar."""
import pytest

from swingbot import config
from swingbot.core.backtesting import fvg_diagnostic as fd
from swingbot.core.market.indicators import atr
from swingbot.core.planning.quality import atr_percentile, score_plan
from tests.market.fvg_frames import BULL_THIRD, FLAT, STRONG_BULL, WEAK_BULL, bar_frame
from tests.planning.test_exit_sim_single import _plan

ABOVE = (104.5, 105.5, 103.5, 104.5)     # stays above the gap top (101.5)
LATER = (104.5, 130.0, 80.0, 104.5)      # a wild bar AFTER the signal bar


def gap_frame(flat_bars=20, middle=STRONG_BULL, after=5):
    """flat bars, a middle candle, the third candle that opens a bullish gap
    101.0..101.5 (mid 101.25) at bar flat_bars + 1, then `after` quiet bars."""
    return bar_frame([FLAT] * flat_bars + [middle, BULL_THIRD] + [ABOVE] * after)


def ctx(target=101.25, stop=107.0, target_sources=(fd.STRATEGY, "EMA 50"),
        stop_sources=("Swing High",), tolerance_pct=5.0, **kw):
    """The scenario behind plan(): a bearish trade aimed at the gap's level."""
    return fd.SignalContext(target=target, target_sources=target_sources, stop=stop,
                            stop_sources=stop_sources, tolerance_pct=tolerance_pct, **kw)


def plan(**kw):
    base = dict(source="confluence", strategy=fd.STRATEGY, direction="bearish",
                trigger_price=104.5, stop_loss=107.0, tp1=101.25, quality_score=60)
    base.update(kw)
    return _plan(**base)


def test_gap_features_at_a_known_bar():
    df = gap_frame()
    i = len(df) - 1                                  # 26; the gap formed at bar 21
    atr_i = float(atr(df, 14).iloc[-1])
    out = fd.features(df, i, plan(), ctx())
    assert out["fvg_role"] == "target"
    assert out["gap_age"] == 5
    assert out["gap_open"] is True
    assert out["gap_height_atr"] == pytest.approx(0.5 / atr_i)
    assert out["displacement"] is True
    assert out["stop_atr"] == pytest.approx(2.5 / atr_i)
    assert out["quality"] is None                    # no confluence count was given
    assert out["volatility"] == pytest.approx(atr_i / 104.5)
    assert out["trend_aligned"] is None              # 27 bars: no SMA200
    assert out["earnings_distance"] is None


def test_a_weak_middle_candle_is_not_displacement():
    df = gap_frame(middle=WEAK_BULL)
    assert fd.features(df, len(df) - 1, plan(), ctx())["displacement"] is False


def test_trend_alignment_needs_200_bars_and_follows_direction():
    df = gap_frame(flat_bars=220)
    i = len(df) - 1
    assert fd.trend_aligned(df, i, "bullish") is True     # close 104.5 > SMA200 ~100.1
    assert fd.trend_aligned(df, i, "bearish") is False
    assert fd.trend_aligned(df, 198, "bullish") is None   # 199 bars


def test_no_feature_changes_when_later_bars_are_removed():
    full = bar_frame([FLAT] * 220 + [STRONG_BULL, BULL_THIRD] + [ABOVE] * 5 + [LATER] * 30)
    i = 226
    known = ctx(map_bar=224, earnings_distance=7, confluence_count=3)
    for p in (plan(), plan(direction="bullish", stop_loss=101.2, tp1=112.0)):
        out = fd.features(full, i, p, known)
        assert out == fd.features(full.iloc[:i + 1], i, p, known)
        assert out["fvg_role"] == "target" and out["quality"] is not None


GAPS = [{"mid": 101.25, "direction": "bullish", "bar_index": 21},
        {"mid": 99.0, "direction": "bullish", "bar_index": 9},
        {"mid": 104.0, "direction": "bearish", "bar_index": 30}]
FVG = (fd.STRATEGY,)


def test_match_uses_the_level_fvg_is_a_source_of_target_before_stop():
    both = ctx(target=101.0, target_sources=FVG, stop=99.5, stop_sources=FVG)
    assert fd.match_gap(GAPS, both) == (GAPS[0], "target")
    stop_only = ctx(target=101.0, target_sources=("EMA 50",), stop=99.5, stop_sources=FVG)
    assert fd.match_gap(GAPS, stop_only) == (GAPS[1], "stop")       # 101.25 is nearer the target, but
    #                                                                 FVG is not a source of the target


def test_match_tolerance_is_a_percent_of_the_level_and_inclusive():
    at_edge = ctx(target=100.0, target_sources=FVG, tolerance_pct=1.25)    # 101.25 is 1.25% away
    assert fd.match_gap(GAPS[:1], at_edge) == (GAPS[0], "target")
    just_past = ctx(target=100.0, target_sources=FVG, tolerance_pct=1.24)
    assert fd.match_gap(GAPS[:1], just_past) == (None, "unidentified")


def test_match_unidentified_paths():
    no_source = ctx(target_sources=("EMA 50",), stop_sources=("Swing High",))
    assert fd.match_gap(GAPS, no_source) == (None, "unidentified")
    bearish_only = ctx(target=104.0, target_sources=FVG)
    assert fd.match_gap(GAPS[2:], bearish_only) == (None, "unidentified")   # bearish gap ignored
    assert fd.match_gap([], ctx()) == (None, "unidentified")
    assert fd.match_gap(GAPS, ctx(target=None, target_sources=FVG)) == (None, "unidentified")
    falls_through = ctx(target=150.0, target_sources=FVG, stop=99.0, stop_sources=FVG)
    assert fd.match_gap(GAPS, falls_through) == (GAPS[1], "stop")   # nothing near the target


def test_unidentified_trade_has_no_gap_features_but_keeps_the_plan_features():
    df = gap_frame()
    out = fd.features(df, len(df) - 1, plan(), ctx(target_sources=("EMA 50",)))
    assert out["fvg_role"] == "unidentified"
    assert [out[k] for k in fd.GAP_FEATURES] == [None] * 4
    assert out["stop_atr"] is not None and out["volatility"] is not None


DIP = (104.5, 105.0, 101.2, 104.0)       # trades back into the gap (top 101.5): filled


def test_the_gap_is_looked_up_on_the_map_bar_and_open_is_read_at_the_signal_bar():
    # gap forms at bar 21; the map was built at bar 23; bar 25 fills the gap; signal at bar 27
    df = bar_frame([FLAT] * 20 + [STRONG_BULL, BULL_THIRD, ABOVE, ABOVE, ABOVE, DIP, ABOVE, ABOVE])
    i = len(df) - 1
    stale = fd.features(df, i, plan(), ctx(map_bar=23))
    assert (stale["fvg_role"], stale["gap_open"], stale["gap_age"]) == ("target", False, 6)
    atr_i = float(atr(df, 14).iloc[-1])
    assert stale["gap_height_atr"] == pytest.approx(0.5 / atr_i)     # ATR14 at the SIGNAL bar
    assert stale["displacement"] is True
    fresh = fd.features(df, i, plan(), ctx(map_bar=None))            # a map built at the signal bar
    assert fresh["fvg_role"] == "unidentified" and fresh["gap_open"] is None
    assert fd.features(df, 24, plan(), ctx(map_bar=23))["gap_open"] is True    # before the fill


def test_the_map_bar_is_never_read_past_the_signal_bar():
    df = bar_frame([FLAT] * 20 + [STRONG_BULL, BULL_THIRD, ABOVE, ABOVE])
    late_map = ctx(map_bar=23)
    assert fd.map_gaps(df, 20, late_map) == fd.map_gaps(df.iloc[:21], 20, late_map) == []
    assert fd.features(df, 20, plan(), late_map)["fvg_role"] == "unidentified"


def test_gap_is_open_needs_the_same_bar_and_direction():
    gap = {"bar_index": 21, "direction": "bullish"}
    assert fd.gap_is_open([{"bar_index": 21, "direction": "bullish"}], gap)
    assert not fd.gap_is_open([{"bar_index": 21, "direction": "bearish"}], gap)
    assert not fd.gap_is_open([{"bar_index": 22, "direction": "bullish"}], gap)


def test_the_stop_role():
    df = gap_frame()
    scenario = ctx(target=112.0, target_sources=("EMA 50",), stop=101.2, stop_sources=FVG)
    out = fd.features(df, len(df) - 1,
                      plan(direction="bullish", stop_loss=101.2, tp1=112.0), scenario)
    assert out["fvg_role"] == "stop" and out["gap_age"] == 5


def test_replay_quality_scores_the_causal_inputs_with_the_live_scorer(monkeypatch):
    monkeypatch.setattr(config, "HTF_CONFLUENCE_ENABLED", True)
    df = gap_frame(flat_bars=220)
    i = len(df) - 1
    inputs = fd.quality_inputs(df, i, plan(), 3)
    assert inputs == {"regime": None, "htf_bias": "bullish", "confluence_count": 3,
                      "volume_ratio": 1.0, "atr_pct": atr_percentile(df),
                      "trigger_distance_pct": 0.0, "rs_percentile": None, "breadth": None}
    expected = score_plan(direction="bearish", badge_status="WEAK", **inputs).score
    assert fd.replay_quality(df, i, plan(), 3) == expected
    assert fd.features(df, i, plan(), ctx(confluence_count=3))["quality"] == expected


def test_replay_quality_moves_with_its_inputs_and_is_never_made_up(monkeypatch):
    monkeypatch.setattr(config, "HTF_CONFLUENCE_ENABLED", True)
    df = gap_frame(flat_bars=220)
    i = len(df) - 1
    base = fd.replay_quality(df, i, plan(), 3)
    assert fd.replay_quality(df, i, plan(), None) is None
    assert fd.replay_quality(df, i, plan(), 4) > base > fd.replay_quality(df, i, plan(), 1)
    aligned = plan(direction="bullish", stop_loss=101.2, tp1=112.0)   # with the 50-bar EMA bias
    assert fd.replay_quality(df, i, aligned, 3) > base
    assert fd.replay_quality(df, i, plan(trigger_price=110.0), 3) < base   # 5% from the close


def test_volume_ratio_needs_twenty_bars():
    df = gap_frame()
    assert fd.volume_ratio(df.iloc[:19]) is None
    assert fd.volume_ratio(df) == 1.0
    loud = df.copy()
    loud.iloc[-1, loud.columns.get_loc("Volume")] = 3_000_000.0
    assert fd.volume_ratio(loud) == pytest.approx(3.0 / 1.1)   # 20-bar mean is 1.1M


def test_quality_inputs_and_confluence_count_ignore_later_bars(monkeypatch):
    monkeypatch.setattr(config, "HTF_CONFLUENCE_ENABLED", True)
    full = bar_frame([FLAT] * 220 + [STRONG_BULL, BULL_THIRD] + [ABOVE] * 5 + [LATER] * 30)
    i = 226
    full.loc[full.index[i + 1:], "Volume"] = 9_000_000.0
    cut = full.iloc[:i + 1]
    assert fd.quality_inputs(full, i, plan(), 3) == fd.quality_inputs(cut, i, plan(), 3)
    count = fd.target_confluence_count(full, i, "2w", 101.25, 2.0)
    assert count == fd.target_confluence_count(cut, i, "2w", 101.25, 2.0)
    assert count >= 1                                    # the gap itself is a level there
    assert fd.target_confluence_count(full, i, "2w", None, 2.0) == 0


def test_earnings_distance_uses_the_covered_span():
    assert fd.earnings_distance(10, [5, 20, 40]) == 10
    assert fd.earnings_distance(20, [5, 20, 40]) == 0
    assert fd.earnings_distance(4, [5, 20, 40]) is None      # before the first record
    assert fd.earnings_distance(41, [5, 20, 40]) is None     # after the last
    assert fd.earnings_distance(10, []) is None
    assert fd.earnings_distance(None, [5]) is None
```

Create `tests/backtesting/test_fvg_diagnostic_import_guard.py`:

```python
"""v143: the diagnostic is research tooling. Nothing under swingbot/, and
neither entry point, may import it (no research code in the live path)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = "swingbot.core.backtesting.fvg_diagnostic"


def imported_names(text: str) -> set:
    """Every dotted module name an import statement can bind, including
    ``from pkg import mod`` as ``pkg.mod``."""
    names = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_the_guard_sees_both_import_forms():
    assert MODULE in imported_names("from swingbot.core.backtesting import fvg_diagnostic")
    assert MODULE in imported_names("import swingbot.core.backtesting.fvg_diagnostic as fd")
    assert MODULE not in imported_names("from swingbot.core.market import fvg")


def test_no_live_path_imports_the_diagnostic():
    live = sorted((ROOT / "swingbot").rglob("*.py")) + [ROOT / "bot.py", ROOT / "admin_ui.py"]
    offenders = [path.relative_to(ROOT).as_posix() for path in live
                 if MODULE in imported_names(path.read_text(encoding="utf-8"))]
    assert offenders == []
```

- [ ] **Step 2: Run the feature tests to verify they fail**

Run: `python -m pytest tests/backtesting/test_fvg_diagnostic_features.py -q -x`
Expected: a collection error, `ImportError: cannot import name 'fvg_diagnostic' from 'swingbot.core.backtesting'`.

- [ ] **Step 3: Create the module**

Create `swingbot/core/backtesting/fvg_diagnostic.py`:

```python
"""v143 FVG (bullish) badge diagnostic: the pure logic.

Research tooling. Nothing under swingbot/ imports this module (pinned by
tests/backtesting/test_fvg_diagnostic_import_guard.py); the one caller is
scripts/backtest/measure_fvg_bullish_diagnostic.py.

NO LOOKAHEAD: every feature reads df.iloc[:i + 1] only, i the signal bar.
Only `outcome` walks forward, and it is the thing being measured.

Spec: docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md
"""
from __future__ import annotations

import dataclasses
import math

from swingbot.core.market import fvg, levels
from swingbot.core.market.earnings_calendar import next_reaction_distance
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.quality import atr_percentile, score_plan
from swingbot.core.scanning.regime import get_htf_bias

STRATEGY = "FVG (bullish)"
TRAIN = ("2020-01-01", "2023-12-31")
SMA_BARS = 200
ROLE_TARGET, ROLE_STOP, ROLE_NONE = "target", "stop", "unidentified"
GAP_FEATURES = ("gap_age", "gap_height_atr", "displacement", "gap_open")


# --- features (window = df.iloc[:i + 1] only) --------------------------------

@dataclasses.dataclass(frozen=True)
class SignalContext:
    """What the replay knew about one plan at its signal bar, beyond the plan:
    the scenario's own clustered target and stop levels with the sources
    behind each (levels.Scenario.take_profit / target_sources / stop_loss /
    stop_sources, captured at plan build), the live confluence tolerance in
    percent, the bar the replay's cached level map was built on (never later
    than the signal bar; None = the signal bar), and the two per-trade
    readings the driver computes."""
    target: float | None
    target_sources: tuple
    stop: float | None
    stop_sources: tuple
    tolerance_pct: float
    map_bar: int | None = None
    earnings_distance: int | None = None
    confluence_count: int | None = None


def atr14_at(df, i) -> float | None:
    """ATR14 at the signal bar, or None when it is not a positive number."""
    value = float(atr(df.iloc[:i + 1], 14).iloc[-1])
    return value if math.isfinite(value) and value > 0 else None


def _nearest(gaps, level, tolerance_pct):
    """The gap whose mid is nearest `level`, when it lies within
    `tolerance_pct` percent of the level -- the comparison
    levels.count_confirming_strategies makes."""
    if not level or level <= 0:
        return None
    best = min(gaps, key=lambda gap: abs(gap["mid"] - level), default=None)
    if best is None or abs(best["mid"] - level) / level * 100 > tolerance_pct:
        return None
    return best


def match_gap(gaps, ctx) -> tuple:
    """(gap, role): the unfilled BULLISH gap that made FVG a source of this
    plan. The scan labels a plan from the sources clustered into its
    scenario's target level, then its stop level, so a level is tried only
    when "FVG (bullish)" is among its sources: target first, then stop. The
    gap is the one whose mid is nearest that level, within the confluence
    tolerance of it. Otherwise (None, "unidentified")."""
    bullish = [gap for gap in gaps if gap["direction"] == "bullish"]
    for level, sources, role in ((ctx.target, ctx.target_sources, ROLE_TARGET),
                                 (ctx.stop, ctx.stop_sources, ROLE_STOP)):
        if STRATEGY not in sources:
            continue
        gap = _nearest(bullish, level, ctx.tolerance_pct)
        if gap is not None:
            return gap, role
    return None, ROLE_NONE


def gap_is_open(gaps, gap) -> bool:
    """True when `gaps` still holds the same gap: same formation bar, same
    direction."""
    return any(g["bar_index"] == gap["bar_index"] and g["direction"] == gap["direction"]
               for g in gaps)


def gap_features(df, i, gap, atr_val) -> dict:
    """Features 1-3 and 9 for an identified gap. Age, height and displacement
    are read at the signal bar; `gap_open` is whether the finder still
    returns the gap on bars <= i."""
    window = df.iloc[:i + 1]
    return {
        "gap_age": int(i - gap["bar_index"]),
        "gap_height_atr": (gap["top"] - gap["bottom"]) / atr_val if atr_val else None,
        "displacement": bool(fvg.is_displacement_gap(
            window, gap, fvg.DEFAULT_DISPLACEMENT_ATR_K)),
        "gap_open": gap_is_open(fvg.find_fair_value_gaps_detailed(window), gap),
    }


def entry_reference(plan) -> float:
    """The price 1R is measured from (acceptance.arm_trade_from_plan's rule)."""
    return plan.entry_price if plan.entry_price is not None else plan.trigger_price


def trend_aligned(df, i, direction) -> bool | None:
    """close > SMA200 for a bullish plan, close < SMA200 for a bearish one."""
    closes = df["Close"].values[:i + 1]
    if len(closes) < SMA_BARS:
        return None
    sma, close = float(closes[-SMA_BARS:].mean()), float(closes[-1])
    return close > sma if direction == "bullish" else close < sma


def target_confluence_count(df, i, horizon_key, target, tolerance_pct) -> int:
    """Strategy families whose own level lies within `tolerance_pct` of the
    scenario's target, on bars <= i: the number the live scan stores as
    item.target_confluence[0] (scanning/analyze.py). 0 without a target."""
    window = df.iloc[:i + 1]
    close = float(window["Close"].iloc[-1])
    return levels.count_confirming_strategies(
        window, HORIZONS[horizon_key], close, target, tolerance_pct=tolerance_pct)[0]


def volume_ratio(window) -> float | None:
    """Last bar's volume over its 20-bar mean, as _build_quality_inputs has it."""
    if len(window) < 20:
        return None
    average = window["Volume"].rolling(20).mean().iloc[-1]
    return float(window["Volume"].iloc[-1] / average) if average else None


def quality_inputs(df, i, plan, confluence_count) -> dict:
    """score_plan's inputs, built the way scanning.analyze._build_quality_inputs
    builds them, from bars <= i of this ticker only. Market regime,
    relative-strength percentile and breadth need the whole market at that
    date and stay None (the scorer's neutral defaults)."""
    window = df.iloc[:i + 1]
    close = float(window["Close"].iloc[-1])
    bias = get_htf_bias(window, plan.horizon_key)
    return {
        "regime": None,
        "htf_bias": bias["bias"] if bias else None,
        "confluence_count": confluence_count,
        "volume_ratio": volume_ratio(window),
        "atr_pct": atr_percentile(window),
        "trigger_distance_pct": abs(plan.trigger_price - close) / close * 100,
        "rs_percentile": None,
        "breadth": None,
    }


def replay_quality(df, i, plan, confluence_count) -> int | None:
    """The live scorer on the causal inputs: a REPLAY quality score, not the
    live one. None without a confluence count; one is never made up."""
    if confluence_count is None:
        return None
    inputs = quality_inputs(df, i, plan, confluence_count)
    return score_plan(direction=plan.direction, badge_status=plan.badge, **inputs).score


def plan_features(df, i, plan, atr_val, confluence_count=None) -> dict:
    """Features 4-7. An unusable ATR14 leaves 4 and 7 not computable."""
    close = float(df["Close"].values[i])
    has_atr = atr_val is not None
    return {
        "stop_atr": abs(entry_reference(plan) - plan.stop_loss) / atr_val if has_atr else None,
        "quality": replay_quality(df, i, plan, confluence_count),
        "trend_aligned": trend_aligned(df, i, plan.direction),
        "volatility": atr_val / close if has_atr and close > 0 else None,
    }


def earnings_distance(signal_pos, reaction_positions) -> int | None:
    """Sessions to the next earnings reaction, v82's exposure definition:
    None unless the signal sits inside the ticker's covered span."""
    if signal_pos is None or not reaction_positions:
        return None
    if not reaction_positions[0] <= signal_pos <= reaction_positions[-1]:
        return None
    return next_reaction_distance(signal_pos, reaction_positions)


def map_gaps(df, i, ctx) -> list:
    """The finder's gaps on the window the level map was built on. The replay
    reuses one map for up to LEVEL_REFRESH_BARS bars, so the gap behind a
    level's FVG source is looked up where the map saw it -- never past bar i."""
    map_bar = i if ctx.map_bar is None else min(ctx.map_bar, i)
    return fvg.find_fair_value_gaps_detailed(df.iloc[:map_bar + 1])


def features(df, i, plan, ctx) -> dict:
    """All nine features plus fvg_role, from bars <= i. None = not computable."""
    atr_val = atr14_at(df, i)
    gap, role = match_gap(map_gaps(df, i, ctx), ctx)
    out = {"fvg_role": role, **dict.fromkeys(GAP_FEATURES)}
    if gap is not None:
        out.update(gap_features(df, i, gap, atr_val))
    out.update(plan_features(df, i, plan, atr_val, ctx.confluence_count))
    out["earnings_distance"] = ctx.earnings_distance
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_fvg_diagnostic_features.py`
Expected: 17 passed, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_fvg_diagnostic_import_guard.py`
Expected: 2 passed, 0 failed.

- [ ] **Step 5: Check complexity**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/fvg_diagnostic.py tests/backtesting/test_fvg_diagnostic_features.py`
Expected: one line, `test_gap_features_at_a_known_bar - C (11)`. Nothing at 15 or above.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/fvg_diagnostic.py tests/backtesting/test_fvg_diagnostic_features.py tests/backtesting/test_fvg_diagnostic_import_guard.py
git commit -m "feat(v143): FVG diagnostic features, map-bar gap matching, replay quality score (V143-1)"
```

### Task V143-2: Geometry copies and the trade row

**Files:**
- Modify: `swingbot/core/backtesting/fvg_diagnostic.py` (import block; append one section)
- Test: `tests/backtesting/test_fvg_diagnostic_outcomes.py`

**Interfaces:**
- Consumes: V143-1's `entry_reference(plan)`, `SignalContext` and `features(df, i, plan, ctx)`. Existing: `exit_sim.simulate_exit(df, signal_index, plan, *, scale_out=False, max_holding_days=None) -> ExitResult` (fields `outcome`, `r_total`, `legs`; each leg a dict with a `reason`). Test helpers: `tests.helpers.make_ohlcv`, `tests.planning.test_exit_sim_single._plan` (defaults: market entry at 100, stop 95, tp1 110, `tp1_fraction` 0.5).
- Produces: `GEOMETRIES = (("live", None), ("g125", 1.25), ("g100", 1.00))`, `UNTRIGGERED`, `geometry_plan(plan, g) -> TradePlanV2`, `outcome(df, i, plan) -> dict | None` (keys `outcome`, `r`, `exit_mix`), `trade_row(df, i, plan, ctx) -> dict | None`. A trade row is plain JSON types: `ticker`, `horizon_key`, `signal_date`, `year`, `direction`, `features` (V143-1's dict), `outcomes` (`{"live": ..., "g125": ..., "g100": ...}`, each an `outcome` dict or `None`).

- [ ] **Step 0: Invoke the `no-lookahead` skill** (this task adds the one forward-walking function; confirm nothing in `features` moved with it).

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_fvg_diagnostic_outcomes.py`:

```python
"""v143 outcomes: the g125 / g100 copies move tp1 only and never touch the
original plan; an untriggered plan is not a trade."""
import dataclasses

from swingbot.core.backtesting import fvg_diagnostic as fd
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan


def bull(**kw):
    return _plan(strategy=fd.STRATEGY, source="confluence", **kw)   # entry 100, stop 95, tp1 110


NO_FVG = fd.SignalContext(target=110.0, target_sources=("EMA 50",), stop=95.0,
                          stop_sources=("Swing Low",), tolerance_pct=5.0)


def test_geometry_copies_move_only_tp1_and_leave_the_original_alone():
    original = bull(tp2=120.0)
    before = dataclasses.asdict(original)
    g125, g100 = fd.geometry_plan(original, 1.25), fd.geometry_plan(original, 1.0)
    assert (g125.tp1, g100.tp1) == (106.25, 105.0)
    assert dataclasses.asdict(original) == before
    assert {**dataclasses.asdict(g100), "tp1": 110.0} == before
    assert fd.geometry_plan(original, None) is original
    short = bull(direction="bearish", stop_loss=104.0, tp1=90.0)
    assert fd.geometry_plan(short, 1.25).tp1 == 95.0


def test_entry_reference_prefers_the_entry_price():
    assert fd.entry_reference(bull(entry_price=101.0)) == 101.0
    assert fd.entry_reference(bull()) == 100.0


def test_a_nearer_target_turns_a_live_loss_into_a_win():
    df = make_ohlcv([100.0, (100.0, 105.5, 99.5, 101.0), (101.0, 101.5, 94.0, 94.5)])
    row = fd.trade_row(df, 0, bull(), NO_FVG)
    assert row["outcomes"]["g100"]["outcome"] == "win"
    assert row["outcomes"]["live"]["outcome"] != "win"
    assert row["outcomes"]["g100"]["exit_mix"].startswith("tp1+")
    assert row["signal_date"] == "2024-01-02" and row["year"] == "2024"
    assert row["features"]["fvg_role"] == "unidentified"


def test_an_untriggered_plan_is_not_a_trade():
    df = make_ohlcv([100.0, 99.0, 98.5, 98.0, 98.0])
    assert fd.trade_row(df, 0, bull(entry_type="stop_entry", trigger_price=103.0), NO_FVG) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/backtesting/test_fvg_diagnostic_outcomes.py -q -x`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.fvg_diagnostic' has no attribute 'geometry_plan'`.

- [ ] **Step 3: Extend the module**

In `swingbot/core/backtesting/fvg_diagnostic.py`, replace the import block (from `from __future__` down to the last `from swingbot...` line) so it reads:

```python
from __future__ import annotations

import dataclasses
import math

from swingbot.core.market import fvg, levels
from swingbot.core.market.earnings_calendar import next_reaction_distance
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.quality import atr_percentile, score_plan
from swingbot.core.scanning.regime import get_htf_bias
```

Then append to the end of the file, after two blank lines:

```python
# --- outcomes ----------------------------------------------------------------

#: name -> first-target distance in R (None = the plan as built).
GEOMETRIES = (("live", None), ("g125", 1.25), ("g100", 1.00))
UNTRIGGERED = ("not_triggered", "no_trade")


def geometry_plan(plan, g):
    """`plan` itself for g=None; else a COPY with tp1 at entry +/- g x risk.
    Stop, tp2 and every other field are unchanged; the original is never
    mutated."""
    if g is None:
        return plan
    entry = entry_reference(plan)
    sign = 1.0 if plan.direction == "bullish" else -1.0
    return dataclasses.replace(plan, tp1=entry + sign * g * abs(entry - plan.stop_loss))


def outcome(df, i, plan) -> dict | None:
    """The exit as plain JSON types, or None when the plan never triggered."""
    res = simulate_exit(df, i, plan, scale_out=True)
    if res.outcome in UNTRIGGERED:
        return None
    reason = res.legs[-1]["reason"]
    mix = reason if len(res.legs) == 1 else f"tp1+{reason}"
    return {"outcome": res.outcome, "r": float(res.r_total), "exit_mix": mix}


def trade_row(df, i, plan, ctx) -> dict | None:
    """One trade: features at the signal bar and its exit at each geometry.
    None when the plan as built never triggered (the population rule)."""
    live = outcome(df, i, plan)
    if live is None:
        return None
    outcomes = {name: live if g is None else outcome(df, i, geometry_plan(plan, g))
                for name, g in GEOMETRIES}
    signal_date = str(df.index[i].date())
    return {"ticker": plan.ticker, "horizon_key": plan.horizon_key,
            "signal_date": signal_date, "year": signal_date[:4],
            "direction": plan.direction,
            "features": features(df, i, plan, ctx),
            "outcomes": outcomes}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_fvg_diagnostic_outcomes.py`
Expected: 4 passed, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_fvg_diagnostic_features.py`
Expected: 17 passed, 0 failed.

- [ ] **Step 5: Check complexity**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/fvg_diagnostic.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/fvg_diagnostic.py tests/backtesting/test_fvg_diagnostic_outcomes.py
git commit -m "feat(v143): g125/g100 geometry copies and the per-trade row (V143-2)"
```

### Task V143-3: Statistics and the candidate rule

**Files:**
- Modify: `swingbot/core/backtesting/fvg_diagnostic.py` (import block; append one section)
- Create: `tests/backtesting/fvg_diagnostic_rows.py` (helper; no `test_` prefix, so it is not collected)
- Test: `tests/backtesting/test_fvg_diagnostic_rule.py`

**Interfaces:**
- Consumes: the trade-row shape from V143-2, `ROLE_NONE` from V143-1. Existing: `acceptance.CLOSED = ("win", "loss", "scratch", "timeout")`, `acceptance.DECIDED = ("win", "loss")`.
- Produces: constants `YEARS`, `EXPECTED_N` (1278), `N_TOLERANCE` (0.02), `MIN_N`, `MIN_WIN_RATE`, `MIN_GAP_R`, `MIN_YEARS_POSITIVE`, `MIN_COMPUTABLE_SHARE`, `NOT_TESTED` (the one-element failure a pair under the 80% floor gets), `FEATURES` (nine `(key, label, favourable(value, median))` tuples), `MEDIAN_FEATURES`; functions `population_ok(n) -> bool`, `stats(rows, geometry) -> {"n", "win_rate", "exp_r"}`, `medians(rows) -> dict`, `side(row, key, med) -> bool | None`, `years_positive(rows, geometry) -> int`, `feature_cell(rows, key, geometry, med) -> dict` (keys `feature`, `geometry`, `favourable`, `unfavourable`, `years_positive`, `computable`, `not_computable`, `computable_share`), `candidate_failures(cell) -> list[str]` (empty list = candidate). Test helpers `row(...)` and `table(...)` in `tests/backtesting/fvg_diagnostic_rows.py`, which V143-4 and V143-5 import.

- [ ] **Step 1: Write the row helper and the failing test**

Create `tests/backtesting/fvg_diagnostic_rows.py`:

```python
"""Hand-built v143 trade rows. No test_ prefix: not collected."""
from swingbot.core.backtesting import fvg_diagnostic as fd


def row(year="2020", fav=True, outcome="win", r=1.0, role="target", quality=60, **kw):
    out = {"outcome": outcome, "r": r, "exit_mix": "tp1+runner_trail" if outcome == "win" else "stop"}
    features = {"fvg_role": role, "gap_age": 5 if fav else 50, "gap_height_atr": 1.0,
                "displacement": True, "gap_open": True, "stop_atr": 1.5, "quality": quality,
                "trend_aligned": True, "volatility": 0.02, "earnings_distance": 10}
    features.update(kw)
    return {"ticker": "AAA", "horizon_key": "2w", "signal_date": f"{year}-03-02", "year": year,
            "direction": "bullish", "features": features,
            "outcomes": {"live": out, "g125": out, "g100": out}}


def table(fav_per_year=40, fav_wins=24, unfav_r=-0.5, win_r=1.0, loss_r=None):
    """Favourable side: per year `fav_wins` wins at `win_r` (an int, or a
    {year: wins} dict) and the rest losses at -1R (`loss_r`: {year: r}
    overrides). Unfavourable side: 10 losses a year at `unfav_r`."""
    rows = []
    for year in fd.YEARS:
        wins = fav_wins[year] if isinstance(fav_wins, dict) else fav_wins
        lost = (loss_r or {}).get(year, -1.0)
        rows += [row(year, outcome="win", r=win_r) for _ in range(wins)]
        rows += [row(year, outcome="loss", r=lost) for _ in range(fav_per_year - wins)]
        rows += [row(year, fav=False, outcome="loss", r=unfav_r) for _ in range(10)]
    return rows
```

Create `tests/backtesting/test_fvg_diagnostic_rule.py`:

```python
"""v143 candidate rule on hand-built tables: one passing cell, then one table
failing each clause alone."""
import pytest

from swingbot.core.backtesting import fvg_diagnostic as fd
from tests.backtesting.fvg_diagnostic_rows import row, table


def cell(rows, key="gap_age", geometry="live"):
    return fd.feature_cell(rows, key, geometry, fd.medians(rows))


def test_a_cell_passing_every_clause_is_a_candidate():
    c = cell(table())                    # N 160, WR 60%, ExpR +0.20, unfav -0.5, 4/4 years
    assert c["favourable"] == {"n": 160, "win_rate": pytest.approx(60.0), "exp_r": pytest.approx(0.2)}
    assert c["unfavourable"]["n"] == 40 and c["years_positive"] == 4
    assert fd.candidate_failures(c) == []


@pytest.mark.parametrize("kwargs, failure", [
    (dict(fav_per_year=30, fav_wins=18), "N < 150"),
    (dict(unfav_r=0.15), "under +0.10R above the unfavourable side"),
])
def test_one_clause_fails_alone(kwargs, failure):
    assert fd.candidate_failures(cell(table(**kwargs))) == [failure]


def test_win_rate_clause_fails_alone():
    c = cell(table(fav_wins=19, win_r=2.0))           # 47.5% wins, ExpR +0.425
    assert c["favourable"]["exp_r"] == pytest.approx(0.425)
    assert fd.candidate_failures(c) == ["win rate < 50%"]


def test_expectancy_clause_fails_alone():
    c = cell(table(loss_r={"2023": -4.0}, unfav_r=-2.0))   # 60% wins, ExpR -0.10, 3 good years
    assert c["favourable"]["exp_r"] == pytest.approx(-0.1) and c["years_positive"] == 3
    assert fd.candidate_failures(c) == ["expectancy <= 0"]


def test_year_clause_fails_alone():
    wins = {"2020": 20, "2021": 20, "2022": 50, "2023": 50}
    c = cell(table(fav_per_year=50, fav_wins=wins))   # 70% wins, ExpR +0.40, 2 good years
    assert c["years_positive"] == 2
    assert fd.candidate_failures(c) == ["positive in fewer than 3 of 4 years"]


def test_under_the_computable_floor_is_not_tested_and_an_empty_side_fails_the_gap():
    rows = table() + [row(gap_age=None, role="unidentified") for _ in range(60)]
    c = cell(rows)                       # 200 of 260 computable = 76.9%
    assert (c["computable"], c["not_computable"]) == (200, 60)
    assert fd.candidate_failures(c) == [fd.NOT_TESTED]
    only_fav = [r for r in table() if r["features"]["gap_age"] == 5]
    assert fd.candidate_failures(cell(only_fav)) == ["under +0.10R above the unfavourable side"]


def test_medians_come_from_identified_rows_and_ties_are_favourable():
    rows = [row(quality=q) for q in (40, 60, 80)] + [row(quality=1000, role="unidentified")]
    med = fd.medians(rows)
    assert med["quality"] == 60
    assert [fd.side(r, "quality", med) for r in rows] == [False, True, True, True]
    assert fd.side(row(volatility=0.02), "volatility", {"volatility": 0.02}) is True
    assert fd.side(row(volatility=0.03), "volatility", {"volatility": 0.02}) is False
    assert fd.side(row(quality=None), "quality", med) is None
    assert fd.side(row(), "quality", {"quality": None}) is None


def test_stats_use_the_badge_definitions():
    rows = [row(outcome="win", r=1.0), row(outcome="loss", r=-1.0),
            row(outcome="timeout", r=0.4), row(outcome="scratch", r=0.0)]
    assert fd.stats(rows, "live") == {"n": 4, "win_rate": 50.0, "exp_r": pytest.approx(0.1)}
    assert fd.stats([], "live") == {"n": 0, "win_rate": None, "exp_r": None}


def test_population_tolerance_is_two_percent():
    assert fd.population_ok(1278) and fd.population_ok(1253) and fd.population_ok(1303)
    assert not fd.population_ok(1252) and not fd.population_ok(1304)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/backtesting/test_fvg_diagnostic_rule.py -q -x`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.fvg_diagnostic' has no attribute 'YEARS'`.

- [ ] **Step 3: Extend the module**

In `swingbot/core/backtesting/fvg_diagnostic.py`, replace the import block so it reads:

```python
from __future__ import annotations

import dataclasses
import math
import statistics

from swingbot.core.backtesting.acceptance import CLOSED, DECIDED
from swingbot.core.market import fvg, levels
from swingbot.core.market.earnings_calendar import next_reaction_distance
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.quality import atr_percentile, score_plan
from swingbot.core.scanning.regime import get_htf_bias
```

Then append to the end of the file, after two blank lines:

```python
# --- tables ------------------------------------------------------------------

YEARS = ("2020", "2021", "2022", "2023")
EXPECTED_N = 1278
N_TOLERANCE = 0.02

#: The pre-registered rule (spec § The rule). Never moved.
MIN_N = 150
MIN_WIN_RATE = 50.0
MIN_GAP_R = 0.10
MIN_YEARS_POSITIVE = 3
MIN_COMPUTABLE_SHARE = 0.80
#: Under the computable floor a feature is NOT TESTED: no candidate, and not
#: closed by this diagnostic either (spec § Candidate features).
NOT_TESTED = "not tested (computable for under 80% of the population)"

#: (key, label, favourable(value, median)). One split each, the favourable
#: side fixed here before any outcome is joined (spec § Candidate features).
FEATURES = (
    ("gap_age", "Gap age <= 20 bars", lambda v, m: v <= 20),
    ("gap_height_atr", "Gap height >= 0.5 ATR14", lambda v, m: v >= 0.5),
    ("displacement", "Displacement candle (v128 definition, k = 1.5)", lambda v, m: bool(v)),
    ("stop_atr", "Stop distance >= 1.0 ATR14", lambda v, m: v >= 1.0),
    ("quality", "Replay quality score >= median", lambda v, m: v >= m),
    ("trend_aligned", "Trend-aligned (SMA200)", lambda v, m: bool(v)),
    ("volatility", "ATR14 / close <= median", lambda v, m: v <= m),
    ("earnings_distance", "Earnings distance > 5 sessions", lambda v, m: v > 5),
    ("gap_open", "Gap open at the signal bar", lambda v, m: bool(v)),
)
MEDIAN_FEATURES = ("quality", "volatility")
_FAVOURABLE = {key: test for key, _label, test in FEATURES}


def population_ok(n: int) -> bool:
    """Within 2% of the expected 1,278; outside it the engine has moved."""
    return abs(n - EXPECTED_N) <= N_TOLERANCE * EXPECTED_N


def stats(rows, geometry) -> dict:
    """Badge definitions: win rate over win + loss, expectancy over closed."""
    outs = [row["outcomes"][geometry] for row in rows if row["outcomes"].get(geometry)]
    closed = [o for o in outs if o["outcome"] in CLOSED]
    decided = [o for o in closed if o["outcome"] in DECIDED]
    wins = sum(1 for o in decided if o["outcome"] == "win")
    return {"n": len(closed),
            "win_rate": 100.0 * wins / len(decided) if decided else None,
            "exp_r": statistics.fmean(o["r"] for o in closed) if closed else None}


def medians(rows) -> dict:
    """Median of each median-split feature over the IDENTIFIED population,
    from the feature alone."""
    out = {}
    for key in MEDIAN_FEATURES:
        values = [row["features"][key] for row in rows
                  if row["features"]["fvg_role"] != ROLE_NONE
                  and row["features"][key] is not None]
        out[key] = statistics.median(values) if values else None
    return out


def side(row, key, med) -> bool | None:
    """True = favourable, False = unfavourable, None = not computable."""
    value = row["features"][key]
    median = med.get(key)
    if value is None or (key in MEDIAN_FEATURES and median is None):
        return None
    return bool(_FAVOURABLE[key](value, median))


def _positive(value) -> bool:
    return value is not None and value > 0


def years_positive(rows, geometry) -> int:
    """Calendar years 2020-2023 whose expectancy is above zero. A year with
    no closed trade is not positive."""
    return sum(1 for year in YEARS
               if _positive(stats([r for r in rows if r["year"] == year], geometry)["exp_r"]))


def feature_cell(rows, key, geometry, med) -> dict:
    """One (feature, geometry) pair: both sides, the year count, coverage."""
    sides = [(row, side(row, key, med)) for row in rows]
    favourable = [row for row, verdict in sides if verdict is True]
    unfavourable = [row for row, verdict in sides if verdict is False]
    computable = len(favourable) + len(unfavourable)
    return {"feature": key, "geometry": geometry,
            "favourable": stats(favourable, geometry),
            "unfavourable": stats(unfavourable, geometry),
            "years_positive": years_positive(favourable, geometry),
            "computable": computable,
            "not_computable": len(rows) - computable,
            "computable_share": computable / len(rows) if rows else 0.0}


def _gap_r(cell) -> float | None:
    fav, unfav = cell["favourable"]["exp_r"], cell["unfavourable"]["exp_r"]
    return None if fav is None or unfav is None else fav - unfav


def candidate_failures(cell) -> list:
    """The clauses this (feature, geometry) pair fails; [] = a candidate.
    Under the computable floor the pair is NOT TESTED and no clause is read.
    An empty unfavourable side fails the +0.10R clause: there is nothing to
    be better than."""
    if cell["computable_share"] < MIN_COMPUTABLE_SHARE:
        return [NOT_TESTED]
    fav, gap = cell["favourable"], _gap_r(cell)
    checks = (
        ("N < 150", fav["n"] >= MIN_N),
        ("win rate < 50%", fav["win_rate"] is not None and fav["win_rate"] >= MIN_WIN_RATE),
        ("expectancy <= 0", _positive(fav["exp_r"])),
        ("under +0.10R above the unfavourable side",
         gap is not None and gap >= MIN_GAP_R - 1e-9),
        ("positive in fewer than 3 of 4 years", cell["years_positive"] >= MIN_YEARS_POSITIVE),
    )
    return [name for name, ok in checks if not ok]
```

The nine `FEATURES` rows are the spec's table, in its order, with its thresholds. Do not reorder, rename or re-threshold them. A pair under the computable floor returns `[NOT_TESTED]` and no other clause is read: it is not tested, which is different from failing.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_fvg_diagnostic_rule.py`
Expected: 10 passed, 0 failed.

- [ ] **Step 5: Check complexity**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/fvg_diagnostic.py tests/backtesting/fvg_diagnostic_rows.py`
Expected: one line, `stats - C (12)`. Nothing at 15 or above.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/fvg_diagnostic.py tests/backtesting/fvg_diagnostic_rows.py tests/backtesting/test_fvg_diagnostic_rule.py
git commit -m "feat(v143): badge statistics and the candidate rule, not-tested floor (V143-3)"
```

### Task V143-4: Report, coverage and results-document renderer

**Files:**
- Modify: `swingbot/core/backtesting/fvg_diagnostic.py` (import block; append one section)
- Test: `tests/backtesting/test_fvg_diagnostic_report.py`

**Interfaces:**
- Consumes: V143-3's `FEATURES`, `GEOMETRIES` (V143-2), `stats`, `medians`, `side`, `feature_cell`, `candidate_failures`, `NOT_TESTED`, `MIN_COMPUTABLE_SHARE`, `EXPECTED_N`; V143-1's `TRAIN`, `ROLE_NONE`; `row` / `table` from `tests/backtesting/fvg_diagnostic_rows.py`.
- Produces: `CONTEXT_DIMENSIONS = ("fvg_role", "direction", "horizon_key", "year")`, `context_table(rows, dimension) -> {value: {geometry: stats}}`, `exit_mix(rows, geometry) -> dict`, `coverage(rows, med) -> {feature: {"computable", "not_computable", "share", "tested"}}`, `gap_split(rows) -> {"target", "stop", "unidentified", "open", "filled"}`, `build_report(rows) -> dict` (keys `n`, `unidentified`, `gap_split`, `medians`, `coverage`, `population`, `cells` (27, each a `feature_cell` plus `failures`), `candidates` (list of `(feature, geometry)`), `context`, `exit_mix`), `not_tested(report) -> list[str]`, `render(report, *, run_date: str, tickers: int, tolerance_pct=None) -> str`. V143-5 calls `build_report` and `render` and reads `report["coverage"]`.
- The document must show, above its tables: the verdict; a `Not tested:` line when any feature is under the floor (not a candidate, not closed); the 27-looks warning; the population N with the unidentified count and share in bold; the role split and, next to it, how many identified trades had the gap open against filled at the signal bar; and a `## Feature coverage` table with every feature's computable count and share. A `## Notes` section says the quality score is a replay score and that share of gap filled was not testable on this population.

- [ ] **Step 1: Write the failing test**

Create `tests/backtesting/test_fvg_diagnostic_report.py`:

```python
"""v143 report and results document: 27 cells, the context tables, the
multiple-looks warning."""
from swingbot.core.backtesting import fvg_diagnostic as fd
from tests.backtesting.fvg_diagnostic_rows import row, table


def rows():
    """The passing table plus one unidentified winner in 2023."""
    return table() + [row("2023", role="unidentified", gap_age=None, gap_open=None)]


def test_report_has_27_cells_and_names_the_candidate():
    report = fd.build_report(rows())
    assert (report["n"], report["unidentified"], len(report["cells"])) == (201, 1, 27)
    assert report["gap_split"] == {"target": 200, "stop": 0, "unidentified": 1,
                                   "open": 200, "filled": 0}
    assert report["coverage"]["gap_age"] == {"computable": 200, "not_computable": 1,
                                             "share": 200 / 201, "tested": True}
    assert ("gap_age", "live") in report["candidates"]
    assert report["population"]["live"]["n"] == 201
    assert report["exit_mix"]["live"] == {"stop": 104, "tp1+runner_trail": 97}


def test_context_tables_cover_role_direction_horizon_and_year():
    context = fd.build_report(rows())["context"]
    assert set(context) == set(fd.CONTEXT_DIMENSIONS)
    assert set(context["year"]) == set(fd.YEARS)
    assert set(context["fvg_role"]) == {"target", "unidentified"}
    assert context["fvg_role"]["unidentified"]["g100"]["n"] == 1


def test_the_document_carries_the_warning_the_rule_and_every_table():
    text = fd.render(fd.build_report(rows()), run_date="2026-10-10", tickers=75,
                     tolerance_pct=2.0)
    expected = ["9 features at 3 geometries is 27 looks",
                "**Gap role: 200 target / 0 stop / 1 unidentified. Gap at the signal bar: "
                "200 open / 0 filled.**",
                "**Population N = 201** (expected 1278). **Unidentified: 1 (0.5%)**",
                "replay quality 60, ATR14/close 0.02.", "| 4/4 | 1 (0.5%) | **CANDIDATE** |",
                "## Feature coverage", "| Gap age <= 20 bars | 200 | 1 | 99.5% | tested |",
                "Replay quality score, not the live one", "within 2% of the scenario target",
                "Share of gap filled: not testable on this population",
                "### By gap role", "### By plan direction", "### By horizon", "### By year",
                "### Exit mix", "VALIDATION never read"]
    assert [piece for piece in expected if piece not in text] == []
    assert text.count("| Gap age <= 20 bars | live |") == 1
    assert "Not tested:" not in text


def test_a_feature_under_the_floor_is_reported_as_not_tested_not_closed():
    blind = dict(role="unidentified", gap_age=None, gap_height_atr=None, displacement=None,
                 gap_open=None)
    report = fd.build_report(table() + [row(**blind) for _ in range(60)])
    gap_features = ["gap_age", "gap_height_atr", "displacement", "gap_open"]
    assert fd.not_tested(report) == gap_features
    assert all(cell["failures"] == [fd.NOT_TESTED]
               for cell in report["cells"] if cell["feature"] in gap_features)
    assert not [pair for pair in report["candidates"] if pair[0] in gap_features]
    text = fd.render(report, run_date="2026-10-10", tickers=75)
    assert "**Not tested: gap_age, gap_height_atr, displacement, gap_open.**" in text
    assert "this diagnostic does not close them" in text
    assert "| Gap age <= 20 bars | 200 | 60 | 76.9% | **NOT TESTED** |" in text
    assert "**Unidentified: 60 (23.1%)**" in text


def test_the_document_counts_gaps_filled_before_the_signal_bar():
    stale = [row("2021", fav=False, outcome="loss", r=-1.0, gap_open=False) for _ in range(7)]
    report = fd.build_report(table() + stale + [row(role="stop")])
    assert report["gap_split"] == {"target": 207, "stop": 1, "unidentified": 0,
                                   "open": 201, "filled": 7}
    text = fd.render(report, run_date="2026-10-10", tickers=75)
    assert "Gap at the signal bar: 201 open / 7 filled.**" in text
    assert "builds its level map fresh" in text


def test_an_empty_population_renders_no_candidate():
    text = fd.render(fd.build_report([]), run_date="2026-10-10", tickers=0)
    assert "**Verdict: NO CANDIDATE.**" in text and "replay quality n/a" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/backtesting/test_fvg_diagnostic_report.py -q -x`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.fvg_diagnostic' has no attribute 'build_report'`.

- [ ] **Step 3: Extend the module**

In `swingbot/core/backtesting/fvg_diagnostic.py`, replace the import block so it reads:

```python
from __future__ import annotations

import dataclasses
import math
import statistics
from collections import Counter

from swingbot.core.backtesting.acceptance import CLOSED, DECIDED
from swingbot.core.market import fvg, levels
from swingbot.core.market.earnings_calendar import next_reaction_distance
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.quality import atr_percentile, score_plan
from swingbot.core.scanning.regime import get_htf_bias
```

Then append to the end of the file, after two blank lines:

```python
# --- report (reported, never gating) -----------------------------------------

CONTEXT_DIMENSIONS = ("fvg_role", "direction", "horizon_key", "year")


def _context_value(row, dimension):
    return row["features"]["fvg_role"] if dimension == "fvg_role" else row[dimension]


def context_table(rows, dimension) -> dict:
    """{value: {geometry: stats}} -- reported, never gating."""
    values = sorted({_context_value(row, dimension) for row in rows})
    return {value: {name: stats([r for r in rows if _context_value(r, dimension) == value], name)
                    for name, _g in GEOMETRIES}
            for value in values}


def exit_mix(rows, geometry) -> dict:
    """{exit reason: count} at one geometry, keys sorted."""
    return dict(sorted(Counter(row["outcomes"][geometry]["exit_mix"] for row in rows
                               if row["outcomes"].get(geometry)).items()))


def coverage(rows, med) -> dict:
    """{feature: computable count, share, tested} -- how much of the
    population each feature can speak for."""
    out = {}
    for key, _label, _test in FEATURES:
        computable = sum(1 for row in rows if side(row, key, med) is not None)
        share = computable / len(rows) if rows else 0.0
        out[key] = {"computable": computable, "not_computable": len(rows) - computable,
                    "share": share, "tested": share >= MIN_COMPUTABLE_SHARE}
    return out


def gap_split(rows) -> dict:
    """Role split and, among identified trades, gap open vs filled at the
    signal bar."""
    roles = Counter(row["features"]["fvg_role"] for row in rows)
    opened = Counter(bool(row["features"]["gap_open"]) for row in rows
                     if row["features"]["fvg_role"] != ROLE_NONE)
    return {"target": roles[ROLE_TARGET], "stop": roles[ROLE_STOP],
            "unidentified": roles[ROLE_NONE], "open": opened[True], "filled": opened[False]}


def build_report(rows) -> dict:
    """Everything the results document prints, from the trade rows."""
    med = medians(rows)
    cells = [feature_cell(rows, key, name, med)
             for key, _label, _test in FEATURES for name, _g in GEOMETRIES]
    for cell in cells:
        cell["failures"] = candidate_failures(cell)
    return {
        "n": len(rows),
        "unidentified": sum(1 for row in rows if row["features"]["fvg_role"] == ROLE_NONE),
        "gap_split": gap_split(rows),
        "medians": med,
        "coverage": coverage(rows, med),
        "population": {name: stats(rows, name) for name, _g in GEOMETRIES},
        "cells": cells,
        "candidates": [(c["feature"], c["geometry"]) for c in cells if not c["failures"]],
        "context": {dim: context_table(rows, dim) for dim in CONTEXT_DIMENSIONS},
        "exit_mix": {name: exit_mix(rows, name) for name, _g in GEOMETRIES},
    }


# --- rendering ---------------------------------------------------------------

def _pct(value) -> str:
    return "n/a" if value is None else f"{value:.1f}%"


def _r(value) -> str:
    return "n/a" if value is None else f"{value:+.3f}R"


def _num(value) -> str:
    return "n/a" if value is None else f"{value:.4g}"


def _stat_cells(s) -> str:
    return f"{s['n']} | {_pct(s['win_rate'])} | {_r(s['exp_r'])}"


def _cell_line(cell, labels) -> str:
    verdict = "**CANDIDATE**" if not cell["failures"] else "; ".join(cell["failures"])
    return (f"| {labels[cell['feature']]} | {cell['geometry']} | "
            f"{_stat_cells(cell['favourable'])} | {_stat_cells(cell['unfavourable'])} | "
            f"{cell['years_positive']}/4 | {cell['not_computable']} "
            f"({(1 - cell['computable_share']) * 100:.1f}%) | {verdict} |")


def _feature_table(report) -> list:
    labels = {key: label for key, label, _test in FEATURES}
    head = ["| Feature (favourable side) | Geometry | N fav | WR fav | ExpR fav | "
            "N unfav | WR unfav | ExpR unfav | Years > 0 | Not computable | Verdict |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    return head + [_cell_line(cell, labels) for cell in report["cells"]]


def _context_section(title, table) -> list:
    names = [name for name, _g in GEOMETRIES]
    lines = [f"### By {title}", "",
             "| Value | " + " | ".join(f"N {n} | WR {n} | ExpR {n}" for n in names) + " |",
             "|---|" + "---|---|---|" * len(names)]
    lines += [f"| {value} | " + " | ".join(_stat_cells(by_geo[n]) for n in names) + " |"
              for value, by_geo in table.items()]
    return lines + [""]


def _coverage_table(report) -> list:
    labels = {key: label for key, label, _test in FEATURES}
    lines = ["| Feature | Computable | Not computable | Share | Status |", "|---|---|---|---|---|"]
    for key, cov in report["coverage"].items():
        status = "tested" if cov["tested"] else "**NOT TESTED**"
        lines.append(f"| {labels[key]} | {cov['computable']} | {cov['not_computable']} | "
                     f"{cov['share'] * 100:.1f}% | {status} |")
    return lines


def not_tested(report) -> list:
    return [key for key, cov in report["coverage"].items() if not cov["tested"]]


def _verdict_lines(report) -> list:
    if report["candidates"]:
        names = ", ".join(f"{feature} @ {geometry}" for feature, geometry in report["candidates"])
        head = (f"**Verdict: {len(report['candidates'])} CANDIDATE(S)** ({names}). "
                "Each has earned a spec, nothing more.")
    else:
        head = "**Verdict: NO CANDIDATE.** FVG (bullish) stays WEAK."
    skipped = not_tested(report)
    if not skipped:
        return [head]
    return [head, "", f"**Not tested: {', '.join(skipped)}.** Computable for under 80% of the "
            "population, so they cannot be candidates and this diagnostic does not close them."]


def _population_lines(report) -> list:
    """N, the unidentified share, the medians and the coverage table."""
    n, unidentified, split = report["n"], report["unidentified"], report["gap_split"]
    share = unidentified / n * 100 if n else 0.0
    med = report["medians"]
    return [
        f"**Population N = {n}** (expected {EXPECTED_N}). **Unidentified: {unidentified} "
        f"({share:.1f}%)** have no bullish gap, on the window the level map was built on, within "
        "the confluence tolerance of a scenario level that carries the FVG source (target, else "
        "stop); they stay in every total and are not computable for the four gap features.",
        "", f"**Gap role: {split['target']} target / {split['stop']} stop / "
        f"{split['unidentified']} unidentified. Gap at the signal bar: {split['open']} open / "
        f"{split['filled']} filled.** A filled gap was unfilled when the replay's level map was "
        "built (up to 4 bars earlier) and is no longer returned by the finder at the signal bar. "
        "The live scan builds its level map fresh at every scan, so it would not have labelled "
        "those plans FVG.",
        "", f"Medians over the identified population: replay quality {_num(med['quality'])}, "
        f"ATR14/close {_num(med['volatility'])}.", "",
        "## Feature coverage", "",
    ] + _coverage_table(report)


def _notes(tolerance_pct) -> list:
    return [
        "## Notes", "",
        "- **Replay quality score, not the live one.** `replay_scenarios` builds plans without "
        "quality inputs, so the diagnostic scores each plan with the live scorer "
        "(`quality.score_plan`) from what is causal on the ticker's own window: higher-timeframe "
        "bias, volume ratio, ATR percentile, trigger distance and the target confluence count "
        f"(strategy families within {_num(tolerance_pct)}% of the scenario target). Market "
        "regime, relative-strength percentile and breadth are passed as None.",
        "- **Share of gap filled: not testable on this population.** The live gap finder drops "
        "a gap as soon as any later bar overlaps it, so every plan here sits on an untouched gap "
        "and the share is 0 by construction. Dropped before the run (partner decision, "
        "2026-10-09); it is neither tested nor closed. \"Gap open at the signal bar\" is its "
        "testable form on the replay, where a level map up to 4 bars old lets a filled gap keep "
        "its label.", "",
    ]


def render(report, *, run_date: str, tickers: int, tolerance_pct=None) -> str:
    """The results document, as markdown."""
    names = [name for name, _g in GEOMETRIES]
    looks = len(report["cells"])
    lines = [
        "# v143 FVG (bullish) badge diagnostic: result", "",
        f"**Run:** {run_date}, TRAIN {TRAIN[0]}..{TRAIN[1]} (signal date), {tickers} cached "
        "tickers, ten horizons. Read-only; VALIDATION never read.",
        "**Spec:** `docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md`",
        "", *_verdict_lines(report), "",
        f"{len(FEATURES)} features at {len(names)} geometries is {looks} looks. At a 5% "
        "false-positive rate one or two chance hits are expected; a candidate below has earned "
        "a spec, not a filter.", "",
        *_population_lines(report), "",
        "## Whole population", "",
        "| Geometry | N | Win rate | ExpR |", "|---|---|---|---|",
    ]
    lines += [f"| {n} | {_stat_cells(report['population'][n])} |" for n in names]
    lines += ["", "## Candidate table", "",
              "The rule, per (feature, geometry) pair, on the favourable side: N >= 150, "
              "win rate >= 50%, ExpR > 0, at least +0.10R above the unfavourable side, and "
              "ExpR > 0 in 3 of the 4 years. A feature computable for under 80% of the "
              "population is not tested.", ""]
    lines += _feature_table(report)
    lines += ["", *_notes(tolerance_pct), "## Reported, never gating", ""]
    for dim, title in zip(CONTEXT_DIMENSIONS, ("gap role", "plan direction", "horizon", "year")):
        lines += _context_section(title, report["context"][dim])
    lines += ["### Exit mix", ""]
    lines += [f"- **{n}:** " + ", ".join(f"{k} {v}" for k, v in report["exit_mix"][n].items())
              for n in names]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_fvg_diagnostic_report.py`
Expected: 6 passed, 0 failed.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_fvg_diagnostic_rule.py`
Expected: 10 passed, 0 failed.

- [ ] **Step 5: Check complexity and unused imports**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/fvg_diagnostic.py tests/backtesting/test_fvg_diagnostic_report.py`
Expected: two lines, `stats - C (12)` and `build_report - C (11)`. Nothing at 15 or above.

Run: `python -m pyflakes swingbot/core/backtesting/fvg_diagnostic.py` (if pyflakes is installed)
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/fvg_diagnostic.py tests/backtesting/test_fvg_diagnostic_report.py
git commit -m "feat(v143): report tables, feature coverage and the results-document renderer (V143-4)"
```
