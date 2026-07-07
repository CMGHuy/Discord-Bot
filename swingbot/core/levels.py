"""
Finds the next support/resistance levels above and below the current
price, using EVERY method this bot knows about as an independent vote:
EMA (fast + slow), rolling VWAP, Fibonacci retracement levels (+ the
swing high/low that anchors them), rolling structural support/resistance
(highest high / lowest low over the lookback), zigzag/Elliott-style
pivot highs & lows, Bollinger Bands (upper/lower), a 20-bar Donchian
Channel (the classic Turtle Trader breakout channel), classic floor
trader pivot points (PP/R1/S1/R2/S2) projected off the prior session,
diagonal trendlines (see trendlines.py, built on the trendln
library) fit through recent swing highs/lows and evaluated at today's
bar -- the one source here that isn't a flat historical price, so a
stock in a genuine up/down channel gets a support/resistance level that
tracks the trend's slope instead of anchoring to a stale historical
high or low -- Fair Value Gaps (see fvg.py), unfilled 3-candle
price-action imbalance zones -- and the Volume Profile High Volume Node
(see strategy.compute_hvn_level), the price where the most shares
actually changed hands recently, which is real traded volume rather
than a level derived purely from price geometry.
Levels produced by different methods that land close together are
merged into one, more-confirmed level -- the more independent methods
agree a price matters, the stronger that level is. This is what lets a
Fibonacci retracement and the Volume Profile HVN, for example, confirm
each other when they coincide: the merged level's `sources` list carries
both labels, so real trading volume backing a technical level shows up
directly in the "confirmed by" fields downstream (scan_engine.py's
embed, confidence.py's scoring).

From there, this builds BOTH possible scenarios for the ticker (not just
whichever direction some indicator happened to trigger on):
  - bullish: price runs up to the next resistance (target 1), and -- if
    that keeps going -- the resistance beyond it (target 2, a stretch
    target). Invalidated by breaking the next support below.
  - bearish: price drops to the next support (target 1), and -- if that
    keeps going -- the support beyond it (target 2). Invalidated by
    breaking the next resistance above.

A scenario only qualifies if its target 1 sits at least MIN_REWARD_PCT
away from TODAY'S CURRENT PRICE (e.g. a €100 stock needs a target at or
beyond €105 (bullish) or €95 (bearish)) AND its stop sits at least
MIN_STOP_DISTANCE_PCT away. Both scenarios can qualify at once; both get
shown. Neither threshold is loosened if nothing qualifies -- finding
zero qualifying scenarios on a given scan is a perfectly fine, expected
outcome. Quality over quantity: this never fabricates a level (an
"estimated" stop when no real support/resistance exists on that side)
just to force a trade plan into existence.

Each qualifying scenario is really describing a small decision tree, not
a single path: the stop-loss level IS the level on the opposite side
(support1 for a bullish scenario, resistance1 for a bearish one) -- so
if target 1 gets hit and then REJECTS instead of continuing, the natural
reversal target is that same stop level; if target 1 gets hit and
CONTINUES, the natural next stop is target 2. scan_engine.py/explain.py
spell both branches out explicitly rather than just listing four prices.

A stop level that sits closer than this horizon's own normal ATR-based
volatility would suggest is flagged as "tight" -- not adjusted (that
would misrepresent the real technical level), just flagged, since a
very tight stop is more exposed to being clipped by ordinary daily noise
rather than a genuine reversal.
"""
import math
from dataclasses import dataclass, field

import pandas as pd

from .indicators import atr, ema, fibonacci_levels, rolling_vwap, zigzag_pivots
from .volatility import bollinger_bands
from .trendlines import trendline_levels
from .fvg import find_fair_value_gaps
from .strategy import compute_hvn_level

# Candidate levels within this % of each other get merged into one,
# combined-confidence level rather than shown as separate near-duplicate
# lines -- a Fib 61.8% and a 50-day EMA sitting within a hair of each
# other are, for trading purposes, the same level.
CLUSTER_TOLERANCE_PCT = 1.5

# How many of the most recent zigzag pivot highs/lows to consider as
# candidate levels -- older pivots are less relevant to price right now.
MAX_RECENT_PIVOTS = 8


@dataclass
class Level:
    price: float
    sources: list


