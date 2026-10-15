#!/usr/bin/env python3
"""v162: backfill and update the Alpaca history store data/market_data/ (spec §2).

    docker compose run --rm bot python scripts/data/fetch_alpaca_history.py
    docker compose run --rm bot python scripts/data/fetch_alpaca_history.py --mode update
    python scripts/data/fetch_alpaca_history.py --tickers AAPL,SPY --timeframes daily --root /tmp/s

15min (all sessions), hourly (from 30-minute bars, RTH) and daily bars from
the SIP tape, Adjustment.ALL, one calendar year per request. Refuses during
the US regular session (--force-hours overrides) and when free disk would drop
below 3 GB; at most 120 requests a minute beside the live scan. Each file is
written atomically and the manifests are saved per ticker, so a killed run
resumes; --force refetches files that are already complete.

Exit codes: 0 done, 1 a guard refused, 2 Alpaca rejected the key.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for _p in (ROOT, ROOT / "scripts" / "data"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import pandas as pd  # noqa: E402

from alpaca_history import fetch, guards, identity, store_io, update  # noqa: E402
from swingbot.core.marketdata import history_store  # noqa: E402
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402
from swingbot.core.marketdata.providers.alpaca_provider import SIP_DELAY, AlpacaAuthError  # noqa: E402

DEFAULT_START = "2016-01-01"
NO_BARS = "skipped: no Alpaca bars"
# Daily first: the intraday entries copy the daily status and identity.
RUN_ORDER = ("daily", "hourly", "15min")


@dataclass
class RunSummary:
    written: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    refetched: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    flagged: dict[str, str] = field(default_factory=dict)
    requests: int = 0

    def render(self) -> str:
        lines = [f"written {len(self.written)}, unchanged {len(self.unchanged)}, "
                 f"refetched {len(self.refetched)}, skipped {len(self.skipped)}, "
                 f"flagged {len(self.flagged)}, requests {self.requests}"]
        lines += [f"  skipped {key}: {why}" for key, why in sorted(self.skipped.items())]
        lines += [f"  flagged {key}: {why}" for key, why in sorted(self.flagged.items())]
        return "\n".join(lines)


@dataclass
class _Run:
    """What one ticker's fetch needs, built once per run."""
    root: Path
    start: str
    timeframes: tuple[str, ...]
    force: bool
    provider: object
    limiter: guards.TokenBucket
    now: datetime
    backtest_dir: Path
    market_dir: Path

    @property
    def stamp(self) -> str:
        return self.now.strftime("%Y-%m-%dT%H:%M:%SZ")


def _csv_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def _timeframes(text: str) -> tuple[str, ...]:
    asked = _csv_list(text)
    bad = [tf for tf in asked if tf not in history_store.TIMEFRAMES]
    if bad or not asked:
        raise argparse.ArgumentTypeError(
            f"unknown timeframe(s) {bad or text!r}; choose from {','.join(RUN_ORDER)}")
    return tuple(tf for tf in RUN_ORDER if tf in asked)


def _iso_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {text!r}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    from swingbot.core.marketdata import backtest_cache
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--timeframes", type=_timeframes, default="15min,hourly,daily")
    ap.add_argument("--start", type=_iso_date, default=DEFAULT_START)
    ap.add_argument("--tickers", default=None,
                    help="comma list (default: the watchlist plus the market-regime benchmark)")
    ap.add_argument("--mode", choices=("full", "update"), default="full")
    ap.add_argument("--force", action="store_true", help="refetch files that are already complete")
    ap.add_argument("--force-hours", action="store_true",
                    help="run during the US regular session anyway")
    ap.add_argument("--root", type=Path, default=None,
                    help="store root (default: HISTORY_STORE_DIR or data/market_data)")
    ap.add_argument("--backtest-dir", type=Path, default=None,
                    help="identity reference (default: data/backtest_cache)")
    ap.add_argument("--market-dir", type=Path, default=None,
                    help="identity fallback (default: market_data/daily)")
    args = ap.parse_args(argv)
    args.root = args.root or history_store.store_root()
    args.backtest_dir = args.backtest_dir or Path(backtest_cache.CACHE_DIR)
    args.market_dir = args.market_dir or ROOT / "market_data" / "daily"
    return args


def _resolve_tickers(args: argparse.Namespace) -> list[str]:
    if args.tickers:
        return sorted({t.upper() for t in _csv_list(args.tickers)})
    import fetch_backtest_data
    from swingbot import config
    return fetch_backtest_data.training_tickers(
        fetch_backtest_data.load_watchlist(), config.MARKET_REGIME_TICKER, None)


