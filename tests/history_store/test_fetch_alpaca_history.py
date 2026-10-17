"""v162 AH7: the backfill CLI in full mode -- guards, skips, identity flags, resume."""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from alpaca_history import guards
from swingbot.core.marketdata.providers import alpaca_provider as ap

ROOT = Path(__file__).resolve().parents[2]
NY = ZoneInfo("America/New_York")
UTC = timezone.utc
NOW = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)            # a Saturday: outside the session
IN_SESSION = datetime(2024, 5, 28, 15, 0, tzinfo=UTC)    # Tuesday 11:00 ET
DAYS = pd.bdate_range("2023-01-02", "2024-05-31")
TF = ("daily", "hourly", "15min")


def load_cli():
    spec = importlib.util.spec_from_file_location(
        "fetch_alpaca_history", ROOT / "scripts" / "data" / "fetch_alpaca_history.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve string annotations via sys.modules
    spec.loader.exec_module(mod)
    mod.make_limiter = _fast_limiter
    return mod


def _fast_limiter():
    """AH3's bucket on a clock that jumps 60 s per read, so it never sleeps."""
    ticks = itertools.count(0.0, 60.0)
    return guards.TokenBucket(clock=lambda: next(ticks), sleep=lambda s: None)


def daily_closes(days, base: float = 100.0) -> np.ndarray:
    return base + 0.1 * np.arange(len(days))


def _utc_index(naive_ny) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(naive_ny).tz_localize(NY).tz_convert("UTC")


def _frame(index_utc, closes) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": closes, "high": closes + 1, "low": closes - 1, "close": closes,
                         "volume": np.full(len(closes), 1000.0)}, index=index_utc)


class FakeHistory:
    """Stands in for AlpacaProvider.history_bars: daily bars on `days`, intraday
    bars 04:00-20:00 ET on the last two of them, every price times `scale`."""

    def __init__(self, tickers, days=DAYS, scale: float = 1.0, error: Exception | None = None):
        self.tickers = set(tickers)
        self.days = days
        self.scale = scale
        self.error = error
        self.calls: list[tuple[str, str, datetime, datetime]] = []

    def _bars(self, timeframe: str) -> pd.DataFrame:
        if timeframe == "1d":
            return _frame(_utc_index(self.days), daily_closes(self.days) * self.scale)
        stamps = [ts for d in self.days[-2:]
                  for ts in pd.date_range(d + pd.Timedelta(hours=4), d + pd.Timedelta(hours=20),
                                          freq=timeframe, inclusive="left")]
        return _frame(_utc_index(stamps), np.full(len(stamps), 150.0) * self.scale)

    def history_bars(self, ticker, timeframe, start, end):
        self.calls.append((ticker, timeframe, start, end))
        if self.error is not None:
            raise self.error
        if ticker not in self.tickers:
            return None
        frame = self._bars(timeframe)
        part = frame[(frame.index >= start) & (frame.index <= end)]
        return part if len(part) else None


def write_reference(directory: Path, ticker: str, days, closes) -> None:
    closes = np.asarray(closes, dtype=float)
    frame = pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                          "Volume": 1.0}, index=pd.DatetimeIndex(days, name="Date"))
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(directory / f"{ticker}.csv")


@pytest.fixture
def dirs(tmp_path, store_root):
    bt, md = tmp_path / "backtest_cache", tmp_path / "market_daily"
    md.mkdir()
    earlier = pd.bdate_range("2022-01-03", "2022-12-30")
    write_reference(bt, "AAPL", earlier.append(DAYS),
                    np.concatenate([np.full(len(earlier), 90.0), daily_closes(DAYS)]))
    late = DAYS[DAYS >= "2024-01-02"]
    write_reference(bt, "SNDK", late, daily_closes(DAYS)[DAYS >= "2024-01-02"])
    write_reference(bt, "MSFT", DAYS, daily_closes(DAYS) * 2)
    return {"root": store_root, "bt": bt, "md": md}


