"""
Confidence scoring for a support/resistance scenario, on a fixed 5-level
scale:

  1. Very Low   (score 0-20)
  2. Low         (score 21-40)
  3. Medium      (score 41-60)
  4. High        (score 61-80)
  5. Very High   (score 81-100)

The score is NOT a statistical probability of winning -- it's a
rule-based way to rank scenarios by how much independent confirmation
their target level has. The *actual* reliability of each level is
whatever the performance tracker (performance.py) measures over time
from real closed trades -- see Step 5 below for how that empirical
track record now feeds back into the level itself, not just a separate
`!performance` report.

WHY THIS WAS RE-TUNED: the old scheme added up points from six
independent factors (confluence, distance, regime, volatility,
candlestick) into one 0-100 sum. That made the number opaque -- a
scenario with just ONE confirming strategy could still reach "Very
High" purely from great distance + aligned regime + a squeeze breakout,
so the level alone never reliably told you how many strategies actually
agreed. The whole point of a "confidence level" is to answer that
question at a glance.

THE MODEL, in one sentence: the level is the number of DISTINCT
strategies confirming the target (capped at 5), nudged by up to ±1 for
technical setup quality AND, independently, up to ±1 for whether this
trade's own reward:risk actually produces a real statistical edge (see
Step 5) at this level's historical win rate -- the metric that answers
"should I risk real money on this", not just "does this look technically
clean". Concretely:

  Step 1 -- BASE LEVEL = min(5, N), where N is how many DISTINCT
  strategies (see levels.count_confirming_strategies -- EMA, VWAP,
  Fibonacci, rolling structure, zigzag pivots, Bollinger Bands,
  Donchian Channel, floor pivots, trendlines, Fair Value Gaps)
  independently land within CONFLUENCE_DEVIATION_PCT of the target
  price. This is the SAME count scan_engine.py's MIN_TARGET_CONFLUENCE_COUNT
  filter uses, so the two can never disagree about what "N strategies
  confirmed this" means.
      N=1 -> base Level 1     N=2 -> base Level 2     N=3 -> base Level 3
      N=4 -> base Level 4     N=5+ -> base Level 5

  Step 2 -- QUALITY SCORE (0-100), technical setup quality -- everything
  that ISN'T "how many strategies agree" and ISN'T the track record below:
      - Target distance quality  (0-20) -- how many multiples of the
        required minimum move (MIN_REWARD_PCT) the target sits beyond it.
      - Stop level confluence    (0-15) -- how many strategies independently
        confirm the STOP side too (same tolerance, see `stop_confluence`).
      - Market regime alignment  (0-15) -- does the scenario's direction
        agree with the broader market trend (SPY vs its 200-day EMA)?
      - ADX trend strength       (0-15) -- is this a genuinely trending
        (vs. choppy/ranging) market, direction-agnostic.
      - MACD momentum alignment  (0-15) -- does the MACD histogram/line
        agree with this scenario's direction (see volatility.py).
      - RSI trend alignment      (0-10) -- does RSI sit on -- and keep
        moving toward -- the expected side of 50 for this direction (see
        volatility.py's rsi_trend_aligned). Added after a real S/R
        Confluence SHORT scored well despite RSI 58 and rising (clearly
        bullish) with nothing in the breakdown reflecting that RSI itself
        disagreed -- price-level confluence alone can build a scenario in
        either direction with no momentum check unless something
        explicitly looks at it, and MACD alone doesn't cover RSI's own
        (sometimes different) read on momentum.
      - Volatility squeeze + volume breakout (0-10) -- a real, independent
        technical confirmation (see volatility.py): was this ticker
        recently compressed and did it just break out on strong volume
        in this scenario's own direction?
      - Candlestick pattern (0-10, on top, min(100,...) capped) -- a
        confirming reversal/continuation pattern on the most recent candle.

  Step 3 -- QUALITY ADJUSTMENT:
      quality >= 70  -> +1 level  (exceptional technical setup quality)
      quality <= 30  -> -1 level  (weak technical setup quality)
      otherwise      ->  0        (quality is unremarkable either way)

  Step 4 -- EXPECTANCY (the "can I confidently trade this with real
  money" metric): the classic trading-edge formula,

      Expectancy (R) = win_rate * reward:risk - (1 - win_rate)

  using this SCENARIO's own reward:risk ratio and the EMPIRICAL win
  rate of closed trades that previously reached this same base level
  (performance.py's TradeLog.get_stats, passed in as `track_record`).
  Positive expectancy means: play this setup/payoff combination many
  times at that win rate and you come out ahead in R-multiples; zero or
  negative means you don't, no matter how clean the setup looks
  technically. Below MIN_CLOSED_TRADES_FOR_EXPECTANCY closed trades at
  this level, there's no real data yet -- a neutral 50% (coin-flip) win
  rate is assumed instead, clearly labeled as such, so early trades
  aren't boosted or penalized on a track record that doesn't exist yet.
      expectancy >= 0.5R  -> +1 level  (a genuine, meaningful edge)
      expectancy <= 0.0R  -> -1 level  (breakeven or a losing edge)
      otherwise            ->  0

  Step 5 -- FINAL LEVEL = clamp(base_level + quality_adjustment +
  expectancy_adjustment, 1, 5).

This means quality and/or track record can never manufacture a "Very
High" out of a single-strategy setup (base 1, best case +1+1 = Level 3,
never higher) purely from looking good on paper, and a well-confirmed
setup can't be fully hidden by one bad afternoon of regime/volatility
either. Reading the level now reliably tells you, within about a
strategy or two either way, both how many independent methods agree
AND whether the payoff/win-rate math actually works out in your favor --
which is the entire point of a number meant to answer "can I confidently
use this trade plan to make a real trade".

The displayed 0-100 SCORE is cosmetic/informational only (used for
sorting/dedup tie-breaking) -- it's the quality score repositioned
inside the final level's own 20-point band, so it never contradicts the
level a person is looking at.
"""
from dataclasses import dataclass, field
import logging