def _cluster_levels(candidates: list, tolerance_pct: float = CLUSTER_TOLERANCE_PCT) -> list:
    """Merges nearby raw (price, source_label) candidates into Level objects, sorted by price."""
    if not candidates:
        return []

    candidates = sorted(candidates, key=lambda c: c[0])
    clusters = []
    bucket_prices = [candidates[0][0]]
    bucket_sources = [candidates[0][1]]

    for price, source in candidates[1:]:
        mean_price = sum(bucket_prices) / len(bucket_prices)
        if mean_price > 0 and abs(price - mean_price) / mean_price * 100 <= tolerance_pct:
            bucket_prices.append(price)
            bucket_sources.append(source)
        else:
            clusters.append(Level(price=sum(bucket_prices) / len(bucket_prices), sources=bucket_sources))
            bucket_prices, bucket_sources = [price], [source]

    clusters.append(Level(price=sum(bucket_prices) / len(bucket_prices), sources=bucket_sources))
    return clusters


def collect_candidate_levels(df: pd.DataFrame, h: dict, current_price: float) -> list:
    """
    Gathers raw (price, source_label) candidates from every method this
    bot knows: EMA fast/slow, rolling VWAP, Fibonacci retracements +
    swing high/low, rolling structural support/resistance, recent
    zigzag pivot highs/lows, Bollinger Bands, Donchian Channel, floor
    pivots, (see trendlines.py) diagonal trendlines fit through
    recent swing highs/lows and evaluated at today's bar -- the one
    source here that isn't a flat historical price, so it can track a
    stock that's trending hard instead of anchoring to a stale level --
    and (see fvg.py) unfilled Fair Value Gaps.
    Any single method failing (e.g. not enough data yet) is skipped
    rather than failing the whole ticker.
    """
    candidates = []
    close = df["Close"]

    try:
        fast = float(ema(close, h["ema_fast"]).iloc[-1])
        if pd.notna(fast):
            candidates.append((fast, f"EMA{h['ema_fast']}"))
    except Exception:
        pass

    try:
        slow = float(ema(close, h["ema_slow"]).iloc[-1])
        if pd.notna(slow):
            candidates.append((slow, f"EMA{h['ema_slow']}"))
    except Exception:
        pass

    try:
        vwap = float(rolling_vwap(df, h["vwap_window"]).iloc[-1])
        if pd.notna(vwap):
            candidates.append((vwap, "VWAP"))
    except Exception:
        pass

    try:
        fib = fibonacci_levels(df, h["fib_lookback"])
        for ratio, price in fib["levels"].items():
            if pd.notna(price):
                candidates.append((float(price), f"Fib {ratio * 100:.1f}%"))
        candidates.append((fib["swing_high"], "Swing high"))
        candidates.append((fib["swing_low"], "Swing low"))
    except Exception:
        pass

    try:
        sr_lookback = h["sr_lookback"]
        resistance = df["High"].rolling(sr_lookback).max().shift(1).iloc[-1]
        support = df["Low"].rolling(sr_lookback).min().shift(1).iloc[-1]
        if pd.notna(resistance):
            candidates.append((float(resistance), "Rolling resistance"))
        if pd.notna(support):
            candidates.append((float(support), "Rolling support"))
    except Exception:
        pass

    try:
        # Reuses the horizon's own risk-scale % as pivot granularity -- same
        # convention strategy.py's Elliott Wave detector uses, so pivots
        # found here line up with the ones that would drive that strategy.
        pivots = zigzag_pivots(df, threshold_pct=h["max_risk_pct"])
        for _, price, kind in pivots[-MAX_RECENT_PIVOTS:]:
            candidates.append((float(price), "Pivot high" if kind == "high" else "Pivot low"))
    except Exception:
        pass

    try:
        # Bollinger Bands -- a classic mean-reversion/volatility envelope
        # (see volatility.py); the bands themselves double as dynamic
        # support/resistance, independent of the trend-following EMAs.
        bb = bollinger_bands(df, window=20, num_std=2.0)
        upper, lower = bb["upper"].iloc[-1], bb["lower"].iloc[-1]
        if pd.notna(upper):
            candidates.append((float(upper), "Bollinger upper"))
        if pd.notna(lower):
            candidates.append((float(lower), "Bollinger lower"))
    except Exception:
        pass

    try:
        # Donchian Channel -- highest high / lowest low over a fixed
        # 20-bar window (the classic Turtle Trader breakout channel).
        # Distinct from the horizon's own sr_lookback rolling S/R: this
        # is always a short, fixed window regardless of horizon, so it
        # tends to catch tighter, more recent structure than the
        # horizon-scaled rolling S/R does.
        donchian_high = df["High"].rolling(20).max().shift(1).iloc[-1]
        donchian_low = df["Low"].rolling(20).min().shift(1).iloc[-1]
        if pd.notna(donchian_high):
            candidates.append((float(donchian_high), "Donchian high"))
        if pd.notna(donchian_low):
            candidates.append((float(donchian_low), "Donchian low"))
    except Exception:
        pass

    try:
        # Classic floor pivot points, from the most recently completed
        # bar: PP = (H+L+C)/3, with R1/S1 and R2/S2 projected off it --
        # a long-standing, widely-used way to project the next
        # support/resistance from nothing but the last session's range.
        prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
        pp = (prev["High"] + prev["Low"] + prev["Close"]) / 3
        span = prev["High"] - prev["Low"]
        if pd.notna(pp) and span > 0:
            candidates.append((float(pp), "Floor Pivot"))
            candidates.append((float(pp + span), "Floor R1"))
            candidates.append((float(pp - span), "Floor S1"))
            candidates.append((float(pp + span * 1.5), "Floor R2"))
            candidates.append((float(pp - span * 1.5), "Floor S2"))
    except Exception:
        pass

    try:
        # Diagonal trendlines (see trendlines.py) -- the one source here
        # that isn't a flat historical price. Uses the same lookback
        # window as the Fibonacci swing anchor above, since both are
        # asking essentially the same question ("how far back does the
        # current swing structure go").
        candidates.extend(trendline_levels(df, h["fib_lookback"], current_price))
    except Exception:
        pass

    try:
        # Fair Value Gaps (see fvg.py) -- unfilled 3-candle imbalance
        # zones, a widely-used price-action concept distinct from every
        # other source here (none of the others look at *gaps* between
        # candles). Only still-unfilled gaps count, so this is a live,
        # currently-relevant level, not a historical curiosity.
        candidates.extend(find_fair_value_gaps(df))
    except Exception:
        pass

    try:
        # Volume Profile High Volume Node (see strategy.compute_hvn_level)
        # -- the price where the most shares actually traded in this
        # horizon's lookback window. Every other source here is derived
        # purely from price geometry (moving averages, retracements,
        # bands, pivots); this is the one source that's about REAL
        # trading volume, not price shape -- so when it clusters with
        # e.g. a Fibonacci level, that level is confirmed by actual
        # traded interest, not just a formula.
        hvn = compute_hvn_level(df, h["sr_lookback"])
        if hvn:
            candidates.append((hvn[0], "Volume Profile HVN"))
    except Exception:
        pass

    return [(p, s) for p, s in candidates if p and p > 0 and pd.notna(p)]


