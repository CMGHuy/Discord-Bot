"""v209 V209-12: build the 2026-11-05 market-shock replay fixture.

The fixture is the sequence of snapshots the live shock pass would have seen on
2026-11-05 (Eastern Standard Time, session 14:30-21:00 UTC): one step per
15-minute bar end from 14:45 to 21:00 UTC, 26 in all. Each name's `last` is the
close of the last 15-minute bar finished by the step; `prev_close` and `atr14`
come from daily bars through 2026-11-04, derived by `shock_scan.build_snapshot`.

VIX is not fetchable by minute, so it is interpolated linearly from 0 % at
14:30 UTC to the tape reading at 15:20 UTC (21.13, +27.21 %), then held; the
fixture says so (`vix_interpolated`). When Alpaca cannot be used (no keys, a
fetch error, or fewer than `ShockThresholds().min_names` equities with both bar
sets) a synthetic sequence shaped on the day is written with the reason in
`note`. Each ticker's raw bars are checkpointed to
`market_data/shock_replay_2026_11_05/<TICKER>.json` (gitignored); a rerun skips
tickers already on disk.

Usage: python scripts/data/build_shock_replay_fixture.py [--tickers A,B] [--synthetic]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "scripts" / "data"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from alpaca_history.fetch import fetch_raw, to_store_frame  # noqa: E402
from alpaca_history.guards import TokenBucket  # noqa: E402
from fetch_alpaca_history import AlpacaAuthError, make_provider  # noqa: E402
from swingbot.core.marketdata import asset_class  # noqa: E402
from swingbot.core.market import shock  # noqa: E402
from swingbot.core.scanning import shock_scan  # noqa: E402

UTC = timezone.utc
SESSION = date(2026, 11, 5)


def _at(h: int, m: int) -> datetime:
    return datetime(SESSION.year, SESSION.month, SESSION.day, h, m, tzinfo=UTC)


OPEN_UTC = _at(14, 30)
CLOSE_UTC = _at(21, 0)
TURN_UTC = _at(14, 36)
STEP = timedelta(minutes=15)
VIX_TAPE_AT = _at(15, 20)
VIX_TAPE_LEVEL = 21.13
VIX_TAPE_CHG = 27.21
VIX_PRIOR = VIX_TAPE_LEVEL / (1 + VIX_TAPE_CHG / 100)
DAILY_START = date(2026, 7, 1)
DEFAULT_OUT = ROOT / "tests/fixtures/shock_replay_2026_11_05.json"
DEFAULT_CACHE = ROOT / "market_data/shock_replay_2026_11_05"
BENCHMARKS = ("SPY", "QQQ")
RATE_PER_MINUTE = 120
SYNTH_SECTORS = ("Information Technology", "Financials", "Health Care", "Industrials",
                 "Consumer Discretionary")
_COLS = ["open", "high", "low", "close", "volume"]


def step_times() -> list[datetime]:
    out, t = [], OPEN_UTC + STEP
    while t <= CLOSE_UTC:
        out.append(t)
        t += STEP
    return out


def vix_path(t: datetime) -> dict:
    frac = min(1.0, max(0.0, (t - OPEN_UTC) / (VIX_TAPE_AT - OPEN_UTC)))
    chg = VIX_TAPE_CHG * frac
    return {"level": round(VIX_PRIOR * (1 + chg / 100), 4), "chg_pct": round(chg, 4)}


def last_at(bars: pd.DataFrame | None, t: datetime) -> float | None:
    if bars is None or not len(bars):
        return None
    done = bars[bars.index + STEP <= t]
    return float(done["close"].iloc[-1]) if len(done) else None


def to_daily(raw: pd.DataFrame) -> pd.DataFrame:
    return to_store_frame("daily", raw)


def _round_row(row) -> dict | None:
    if row is None:
        return None
    return {k: round(v, 4) if isinstance(v, float) else v for k, v in asdict(row).items()}


def _minutes_since_open(t: datetime) -> float:
    return (t - OPEN_UTC).total_seconds() / 60.0


def fixture_step(t: datetime, daily: dict, bars15: dict, sector_of: Mapping[str, str]) -> dict:
    live = {tk: v for tk in daily if (v := last_at(bars15.get(tk), t)) is not None}
    snap = shock_scan.build_snapshot(
        daily, live, sector_of, now=t, quotes_at=t,
        vix=shock.VixTape(None, None, None), th=shock.ShockThresholds(),
        spy_ticker="SPY", spy_df=daily.get("SPY"))
    return {"as_of": t.isoformat(), "minutes_since_open": round(snap.minutes_since_open, 4),
            "vix": vix_path(t), "spy": _round_row(snap.spy), "qqq": _round_row(snap.qqq),
            "names": [_round_row(n) for n in sorted(snap.names, key=lambda n: n.ticker)]}


def _synth_name(i: int, down: bool) -> dict:
    prev, atr = 100.0, 2.0
    last = prev - (1.6 if down else 0.3) * atr
    return {"ticker": f"S{i + 1:02d}", "sector": SYNTH_SECTORS[i // 8], "last": last,
            "prev_close": prev, "atr14": atr, "is_equity": True}


def _synth_names(minutes: float) -> list[dict]:
    n_down = round((0.65 if minutes < 150 else 0.25) * 8)
    return [_synth_name(i, i % 8 < n_down) for i in range(40)]


def synthetic_steps() -> list[dict]:
    spy = {"ticker": "SPY", "sector": None, "last": 494.0, "prev_close": 500.0,
           "atr14": 5.0, "is_equity": False}
    qqq = {"ticker": "QQQ", "sector": None, "last": 391.0, "prev_close": 400.0,
           "atr14": 6.0, "is_equity": False}
    return [{"as_of": t.isoformat(), "minutes_since_open": _minutes_since_open(t),
             "vix": vix_path(t), "spy": spy, "qqq": qqq,
             "names": _synth_names(_minutes_since_open(t))} for t in step_times()]


def _rows(frame: pd.DataFrame | None):
    if frame is None:
        return None
    return [[ts.isoformat(), *[float(r[c]) for c in _COLS]] for ts, r in frame.iterrows()]


def _frame(rows) -> pd.DataFrame | None:
    if rows is None:
        return None
    frame = pd.DataFrame(rows, columns=["ts", *_COLS])
    frame.index = pd.to_datetime(frame.pop("ts"), utc=True)
    return frame


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def load_or_fetch(ticker, provider, limiter, cache_dir: Path):
    path = Path(cache_dir) / f"{ticker}.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return _frame(data["daily"]), _frame(data["m15"])
    daily = fetch_raw(provider, ticker, "daily", DAILY_START,
                      datetime(2026, 11, 5, tzinfo=UTC), limiter=limiter)
    m15 = fetch_raw(provider, ticker, "15min", SESSION, CLOSE_UTC, limiter=limiter)
    _atomic_write(path, {"daily": _rows(daily), "m15": _rows(m15)})
    return daily, m15


def long_entries(trades: list[dict]) -> list[dict]:
    keep = [t for t in trades if t.get("direction") == "bullish"
            and TURN_UTC <= datetime.fromisoformat(t["opened_at"]) < CLOSE_UTC]
    keep.sort(key=lambda t: datetime.fromisoformat(t["opened_at"]))
    return [{"ticker": t["ticker"], "opened_at": t["opened_at"]} for t in keep]


_TRADES_ERROR: list[str] = []


def _trades() -> list[dict]:
    try:
        from swingbot.core.scanning import singletons
        return list(singletons.trade_log.get_trades(limit=None))
    except Exception as exc:
        _TRADES_ERROR.append(type(exc).__name__)
        return []


def _fetch_all(tickers, provider, limiter, cache_dir):
    names = list(dict.fromkeys([*tickers, *BENCHMARKS]))
    daily, bars15 = {}, {}
    for i, tk in enumerate(names, 1):
        d, m = load_or_fetch(tk, provider, limiter, cache_dir)
        if d is not None and len(d):
            daily[tk] = to_daily(d)
        if m is not None and len(m):
            bars15[tk] = m
        if i % 10 == 0:
            print(f"[{i}/{len(names)}] {tk}", flush=True)
    return daily, bars15


def _synthetic_fixture(note: str) -> dict:
    return {"source": "synthetic", "vix_interpolated": True, "note": note,
            "steps": synthetic_steps()}


def build_fixture(tickers, *, provider, limiter, cache_dir) -> dict:
    from swingbot.core.scanning import fetch
    daily, bars15 = _fetch_all(tickers, provider, limiter, cache_dir)
    both = [t for t in daily if t in bars15]
    equities = [t for t in both if asset_class.classify(t) == "equity"]
    if len(equities) < shock.ShockThresholds().min_names:
        return _synthetic_fixture(
            f"alpaca: fewer than {shock.ShockThresholds().min_names} equities with daily + "
            f"15-minute bars ({len(equities)}); synthetic sequence shaped on the day")
    sector_of = fetch._sector_etfs_for_tickers(list(tickers))[0]
    daily = {t: daily[t] for t in both}
    steps = [fixture_step(t, daily, bars15, sector_of) for t in step_times()]
    note = (f"{len(both)} tickers with daily + 15-minute Alpaca bars; VIX interpolated "
            "linearly from the 15:20 UTC tape reading (21.13, +27.21%); long_entries "
            "comes from the trade log")
    return {"source": "alpaca", "vix_interpolated": True, "note": note, "steps": steps}


def _parse(argv) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tickers", default=None)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--synthetic", action="store_true")
    return ap.parse_args(argv)


def _tickers(args) -> list[str]:
    if args.tickers:
        return [t.strip() for t in args.tickers.split(",") if t.strip()]
    from swingbot.core.marketdata.watchlist import load_watchlist
    return list(load_watchlist())


def _build(args, provider, limiter) -> dict:
    if args.synthetic:
        return _synthetic_fixture("--synthetic requested; synthetic sequence shaped on the day")
    try:
        provider = provider or make_provider()
        limiter = limiter or TokenBucket(RATE_PER_MINUTE)
        return build_fixture(_tickers(args), provider=provider, limiter=limiter,
                             cache_dir=Path(args.cache_dir))
    except Exception as exc:
        return _synthetic_fixture(f"alpaca unavailable: {type(exc).__name__}: {exc}; "
                                  "synthetic sequence shaped on the day")


def main(argv=None, *, provider=None, limiter=None) -> int:
    args = _parse(argv)
    fixture = _build(args, provider, limiter)
    entries = long_entries(_trades())
    fixture["long_entries"] = entries
    if _TRADES_ERROR:
        fixture["note"] += f"; long entries unavailable: {_TRADES_ERROR[-1]}"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out}: {fixture['source']}, {len(fixture['steps'])} steps, "
          f"{len(entries)} long entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
