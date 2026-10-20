# v172 Equity candlestick chart, part 2b: backfill CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull the task with `grep -n "^### Task V172-7:" -A 400 <this file>`.

**Spec:** [`docs/superpowers/specs/2026-10-17-v172-equity-candlestick-chart-design.md`](../specs/2026-10-17-v172-equity-candlestick-chart-design.md)
**Index:** [`2026-10-17-v172-equity-candlestick-chart_0-index.md`](2026-10-17-v172-equity-candlestick-chart_0-index.md): Global Constraints, Parallelisation, `$WT`/`$R` and the task ledger live there and bind this task.

V172-7 sits in its own file only because part 2 would otherwise pass the 1500-line cap; it is the second half of part 2's backfill work and runs after V172-6 (same script, same test file; see `_2-recorder-api-backfill.md` § V172-6 for the builder it extends).

# Phase 2 (continued): backfill CLI

### Task V172-7: Backfill CLI: raw-bar fetch, coverage gate, dry run, `--apply`/`--replace`/`--allow-gaps`/`--recompute-realized`

**Model:** sonnet — CLI over V172-6's builder and V172-2's repository, behaviour fixed by the spec

**Files:**
- Modify: `scripts/data/backfill_equity_samples.py` (imports block; new functions appended after `build_day_rows`; `if __name__` guard at the end)
- Test: `tests/scripts/test_backfill_equity_samples.py` (append)

**Interfaces:**
- Consumes (V172-6, same file): `filled_trades`, `held_positions`, `build_day_rows`, `ny_day`, `_slices`, `Skip`, `GAP_REASONS`, `_OHLC`.
- Consumes (V172-1): `equity.realized_legs`, `equity.realized_balance_at`, `equity.starting_balance() -> Decimal`, `equity.load_plans_by_id() -> dict`.
- Consumes (V172-2): `equity_samples_repo()`; `EquitySampleRepository.upsert_many(rows, conn=None) -> int`, `.replace_backfill(rows, conn=None) -> int` (deletes every `backfill` row and inserts, one transaction), `.earliest_at(source, conn=None)`, `.backfill_session_dates(conn=None) -> set[date]` (NY dates), `.list_rows(*, sources=..., since=None, conn=None)` (rows carry `id`), `.update_realized(sample_id, realized_balance: Decimal, equity: Decimal, conn=None) -> None`, `.insert_sample(row, conn=None) -> int`.
- Consumes (existing): `swingbot.core.market.session.nyse_calendar().sessions(start, end) -> list[date]` (`session.py:235`, inclusive both ends); `yfinance.download`.
- Produces: `fetch_raw_bars(ticker: str, start: date, end: date) -> pd.DataFrame` (columns `Open, High, Low, Close`; calls module-level `yf.download(..., auto_adjust=False, progress=False, interval="1d")`); `new_run_id() -> str` (UTC `%Y%m%dT%H%M%SZ`; test seam); `backfill_days(trades, repo, today: date) -> list[date]`; `recompute_realized(repo, trades, *, apply: bool) -> int`; `main(argv: list[str] | None = None, *, bars_fn=None, repo=None, trades_fn=None, plans_fn=None, today: date | None = None, out_dir: Path | None = None) -> dict` with summary keys exactly `run_id, bars_asof, days, rows, written, gaps, skipped, recomputed`. V172-13 runs the two VM commands in the module docstring.

Behaviour (Global Constraints, Backfill bars/rows/flags): one fetch per traded ticker over the span of days it was held, saved to `<out_dir>/<TICKER>.csv` (default `data/backfill_equity_samples/<run_id>/`); `bars_asof` = latest bar date fetched (`"none"` when nothing came back); `backfill_run = f"{run_id}@bars-asof-{bars_asof}"`; days = NYSE sessions from the earliest main-book entry day to the session before the first `live` sample (before `today` when none). `build_day_rows` is called with `allow_gaps=True` so the dry run lists every gap; the gate then refuses `--apply` on any gap unless `--allow-gaps`. Without `--replace` only days with no backfill rows are written; `--replace` rewrites every backfill row in one transaction. `--recompute-realized` is its own mode: it touches `live` rows only, rewriting `realized_balance` and `equity` and keeping `unrealized_pnl`.