# Canonical strategy families every raw source label collapses to --
# used by count_confirming_strategies() (and trade_chart.py's strategy
# overview) to count DISTINCT STRATEGIES rather than distinct raw
# numbers. A single strategy can produce several raw candidates (5
# Fibonacci ratios, 2 EMAs, 5 floor-pivot lines, ...) that would
# otherwise inflate a naive count; this maps every one of those back to
# the one strategy that produced it. Order matters only in that a label
# is matched against its first hit, so put longer variants that would
# accidentally match FIRST if there's a naming ambiguity (there isn't
# one currently among these).
_STRATEGY_FAMILY_PREFIXES = [
    ("EMA", "EMA"),
    ("VWAP", "VWAP"),
    ("Fib", "Fibonacci"),
    ("Swing high", "Fibonacci"),
    ("Swing low", "Fibonacci"),
    ("Rolling", "Rolling S/R"),
    ("Pivot", "Zigzag Pivot"),
    ("Bollinger Squeeze Breakout", "Volatility Squeeze"),
    ("Bollinger", "Bollinger Bands"),
    ("Donchian", "Donchian Channel"),
    ("Floor", "Floor Pivot"),
    ("Trendline", "Trendline"),
    ("FVG", "FVG"),
    ("Volume Profile", "Volume Profile"),
    ("Candlestick:", "Candlestick Pattern"),
]

