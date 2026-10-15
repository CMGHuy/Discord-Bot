"""v162 AH8: --mode update -- an unchanged day writes nothing, a tiny rescale
refetches all three timeframes together, new bars append."""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from alpaca_history import store_io, update
from tests.history_store.test_fetch_alpaca_history import (  # noqa: F401  (dirs is a fixture)
    DAYS,
    NOW,
    FakeHistory,
    _argv,
    _manifest,
    dirs,
    load_cli,
)

UTC = timezone.utc
LATER = datetime(2024, 6, 8, 12, 0, tzinfo=UTC)          # the next Saturday
LONGER = pd.bdate_range("2023-01-02", "2024-06-07")


def _daily(closes, days) -> pd.DataFrame:
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Volume": 1.0}, index=pd.DatetimeIndex(days, name="Date"))


def _snapshot(root):
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def _backfill(cli, dirs, tickers="AAPL"):
    assert cli.main(_argv(dirs, tickers), provider=FakeHistory(tickers.split(",")), now=NOW) == 0


# --- pure helpers --------------------------------------------------------------

DAYS5 = pd.bdate_range("2024-01-01", periods=5)


def test_identical_history_is_the_same_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    assert update.basis_changed(stored, stored.copy()) is False


def test_a_uniform_rescale_far_below_a_hundredth_of_a_percent_is_a_new_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    fresh = stored.copy()
    fresh["Close"] *= 1 - 5e-6
    assert update.basis_changed(stored, fresh) is True


def test_float_noise_under_the_tolerance_is_not_a_new_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    fresh = stored.copy()
    fresh["Close"] *= 1 + 1e-8
    assert update.basis_changed(stored, fresh) is False


def test_a_vanished_stored_row_or_one_sided_nan_is_a_new_basis():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    assert update.basis_changed(stored, stored.drop(DAYS5[2])) is True
    fresh = stored.copy()
    fresh.loc[DAYS5[1], "Close"] = np.nan
    assert update.basis_changed(stored, fresh) is True


def test_a_split_step_is_a_new_basis_and_new_rows_alone_are_not():
    stored = _daily([10.0, 10.5, 11.0, 11.5, 12.0], DAYS5)
    split = stored.copy()
    split.loc[DAYS5[:3], "Close"] /= 2
    assert update.basis_changed(stored, split) is True
    longer = _daily([10.0, 10.5, 11.0, 11.5, 12.0, 12.5], pd.bdate_range("2024-01-01", periods=6))
    assert update.basis_changed(stored, longer) is False
    assert update.basis_changed(None, longer) is False


def test_new_bars_are_strictly_after_the_last_stored_bar():
    stored = _daily([1.0, 2.0, 3.0], DAYS5[:3])
    fresh = _daily([1.0, 2.0, 3.0, 4.0, 5.0], DAYS5)
    assert list(update.new_bars(stored, fresh).index) == list(DAYS5[3:])
    none = update.new_bars(stored, stored.copy())
    assert none.empty and list(none.columns) == list(stored.columns)
    assert len(update.new_bars(None, fresh)) == 5


def test_the_no_bars_status_matches_the_cli():
    assert update.NO_BARS == load_cli().NO_BARS
    assert update.WRITE_ORDER[-1] == "daily"


# --- through the CLI ------------------------------------------------------------

def test_an_unchanged_day_writes_nothing(dirs, capsys):
    cli = load_cli()
    _backfill(cli, dirs, "AAPL,SNDK")
    before = _snapshot(dirs["root"])
    prov = FakeHistory(["AAPL", "SNDK"])
    assert cli.main(_argv(dirs, "AAPL,SNDK", "--mode", "update"), provider=prov, now=NOW) == 0
    assert prov.calls, "update must still compare against a fresh daily history"
    assert _snapshot(dirs["root"]) == before
    out = capsys.readouterr().out
    assert "unchanged 6" in out and "flagged SNDK" in out


def test_a_tiny_dividend_rescale_refetches_all_three_timeframes(dirs, capsys):
    cli = load_cli()
    _backfill(cli, dirs)
    scale = 1 - 5e-6                       # 0.0005 %: far below 0.01 %
    prov = FakeHistory(["AAPL"], scale=scale)
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=prov, now=NOW) == 0
    root = dirs["root"]
    daily = pd.read_csv(root / "daily" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert daily["Close"].iloc[0] == pytest.approx(100.0 * scale, rel=1e-12)
    for tf in ("hourly", "15min"):
        frame = pd.read_csv(root / tf / "AAPL.csv", index_col="Datetime", parse_dates=True)
        assert frame["Close"].eq(frame["Close"].iloc[0]).all()           # one basis per file
        assert frame["Close"].iloc[0] == pytest.approx(150.0 * scale, rel=1e-12)
        entry = _manifest(root, tf)["tickers"]["AAPL"]
        assert entry["sha256"] == store_io.sha256_file(root / tf / "AAPL.csv")
    assert "refetched 3" in capsys.readouterr().out


def test_a_refetch_writes_daily_last(dirs, monkeypatch):
    cli = load_cli()
    _backfill(cli, dirs)
    order: list[str] = []
    real = store_io.write_frame

    def spy(frame, path, timeframe):
        order.append(timeframe)
        return real(frame, path, timeframe)

    monkeypatch.setattr(store_io, "write_frame", spy)
    cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=FakeHistory(["AAPL"], scale=0.5),
             now=NOW)
    assert order == ["15min", "hourly", "daily"]


