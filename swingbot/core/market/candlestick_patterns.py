"""
Classic candlestick pattern recognition, via pandas-ta-classic
(https://github.com/xgboosted/pandas-ta-classic) -- 62 native reversal/
continuation patterns (engulfing, hammer, doji, morning star, etc.)
implemented in pure Python, no TA-Lib/C compilation needed. Same
reasoning volatility.py already gives for avoiding ta-lib/pandas-ta
proper: this keeps the whole project pip-installable with no compiler
required, which matters for the Docker build (see Dockerfile).

Used as ONE MORE independent confirmation in confidence.py (factor F):
did the most recent completed candle (or the one before it) form a
recognized pattern that agrees with the scenario's own direction? This
is a real, objective signal about today's specific candle shape --
distinct from every price-LEVEL-based method in levels.py, closer in
spirit to the volatility squeeze/breakout confirmation (factor E) than
to a support/resistance level. Deliberately weighted lower than the
core confluence factors (see confidence.py) -- a single candle's shape
is a much weaker signal than multiple independent price levels agreeing,
but it can tip a genuinely borderline scenario over the line.

Optional in practice: if pandas-ta-classic isn't installed, or there
isn't enough data, or nothing fires, this simply contributes nothing --
confidence scoring and every other factor work exactly as before.
"""
import logging

import pandas as pd

log = logging.getLogger("swing-bot.candlestick_patterns")

try:
    import pandas_ta_classic  # noqa: F401 -- registers the .ta accessor on DataFrames
    _PANDAS_TA_AVAILABLE = True
except ImportError:
    _PANDAS_TA_AVAILABLE = False
    log.info("pandas-ta-classic not installed -- candlestick pattern confirmation is disabled; every other confidence factor is unaffected.")

# Patterns checked for a BULLISH scenario -- classic reversal/continuation
# patterns that read bullish. "Engulfing" is direction-agnostic in
# pandas-ta-classic's own output (+100 for a bullish engulfing on a given
# bar, -100 for a bearish one), so it appears on both lists; the sign of
# the value, not the pattern name, is what's actually checked below.
BULLISH_PATTERNS = [
    "engulfing", "hammer", "invertedhammer", "morningstar",
    "morningdojistar", "piercing", "3whitesoldiers", "dragonflydoji",
]
# Patterns checked for a BEARISH scenario.
BEARISH_PATTERNS = [
    "engulfing", "hangingman", "shootingstar", "eveningstar",
    "eveningdojistar", "darkcloudcover", "3blackcrows", "gravestonedoji",
]

# How many of the most recent completed candles to check -- today's, or
# yesterday's if today's session hasn't produced a clean signal. Doesn't
# look further back than that: a pattern from a week ago isn't "the
# moment" of anything anymore.
CHECK_LAST_N_BARS = 2


# Human-readable names for each pattern's CDL_* column -- the raw column
# names have no word boundaries to split programmatically (e.g.
# "MORNINGSTAR" isn't "MORNING_STAR"), so this is an explicit mapping
# rather than an attempt to auto-format them.
PATTERN_DISPLAY_NAMES = {
    "CDL_ENGULFING": "Engulfing",
    "CDL_HAMMER": "Hammer",
    "CDL_INVERTEDHAMMER": "Inverted Hammer",
    "CDL_MORNINGSTAR": "Morning Star",
    "CDL_MORNINGDOJISTAR": "Morning Doji Star",
    "CDL_PIERCING": "Piercing Line",
    "CDL_3WHITESOLDIERS": "Three White Soldiers",
    "CDL_DRAGONFLYDOJI": "Dragonfly Doji",
    "CDL_HANGINGMAN": "Hanging Man",
    "CDL_SHOOTINGSTAR": "Shooting Star",
    "CDL_EVENINGSTAR": "Evening Star",
    "CDL_EVENINGDOJISTAR": "Evening Doji Star",
    "CDL_DARKCLOUDCOVER": "Dark Cloud Cover",
    "CDL_3BLACKCROWS": "Three Black Crows",
    "CDL_GRAVESTONEDOJI": "Gravestone Doji",
}


def detect_confirming_pattern(df: pd.DataFrame, direction: str) -> dict:
    """
    Checks the most recent CHECK_LAST_N_BARS completed candles for any
    recognized pattern agreeing with `direction` ("bullish" or "bearish"),
    most recent bar first.

    Returns {"confirmed": bool, "pattern": str or None, "bars_ago": int or
    None}. `pattern` is a human-readable name (e.g. "Engulfing", "Morning
    Star"); `bars_ago` is 0 for today's candle, 1 for yesterday's. Never
    raises: any failure (library missing, not enough data, detection
    error) just returns confirmed=False, same as every other confidence
    factor's failure handling.
    """
    empty = {"confirmed": False, "pattern": None, "bars_ago": None}
    if not _PANDAS_TA_AVAILABLE or len(df) < 10 or direction not in ("bullish", "bearish"):
        return empty

    wanted = BULLISH_PATTERNS if direction == "bullish" else BEARISH_PATTERNS
    look_for_positive = direction == "bullish"

    try:
        patterns = df.ta.cdl_pattern(name=wanted)
    except Exception as e:
        log.debug("Candlestick pattern detection failed: %s", e)
        return empty
    if patterns is None or patterns.empty:
        return empty

    recent = patterns.tail(CHECK_LAST_N_BARS)
    for bars_ago in range(len(recent)):
        row = recent.iloc[-(bars_ago + 1)]
        for col in patterns.columns:
            value = row[col]
            if pd.isna(value) or value == 0:
                continue
            fired_positive = value > 0
            if fired_positive == look_for_positive:
                pattern_name = PATTERN_DISPLAY_NAMES.get(col, col.replace("CDL_", "").title())
                return {"confirmed": True, "pattern": pattern_name, "bars_ago": bars_ago}

    return empty