from swingbot import config
from swingbot.core.candlestick_patterns import detect_confirming_pattern
from swingbot.core.volatility import adx_trend_strength, macd_momentum_aligned, rsi_trend_aligned, squeeze_breakout_confirmation

log = logging.getLogger("swing-bot.confidence")

LEVELS = [
    (1, "Very Low", 0, 20),
    (2, "Low", 21, 40),
    (3, "Medium", 41, 60),
    (4, "High", 61, 80),
    (5, "Very High", 81, 100),
]
_LEVEL_LABELS = {lvl: label for lvl, label, _lo, _hi in LEVELS}
_LEVEL_RANGE = {lvl: (lo, hi) for lvl, _label, lo, hi in LEVELS}

# Step 3's thresholds -- quality has to be genuinely strong or genuinely
# weak to move the level at all; the broad 31-69 middle ground leaves the
# strategy-count base level untouched, since "unremarkable quality"
# shouldn't move a legibility-critical number either way.
QUALITY_BOOST_THRESHOLD = 70
QUALITY_PENALTY_THRESHOLD = 30

# Step 4's thresholds, in R-multiples (reward:risk-adjusted expected
# value per trade at the historical win rate). +0.5R is a real, worth-
# noticing edge, not just barely-positive noise; <=0.0R is breakeven or
# a loser -- deliberately asymmetric (easier to get flagged down than
# boosted up) since this feeds a real-money decision, not just a rank.
EXPECTANCY_BOOST_THRESHOLD = 0.5
EXPECTANCY_PENALTY_THRESHOLD = 0.0

# Below this many closed trades at a given base level, there isn't
# enough history yet for its win rate to mean anything -- same bar
# risk_metrics.py uses for Sharpe/Sortino to avoid presenting sampling
# noise as if it were signal.
MIN_CLOSED_TRADES_FOR_EXPECTANCY = 5

# Assumed win rate when there isn't enough track record yet -- a plain
# coin flip, so the earliest trades at a level get a neutral read on
# this factor rather than an artificial boost or penalty.
ASSUMED_WIN_RATE = 0.5


@dataclass
class ConfidenceResult:
    level: int
    label: str
    score: int
    breakdown: dict = field(default_factory=dict)


