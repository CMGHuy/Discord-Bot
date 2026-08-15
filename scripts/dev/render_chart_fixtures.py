#!/usr/bin/env python
"""
Renders one trade-chart PNG per confirming-overlay kind and hashes each
file -- the acceptance instrument for SR32's geometry extraction.

The extraction moves every overlay's geometry computation out of
chart_strategy_overlay.py into chart_geometry.py and rewrites the
drawing to consume that data. The only acceptable outcome of a pure
refactor is that the PNGs the bot posts to Discord do not change by a
single byte, and "looks the same" is not a check anyone can run twice.
So: render the full set before, render it again after, compare hashes.

    python scripts/render_chart_fixtures.py --out /tmp/chart-baseline
    # ... refactor ...
    python scripts/render_chart_fixtures.py --out /tmp/chart-after
    python scripts/render_chart_fixtures.py --check /tmp/chart-baseline/SHA256 --out /tmp/chart-after

The manifest is written in `sha256sum` format so `sha256sum -c SHA256`
works too, but --check is the portable path (this repo runs on Windows,
where sha256sum is not a given).

Every fixture frame is built arithmetically from a closing series -- no
RNG anywhere, seeded or otherwise -- so two runs of this script on one
machine differ only if the rendering code changed. The frames are shaped
to make each overlay actually computable: the FVG case really does leave
an unfilled three-bar gap, the Pivot case really does swing far enough
for the zigzag detector to register, and so on. A fixture whose source
silently fails to compute would render an identical PNG before and after
any refactor while testing nothing at all, which is the failure mode this
whole file exists to avoid -- so --verify-overlays asserts that each one
drew.
"""
import argparse
import hashlib
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import matplotlib
matplotlib.use("Agg")

from swingbot.core.charts.trade_chart import generate_trade_chart  # noqa: E402