def _tickers(args: argparse.Namespace) -> list[str]:
    """The run's tickers, resolved once (the watchlist is read a single time)."""
    if getattr(args, "ticker_list", None) is None:
        args.ticker_list = _resolve_tickers(args)
    return args.ticker_list


def make_provider():
    from swingbot import config
    from swingbot.core.marketdata.providers.alpaca_provider import AlpacaProvider
    if not (config.ALPACA_API_KEY_ID and config.ALPACA_API_SECRET_KEY):
        raise AlpacaAuthError("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not set")
    return AlpacaProvider(config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY,
                          config.ALPACA_DATA_FEED_LIVE)


def _make_run(args, provider, limiter, now: datetime) -> _Run:
    return _Run(root=Path(args.root), start=args.start, timeframes=tuple(args.timeframes),
                force=args.force, provider=provider, limiter=limiter, now=now,
                backtest_dir=Path(args.backtest_dir), market_dir=Path(args.market_dir))


def _store_path(root: Path, timeframe: str, ticker: str) -> Path:
    return Path(root) / timeframe / f"{safe_symbol(ticker)}.csv"


def _manifests(root: Path) -> dict[str, dict]:
    return {tf: store_io.load_manifest(root, tf) for tf in history_store.TIMEFRAMES}


def _save(run: _Run, manifests: dict[str, dict], timeframes) -> None:
    for tf in timeframes:
        store_io.save_manifest(run.root, tf, manifests[tf], now=run.now)


def _todo(run: _Run, manifests: dict[str, dict], ticker: str) -> list[str]:
    if run.force:
        return list(run.timeframes)
    return [tf for tf in run.timeframes
            if not store_io.is_complete(manifests[tf]["tickers"].get(ticker), run.start)]


def _record_skip(ticker: str, reason: str, run: _Run, manifests, summary: RunSummary) -> None:
    summary.skipped[ticker] = reason
    stale = [tf for tf in run.timeframes
             if (manifests[tf]["tickers"].get(ticker) or {}).get("status") != reason]
    for tf in stale:
        manifests[tf]["tickers"][ticker] = store_io.skipped_entry(
            reason, start=run.start, fetched_at=run.stamp)
    if stale:
        _save(run, manifests, stale)


def _fetch(run: _Run, ticker: str, timeframe: str) -> pd.DataFrame | None:
    return fetch.fetch_store_frame(run.provider, ticker, timeframe,
                                   date.fromisoformat(run.start), run.now - SIP_DELAY,
                                   limiter=run.limiter)


def _daily_identity(ticker: str, run: _Run, manifests, todo: list[str]):
    """(status, identity dict, trimmed daily frame or None). Reuses the stored
    daily verdict when daily itself is not being refetched."""
    entry = manifests["daily"]["tickers"].get(ticker) or {}
    if "daily" not in todo and entry.get("identity") is not None:
        return entry["status"], entry["identity"], None
    daily = _fetch(run, ticker, "daily")
    if daily is None:
        return NO_BARS, None, None
    reference = identity.reference_frame(ticker, backtest_dir=run.backtest_dir,
                                         market_dir=run.market_dir)
    result, trimmed = identity.identity_check(daily, reference)
    if trimmed is None or not len(trimmed):
        return NO_BARS, None, None
    return result.status, result.to_json(), trimmed


def _trim(frame: pd.DataFrame | None, dropped_before: str | None) -> pd.DataFrame | None:
    if frame is not None and dropped_before:
        frame = frame[frame.index >= pd.Timestamp(dropped_before)]
    return frame if frame is not None and len(frame) else None


def _write(ticker, timeframe, frame, run: _Run, manifests, status, ident) -> None:
    sha = store_io.write_frame(frame, _store_path(run.root, timeframe, ticker), timeframe)
    manifests[timeframe]["tickers"][ticker] = store_io.ok_entry(
        frame, timeframe, start=run.start, sha256=sha, identity=ident, status=status,
        fetched_at=run.stamp)


def _write_timeframes(ticker, todo, run: _Run, manifests, verdict, summary) -> None:
    status, ident, daily = verdict
    dropped = (ident or {}).get("dropped_before")
    for tf in todo:
        frame = daily if tf == "daily" else _trim(_fetch(run, ticker, tf), dropped)
        if frame is None:
            manifests[tf]["tickers"][ticker] = store_io.skipped_entry(
                NO_BARS, start=run.start, fetched_at=run.stamp)
            summary.skipped[f"{ticker}/{tf}"] = NO_BARS
            continue
        _write(ticker, tf, frame, run, manifests, status, ident)
        summary.written.append(f"{ticker}/{tf}")