def _expectancy_adjustment(risk_reward_ratio: float, track_record: tuple) -> tuple:
    """
    Computes Expectancy (R) = win_rate * reward:risk - (1 - win_rate) --
    the real-money "should I take this trade" metric -- using this
    scenario's OWN reward:risk ratio and the empirical win rate of
    closed trades that reached this same base confidence level.

    `track_record`, if given, is (win_rate_pct: float | None, closed_count: int)
    from performance.py's TradeLog.get_stats(base_level) -- win_rate_pct
    is None if there are no closed trades at all yet. Falls back to an
    assumed 50% win rate (clearly labeled) if there's no track record
    passed in, or fewer than MIN_CLOSED_TRADES_FOR_EXPECTANCY closed
    trades at this level so far.

    Returns (adjustment, detail_string).
    """
    win_rate_pct, closed_count = track_record if track_record else (None, 0)
    if win_rate_pct is not None and closed_count >= MIN_CLOSED_TRADES_FOR_EXPECTANCY:
        win_rate = win_rate_pct / 100
        basis = f"{win_rate_pct:.0f}% empirical win rate ({closed_count} closed trades at this level)"
    else:
        win_rate = ASSUMED_WIN_RATE
        basis = (
            f"{ASSUMED_WIN_RATE * 100:.0f}% assumed win rate (only {closed_count} closed trade(s) at this "
            f"level so far -- needs {MIN_CLOSED_TRADES_FOR_EXPECTANCY}+ for real data)"
        )

    expectancy = win_rate * risk_reward_ratio - (1 - win_rate)

    if expectancy >= EXPECTANCY_BOOST_THRESHOLD:
        adjustment = 1
        verdict = f">= {EXPECTANCY_BOOST_THRESHOLD:+.1f}R -> +1 level"
    elif expectancy <= EXPECTANCY_PENALTY_THRESHOLD:
        adjustment = -1
        verdict = f"<= {EXPECTANCY_PENALTY_THRESHOLD:+.1f}R -> -1 level"
    else:
        adjustment = 0
        verdict = "no adjustment"

    detail = f"{basis}, {risk_reward_ratio}:1 reward:risk -> expectancy {expectancy:+.2f}R ({verdict})"
    return adjustment, detail