# The 11 strategies that actually produce a PRICE (as opposed to the
# two bonus, non-price confirmation factors from confidence.py --
# "Volatility Squeeze" and "Candlestick Pattern" -- which can't be
# measured against a target price and so never come from
# collect_candidate_levels in the first place).
ALL_STRATEGY_FAMILIES = [
    "EMA", "VWAP", "Fibonacci", "Rolling S/R", "Zigzag Pivot",
    "Bollinger Bands", "Donchian Channel", "Floor Pivot", "Trendline", "FVG",
    "Volume Profile",
]


def strategy_family(label: str) -> str:
    """Collapses a raw source label (e.g. "Fib 61.8%", "EMA50") to its canonical strategy family name."""
    for prefix, family in _STRATEGY_FAMILY_PREFIXES:
        if label.startswith(prefix):
            return family
    return label


def count_confirming_strategies(df: pd.DataFrame, h: dict, current_price: float, target_price: float,
                                 tolerance_pct: float) -> tuple:
    """
    Simulates EVERY supported strategy independently against this
    ticker (via collect_candidate_levels -- the same raw, pre-cluster
    scan every strategy already runs), then checks how many of them put
    their OWN predicted level within `tolerance_pct` of `target_price`
    -- the scenario's actual confirmed target. This is deliberately a
    separate, usually looser pass from the tight CLUSTER_TOLERANCE_PCT
    _cluster_levels() uses to decide what counts as "the same level" in
    the first place: a strategy whose own number lands close to, but
    not quite inside, that tight cluster still gets counted as
    corroborating evidence here.

    Multiple raw candidates from the same strategy (several Fibonacci
    ratios, both EMAs, every floor pivot line, ...) only ever count
    once -- see `strategy_family` -- since the question is "how many
    independent strategies agree", not "how many individual numbers
    happened to land nearby".

    Returns (count, sorted_family_names). (0, []) if target_price is
    falsy (nothing to measure deviation against).
    """
    if not target_price:
        return 0, []
    candidates = collect_candidate_levels(df, h, current_price)
    families = set()
    for price, label in candidates:
        if not price or price <= 0:
            continue
        deviation_pct = abs(price - target_price) / target_price * 100
        if deviation_pct <= tolerance_pct:
            families.add(strategy_family(label))
    return len(families), sorted(families)


def simulate_all_strategy_levels(df: pd.DataFrame, h: dict, current_price: float) -> dict:
    """
    Runs every supported strategy and returns, PER STRATEGY FAMILY, its
    own nearest support and resistance candidate (whichever raw
    candidates it produced, collapsed to that one family) -- i.e. "if
    you only trusted this one strategy, what would it say the next
    support/resistance is". Used by trade_chart.py's strategy-overview
    chart generator to actually show what each strategy independently
    thinks, one chart per strategy, rather than only the already-merged
    consensus scenario.

    Returns {family: {"support": (price, label) | None, "resistance": (price, label) | None}}
    for every family that produced at least one candidate; families
    that failed entirely for this ticker/horizon (e.g. not enough
    history) are simply absent, same as every other "fails silently"
    convention in this module.
    """
    candidates = collect_candidate_levels(df, h, current_price)
    by_family: dict = {}
    for price, label in candidates:
        if not price or price <= 0:
            continue
        family = strategy_family(label)
        side = "resistance" if price > current_price else "support"
        bucket = by_family.setdefault(family, {"support": None, "resistance": None})
        current_best = bucket[side]
        is_closer = current_best is None or abs(price - current_price) < abs(current_best[0] - current_price)
        if is_closer:
            bucket[side] = (price, label)
    return by_family


def build_level_map(df: pd.DataFrame, h: dict, current_price: float):
    """Returns (supports, resistances): Level lists below/above current_price, nearest first."""
    clustered = _cluster_levels(collect_candidate_levels(df, h, current_price))
    supports = sorted([lv for lv in clustered if lv.price < current_price], key=lambda l: -l.price)
    resistances = sorted([lv for lv in clustered if lv.price > current_price], key=lambda l: l.price)
    return supports, resistances