def _argv(dirs, tickers: str, *extra: str) -> list[str]:
    return ["--tickers", tickers, "--start", "2023-01-01", "--root", str(dirs["root"]),
            "--backtest-dir", str(dirs["bt"]), "--market-dir", str(dirs["md"]), *extra]


def _manifest(root: Path, tf: str) -> dict:
    return json.loads((root / tf / "_manifest.json").read_text())


def test_full_run_writes_three_timeframes_with_hashed_manifests(dirs):
    cli = load_cli()
    assert cli.main(_argv(dirs, "AAPL"), provider=FakeHistory(["AAPL"]), now=NOW) == 0
    for tf in TF:
        path = dirs["root"] / tf / "AAPL.csv"
        entry = _manifest(dirs["root"], tf)["tickers"]["AAPL"]
        assert entry["status"] == "ok" and entry["start"] == "2023-01-01"
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert entry["rows"] == len(pd.read_csv(path))
        assert entry["identity"]["status"] == "ok"
    assert _manifest(dirs["root"], "daily")["feed"] == "sip"
    m15 = pd.read_csv(dirs["root"] / "15min" / "AAPL.csv", index_col="Datetime", parse_dates=True)
    assert m15.index[0].strftime("%H:%M") == "04:00" and len(m15) == 128
    hourly = pd.read_csv(dirs["root"] / "hourly" / "AAPL.csv", index_col="Datetime", parse_dates=True)
    assert len(hourly) == 14 and hourly.index[-1].strftime("%H:%M") == "15:30"


def test_identity_flags_are_written_inherited_and_listed(dirs, capsys):
    cli = load_cli()
    tickers = "AAPL,SNDK,MSFT,NVDA"
    assert cli.main(_argv(dirs, tickers), provider=FakeHistory(tickers.split(",")), now=NOW) == 0
    daily = _manifest(dirs["root"], "daily")["tickers"]
    assert daily["SNDK"]["status"] == "flagged: short-overlap"
    assert daily["MSFT"]["status"] == "flagged: price-mismatch"
    assert daily["NVDA"]["status"] == "flagged: no-reference"
    assert daily["SNDK"]["identity"]["dropped_before"] == "2024-01-02"
    first = pd.read_csv(dirs["root"] / "daily" / "SNDK.csv", index_col="Date", parse_dates=True).index[0]
    assert first == pd.Timestamp("2024-01-02")
    for tf in ("hourly", "15min"):
        entry = _manifest(dirs["root"], tf)["tickers"]["SNDK"]
        assert entry["status"] == "flagged: short-overlap"
        assert entry["identity"] == daily["SNDK"]["identity"]
    out = capsys.readouterr().out
    assert "flagged SNDK: flagged: short-overlap" in out and "flagged NVDA" in out


def test_skips_are_recorded_with_reasons_and_make_no_request(dirs, capsys):
    cli = load_cli()
    prov = FakeHistory([])
    assert cli.main(_argv(dirs, "XAUUSD,GC=F,^VIX"), provider=prov, now=NOW) == 0
    assert prov.calls == []
    for tf in TF:
        tickers = _manifest(dirs["root"], tf)["tickers"]
        for t in ("XAUUSD", "GC=F", "^VIX"):
            assert tickers[t]["status"].startswith("skipped: ") and tickers[t]["rows"] == 0
            assert tickers[t]["sha256"] is None
    out = capsys.readouterr().out
    assert "skipped XAUUSD: skipped: spot metal" in out and "skipped GC=F: skipped: futures" in out


def test_a_ticker_alpaca_does_not_serve_is_skipped_no_bars(dirs):
    cli = load_cli()
    assert cli.main(_argv(dirs, "AMZN"), provider=FakeHistory([]), now=NOW) == 0
    assert _manifest(dirs["root"], "daily")["tickers"]["AMZN"]["status"] == cli.NO_BARS
    assert not (dirs["root"] / "daily" / "AMZN.csv").exists()