def test_a_killed_refetch_is_redone_by_the_next_update(dirs, monkeypatch):
    cli = load_cli()
    _backfill(cli, dirs)
    real = store_io.write_frame

    def die_on_daily(frame, path, timeframe):
        if timeframe == "daily":
            raise KeyboardInterrupt
        return real(frame, path, timeframe)

    monkeypatch.setattr(store_io, "write_frame", die_on_daily)
    with pytest.raises(KeyboardInterrupt):
        cli.main(_argv(dirs, "AAPL", "--mode", "update"),
                 provider=FakeHistory(["AAPL"], scale=0.5), now=NOW)
    monkeypatch.setattr(store_io, "write_frame", real)
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"),
                    provider=FakeHistory(["AAPL"], scale=0.5), now=NOW) == 0
    daily = pd.read_csv(dirs["root"] / "daily" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert daily["Close"].iloc[0] == pytest.approx(50.0)


def test_new_sessions_append_to_every_timeframe(dirs, capsys):
    cli = load_cli()
    _backfill(cli, dirs)
    prov = FakeHistory(["AAPL"], days=LONGER)
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=prov, now=LATER) == 0
    root = dirs["root"]
    daily = pd.read_csv(root / "daily" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert len(daily) == len(DAYS) + 5 and daily.index.is_unique
    assert len(pd.read_csv(root / "15min" / "AAPL.csv")) == 256
    assert len(pd.read_csv(root / "hourly" / "AAPL.csv")) == 28
    entry = _manifest(root, "daily")["tickers"]["AAPL"]
    assert entry["last"] == "2024-06-07" and entry["start"] == "2023-01-01"
    assert entry["rows"] == len(daily)
    assert "written 3" in capsys.readouterr().out


def test_an_empty_daily_answer_leaves_the_store_untouched(dirs):
    cli = load_cli()
    _backfill(cli, dirs)
    before = _snapshot(dirs["root"])
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=FakeHistory([]), now=NOW) == 0
    assert _snapshot(dirs["root"]) == before


def test_a_new_watchlist_ticker_is_backfilled_by_update(dirs):
    cli = load_cli()
    _backfill(cli, dirs)
    prov = FakeHistory(["AAPL", "NVDA"])
    assert cli.main(_argv(dirs, "AAPL,NVDA", "--mode", "update"), provider=prov, now=NOW) == 0
    for tf in ("daily", "hourly", "15min"):
        assert (dirs["root"] / tf / "NVDA.csv").exists()
        assert _manifest(dirs["root"], tf)["tickers"]["NVDA"]["status"] == "flagged: no-reference"


def test_update_requests_end_at_now_minus_the_sip_delay(dirs):
    cli = load_cli()
    _backfill(cli, dirs)
    prov = FakeHistory(["AAPL"], scale=0.5)          # a refetch: every timeframe is requested
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=prov, now=NOW) == 0
    assert {c[1] for c in prov.calls} == {"1d", "30min", "15min"}
    assert max(c[3] for c in prov.calls) == NOW - cli.SIP_DELAY


class _DailyOnly(FakeHistory):
    def history_bars(self, ticker, timeframe, start, end):
        frame = super().history_bars(ticker, timeframe, start, end)
        return frame if timeframe == "1d" else None


def test_an_intraday_timeframe_empty_on_refetch_drops_its_old_basis_file(dirs):
    cli = load_cli()
    _backfill(cli, dirs)
    prov = _DailyOnly(["AAPL"], scale=0.5)
    assert cli.main(_argv(dirs, "AAPL", "--mode", "update"), provider=prov, now=NOW) == 0
    for tf in ("hourly", "15min"):
        assert not (dirs["root"] / tf / "AAPL.csv").exists()
        entry = _manifest(dirs["root"], tf)["tickers"]["AAPL"]
        assert entry["status"] == update.NO_BARS and entry["sha256"] is None
        assert entry["start"] == "2023-01-01"
    daily = pd.read_csv(dirs["root"] / "daily" / "AAPL.csv", index_col="Date", parse_dates=True)
    assert daily["Close"].iloc[0] == pytest.approx(50.0)