- [ ] **Step 1: Append the failing tests**

Append to `tests/scripts/test_backfill_equity_samples.py`:

```python
# --- V172-7: the CLI -------------------------------------------------------------
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository  # noqa: E402
from tests.store_seed import seed_store  # noqa: E402

TODAY = date(2026, 10, 8)            # Thursday, no live rows: days covered are Mon..Wed
RUN = "20261008T120000Z"


@pytest.fixture
def account():
    seed_store("account", {"base_balance": 10000.0, "balance": 10000.0, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})


@pytest.fixture
def repo():
    return EquitySampleRepository()


def _bars_fn(frames, calls):
    def fetch(ticker, start, end):
        calls.append((ticker, start, end))
        if ticker not in frames:
            raise OSError("HTTP 404")
        return frames[ticker].copy()
    return fetch


def _main(monkeypatch, argv, repo, tmp_path, *, frames=BARS, calls=None, run_id=RUN):
    monkeypatch.setattr(bes, "new_run_id", lambda: run_id)
    return bes.main(argv, bars_fn=_bars_fn(frames, [] if calls is None else calls), repo=repo,
                    trades_fn=lambda: list(TRADES), plans_fn=lambda: {}, today=TODAY,
                    out_dir=tmp_path / run_id)


def _live(at, realized, unrealized):
    return {"at": at, "realized_balance": Decimal(str(realized)),
            "unrealized_pnl": Decimal(str(unrealized)),
            "equity": Decimal(str(realized)) + Decimal(str(unrealized)), "open_n": 1,
            "skipped_n": 0, "source": "live", "kind": "point", "backfill_run": None}


def test_dry_run_reports_coverage_and_writes_nothing(monkeypatch, repo, account, tmp_path, capsys):
    calls = []
    assert _main(monkeypatch, [], repo, tmp_path, calls=calls) == {
        "run_id": RUN, "bars_asof": "2026-10-07", "days": 3, "rows": 12, "written": 0,
        "gaps": 0, "skipped": 0, "recomputed": 0}
    assert repo.list_rows() == []
    out = capsys.readouterr().out
    for line in (f"run id: {RUN}", "bars as-of: 2026-10-07",
                 "days covered: 3 (2026-10-05..2026-10-07)", "DRY RUN: rows=12 gaps=0 skipped=0",
                 "Dry run only -- pass --apply to write."):
        assert line in out
    assert sorted(calls) == [("AAPL", MON, WED), ("MSFT", TUE, WED)]     # held days only
    assert (tmp_path / RUN / "AAPL.csv").exists() and (tmp_path / RUN / "MSFT.csv").exists()


def test_apply_writes_four_rows_a_day_and_a_rerun_writes_nothing_new(
        monkeypatch, repo, account, tmp_path):
    assert _main(monkeypatch, ["--apply"], repo, tmp_path)["written"] == 12
    rows = repo.list_rows(sources=("backfill",))
    assert {r["backfill_run"] for r in rows} == {f"{RUN}@bars-asof-2026-10-07"}
    assert sorted(r["equity"] for r in rows if bes.ny_day(r["at"]) == WED) == [
        10055.0, 10060.0, 10125.0, 10130.0]
    assert _main(monkeypatch, ["--apply"], repo, tmp_path, run_id="20261009T090000Z")["written"] == 0
    assert len(repo.list_rows()) == 12


def test_replace_rewrites_every_backfill_row_with_the_new_run(monkeypatch, repo, account, tmp_path):
    _main(monkeypatch, ["--apply"], repo, tmp_path)
    assert _main(monkeypatch, ["--apply", "--replace"], repo, tmp_path,
                 run_id="20261009T090000Z")["written"] == 12
    rows = repo.list_rows(sources=("backfill",))
    assert len(rows) == 12
    assert {r["backfill_run"] for r in rows} == {"20261009T090000Z@bars-asof-2026-10-07"}


def test_the_coverage_gate_refuses_a_gap_unless_allowed(monkeypatch, repo, account, tmp_path, capsys):
    short = {"AAPL": BARS["AAPL"], "MSFT": _frame({TUE: (201, 203, 196, 198)})}
    summary = _main(monkeypatch, ["--apply"], repo, tmp_path, frames=short)
    assert (summary["gaps"], summary["written"]) == (1, 0)
    assert repo.list_rows() == []
    assert "REFUSED: 1 coverage gap(s)" in capsys.readouterr().out
    assert _main(monkeypatch, ["--apply", "--allow-gaps"], repo, tmp_path, frames=short)["written"] == 12
    wed = [r for r in repo.list_rows() if bes.ny_day(r["at"]) == WED]
    assert {r["skipped_n"] for r in wed} == {1}


def test_a_failed_fetch_is_a_gap_and_is_reported(monkeypatch, repo, account, tmp_path, capsys):
    summary = _main(monkeypatch, [], repo, tmp_path, frames={"AAPL": BARS["AAPL"]})
    assert summary["gaps"] == 2                               # MSFT on Tue and on Wed
    out = capsys.readouterr().out
    assert "MSFT: fetch failed (HTTP 404)" in out
    assert "skipped 2026-10-06 MSFT trade m1: fetch failed" in out


def test_days_stop_at_the_session_before_the_first_live_sample(monkeypatch, repo, account, tmp_path):
    repo.insert_sample(_live(datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc), 10000, 0))
    assert _main(monkeypatch, [], repo, tmp_path)["days"] == 2   # Mon, Tue


def test_fetch_raw_bars_asks_yfinance_for_unadjusted_daily_bars(monkeypatch):
    seen = {}

    def fake_download(ticker, **kwargs):
        seen.update(ticker=ticker, **kwargs)
        frame = BARS["AAPL"].copy()
        frame.columns = pd.MultiIndex.from_product([frame.columns, [ticker]])
        frame[("Adj Close", ticker)] = 1.0
        return frame

    monkeypatch.setattr(bes.yf, "download", fake_download)
    frame = bes.fetch_raw_bars("AAPL", MON, WED)
    assert seen["auto_adjust"] is False
    assert (seen["ticker"], seen["interval"], seen["progress"]) == ("AAPL", "1d", False)
    assert (seen["start"], seen["end"]) == ("2026-10-05", "2026-10-08")  # yfinance's end is exclusive
    assert list(frame.columns) == ["Open", "High", "Low", "Close"]


def test_recompute_realized_rewrites_only_the_realized_columns_of_live_rows(
        monkeypatch, repo, account, tmp_path):
    at = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
    repo.insert_sample(_live(at, 9000.0, 25.0))                       # stale: AAPL's +100 missing
    repo.upsert_many([{**_live(at, 1.0, 0.0), "source": "backfill", "backfill_run": "old@bars-asof-x"}])
    assert _main(monkeypatch, ["--recompute-realized"], repo, tmp_path)["recomputed"] == 1
    assert repo.list_rows(sources=("live",))[0]["realized_balance"] == 9000.0   # dry run
    assert _main(monkeypatch, ["--recompute-realized", "--apply"], repo, tmp_path)["recomputed"] == 1
    (live,) = repo.list_rows(sources=("live",))
    assert (live["realized_balance"], live["unrealized_pnl"], live["equity"]) == (10100.0, 25.0, 10125.0)
    (old,) = repo.list_rows(sources=("backfill",))
    assert old["realized_balance"] == 1.0
    assert _main(monkeypatch, ["--recompute-realized", "--apply"], repo, tmp_path)["recomputed"] == 0
```

