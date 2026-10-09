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
import statistics

from swingbot.core.backtesting.acceptance import CLOSED, DECIDED
from swingbot.core.market import fvg, levels
from swingbot.core.market.earnings_calendar import next_reaction_distance
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.exit_sim import simulate_exit
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