def _ohlcv(closes, spread_pct=1.5, highs=None, lows=None, start="2019-01-01"):
    """An OHLCV frame from a closing series -- same construction as
    tests/conftest.make_ohlcv, duplicated rather than imported because a
    script that renders the bot's real charts should not depend on the
    test package. `highs`/`lows` override the straddle for fixtures that
    need a specific bar geometry (the FVG gap)."""
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    idx = pd.bdate_range(start, periods=n)
    half = closes * (spread_pct / 100) / 2
    return pd.DataFrame(
        {
            "Open": np.concatenate([[closes[0]], closes[:-1]]),
            "High": closes + half if highs is None else np.asarray(highs, dtype=float),
            "Low": closes - half if lows is None else np.asarray(lows, dtype=float),
            "Close": closes,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def _trending_df(n=90, daily_pct=0.25, start_price=100.0):
    closes = start_price * (1 + daily_pct / 100) ** np.arange(n)
    return _ohlcv(closes)


def _fvg_df(n=60):
    """A frame with one unfilled bullish fair value gap near the right
    edge. find_fair_value_gaps_detailed looks for low[i] > high[i-2] and
    then requires no later bar to trade back into the gap, so the jump
    has to happen late and price has to keep climbing afterwards."""
    closes = [100 + i * 0.2 for i in range(n)]
    jump_at = n - 6
    for i in range(jump_at, n):
        closes[i] += 12.0
    df = _ohlcv(closes, spread_pct=1.0)
    # Widen the gap explicitly: the bar two before the jump must top out
    # below where the jump bar bottoms.
    df.iloc[jump_at - 2, df.columns.get_loc("High")] = closes[jump_at - 2] + 0.1
    df.iloc[jump_at, df.columns.get_loc("Low")] = closes[jump_at] - 0.1
    return df


def _oscillating_df(n=120, drift_pct=0.3, amp=8.0, period=7):
    """An uptrend with enough swing structure for
    trendlines.strongest_trendline_pair() to actually FIT a line.

    A smooth arithmetic trend has no pivots, so the trendline scanner
    returns None on one and the chart draws no trendline at all -- a
    fixture named "trendline" that contains no trendline pins nothing and
    quietly misleads whoever reads it next. These parameters were chosen
    because they yield BOTH sides (support at 5 touches, resistance at 6),
    so the diamonds and the "Nx" strength label are on the chart too.
    """
    i = np.arange(n)
    closes = 100.0 * (1 + drift_pct / 100) ** i + amp * np.sin(2 * np.pi * i / period)
    return _ohlcv(closes)


def _zigzag_df(n=60):
    """A frame whose last 20 bars contain a completed down-then-up swing
    large enough for zigzag_pivots(threshold_pct=3) to confirm a low
    inside the chart's default 20-bar display window. A pivot older than
    that window is deliberately skipped by the drawing code, so a gentler
    series would render nothing."""
    closes = [100.0 + i * 0.1 for i in range(n - 20)]
    closes += [closes[-1] * (1 - 0.012) ** i for i in range(1, 9)]   # down ~10%
    closes += [closes[-1] * (1 + 0.014) ** i for i in range(1, 13)]  # back up ~18%
    return _ohlcv(closes[:n], spread_pct=1.2)


# name -> (frame, kwargs). One per shape kind in spec Decision 10's
# table, plus the marker kind a zigzag Pivot needs, plus the case where
# no source is drawable at all (which falls back to the plain
# support/resistance trendlines and must be pinned too).
FIXTURES = {
    "curve_ema": (
        _trending_df(),
        dict(target_sources=["EMA20"], stop_sources=["EMA50"], horizon={"vwap_window": 20}),
    ),
    "fib_fan": (
        _trending_df(n=70, daily_pct=0.4),
        dict(target_sources=["Fib 61.8%"], stop_sources=["Swing low"], horizon={"fib_lookback": 40}),
    ),
    "fvg_zone": (
        _fvg_df(),
        dict(target_sources=["FVG bullish"], stop_sources=[], horizon={}),
    ),
    "horizontal_rolling": (
        _trending_df(n=60, daily_pct=0.15),
        dict(target_sources=["Rolling resistance"], stop_sources=["Floor S1"],
             horizon={"sr_lookback": 20}),
    ),
    "horizontal_hvn": (
        _trending_df(n=80, daily_pct=0.1),
        dict(target_sources=["Volume Profile HVN"], stop_sources=[], horizon={"sr_lookback": 30}),
    ),
    "trendline": (
        _oscillating_df(),
        dict(target_sources=["Trendline (resistance)"], stop_sources=["Trendline (support)"],
             horizon={}, trendline_lookback=60),
    ),
    "marker_pivot": (
        _zigzag_df(),
        dict(target_sources=["Pivot low"], stop_sources=[], horizon={"max_risk_pct": 3.0}),
    ),
    # The secondary drawer is the same geometry at reduced opacity with no
    # label, so the extraction has to keep it identical too. Between them
    # these two fixtures put every one of its five branches -- EMA, VWAP,
    # Fib, Bollinger, Volume Profile -- on a chart. Which source ends up
    # secondary is positional, not by rank (the caller slices [1:3] and
    # then drops whichever is primary), so the ORDER of these lists is
    # load-bearing: a higher-priority source at index 1 becomes primary
    # and its secondary branch never runs.
    "secondary_sources": (
        _fvg_df(n=90),
        dict(target_sources=["FVG bullish", "Volume Profile HVN", "EMA20"],
             stop_sources=["Fib 38.2%", "VWAP"],
             horizon={"vwap_window": 20, "fib_lookback": 40, "sr_lookback": 20}),
    ),
    "secondary_bollinger": (
        _oscillating_df(),
        dict(target_sources=["Trendline (resistance)", "Bollinger upper", "Fib 50.0%"],
             stop_sources=[],
             horizon={"fib_lookback": 40}, trendline_lookback=60),
    ),
    "no_drawable_source": (
        # Oscillating, not smooth: with no drawable source on either side
        # the chart falls back to drawing BOTH trendline sides in their
        # fixed support/resistance colors, and a frame the scanner can't
        # fit a line on would pin that fallback drawing nothing at all.
        _oscillating_df(),
        # "Hammer" is a candlestick pattern confidence.py appends, not a
        # price level -- _pick_primary_source returns None for it on both
        # sides, which is the fallback path.
        dict(target_sources=["Hammer"], stop_sources=["Bullish Engulfing"], horizon={}),
    ),
}


def render_all(out_dir: str) -> dict:
    """Renders every fixture into `out_dir`. Returns {filename: sha256}."""
    os.makedirs(out_dir, exist_ok=True)
    digests = {}
    for name in sorted(FIXTURES):
        df, kwargs = FIXTURES[name]
        last = float(df["Close"].iloc[-1])
        path = generate_trade_chart(
            "FIXT", df,
            entry=last,
            stop_loss=last * 0.94,
            take_profit=last * 1.08,
            direction="bullish",
            strategy="Fixture",
            horizon_label="4 Weeks",
            out_dir=out_dir,
            filename=f"{name}.png",
            target2=last * 1.14,
            currency_symbol="$",
            **kwargs,
        )
        with open(path, "rb") as fh:
            digests[os.path.basename(path)] = hashlib.sha256(fh.read()).hexdigest()
        print(f"  rendered {name}.png  {digests[os.path.basename(path)][:16]}", flush=True)
    return digests


def verify_overlays() -> int:
    """Asserts each fixture's primary source is actually drawable, so a
    silently-failing overlay can't masquerade as a passing refactor."""
    from swingbot.core.charts.chart_geometry import overlay_geometry, _pick_primary_source
    from swingbot.core.trendlines import strongest_trendline_pair

    failures = 0
    for name in sorted(FIXTURES):
        df, kwargs = FIXTURES[name]
        expect_none = name == "no_drawable_source"
        # A Trendline overlay is the one shape chart_geometry refuses to
        # derive on its own: the fit needs the entry price and happens in
        # generate_trade_chart before the display window exists, so the
        # geometry converts that result instead of re-fitting it (one
        # source of truth for the line). Mirror what generate_trade_chart
        # does here so the trendline branch is actually exercised.
        #
        # These two fixtures' frames are smooth arithmetic trends with no
        # pivot structure, so strongest_trendline_pair() finds nothing to
        # fit and generate_trade_chart draws NO trendline on them either
        # (_draw_side_trendline returns early on a null trend_info) -- a
        # null overlay is therefore the correct expectation, and it is
        # derived from the same fit rather than hardcoded so a future
        # fixture with real swing structure verifies the real shape.
        trend_info, window_bars = None, 0
        primary = _pick_primary_source(kwargs["target_sources"])
        if primary and primary.startswith("Trendline"):
            trend_info = strongest_trendline_pair(
                df, kwargs.get("trendline_lookback", 90), float(df["Close"].iloc[-1]))
            window_bars = trend_info["window_bars"] if trend_info else 0
            expect_none = not (trend_info or {}).get("resistance")  # bullish fixtures -> target side
        geom = overlay_geometry(
            df, "target", kwargs["target_sources"],
            horizon=kwargs.get("horizon") or {},
            recent_len=max(min(20, len(df)), window_bars),
            trend_info=trend_info, trendline_window_bars=window_bars,
        )
        ok = (geom is None) if expect_none else (geom is not None)
        kind = geom["shape"]["kind"] if geom else None
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: {kind}", flush=True)
        failures += 0 if ok else 1
    return failures


def write_manifest(digests: dict, path: str):
    with open(path, "w", newline="\n") as fh:
        for name in sorted(digests):
            fh.write(f"{digests[name]}  {name}\n")


def read_manifest(path: str) -> dict:
    out = {}
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                digest, name = line.split(None, 1)
                out[name.strip()] = digest
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="directory to render into")
    ap.add_argument("--check", metavar="MANIFEST",
                    help="compare the rendered hashes against this SHA256 manifest")
    ap.add_argument("--verify-overlays", action="store_true",
                    help="assert every fixture's overlay is computable, then exit")
    args = ap.parse_args()

    if args.verify_overlays:
        print("Verifying fixture overlays are drawable:")
        failures = verify_overlays()
        print("OK -- every fixture overlay resolves" if not failures
              else f"FAILED -- {failures} fixture(s) resolve to the wrong thing")
        return 1 if failures else 0

    print(f"Rendering {len(FIXTURES)} chart fixtures into {args.out}")
    digests = render_all(args.out)
    manifest = os.path.join(args.out, "SHA256")
    write_manifest(digests, manifest)
    print(f"Wrote {manifest}")

    if not args.check:
        return 0

    expected = read_manifest(args.check)
    missing = sorted(set(expected) - set(digests))
    extra = sorted(set(digests) - set(expected))
    changed = sorted(n for n in set(expected) & set(digests) if expected[n] != digests[n])

    for name in missing:
        print(f"  MISSING  {name}")
    for name in extra:
        print(f"  NEW      {name}")
    for name in changed:
        print(f"  CHANGED  {name}\n           expected {expected[name]}\n           got      {digests[name]}")

    if missing or extra or changed:
        print(f"\nFAILED -- {len(changed)} changed, {len(missing)} missing, {len(extra)} new. "
              "A pure refactor must leave every hash untouched.")
        return 1
    print(f"\nOK -- all {len(digests)} renders byte-identical to the baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