@dataclass
class LevelTarget:
    price: float
    distance_pct: float
    sources: list


@dataclass
class Scenario:
    direction: str            # "bullish" | "bearish"
    entry: float
    market_price: float        # same as entry in this model -- the plan reacts to where price is right now
    stop_loss: float
    stop_sources: list
    stop_distance_pct: float
    tight_stop: bool             # True if the stop is closer than this horizon's normal ATR-based cushion
    atr_floor_pct: float          # that ATR-based cushion, for display alongside the warning
    take_profit: float          # target 1's price
    target_distance_pct: float
    target_sources: list
    target2_price: float | None
    target2_distance_pct: float | None
    target2_sources: list | None
    constraints: dict = field(default_factory=dict)  # {"min_reward": bool, "min_stop_distance": bool, "max_stop_distance": bool, "min_risk_reward": bool}

    @property
    def risk_reward_ratio(self) -> float:
        risk = abs(self.entry - self.stop_loss)
        reward = abs(self.take_profit - self.entry)
        return round(reward / risk, 2) if risk > 0 else 0.0

    @property
    def meets_all_own_constraints(self) -> bool:
        """True if every constraint computed at build time (reward/stop distance/max stop/reward:risk) passed."""
        return all(self.constraints.values())


def atr_floor_pct(df, current_price: float, h: dict) -> float:
    """
    The minimum stop distance (%) this horizon's own volatility would
    normally call for -- ATR(14) scaled by the horizon's atr_stop_multiple
    (the same convention the old ATR-based stop sizing used), expressed
    as a % of current price. A structural stop tighter than this is at
    real risk of getting clipped by ordinary daily noise rather than a
    genuine reversal.
    """
    try:
        atr_value = float(atr(df, 14).iloc[-1])
        if not atr_value or current_price <= 0:
            return 0.0
        return atr_value * h.get("atr_stop_multiple", 1.5) / current_price * 100
    except Exception:
        return 0.0