def score_confidence(scenario, regime_trend: str = None, df=None,
                      target_confluence: tuple = None, stop_confluence: tuple = None,
                      track_record: tuple = None) -> ConfidenceResult:
    """
    `target_confluence` / `stop_confluence`, if given, are (count,
    family_names) tuples from levels.count_confirming_strategies -- the
    same "how many DISTINCT strategies land within
    config.CONFLUENCE_DEVIATION_PCT of this price" measure
    scan_engine.py's MIN_TARGET_CONFLUENCE_COUNT filter uses. Passing
    them in keeps the base level and that filter permanently in
    agreement about what "N strategies confirmed this" means. If not
    given (e.g. a caller without a horizon dict/full df handy), falls
    back to counting the scenario's own already-clustered raw
    target_sources/stop_sources instead -- a reasonable approximation,
    just not guaranteed to match the filter's tolerance exactly.

    `track_record`, if given, is (win_rate_pct, closed_count) from
    performance.py's TradeLog.get_stats(base_level) -- the empirical win
    rate for previously-closed trades that reached this scenario's own
    base level (see Step 4/_expectancy_adjustment). Passed in rather
    than looked up here so confidence.py stays decoupled from
    performance.py/TradeLog (same dependency-injection pattern as the
    confluence tuples above).
    """
    breakdown = {}

    if target_confluence is not None:
        target_count, target_families = target_confluence
    else:
        target_families = list(dict.fromkeys(scenario.target_sources))
        target_count = len(target_families)

    if stop_confluence is not None:
        stop_count, stop_families = stop_confluence
    else:
        stop_families = list(dict.fromkeys(scenario.stop_sources))
        stop_count = len(stop_families)

    # --- Step 1: base level, directly from strategy count -----------
    base_level = max(1, min(5, target_count))
    families_str = ", ".join(target_families) if target_families else "none"
    plural = "y" if target_count == 1 else "ies"
    breakdown["Strategies confirmed (base level)"] = (
        f"{target_count} strateg{plural} agree on the target: {families_str} "
        f"-> base Level {base_level} ({_LEVEL_LABELS[base_level]})"
    )

    # --- Step 2: quality score (0-100), technical setup quality -------
    # Quality sub-factors and their max points (must sum to 100 before the
    # +10 candlestick bonus):
    #   Target distance quality        0-20
    #   Stop level confluence          0-15
    #   Market regime alignment        0-15   trimmed from 0-20 to make room for RSI below
    #   ADX trend strength             0-15   trending market = higher quality
    #   MACD momentum alignment        0-15   independent momentum confirmation
    #   RSI trend alignment            0-10   NEW: independent momentum confirmation,
    #                                         RSI's own read (see volatility.rsi_trend_aligned)
    #   TTM Squeeze / volume breakout  0-10   trimmed from 0-15 to make room for RSI above
    #   Candlestick pattern            0-10 bonus (min(100, total) caps it)
    # Total possible: 100 + 10 bonus = 110, capped at 100.

    # Target distance quality (0-20) -- how many multiples of the required minimum move this is
    min_reward = config.MIN_REWARD_PCT if config.MIN_REWARD_PCT > 0 else 5.0
    ratio = scenario.target_distance_pct / min_reward
    pts_distance = min(20, round(10 * ratio))
    breakdown["Target distance quality"] = (
        f"{scenario.target_distance_pct:.1f}% away ({ratio:.1f}x the {min_reward:.0f}% minimum) (+{pts_distance})"
    )

    # Stop level confluence (0-15) -- a well-confirmed stop is a quality signal, not a strategy-count one
    pts_stop = min(15, 5 * stop_count)
    stop_families_str = ", ".join(stop_families) if stop_families else "none"
    plural_stop = "y" if stop_count == 1 else "ies"
    breakdown["Stop level confluence"] = f"{stop_count} strateg{plural_stop} agree: {stop_families_str} (+{pts_stop})"

    # Market regime alignment (0-15) -- macro direction from SPY vs 200 EMA
    if regime_trend is None:
        pts_regime = 7
        breakdown["Market regime alignment"] = "regime unavailable (+7)"
    elif regime_trend == scenario.direction:
        pts_regime = 15
        breakdown["Market regime alignment"] = f"aligned with {regime_trend} market regime (+{pts_regime})"
    else:
        pts_regime = 0
        breakdown["Market regime alignment"] = f"⚠️ counter to {regime_trend} market regime (+0)"

    # ADX trend strength (0-15) -- NEW factor.
    # A genuinely trending market (ADX >= 20) raises quality; a strong trend
    # (ADX >= 25) raises it further. A ranging, choppy market (ADX < 20)
    # scores 0 -- setups in flat, directionless tape are statistically weaker.
    pts_adx = 0
    if df is not None:
        adx_info = adx_trend_strength(df)
        if adx_info["adx"] is not None:
            if adx_info["strong"]:          # ADX >= 25: strong trend
                pts_adx = 15
            elif adx_info["trending"]:      # ADX 20-24: emerging trend
                pts_adx = 8
            else:                           # ADX < 20: ranging
                pts_adx = 0
            breakdown["ADX trend strength"] = (
                f"ADX {adx_info['adx']} ({adx_info['label']}) (+{pts_adx})"
            )
        else:
            pts_adx = 7   # neutral when unavailable
            breakdown["ADX trend strength"] = "not evaluated (insufficient history) (+7)"
    else:
        pts_adx = 7
        breakdown["ADX trend strength"] = "not evaluated (no price history passed in) (+7)"

    # MACD momentum alignment (0-15) -- NEW factor.
    # Independent momentum confirmation from the MACD histogram direction
    # and zero-line context. Strong = histogram positive AND rising (bullish)
    # or negative AND falling (bearish). Moderate = histogram on the right
    # side of zero. Weak = MACD line above/below signal only.
    pts_macd = 0
    if df is not None:
        mom = macd_momentum_aligned(df, scenario.direction)
        if mom["strength"] == "strong":
            pts_macd = 15
            breakdown["MACD momentum"] = (
                f"histogram {'positive & rising' if scenario.direction == 'bullish' else 'negative & falling'} "
                f"(MACD {mom['macd_val']:+.4f}, hist {mom['histogram']:+.4f}) (+{pts_macd})"
            )
        elif mom["strength"] == "moderate":
            pts_macd = 10
            breakdown["MACD momentum"] = (
                f"histogram on the {'positive' if scenario.direction == 'bullish' else 'negative'} side "
                f"(MACD {mom['macd_val']:+.4f}, hist {mom['histogram']:+.4f}) (+{pts_macd})"
            )
        elif mom["strength"] == "weak":
            pts_macd = 5
            breakdown["MACD momentum"] = (
                f"MACD {'above' if scenario.direction == 'bullish' else 'below'} signal line only "
                f"(hist {mom['histogram']:+.4f}) (+{pts_macd})"
            )
        else:
            pts_macd = 0
            breakdown["MACD momentum"] = f"⚠️ MACD momentum opposes {scenario.direction} direction (+0)"
    else:
        pts_macd = 7   # neutral when unavailable
        breakdown["MACD momentum"] = "not evaluated (no price history passed in) (+7)"

    # RSI trend alignment (0-10) -- NEW factor. Independent of MACD: MACD
    # can look aligned (or simply not be checked) while RSI's own read on
    # momentum disagrees -- exactly what happened on a real S/R Confluence
    # SHORT that scored well with RSI 58 and rising (bullish) and nothing
    # in the breakdown reflecting it. See volatility.rsi_trend_aligned.
    pts_rsi = 0
    if df is not None:
        rsi_mom = rsi_trend_aligned(df, scenario.direction)
        if rsi_mom["rsi_val"] is None:
            pts_rsi = 5   # neutral when unavailable
            breakdown["RSI trend alignment"] = "not evaluated (insufficient history) (+5)"
        elif rsi_mom["strength"] == "strong":
            pts_rsi = 10
            breakdown["RSI trend alignment"] = (
                f"RSI {rsi_mom['rsi_val']} on the {'bullish' if scenario.direction == 'bullish' else 'bearish'} "
                f"side of 50 and still moving that way (+{pts_rsi})"
            )
        elif rsi_mom["strength"] == "moderate":
            pts_rsi = 6
            breakdown["RSI trend alignment"] = (
                f"RSI {rsi_mom['rsi_val']} on the expected side of 50 (+{pts_rsi})"
            )
        elif rsi_mom["strength"] == "weak":
            pts_rsi = 3
            breakdown["RSI trend alignment"] = (
                f"RSI {rsi_mom['rsi_val']} near the neutral midline -- neither confirms nor opposes (+{pts_rsi})"
            )
        else:
            pts_rsi = 0
            breakdown["RSI trend alignment"] = (
                f"⚠️ RSI {rsi_mom['rsi_val']} opposes {scenario.direction} direction (+0)"
            )
    else:
        pts_rsi = 5   # neutral when unavailable
        breakdown["RSI trend alignment"] = "not evaluated (no price history passed in) (+5)"

    # TTM Squeeze + volume breakout confirmation (0-10) -- uses proper TTM
    # Squeeze logic: Bollinger Bands contracting inside Keltner Channel =
    # extreme compression. The bar the squeeze fires (BBands expand back
    # outside KC) on directional volume is the classical highest-
    # probability entry point.
    pts_squeeze = 0
    if df is not None:
        squeeze = squeeze_breakout_confirmation(df, scenario.direction)
        if squeeze["confirmed"]:
            pts_squeeze = 10
            breakdown["TTM Squeeze + volume breakout"] = (
                f"TTM Squeeze fired -- BBands broke outside Keltner Channel "
                f"on {squeeze['width_pct']:.1f}% width, 1.5x+ volume in the {scenario.direction} direction (+{pts_squeeze})"
            )
            if "Bollinger Squeeze Breakout" not in scenario.target_sources:
                scenario.target_sources.append("Bollinger Squeeze Breakout")
        elif squeeze["is_squeeze"]:
            pts_squeeze = 5
            breakdown["TTM Squeeze + volume breakout"] = (
                f"squeeze ON (BBands inside Keltner Channel, width {squeeze['width_pct']:.1f}%) "
                f"-- awaiting breakout direction (+{pts_squeeze})"
            )
        else:
            breakdown["TTM Squeeze + volume breakout"] = "no squeeze/breakout confirmation right now (+0)"
    else:
        breakdown["TTM Squeeze + volume breakout"] = "not evaluated (no price history passed in) (+0)"

    # Candlestick pattern confirmation (0-10, bonus on top of the
    # 100-point quality base -- min(100, ...) below caps its effect).
    # Needs price history (`df`) to compute; scored neutrally (0) if not provided.
    pts_candle = 0
    if df is not None:
        pattern = detect_confirming_pattern(df, scenario.direction)
        if pattern["confirmed"]:
            pts_candle = 10 if pattern["bars_ago"] == 0 else 6
            when = "today's candle" if pattern["bars_ago"] == 0 else "yesterday's candle"
            breakdown["Candlestick pattern"] = f"{pattern['pattern']} on {when} confirms {scenario.direction} (+{pts_candle})"
            source_label = f"Candlestick: {pattern['pattern']}"
            if source_label not in scenario.target_sources:
                scenario.target_sources.append(source_label)
        else:
            breakdown["Candlestick pattern"] = "no confirming pattern on the most recent candle(s) (+0)"
    else:
        breakdown["Candlestick pattern"] = "not evaluated (no price history passed in) (+0)"

    quality_score = min(100, pts_distance + pts_stop + pts_regime + pts_adx + pts_macd + pts_rsi + pts_squeeze + pts_candle)

    # --- Step 3: quality-based adjustment, at most one level either way ---
    if quality_score >= QUALITY_BOOST_THRESHOLD:
        quality_adjustment = 1
        quality_reason = f"quality score {quality_score}/100 >= {QUALITY_BOOST_THRESHOLD} -> +1 level"
    elif quality_score <= QUALITY_PENALTY_THRESHOLD:
        quality_adjustment = -1
        quality_reason = f"quality score {quality_score}/100 <= {QUALITY_PENALTY_THRESHOLD} -> -1 level"
    else:
        quality_adjustment = 0
        quality_reason = f"quality score {quality_score}/100 -> no adjustment"
    breakdown["Quality score"] = f"{quality_score}/100 ({quality_reason})"

    # --- Step 4: expectancy-based adjustment -- "can I confidently trade this?" ---
    expectancy_adjustment, expectancy_detail = _expectancy_adjustment(scenario.risk_reward_ratio, track_record)
    breakdown["Track record (expectancy)"] = expectancy_detail

    # --- Step 5: final level, clamped ---------------------------------
    total_adjustment = quality_adjustment + expectancy_adjustment
    level = max(1, min(5, base_level + total_adjustment))
    label = _LEVEL_LABELS[level]
    if total_adjustment != 0:
        breakdown["Level adjustment"] = (
            f"base Level {base_level} {total_adjustment:+d} (quality {quality_adjustment:+d}, "
            f"expectancy {expectancy_adjustment:+d}) -> final Level {level} ({label})"
        )

    # Displayed score is cosmetic: the quality score repositioned inside
    # the FINAL level's own band, so the number on screen never
    # contradicts the level right next to it.
    lo, hi = _LEVEL_RANGE[level]
    score = lo + round(quality_score / 100 * (hi - lo))
    score = max(lo, min(hi, score))

    log.debug("scenario %s target=%.2f: %d strateg%s (%s) -> base Lv%d, quality=%d "
               "(dist=%d stop=%d regime=%d adx=%d macd=%d rsi=%d squeeze=%d candle=%d), "
               "quality_adj=%+d expectancy_adj=%+d -> final Lv%d(%s) score=%d",
               scenario.direction, scenario.take_profit, target_count, "y" if target_count == 1 else "ies",
               target_families, base_level, quality_score,
               pts_distance, pts_stop, pts_regime, pts_adx, pts_macd, pts_rsi, pts_squeeze, pts_candle,
               quality_adjustment, expectancy_adjustment, level, label, score)

    return ConfidenceResult(level=level, label=label, score=score, breakdown=breakdown)