- [ ] **Step 2: Run the tests to verify the new ones fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_backfill_equity_samples.py`
Expected: V172-6's 16 PASS; the 8 new tests FAIL with `AttributeError: module 'scripts.data.backfill_equity_samples' has no attribute 'new_run_id'` (or `'yf'` / `'fetch_raw_bars'`).

- [ ] **Step 3: Add the CLI**

In `scripts/data/backfill_equity_samples.py`, extend the imports (keep the existing ones):

```python
import argparse
from decimal import ROUND_HALF_UP
from pathlib import Path

import yfinance as yf

from swingbot.core.db.repositories.equity_samples import equity_samples_repo  # noqa: E402
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar  # noqa: E402
```

(`import yfinance as yf` and `from pathlib import Path` go above the `sys.path.insert` line with the other third-party/stdlib imports; the two `swingbot` imports go below it, replacing the existing `session` import line.) Add `ROOT = Path(__file__).resolve().parents[2]` and `DRY_RUN_NOTE = "Dry run only -- pass --apply to write."` under the constants, then append after `build_day_rows`:

```python
def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def fetch_raw_bars(ticker: str, start: date, end: date) -> pd.DataFrame:
    """UNADJUSTED daily bars, start..end inclusive (yfinance's `end` is exclusive).
    Entries and exits are raw fills, so raw bars match them with no rebase."""
    frame = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(),
                        interval="1d", auto_adjust=False, progress=False)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(_OHLC))
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return frame[list(_OHLC)]