def build_scenarios(current_price: float, supports: list, resistances: list, min_reward_pct: float,
                     atr_floor: float = 0.0, min_stop_distance_pct: float = 0.0,
                     max_stop_distance_pct: float = 0.0, min_risk_reward: float = 0.0) -> list:
    """
    Builds both possible scenarios (bullish toward resistance, bearish
    toward support), each only included if it clears EVERY one of these
    HARD requirements -- no exceptions, no "close enough":
      - target 1 at least `min_reward_pct` away from `current_price`
      - stop at least `min_stop_distance_pct` away (not too tight)
      - stop no further than `max_stop_distance_pct` away, if set (not too wide)
      - reward:risk to target 1 at least `min_risk_reward`, if set
    A scenario failing ANY of these is simply not built -- these are the
    thresholds the person configured, and they're respected exactly as
    set, with no soft "shown anyway" fallback. Either, both, or neither
    direction can qualify; not finding a qualifying trade for a given
    ticker/horizon is a perfectly fine, expected outcome.

    A scenario also needs a REAL level on both sides to exist AT ALL --
    if there's no genuine support/resistance to use as the invalidation
    point, this does NOT invent one. No fabricated "estimated" stop; the
    scenario is simply not built either way.

    Each scenario built still carries a `constraints` dict recording
    which of these it passed (trivially all True, since a scenario that
    failed any of them never gets built) -- kept so downstream display
    code (scan_engine.py's requirement table) has a consistent shape to
    read regardless of which requirements are hard filters here vs.
    checked further up the pipeline (confluence count, confidence level).
    """
    scenarios = []

    def _check_constraints(dist1, stop_dist, entry, stop_price, target_price) -> dict:
        risk = abs(entry - stop_price)
        reward = abs(target_price - entry)
        rr = reward / risk if risk > 0 else 0.0
        return {
            "min_reward": dist1 >= min_reward_pct,
            "min_stop_distance": stop_dist >= min_stop_distance_pct,
            "max_stop_distance": max_stop_distance_pct <= 0 or stop_dist <= max_stop_distance_pct,
            "min_risk_reward": min_risk_reward <= 0 or rr >= min_risk_reward,
        }

    if resistances and supports and current_price:
        t1 = resistances[0]
        dist1 = (t1.price - current_price) / current_price * 100
        stop_price, stop_sources = supports[0].price, supports[0].sources
        stop_dist = abs(current_price - stop_price) / current_price * 100
        constraints = _check_constraints(dist1, stop_dist, current_price, stop_price, t1.price)
        if all(constraints.values()):
            target2_price = target2_dist = target2_sources = None
            if len(resistances) > 1:
                t2 = resistances[1]
                target2_price = t2.price
                target2_dist = (t2.price - current_price) / current_price * 100
                target2_sources = t2.sources
            scenarios.append(Scenario(
                direction="bullish", entry=current_price, market_price=current_price,
                stop_loss=stop_price, stop_sources=stop_sources,
                stop_distance_pct=stop_dist, tight_stop=stop_dist < atr_floor, atr_floor_pct=atr_floor,
                take_profit=t1.price, target_distance_pct=dist1, target_sources=t1.sources,
                target2_price=target2_price, target2_distance_pct=target2_dist, target2_sources=target2_sources,
                constraints=constraints,
            ))

    if supports and resistances and current_price:
        t1 = supports[0]
        dist1 = (current_price - t1.price) / current_price * 100
        stop_price, stop_sources = resistances[0].price, resistances[0].sources
        stop_dist = abs(stop_price - current_price) / current_price * 100
        constraints = _check_constraints(dist1, stop_dist, current_price, stop_price, t1.price)
        if all(constraints.values()):
            target2_price = target2_dist = target2_sources = None
            if len(supports) > 1:
                t2 = supports[1]
                target2_price = t2.price
                target2_dist = (current_price - t2.price) / current_price * 100
                target2_sources = t2.sources
            scenarios.append(Scenario(
                direction="bearish", entry=current_price, market_price=current_price,
                stop_loss=stop_price, stop_sources=stop_sources,
                stop_distance_pct=stop_dist, tight_stop=stop_dist < atr_floor, atr_floor_pct=atr_floor,
                take_profit=t1.price, target_distance_pct=dist1, target_sources=t1.sources,
                target2_price=target2_price, target2_distance_pct=target2_dist, target2_sources=target2_sources,
                constraints=constraints,
            ))

    return scenarios


@dataclass
class ScenarioSignal:
    """
    Lightweight stand-in for strategy.SignalResult so the new level-based
    scenario engine can flow through the same dedup/state/embed pipeline
    as the old per-strategy signals did.
    """
    ticker: str
    horizon_key: str
    horizon_label: str
    trend: str
    close: float
    scenario: Scenario
    strategy: str = "S/R Confluence"
    triggered: bool = True

    @property
    def state_key(self) -> str:
        return f"{self.ticker}|{self.strategy}|{self.horizon_key}|{self.trend}"

    @property
    def state_value(self) -> str:
        # Re-confirm (reset the debounce) if the target has meaningfully
        # moved since the last scan, rather than treating a slightly
        # recalculated level as a brand new setup every single scan.
        #
        # This used to round to a fixed 2 decimal places, which is an
        # absolute-dollar tolerance -- fine for a $5 stock, but for
        # anything priced in the tens/hundreds of dollars, ordinary
        # intraday noise in the still-forming daily candle's high/low
        # shifts an S/R-based target by MORE than $0.01 on almost every
        # scan. Since confirm_or_update() (state.py) only counts a scan
        # toward SIGNAL_CONFIRMATION_SCANS when state_value is IDENTICAL
        # to the previous scan's, that meant most scenarios' debounce
        # count kept getting reset back to 1 before ever reaching the
        # required count -- only the rare ticker whose target happened to
        # round to the exact same cent on back-to-back scans ever actually
        # confirmed and alerted, while `!check` (require_confirmation=
        # False, no debounce) showed everything else that was really
        # qualifying.
        tp = max(self.scenario.take_profit, 0.01)
        tol_pct = 0.15  # ~0.15% tolerance per bucket, on a log scale (see
                        # note above -- a linear tp/bucket_size division
                        # would make tp cancel out entirely).
        bucket = round(math.log(tp) / math.log(1 + tol_pct / 100.0))
        return str(bucket)
