"""The one trendline fit, and the shape it is stored in.

`generate_trade_chart()` used to fit the trendline pair itself, immediately
before deciding its display window (the window is then widened to fit the
line's own touches). That made the chart endpoint's position untenable:
re-fitting there would have been a SECOND source of truth for the same line,
which is exactly what `chart_geometry.py` exists to prevent -- so the endpoint
left `trend_info` unset and a trendline-confirmed trade drew no overlay at all.

Both problems dissolve if the fit happens once and is written down. This module
is that once. The PNG and the API both read what it produced; neither fits.

**Points, not just slope and intercept.** `strongest_trendline_pair` returns
geometry in DISPLAY-WINDOW bar coordinates -- bar 0 is the leftmost visible
bar, which is a different origin for every window a caller chooses. Storing
slope and intercept alone would mean every reader had to reconstruct that
window to know where the line goes. The two endpoints are resolved here, once,
into absolute (epoch, price) pairs that mean the same thing to a matplotlib
axis and a lightweight-charts pane.

**`points` are the line's ENDS. `pivots` are the swing touches. They are not
the same thing and must never be conflated.** `points` is where the drawn
segment starts and stops -- two extrapolated positions at the window edges,
which no candle need ever have visited. `pivots` are the real bars that
touched the line and earned it its `strength` ("Trendline (6x)"). Drawing
`points` as the diamonds would put two markers under a label claiming six.
`trade_chart.py:752-760` records that exact bug being fixed once already, by
switching to detection-time touches; storing only the endpoints would
reintroduce it.

**`pair` is `strongest_trendline_pair`'s output, verbatim.** `trade_chart.py`
reads a pair keyed `"support"`/`"resistance"`, at seven sites. Keeping it
whole means the PNG reads the stored fit through the identical shape it
computes today -- one fit, one answer, and no behavioural change on the live
alert path. The top-level keys are the TRADE's own side, lifted out for
readers (the API, the browser) that only care about the line the plan rests
on.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from ..trendlines import strongest_trendline_pair

TRENDLINE_FIT_KEY = "trendline_fit"


def fit_trendline(df: pd.DataFrame, *, lookback: int, current_price: float,
                  is_bull: bool) -> dict | None:
    """Fit the trade's trendline and return it in storable form.

    A bull trade is drawn against SUPPORT -- the line it is holding above --
    and a bear against resistance. That is the side the plan's thesis rests
    on; drawing the other one would illustrate a trade nobody took.

    Returns None when nothing is drawable: too little history, no qualifying
    pivot pair, or a non-positive price. None is a normal outcome, not an
    error -- a candlestick-pattern-only confirmation has no trendline and
    never did.
    """
    pair = strongest_trendline_pair(df, lookback, current_price)
    if not pair:
        return None

    side = "support" if is_bull else "resistance"
    line = pair.get(side)
    if not line:
        return None

    window_bars = int(pair["window_bars"])
    if window_bars < 2 or len(df) < window_bars:
        return None

    # The display window's own bars, which is the coordinate system the slope
    # and intercept are expressed in.
    visible = df.tail(window_bars)
    slope = float(line["slope"])
    intercept = float(line["intercept"])

    first_x, last_x = 0, window_bars - 1
    points = [
        {"t": _epoch(visible.index[first_x]), "price": round(intercept + slope * first_x, 4)},
        {"t": _epoch(visible.index[last_x]), "price": round(intercept + slope * last_x, 4)},
    ]

    return {
        "slope": slope,
        "intercept": intercept,
        "points": points,
        "pivots": _absolute_pivots(visible, line.get("touches", []), window_bars),
        "side": side,
        "strength": int(line.get("strength", 0)),
        "window_bars": window_bars,
        "lookback": int(lookback),
        "fit_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pair": pair,
    }


def _absolute_pivots(visible: pd.DataFrame, touches, window_bars: int) -> list[dict]:
    """The line's swing touches, in absolute (epoch, price) form.

    `touches` arrive as `(x, price)` in display-window bar coordinates, x=0
    being the leftmost visible bar. Out-of-window entries are dropped rather
    than clamped: a clamped pivot would be drawn at a bar it never touched,
    which is a wrong diamond rather than a missing one.
    """
    out = []
    for touch in touches:
        try:
            x, price = int(touch[0]), float(touch[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not 0 <= x < window_bars:
            continue
        out.append({"t": _epoch(visible.index[x]), "price": round(price, 4)})
    return out


def _epoch(stamp) -> int:
    """A pandas index entry -> Unix seconds. One time type across the payload;
    see `models.ts` on what mixing representations costs."""
    return int(pd.Timestamp(stamp).tz_localize(None).timestamp())