def _load_trades() -> list[dict]:
    from swingbot.core.tracking.performance import TradeLog
    return TradeLog().get_trades(status=None, limit=None, sort_by="opened_at") or []


def backfill_days(trades: list[dict], repo, today: date) -> list[date]:
    """NYSE sessions from the earliest entry day to the session before the first live sample."""
    entries = [piece["entry_day"] for trade in equity.main_book(trades) for piece in _slices(trade)]
    if not entries:
        return []
    first_live = repo.earliest_at("live")
    stop = ny_day(first_live) if first_live is not None else today
    return nyse_calendar().sessions(min(entries), stop - timedelta(days=1))


def _spans(trades: list[dict], days: list[date]) -> dict[str, tuple[date, date]]:
    """Per ticker, the first and last backfill day it was held: one fetch each."""
    spans: dict[str, tuple[date, date]] = {}
    for day in days:
        for pos in held_positions(trades, day):
            first, last = spans.get(pos["ticker"], (day, day))
            spans[pos["ticker"]] = (min(first, day), max(last, day))
    return spans


def _fetch_all(spans: dict, bars_fn, out_dir: Path) -> dict[str, pd.DataFrame | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame | None] = {}
    for ticker, (start, end) in sorted(spans.items()):
        try:
            frame = bars_fn(ticker, start, end)
        except Exception as exc:                       # a failed fetch is a coverage gap
            print(f"  {ticker}: fetch failed ({exc})")
            frame = None
        if frame is not None and not frame.empty:
            frame.to_csv(out_dir / f"{ticker}.csv")
        frames[ticker] = frame
    return frames


def _bars_asof(frames: dict) -> str:
    dates = [frame.index.max().date() for frame in frames.values()
             if frame is not None and not frame.empty]
    return max(dates).isoformat() if dates else "none"


def _build_all(days, trades, frames, legs, start, run_tag) -> tuple[list[dict], list[Skip]]:
    rows: list[dict] = []
    skips: list[Skip] = []
    for day in days:
        day_rows, day_skips = build_day_rows(day, held_positions(trades, day), frames, legs,
                                             start, run_tag, allow_gaps=True)
        rows.extend(day_rows)
        skips.extend(day_skips)
    return rows, skips


def _write(repo, rows: list[dict], *, replace: bool) -> int:
    if replace:
        return repo.replace_backfill(rows)
    existing = repo.backfill_session_dates()
    fresh = [row for row in rows if ny_day(row["at"]) not in existing]
    return repo.upsert_many(fresh) if fresh else 0


def recompute_realized(repo, trades: list[dict], *, apply: bool) -> int:
    """Live rows whose stored realized balance differs from today's trade log;
    with `apply`, rewrite realized_balance and equity, keeping unrealized_pnl."""
    legs, start, changed = equity.realized_legs(trades), equity.starting_balance(), 0
    for row in repo.list_rows(sources=("live",)):
        realized = equity.realized_balance_at(start, legs, row["at"])
        if float(realized.quantize(Decimal("0.01"), ROUND_HALF_UP)) == row["realized_balance"]:
            continue
        changed += 1
        if apply:
            repo.update_realized(row["id"], realized,
                                 realized + Decimal(str(row["unrealized_pnl"])))
    return changed