def test_rerun_skips_complete_files_unless_forced(dirs):
    cli = load_cli()
    cli.main(_argv(dirs, "AAPL"), provider=FakeHistory(["AAPL"]), now=NOW)
    manifest_before = (dirs["root"] / "daily" / "_manifest.json").read_text()
    again = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL"), provider=again, now=NOW) == 0
    assert again.calls == []
    assert (dirs["root"] / "daily" / "_manifest.json").read_text() == manifest_before
    forced = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL", "--force"), provider=forced, now=NOW) == 0
    assert {c[1] for c in forced.calls} == {"1d", "30min", "15min"}


def test_an_earlier_start_is_not_covered_and_refetches(dirs):
    cli = load_cli()
    cli.main(_argv(dirs, "AAPL"), provider=FakeHistory(["AAPL"]), now=NOW)
    earlier = FakeHistory(["AAPL"])
    argv = _argv(dirs, "AAPL")
    argv[argv.index("2023-01-01")] = "2022-06-01"
    assert cli.main(argv, provider=earlier, now=NOW) == 0
    assert earlier.calls
    assert _manifest(dirs["root"], "daily")["tickers"]["AAPL"]["start"] == "2022-06-01"


def test_intraday_only_rerun_reuses_the_stored_daily_identity(dirs):
    cli = load_cli()
    cli.main(_argv(dirs, "AAPL", "--timeframes", "daily"), provider=FakeHistory(["AAPL"]), now=NOW)
    prov = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL", "--timeframes", "15min"), provider=prov, now=NOW) == 0
    assert {c[1] for c in prov.calls} == {"15min"}
    assert _manifest(dirs["root"], "15min")["tickers"]["AAPL"]["status"] == "ok"


def test_hours_guard_refuses_in_session_unless_forced(dirs):
    cli = load_cli()
    prov = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL"), provider=prov, now=IN_SESSION) == 1
    assert prov.calls == []
    assert cli.main(_argv(dirs, "AAPL", "--force-hours"), provider=prov, now=IN_SESSION) == 0


def test_disk_guard_refusal_exits_1(dirs, monkeypatch):
    cli = load_cli()

    def refuse(path, needed, **kw):
        raise cli.guards.DiskGuardError("free space would drop below 3 GB")

    monkeypatch.setattr(cli.guards, "check_disk", refuse)
    prov = FakeHistory(["AAPL"])
    assert cli.main(_argv(dirs, "AAPL"), provider=prov, now=NOW) == 1
    assert prov.calls == []


def test_auth_error_stops_the_run_with_exit_2(dirs, capsys):
    cli = load_cli()
    try:
        raise ap.AlpacaAuthError("401 unauthorized")
    except ap.AlpacaAuthError as exc:
        prov = FakeHistory(["AAPL"], error=exc)
    assert cli.main(_argv(dirs, "AAPL"), provider=prov, now=NOW) == 2
    assert len(prov.calls) == 1
    assert "401" in capsys.readouterr().err


def test_parse_args_defaults_resolve_at_call_time(store_root):
    cli = load_cli()
    args = cli.parse_args([])
    assert args.root == store_root
    assert args.timeframes == ("daily", "hourly", "15min")
    assert (args.start, args.mode, args.force, args.force_hours) == ("2016-01-01", "full", False, False)
    assert cli.parse_args(["--timeframes", "15min,daily"]).timeframes == ("daily", "15min")
    with pytest.raises(SystemExit):
        cli.parse_args(["--timeframes", "1Hour"])
    with pytest.raises(SystemExit):
        cli.parse_args(["--start", "2016-13-01"])


def test_run_summary_render_lists_counts_and_reasons():
    cli = load_cli()
    s = cli.RunSummary(written=["AAPL/daily"], skipped={"GC=F": "skipped: futures"},
                       flagged={"SNDK": "flagged: short-overlap"}, requests=3)
    text = s.render()
    assert text.splitlines()[0] == ("written 1, unchanged 0, refetched 0, skipped 1, "
                                    "flagged 1, requests 3")
    assert "skipped GC=F: skipped: futures" in text and "flagged SNDK: flagged: short-overlap" in text