def full_ticker(ticker: str, run: _Run, summary: RunSummary) -> None:
    """Fetch every to-do timeframe of one ticker and save the manifests it changed."""
    manifests = _manifests(run.root)
    reason = identity.skip_reason(ticker)
    if reason:
        _record_skip(ticker, reason, run, manifests, summary)
        return
    todo = _todo(run, manifests, ticker)
    if not todo:
        summary.unchanged += [f"{ticker}/{tf}" for tf in run.timeframes]
        return
    verdict = _daily_identity(ticker, run, manifests, todo)
    if verdict[0] == NO_BARS:
        _record_skip(ticker, NO_BARS, run, manifests, summary)
        return
    if verdict[0] != "ok":
        summary.flagged[ticker] = verdict[0]
    _write_timeframes(ticker, todo, run, manifests, verdict, summary)
    _save(run, manifests, todo)


def run_full(args, provider, limiter: guards.TokenBucket, now: datetime) -> RunSummary:
    run = _make_run(args, provider, limiter, now)
    summary = RunSummary()
    tickers = _tickers(args)
    progress = guards.Progress(len(tickers))
    for ticker in tickers:
        progress.step(ticker)
        full_ticker(ticker, run, summary)
    summary.requests = limiter.calls
    return summary


def _updatable(run: _Run, ticker: str) -> bool:
    """True when daily and every requested timeframe already have a stored file."""
    manifests = _manifests(run.root)
    for tf in {"daily", *run.timeframes}:
        entry = manifests[tf]["tickers"].get(ticker) or {}
        if not entry.get("sha256") or not _store_path(run.root, tf, ticker).exists():
            return False
    return True


_OUTCOME_FIELD = {"unchanged": "unchanged", "appended": "written", "refetched": "refetched"}


def _update_one(ticker: str, run: _Run, summary: RunSummary) -> None:
    if identity.skip_reason(ticker) or not _updatable(run, ticker):
        full_ticker(ticker, run, summary)
        return
    daily = store_io.load_manifest(run.root, "daily")["tickers"][ticker]
    outcome = update.update_ticker(
        ticker, root=run.root, provider=run.provider, limiter=run.limiter, now=run.now,
        timeframes=run.timeframes, start=date.fromisoformat(daily["start"]))
    tfs = history_store.TIMEFRAMES if outcome == "refetched" else run.timeframes
    getattr(summary, _OUTCOME_FIELD[outcome]).extend(f"{ticker}/{tf}" for tf in tfs)
    if daily["status"] != "ok":
        summary.flagged[ticker] = daily["status"]


def run_update(args, provider, limiter: guards.TokenBucket, now: datetime) -> RunSummary:
    run = _make_run(args, provider, limiter, now)
    summary = RunSummary()
    tickers = _tickers(args)
    progress = guards.Progress(len(tickers))
    for ticker in tickers:
        progress.step(ticker)
        _update_one(ticker, run, summary)
    summary.requests = limiter.calls
    return summary


_RUNNERS = {"full": run_full, "update": run_update}


def make_limiter() -> guards.TokenBucket:
    """The run's rate limiter (120 a minute). A seam so tests can swap in a
    bucket on a fake clock instead of sleeping 0.5 s per request."""
    return guards.TokenBucket()


def _utc_now(now: datetime | None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)


def _pending(args) -> int:
    """Tickers that still have a timeframe to fetch (all of them with --force)."""
    tickers = _tickers(args)
    if args.force or args.mode == "update":
        return len(tickers)
    manifests = {tf: store_io.load_manifest(Path(args.root), tf) for tf in args.timeframes}
    return sum(1 for t in tickers
               if any(not store_io.is_complete(manifests[tf]["tickers"].get(t), args.start)
                      for tf in args.timeframes))


def _preflight(args, now: datetime) -> None:
    """Hours guard, then the disk guard. Update mode needs room for one
    ticker's full lockstep refetch (temp file beside the old one) at a time."""
    guards.assert_outside_hours(now, force=args.force_hours)
    Path(args.root).mkdir(parents=True, exist_ok=True)
    years = max((now.date() - date.fromisoformat(args.start)).days / 365.25, 0.0)
    n = 1 if args.mode == "update" else _pending(args)
    guards.check_disk(Path(args.root), guards.estimate_bytes(n, args.timeframes, years))


def main(argv: list[str] | None = None, *, provider=None, now: datetime | None = None) -> int:
    args = parse_args(argv)
    now = _utc_now(now)
    try:
        _preflight(args, now)
        provider = provider or make_provider()
        summary = _RUNNERS[args.mode](args, provider, make_limiter(), now)
    except (guards.HoursGuardError, guards.DiskGuardError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    except AlpacaAuthError as exc:
        print(f"stopped: Alpaca rejected the key ({exc})", file=sys.stderr)
        return 2
    print(summary.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