def _parse(argv):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Write. Default is a dry run that only reports.")
    parser.add_argument("--replace", action="store_true",
                        help="With --apply: delete every backfill row and rewrite them, one transaction.")
    parser.add_argument("--allow-gaps", action="store_true",
                        help="With --apply: write despite missing bars (left out, counted in skipped_n).")
    parser.add_argument("--recompute-realized", action="store_true",
                        help="Rewrite realized_balance/equity on live rows from the current trade log.")
    return parser.parse_args(argv)


def _summary(run_id: str, **values) -> dict:
    return {"run_id": run_id, "bars_asof": None, "days": 0, "rows": 0, "written": 0,
            "gaps": 0, "skipped": 0, "recomputed": 0, **values}


def _run_recompute(args, repo, trades, run_id: str) -> dict:
    count = recompute_realized(repo, trades, apply=args.apply)
    print(f"{'APPLIED' if args.apply else 'DRY RUN'}: recompute-realized changed={count}")
    if not args.apply:
        print(DRY_RUN_NOTE)
    return _summary(run_id, recomputed=count)


def _report(summary: dict, days: list[date], skips: list[Skip]) -> None:
    print(f"run id: {summary['run_id']}")
    print(f"bars as-of: {summary['bars_asof']}")
    span = f"{days[0]}..{days[-1]}" if days else "none"
    print(f"days covered: {summary['days']} ({span})")
    for skip in skips:
        print(f"  skipped {skip.day} {skip.ticker} trade {skip.trade_id}: {skip.reason}")


def _apply(args, repo, rows: list[dict], gaps: int) -> int:
    if gaps and not args.allow_gaps:
        print(f"REFUSED: {gaps} coverage gap(s). Re-run the dry run (a fetch can fail "
              "transiently) before considering --allow-gaps.")
        return 0
    written = _write(repo, rows, replace=args.replace)
    print(f"APPLIED: written={written}")
    return written


def main(argv: list[str] | None = None, *, bars_fn=None, repo=None, trades_fn=None,
         plans_fn=None, today: date | None = None, out_dir: Path | None = None) -> dict:
    args = _parse(argv)
    repo = repo or equity_samples_repo()
    run_id = new_run_id()
    trades = (trades_fn or _load_trades)()
    if args.recompute_realized:
        return _run_recompute(args, repo, trades, run_id)
    filled = filled_trades(trades, (plans_fn or equity.load_plans_by_id)())
    days = backfill_days(filled, repo, today or datetime.now(US_MARKET_TZ).date())
    frames = _fetch_all(_spans(filled, days), bars_fn or fetch_raw_bars,
                        out_dir or ROOT / "data" / "backfill_equity_samples" / run_id)
    bars_asof = _bars_asof(frames)
    rows, skips = _build_all(days, filled, frames, equity.realized_legs(trades),
                             equity.starting_balance(), f"{run_id}@bars-asof-{bars_asof}")
    gaps = sum(1 for skip in skips if skip.reason in GAP_REASONS)
    summary = _summary(run_id, bars_asof=bars_asof, days=len(days), rows=len(rows),
                       gaps=gaps, skipped=len(skips))
    _report(summary, days, skips)
    if args.apply:
        summary["written"] = _apply(args, repo, rows, gaps)
    else:
        print(f"DRY RUN: rows={len(rows)} gaps={gaps} skipped={len(skips)}")
        print(DRY_RUN_NOTE)
    return summary


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_backfill_equity_samples.py`
Expected: PASS (24 tests).

- [ ] **Step 5: Check complexity and that no shared cache is read**

Run: `python -m radon cc -s -n C $WT/scripts/data/backfill_equity_samples.py`
Expected: no output (`main` is the largest, about B (10)).
Run: `git -C $WT grep -nE "backtest_cache|market_data|load_daily|load_cached" -- scripts/data/backfill_equity_samples.py`
Expected: matches in the module docstring only (the "Never read here" sentence), none in code.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/data/backfill_equity_samples.py tests/scripts/test_backfill_equity_samples.py
git -C $WT commit -m "feat(scripts): equity backfill CLI -- raw-bar fetch, coverage gate, --apply/--replace/--allow-gaps/--recompute-realized (v172)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

