# v162 Alpaca history store, part 2b: check script and the training switch

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task AH10:" -A 400 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_2b-check-training-switch.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md) (Acceptance 2, §3 training switch, Amendments "Provenance is a sidecar" and "One loader seam")
**Bump:** bot patch
**Edge:** none (integrity)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md) carries the Global Constraints, `## Parallelisation` and the task ledger. Ledger part 2 outgrew the 1500-line cap: AH6–AH8 are in [`2026-10-15-v162-alpaca-history-store_2-backfill-switch.md`](2026-10-15-v162-alpaca-history-store_2-backfill-switch.md), AH9 and AH10 are here. Both tasks run in parallel with AH3–AH8 (they read only AH2's contract).

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store`, `$R` = the main tree. Never `cd`; use `git -C $WT` and absolute paths. After each task `git -C $R status --short` shows the main tree unchanged.
- Tests in `tests/history_store/` rely on AH2's `conftest.py`: `scripts/data` is on `sys.path` (`import fetch_backtest_data` works) and the `store_root` fixture creates `tmp_path/"market_data"`, points `HISTORY_STORE_DIR` at it and returns it. Neither task imports `alpaca_history`: their tests write the manifest JSON by hand in the shape of the index's "Manifest shape" constraint.
- Per-task runs: `python $WT/scripts/dev/testrun.py file <test>`. Complexity: `python -m radon cc -s -n C <files>` prints nothing for new code.

# Phase B (end): check script

### Task AH9: Row-count and hash check script

**Model:** sonnet — per-date counting against a SPY calendar with every class and threshold stated below; no market logic beyond session lengths

**Files:**
- Create: `scripts/data/check_history_store.py`
- Test: `tests/history_store/test_check_history_store.py`

**Interfaces:**
- Consumes (AH2): `history_store.TIMEFRAMES`, `history_store.store_root()`. Existing: `data_store.safe_symbol` (`data_store.py:104`). The manifest shape from the index (only `tickers.<T>.sha256` and `status` are read).
- Produces (ledger AH9): `RTH_15MIN_FULL = 26`; `RTH_15MIN_HALF = 14`; `HOURLY_FULL = 7`; `HOURLY_HALF = 4`; `session_counts(frame) -> pd.Series`; `check_ticker(ticker, timeframe, *, root, calendar) -> dict`; `verify_hashes(root) -> list[str]`; `main(argv=None) -> int`; CLI `python scripts/data/check_history_store.py [--root DIR] [--tickers A,B] [--verify-hashes]`. AH20 (cron after the update, pull script with `--verify-hashes`) and AH21 (acceptance 2) call it.

**Rules this task freezes (spec Acceptance 1 and 2, §4):**
- **Calendar = SPY's own bars** in the same timeframe (`CALENDAR_TICKER = "SPY"`); a missing SPY file fails the timeframe with one unexplained line. 15min is counted over regular hours only (bars starting 09:30–15:45 ET); hourly is RTH by construction; daily counts one bar per date.
- **Per date** from the ticker's first to its last bar: the ticker's count equals SPY's → `full` (SPY has the full count: 26 / 7 / 1) or `half_day` (SPY has the half count: 14 / 4); fewer but more than zero → `sparse` (a thin name with no trade in some bars: reported, not a failure); zero, or more than SPY → unexplained `"<date>: <n> of <m> bars"`. A SPY date whose own count is neither full nor half is unexplained (`"<date>: calendar has <m> bars"`).
- `holiday` = weekdays between the first and last bar that SPY does not trade; `pre_listing` = SPY dates before the ticker's first bar. Both are explained.
- A ticker date SPY does not trade is unexplained. A ticker ending more than one SPY session before SPY's last bar is unexplained (`"ends <date>, <n> sessions before SPY"`, acceptance 1: "ending within one session of the run").
- **Which pairs are counted:** every (ticker, timeframe) whose manifest entry has a `sha256`; tickers default to every such entry, `--tickers` narrows them. Entries without a file (`skipped:`) print one `SKIP` line and never fail.
- `--verify-hashes`: every manifest entry with a `sha256` must have its file and the same SHA-256; each mismatch, missing file or missing manifest is one problem line. Exit code 1 on any problem or any unexplained gap, else 0.

- [ ] **Step 1: Write the failing test**

Create `tests/history_store/test_check_history_store.py`:

```python
"""v162 AH9: row counts against the SPY calendar (half-days, holidays,
listings, thin names) and the manifest hash check."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
# Thanksgiving week 2024: Thursday 28 closed, Friday 29 a 13:00 half-day.
SESSIONS = {"2024-11-25": "full", "2024-11-26": "full", "2024-11-27": "full",
            "2024-11-29": "half", "2024-12-02": "full"}
INDEX = {"15min": "Datetime", "hourly": "Datetime", "daily": "Date"}


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_history_store", ROOT / "scripts" / "data" / "check_history_store.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _stamps(day: str, kind: str, tf: str) -> list[pd.Timestamp]:
    end = "16:00" if kind == "full" else "13:00"
    if tf == "daily":
        return [pd.Timestamp(day)]
    if tf == "hourly":
        return list(pd.date_range(f"{day} 09:30", f"{day} {end}", freq="60min", inclusive="left"))
    rth = pd.date_range(f"{day} 09:30", f"{day} {end}", freq="15min", inclusive="left")
    return list(rth) + [pd.Timestamp(f"{day} 08:00"), pd.Timestamp(f"{day} 17:00")]


class Store:
    """Writes CSVs and hand-built manifests in the v162 store layout."""

    def __init__(self, root: Path):
        self.root = root
        self.manifests = {tf: {"timeframe": tf, "feed": "sip", "adjustment": "all", "tickers": {}}
                          for tf in INDEX}

    def add(self, ticker: str, sessions: dict[str, str] = SESSIONS, *, drop_15min: int = 0) -> None:
        for tf in INDEX:
            stamps = sorted(s for day, kind in sessions.items() for s in _stamps(day, kind, tf))
            if tf == "15min" and drop_15min:
                stamps = stamps[drop_15min:]
            frame = pd.DataFrame({c: 1.0 for c in ("Open", "High", "Low", "Close", "Volume")},
                                 index=pd.DatetimeIndex(stamps, name=INDEX[tf]))
            path = self.root / tf / f"{ticker}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(path)
            self.manifests[tf]["tickers"][ticker] = {
                "status": "ok", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def skip(self, ticker: str, reason: str) -> None:
        for tf in INDEX:
            self.manifests[tf]["tickers"][ticker] = {"status": reason, "sha256": None}

    def save(self) -> Path:
        for tf, manifest in self.manifests.items():
            (self.root / tf).mkdir(parents=True, exist_ok=True)
            (self.root / tf / "_manifest.json").write_text(json.dumps(manifest))
        return self.root


@pytest.fixture
def store(store_root) -> Store:
    s = Store(store_root)
    s.add("SPY")
    return s


def _calendar(chk, root, tf):
    return chk.session_counts(chk.read_frame(root, "SPY", tf))


def test_session_counts_are_bars_per_date():
    chk = _load()
    idx = pd.DatetimeIndex(["2024-11-25 09:30", "2024-11-25 09:45", "2024-11-26 09:30"])
    counts = chk.session_counts(pd.DataFrame({"Close": [1.0, 1.0, 1.0]}, index=idx))
    assert counts.to_dict() == {pd.Timestamp("2024-11-25"): 2, pd.Timestamp("2024-11-26"): 1}


@pytest.mark.parametrize("tf", ["15min", "hourly", "daily"])
def test_a_clean_ticker_explains_every_session(store, tf):
    chk = _load()
    store.add("AAPL")
    root = store.save()
    res = chk.check_ticker("AAPL", tf, root=root, calendar=_calendar(chk, root, tf))
    assert res["unexplained"] == []
    assert (res["sessions"], res["holiday"], res["pre_listing"], res["sparse"]) == (5, 1, 0, 0)
    if tf == "daily":
        assert res["full"] == 5
    else:
        assert (res["full"], res["half_day"]) == (4, 1)


def test_extended_hours_15min_bars_are_not_counted(store):
    chk = _load()
    root = store.save()
    frame = chk.read_frame(root, "SPY", "15min")
    assert frame.index.min().strftime("%H:%M") == "09:30"
    assert frame.index.max().strftime("%H:%M") == "15:45"


def test_a_thin_name_is_sparse_not_unexplained(store):
    chk = _load()
    store.add("THIN", drop_15min=8)
    root = store.save()
    res = chk.check_ticker("THIN", "15min", root=root, calendar=_calendar(chk, root, "15min"))
    assert res["sparse"] == 1 and res["unexplained"] == []


def test_a_missing_session_is_unexplained(store):
    chk = _load()
    store.add("GAPPY", {d: k for d, k in SESSIONS.items() if d != "2024-11-26"})
    root = store.save()
    res = chk.check_ticker("GAPPY", "15min", root=root, calendar=_calendar(chk, root, "15min"))
    assert res["unexplained"] == ["2024-11-26: 0 of 26 bars"]


def test_a_late_listing_is_pre_listing_and_an_early_end_is_unexplained(store):
    chk = _load()
    store.add("NEWCO", {d: k for d, k in SESSIONS.items() if d >= "2024-11-27"})
    store.add("STALE", {d: k for d, k in SESSIONS.items() if d <= "2024-11-26"})
    root = store.save()
    new = chk.check_ticker("NEWCO", "hourly", root=root, calendar=_calendar(chk, root, "hourly"))
    assert new["pre_listing"] == 2 and new["unexplained"] == []
    stale = chk.check_ticker("STALE", "daily", root=root, calendar=_calendar(chk, root, "daily"))
    assert stale["unexplained"] == ["ends 2024-11-26, 3 sessions before SPY"]


def test_a_bar_on_a_day_spy_does_not_trade_is_unexplained(store):
    chk = _load()
    store.add("ODD", {**SESSIONS, "2024-11-28": "full"})
    root = store.save()
    res = chk.check_ticker("ODD", "daily", root=root, calendar=_calendar(chk, root, "daily"))
    assert res["unexplained"] == ["2024-11-28: bars on a day SPY did not trade"]


def test_verify_hashes_finds_tampered_and_missing_files(store):
    chk = _load()
    store.add("AAPL")
    store.add("MSFT")
    root = store.save()
    assert chk.verify_hashes(root) == []
    (root / "hourly" / "AAPL.csv").write_text("Datetime,Open\n")
    (root / "daily" / "MSFT.csv").unlink()
    problems = chk.verify_hashes(root)
    assert len(problems) == 2
    assert any(p.startswith("hourly/AAPL: sha256") for p in problems)
    assert any(p.startswith("daily/MSFT: file missing") for p in problems)


def test_verify_hashes_reports_a_missing_manifest(store_root):
    chk = _load()
    problems = _load().verify_hashes(store_root)
    assert len(problems) == 3 and all("no manifest" in p for p in problems)
    assert chk.RTH_15MIN_FULL == 26 and chk.HOURLY_HALF == 4


def test_main_exit_codes_and_skip_lines(store, capsys):
    chk = _load()
    store.add("AAPL")
    store.add("GAPPY", {d: k for d, k in SESSIONS.items() if d != "2024-11-26"})
    store.skip("GC=F", "skipped: futures")
    root = store.save()
    assert chk.main(["--root", str(root), "--tickers", "AAPL"]) == 0
    assert chk.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "SKIP GC=F" in out and "2024-11-26: 0 of 26 bars" in out
    (root / "daily" / "AAPL.csv").write_text("Date,Open\n")
    assert chk.main(["--root", str(root), "--tickers", "AAPL", "--verify-hashes"]) == 1
    assert "HASH daily/AAPL" in capsys.readouterr().out


def test_main_fails_without_a_spy_calendar(store_root, capsys):
    chk = _load()
    s = Store(store_root)
    s.add("AAPL")
    root = s.save()
    assert chk.main(["--root", str(root)]) == 1
    assert "no SPY calendar" in capsys.readouterr().out
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_check_history_store.py`
Expected: FAIL with `FileNotFoundError` for `scripts/data/check_history_store.py`.

- [ ] **Step 3: Write the implementation**

Create `scripts/data/check_history_store.py`:

```python
#!/usr/bin/env python3
"""v162: row-count and hash check for the Alpaca history store (spec
Acceptance 1-2, §4).

    python scripts/data/check_history_store.py                    # every stored ticker
    python scripts/data/check_history_store.py --tickers AAPL,MSFT
    python scripts/data/check_history_store.py --verify-hashes    # also every file vs its manifest

Counts each ticker's bars per session against SPY's own bars in the same
timeframe (15min over regular hours: 26 a full session, 14 a 13:00 half-day;
hourly 7 and 4; daily 1). Holidays, half-days and dates before a listing are
explained; thin names with missing bars are reported as sparse. A missing
session, an extra one or a ticker that stops early is unexplained.
Exit code 1 on any unexplained gap or hash problem.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from swingbot.core.marketdata import history_store  # noqa: E402
from swingbot.core.marketdata.data_store import safe_symbol  # noqa: E402

RTH_15MIN_FULL = 26
RTH_15MIN_HALF = 14
HOURLY_FULL = 7
HOURLY_HALF = 4
CALENDAR_TICKER = "SPY"
EXPECTED = {"15min": (RTH_15MIN_FULL, RTH_15MIN_HALF), "hourly": (HOURLY_FULL, HOURLY_HALF),
            "daily": (1, 1)}
MAX_LINES_PER_PAIR = 20


def _path(root: Path, ticker: str, timeframe: str) -> Path:
    return Path(root) / timeframe / f"{safe_symbol(ticker)}.csv"


def read_frame(root: Path, ticker: str, timeframe: str) -> pd.DataFrame | None:
    """The stored frame; 15min cut to bars starting 09:30-15:45. None when absent."""
    path = _path(root, ticker, timeframe)
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if timeframe == "15min":
        frame = frame.between_time("09:30", "15:45")
    return frame if len(frame) else None


def session_counts(frame: pd.DataFrame) -> pd.Series:
    """Bars per date, indexed by the naive midnight of each date."""
    return frame.groupby(frame.index.normalize()).size()


def _label(day: pd.Timestamp) -> str:
    return day.strftime("%Y-%m-%d")


def _classify_days(calendar_days: pd.Series, counts: pd.Series, expected, result: dict) -> None:
    full, half = expected
    for day, want in calendar_days.items():
        have = int(counts.get(day, 0))
        if want not in (full, half):
            result["unexplained"].append(f"{_label(day)}: calendar has {want} bars")
        elif have == want:
            result["full" if want == full else "half_day"] += 1
        elif 0 < have < want:
            result["sparse"] += 1
        else:
            result["unexplained"].append(f"{_label(day)}: {have} of {want} bars")


def _edges(counts: pd.Series, calendar: pd.Series, result: dict) -> None:
    first, last = counts.index.min(), counts.index.max()
    result["pre_listing"] = int((calendar.index < first).sum())
    weekdays = pd.bdate_range(first, last)
    result["holiday"] = int((~weekdays.isin(calendar.index)).sum())
    for day in counts.index.difference(calendar.index):
        result["unexplained"].append(f"{_label(day)}: bars on a day {CALENDAR_TICKER} did not trade")
    after = int((calendar.index > last).sum())
    if after > 1:
        result["unexplained"].append(
            f"ends {_label(last)}, {after} sessions before {CALENDAR_TICKER}")


def check_ticker(ticker: str, timeframe: str, *, root: Path, calendar: pd.Series) -> dict:
    result = {"ticker": ticker, "timeframe": timeframe, "sessions": 0, "full": 0,
              "half_day": 0, "holiday": 0, "pre_listing": 0, "sparse": 0, "unexplained": []}
    frame = read_frame(root, ticker, timeframe)
    if frame is None:
        result["unexplained"].append("no file or no rows")
        return result
    counts = session_counts(frame)
    first, last = counts.index.min(), counts.index.max()
    in_range = calendar[(calendar.index >= first) & (calendar.index <= last)]
    result["sessions"] = len(in_range)
    _classify_days(in_range, counts, EXPECTED[timeframe], result)
    _edges(counts, calendar, result)
    return result


def _manifest(root: Path, timeframe: str) -> dict | None:
    path = Path(root) / timeframe / "_manifest.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _hash_problem(root: Path, timeframe: str, ticker: str, entry: dict) -> list[str]:
    want = entry.get("sha256")
    if not want:
        return []
    path = _path(root, ticker, timeframe)
    if not path.exists():
        return [f"{timeframe}/{ticker}: file missing ({path})"]
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    return [] if got == want else [f"{timeframe}/{ticker}: sha256 {got[:12]} != manifest {want[:12]}"]


def verify_hashes(root: Path) -> list[str]:
    """One line per manifest entry whose file is missing or differs."""
    problems = []
    for tf in history_store.TIMEFRAMES:
        manifest = _manifest(root, tf)
        if manifest is None:
            problems.append(f"{tf}: no manifest at {Path(root) / tf / '_manifest.json'}")
            continue
        for ticker, entry in sorted(manifest.get("tickers", {}).items()):
            problems += _hash_problem(root, tf, ticker, entry)
    return problems


def _pairs(root: Path, tickers: list[str] | None, timeframe: str):
    """(stored tickers, skipped {ticker: status}) for one timeframe."""
    entries = (_manifest(root, timeframe) or {}).get("tickers", {})
    wanted = tickers or sorted(entries)
    stored = [t for t in wanted if (entries.get(t) or {}).get("sha256")]
    skipped = {t: (entries.get(t) or {}).get("status", "not in manifest")
               for t in wanted if t not in stored}
    return stored, skipped


def _print_result(res: dict) -> None:
    print(f"{res['ticker']:<8} {res['timeframe']:<6} sessions={res['sessions']} "
          f"full={res['full']} half={res['half_day']} holiday={res['holiday']} "
          f"pre_listing={res['pre_listing']} sparse={res['sparse']} "
          f"unexplained={len(res['unexplained'])}")
    for line in res["unexplained"][:MAX_LINES_PER_PAIR]:
        print(f"    {line}")


def _check_timeframe(root: Path, tickers: list[str] | None, timeframe: str) -> int:
    """Unexplained-gap count for one timeframe (1 when SPY has no file)."""
    stored, skipped = _pairs(root, tickers, timeframe)
    for ticker, status in sorted(skipped.items()):
        print(f"SKIP {ticker} {timeframe}: {status}")
    spy = read_frame(root, CALENDAR_TICKER, timeframe)
    if spy is None:
        print(f"{timeframe}: no {CALENDAR_TICKER} calendar under {Path(root) / timeframe}")
        return 1
    calendar = session_counts(spy)
    bad = 0
    for ticker in stored:
        res = check_ticker(ticker, timeframe, root=root, calendar=calendar)
        _print_result(res)
        bad += len(res["unexplained"])
    return bad


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=None,
                    help="store root (default: HISTORY_STORE_DIR or data/market_data)")
    ap.add_argument("--tickers", default=None, help="comma list (default: every stored ticker)")
    ap.add_argument("--verify-hashes", action="store_true",
                    help="also check every file against its manifest SHA-256")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root or history_store.store_root()
    tickers = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    problems = verify_hashes(root) if args.verify_hashes else []
    for line in problems:
        print(f"HASH {line}")
    unexplained = sum(_check_timeframe(root, tickers, tf) for tf in history_store.TIMEFRAMES)
    print(f"check: {unexplained} unexplained gap(s), {len(problems)} hash problem(s)")
    return 1 if unexplained or problems else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_check_history_store.py`
Expected: PASS (14 tests: the clean-ticker test runs three times). Then `python -m radon cc -s -n C $WT/scripts/data/check_history_store.py` prints nothing.

- [ ] **Step 5: Commit**

```bash
git -C $WT add scripts/data/check_history_store.py tests/history_store/test_check_history_store.py
git -C $WT commit -m "feat(v162): AH9 history store row-count check against the SPY calendar, hash verify"
```


# Phase C (start): config field and the training switch

### Task AH10: Config `TRAINING_DATA_SOURCE`, `training_data` switch, `load_cached` delegation

**Model:** sonnet — one small stateful module and two thin script helpers, every rule and reason string fixed below; no market logic

**Files:**
- Modify: `swingbot/config.py` (new `Field` after `ALPACA_BREAKER_COOLDOWN_SECONDS` at :780-782; the `ALPACA_ENABLED` help at :743-747; `_MODE_VALUES` at :1361-1370; `_MODE_FALLBACK` at :1374)
- Modify: `.env.example` (after `ALPACA_BREAKER_COOLDOWN_SECONDS=300`, in the Alpaca block at :445-461)
- Create: `swingbot/core/marketdata/training_data.py`
- Modify: `scripts/data/fetch_backtest_data.py` (imports at :49; `load_cached` at :68-73)
- Test: `tests/history_store/test_training_data.py`, `tests/test_config_v162_keys.py`

**Interfaces:**
- Consumes (AH2): `history_store.require_manifest("daily") -> dict` (raises `MissingStoreError` naming the path and `TRAINING_DATA_SOURCE=yfinance`), `history_store.file_path(ticker, "daily") -> Path`, `history_store.load(ticker, "daily") -> pd.DataFrame | None`, `history_store.store_root() -> Path`, `history_store.MissingStoreError`; fixture `store_root` (sets `HISTORY_STORE_DIR`). Existing: `backtest_cache.CACHE_DIR` and `backtest_cache.cache_path(ticker)` (`backtest_cache.py:45,59`), `config._cast`, `config.searchable_attrs()`.
- Produces (ledger AH10, binding for AH11–AH16, AH19, AH23):
  - `config.TRAINING_DATA_SOURCE: str` (`"alpaca"` | `"yfinance"`, default `"alpaca"`, section "Data Sources", `type="select"`; lower-cased, an unknown value falls back to `"alpaca"` with a warning).
  - `training_data.DATA_SOURCES = ("alpaca", "yfinance")`.
  - `select(name: str | None = None) -> str` — `None` resolves to `"yfinance"` when env `BACKTEST_CACHE_DIR` is set and non-blank (an explicit yfinance-shaped cache: the ext-cache fib/v103/v104/v113 scripts and the §5 snapshot legs), else to `config.TRAINING_DATA_SOURCE`. An explicit `name` always wins. `ValueError` on a name outside `DATA_SOURCES`. `"alpaca"` reads the `daily` manifest (raises `MissingStoreError` when absent, and leaves nothing selected) and records the exclusions it already knows. Every call replaces the previous selection.
  - `active() -> str` — the selected source; calls `select(None)` on first use.
  - `reset() -> None` — forget the selection (test isolation).
  - `load_daily(ticker: str) -> pd.DataFrame | None` — `Date` index, `Open..Volume`. `yfinance`: byte-for-byte the pre-v162 `load_cached` (missing or empty file gives `None`, nothing recorded). `alpaca`: an excluded ticker gives `None`; a ticker absent from the manifest is excluded `"not in store"`; an `ok` entry whose load returns `None` is excluded `"no file"` or `"empty file"`.
  - `available_tickers() -> list[str]` — `alpaca`: manifest tickers not excluded; `yfinance`: the stems of `backtest_cache.CACHE_DIR/*.csv`. Sorted.
  - `excluded() -> dict[str, str]` — `{ticker: reason}`, sorted by ticker; `{}` for `yfinance`. Reasons: the manifest `status` (`skipped: ...`, `flagged: ...`, `missing`), `"no file"`, `"empty file"`, `"not in store"`.
  - `exclusion_lines() -> list[str]` — `"excluded <TICKER>: <reason>"` per entry, sorted.
  - `provenance() -> dict` — keys exactly `data_source`, `feed`, `adjustment`, `manifest_hash`, `store_dir`, `excluded`. `alpaca`: `feed`/`adjustment`/`manifest_hash` from the manifest's `feed`/`adjustment`/`hash`, `store_dir = str(history_store.store_root())`. `yfinance`: `feed "yfinance"`, `adjustment "auto_adjust"`, `manifest_hash None`, `store_dir = str(backtest_cache.CACHE_DIR)`, `excluded {}`.
  - `PROVENANCE_SUFFIX = ".provenance.json"`; `provenance_path(out_path: str | Path) -> Path` = `Path(str(out_path) + PROVENANCE_SUFFIX)` (so `res.json` gives `res.json.provenance.json`); `write_provenance(out_path: str | Path) -> Path` writes `provenance()` there (UTF-8, `indent=1`, `sort_keys=True`) and returns the path. AH11's `_replay_data_source` reads the sidecar through `provenance_path`.
  - `fetch_backtest_data.load_cached(ticker)` returns `training_data.load_daily(ticker)`.
  - `fetch_backtest_data.add_data_source_arg(ap: argparse.ArgumentParser) -> None` — `--data-source {alpaca,yfinance}`, default `None` (= the config value).
  - `fetch_backtest_data.apply_data_source(args: argparse.Namespace) -> str` — `training_data.select(getattr(args, "data_source", None))`, prints `training data: <source> (<n> excluded)`, returns the source.

**Rules this task freezes (spec §3 "One switch" and "No silent fallback", Amendments "One loader seam"):**
- A run never mixes sources: `load_daily` reads only the selected source; there is no per-ticker fallback from `alpaca` to `yfinance`.
- `alpaca` with no `daily` manifest is an error on the **first** `load_daily`/`active`/`select` call, never a zero-ticker run.
- With `BACKTEST_CACHE_DIR` set, the default is `yfinance`: the ext-cache scripts (`measure_fib_confluence.py:196`, `measure_fib_diagnostic.py:564`, and through `_load_frames` the fib/v103/v104/v113 scripts) call `load_cached` under that env var and must keep reading `data/backtest_cache_ext/` (Global Constraints "Unchanged").
- The live scan, `data_refresh` and `backtest_cache.ensure_cached` never import `training_data`.

- [ ] **Step 1: Write the failing config test**

Create `$WT/tests/test_config_v162_keys.py`:

```python
"""v162: TRAINING_DATA_SOURCE, the training-data switch (spec §3)."""
import pathlib

from swingbot import config

REPO = pathlib.Path(__file__).resolve().parents[1]


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_training_data_source_is_a_data_sources_select_defaulting_to_alpaca():
    field = _field("TRAINING_DATA_SOURCE")
    assert (field.key, field.section, field.type, field.default) == (
        "TRAINING_DATA_SOURCE", "Data Sources", "select", "alpaca")
    assert [value for value, _label in field.options] == ["alpaca", "yfinance"]
    assert field.hot_reloadable is True
    assert field.search_class == "excluded"
    assert "TRAINING_DATA_SOURCE" not in config.searchable_attrs()
    assert "yfinance" in field.help and "data/market_data/" in field.help


def test_it_sits_after_the_alpaca_breaker_fields():
    attrs = [f.attr for f in config.FIELDS]
    assert attrs.index("TRAINING_DATA_SOURCE") == attrs.index("ALPACA_BREAKER_COOLDOWN_SECONDS") + 1


def test_values_are_lower_cased_and_a_typo_falls_back_to_alpaca():
    field = _field("TRAINING_DATA_SOURCE")
    assert config._cast(field, "YFinance") == "yfinance"
    assert config._cast(field, "alpaca") == "alpaca"
    assert config._cast(field, "polygon") == "alpaca"


def test_module_attribute_is_a_known_source():
    assert config.TRAINING_DATA_SOURCE in ("alpaca", "yfinance")


def test_alpaca_enabled_help_no_longer_says_backtests_never_use_alpaca():
    assert "Backtests never use Alpaca" not in _field("ALPACA_ENABLED").help


def test_env_example_lists_the_key_with_its_default():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "\nTRAINING_DATA_SOURCE=alpaca\n" in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/test_config_v162_keys.py`
Expected: FAIL — `StopIteration` in `_field("TRAINING_DATA_SOURCE")`, and the `.env.example` assertion.

- [ ] **Step 3: Add the config field and the `.env.example` line**

In `$WT/swingbot/config.py`, change the `ALPACA_ENABLED` help literal `"yfinance behaviour. Backtests never use Alpaca. Harmless with no "` to `"yfinance behaviour. Backtests read Alpaca only through the v162 history store (TRAINING_DATA_SOURCE). Harmless with no "` (only this one string piece changes).

Insert directly after the `ALPACA_BREAKER_COOLDOWN_SECONDS` `Field(...)` (ends at :782) and before `SPOT_QUOTE_MAX_AGE_SECONDS`:

```python
    Field("TRAINING_DATA_SOURCE", "TRAINING_DATA_SOURCE", "Data Sources",
          "Training data source", type="select", default="alpaca",
          options=["alpaca", "yfinance"],
          help="v162. Which daily bars every backtest, grid and the admin Tuning page train on. "
               "'alpaca' = the history store data/market_data/ (Alpaca SIP, all adjustments, "
               "from 2016; built by scripts/data/fetch_alpaca_history.py). 'yfinance' = the "
               "legacy data/backtest_cache/. With 'alpaca' and no store a run stops with an "
               "error naming the missing manifest -- never a zero-ticker run. A script's "
               "--data-source overrides this; a set BACKTEST_CACHE_DIR means yfinance. Rollback "
               "is this one line set to yfinance. The live scan and alerts never read it."),
```

Add to `_MODE_VALUES` (after the `"FVG_LEVELS_MODE"` row):

```python
    "TRAINING_DATA_SOURCE": ("alpaca", "yfinance"),
```

and change `_MODE_FALLBACK` to:

```python
_MODE_FALLBACK = {"FVG_LEVELS_MODE": "all", "TRAINING_DATA_SOURCE": "alpaca"}
```

(a typo lands on the documented default, with the `invalid ... falling back` warning `_cast_mode` already logs.)

In `$WT/.env.example`, insert after the line `ALPACA_BREAKER_COOLDOWN_SECONDS=300`:

```
# v162: training data for every backtest, grid and the admin Tuning page.
# 'alpaca' = the data/market_data/ history store (SIP, all adjustments, from 2016);
# 'yfinance' = the legacy data/backtest_cache/. Rollback is this one line.
TRAINING_DATA_SOURCE=alpaca
```

- [ ] **Step 4: Run the config tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/test_config_v162_keys.py`, then `python $WT/scripts/dev/testrun.py file tests/infra/test_env_example_sync.py` and `python $WT/scripts/dev/testrun.py file tests/infra/test_config_alpaca.py`
Expected: all PASS (6 tests in the new file).

- [ ] **Step 5: Write the failing switch tests**

Create `$WT/tests/history_store/test_training_data.py`:

```python
"""v162 AH10: the training-data switch -- source selection, the hard error on
a missing store, exclusions with reasons, provenance, and the load_cached
seam every backtest script reads through."""
from __future__ import annotations

import argparse
import json

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import backtest_cache, history_store, training_data

import fetch_backtest_data as fbd


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    """No selection leaks between tests; config and env start at the defaults."""
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _daily(close: float = 10.0) -> pd.DataFrame:
    idx = pd.DatetimeIndex(pd.to_datetime(["2016-01-04", "2016-01-05"]), name="Date")
    return pd.DataFrame({"Open": [close, close], "High": [close + 1] * 2, "Low": [close - 1] * 2,
                         "Close": [close, close + 0.5], "Volume": [1000.0, 1100.0]}, index=idx)


def _store(root, entries: dict[str, str], files: tuple[str, ...], *, hash_="h-1") -> None:
    """Hand-built daily manifest ({ticker: status}) plus CSVs for `files`."""
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    for ticker in files:
        _daily().to_csv(folder / f"{ticker}.csv", index_label="Date")
    tickers = {t: {"status": s, "sha256": None if s != "ok" else "x"} for t, s in entries.items()}
    (folder / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all", "hash": hash_, "tickers": tickers}))


ENTRIES = {"AAPL": "ok", "MSFT": "ok", "SNDK": "flagged: short-overlap",
           "GLD": "skipped: not Alpaca-eligible"}


# --- selection ------------------------------------------------------------------

def test_sources():
    assert training_data.DATA_SOURCES == ("alpaca", "yfinance")


def test_none_resolves_to_the_config_value(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")
    assert training_data.select() == "yfinance"
    assert training_data.active() == "yfinance"


def test_an_explicit_name_wins_over_config(store_root):
    _store(store_root, {"AAPL": "ok"}, ("AAPL",))
    assert training_data.select("ALPACA") == "alpaca"
    assert training_data.select("yfinance") == "yfinance"     # each call replaces the last


def test_unknown_source_is_rejected():
    with pytest.raises(ValueError, match="polygon"):
        training_data.select("polygon")


def test_backtest_cache_dir_means_yfinance_unless_named(store_root, monkeypatch):
    _store(store_root, {"AAPL": "ok"}, ("AAPL",))
    monkeypatch.setenv("BACKTEST_CACHE_DIR", "data/backtest_cache_ext")
    assert training_data.select() == "yfinance"
    assert training_data.select("alpaca") == "alpaca"


# --- the hard error ---------------------------------------------------------------

def test_alpaca_without_a_manifest_raises_naming_the_path(store_root):
    with pytest.raises(history_store.MissingStoreError) as info:
        training_data.select("alpaca")
    assert str(store_root / "daily" / "_manifest.json") in str(info.value)


def test_first_use_raises_and_nothing_stays_selected(store_root):
    with pytest.raises(history_store.MissingStoreError):
        training_data.load_daily("AAPL")
    with pytest.raises(history_store.MissingStoreError):   # never a silent zero-ticker run
        training_data.active()
    with pytest.raises(history_store.MissingStoreError):
        fbd.load_cached("AAPL")


# --- alpaca reads and exclusions ----------------------------------------------------

def test_alpaca_loads_the_store_frame(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    out = training_data.load_daily("aapl")
    assert list(out.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert out.index.name == "Date"
    assert list(out["Close"]) == [10.0, 10.5]
    assert training_data.active() == "alpaca"


def test_non_ok_entries_and_missing_files_are_excluded_with_reasons(store_root):
    _store(store_root, ENTRIES, ("AAPL",))                      # MSFT is ok but has no file
    training_data.select("alpaca")
    assert training_data.excluded() == {"GLD": "skipped: not Alpaca-eligible", "MSFT": "no file",
                                        "SNDK": "flagged: short-overlap"}
    for ticker in ("GLD", "MSFT", "SNDK"):
        assert training_data.load_daily(ticker) is None


def test_a_ticker_absent_from_the_manifest_is_excluded_when_asked_for(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    assert training_data.load_daily("ZZZ") is None
    assert training_data.excluded()["ZZZ"] == "not in store"


def test_an_ok_entry_with_an_empty_file_is_excluded(store_root):
    _store(store_root, {"AAPL": "ok"}, ())
    (store_root / "daily" / "AAPL.csv").write_text("Date,Open,High,Low,Close,Volume\n")
    training_data.select("alpaca")
    assert training_data.load_daily("AAPL") is None
    assert training_data.excluded() == {"AAPL": "empty file"}


def test_exclusion_lines_and_available_tickers(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    training_data.select("alpaca")
    assert training_data.available_tickers() == ["AAPL", "MSFT"]
    assert training_data.exclusion_lines() == ["excluded GLD: skipped: not Alpaca-eligible",
                                               "excluded SNDK: flagged: short-overlap"]


# --- yfinance is the pre-v162 loader ----------------------------------------------------

def test_yfinance_reads_the_backtest_cache_exactly_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    _daily(20.0).to_csv(tmp_path / "AAPL.csv")
    (tmp_path / "EMPTY.csv").write_text("Date,Open,High,Low,Close,Volume\n")
    training_data.select("yfinance")
    expected = pd.read_csv(tmp_path / "AAPL.csv", index_col="Date", parse_dates=True)
    pd.testing.assert_frame_equal(training_data.load_daily("AAPL"), expected)
    assert training_data.load_daily("EMPTY") is None
    assert training_data.load_daily("NOPE") is None
    assert training_data.excluded() == {}
    assert training_data.available_tickers() == ["AAPL", "EMPTY"]


# --- provenance -------------------------------------------------------------------------

def test_alpaca_provenance(store_root):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"), hash_="abc123")
    training_data.select("alpaca")
    assert training_data.provenance() == {
        "data_source": "alpaca", "feed": "sip", "adjustment": "all", "manifest_hash": "abc123",
        "store_dir": str(store_root),
        "excluded": {"GLD": "skipped: not Alpaca-eligible", "SNDK": "flagged: short-overlap"}}


def test_yfinance_provenance(tmp_path, monkeypatch):
    monkeypatch.setattr(backtest_cache, "CACHE_DIR", tmp_path)
    training_data.select("yfinance")
    assert training_data.provenance() == {
        "data_source": "yfinance", "feed": "yfinance", "adjustment": "auto_adjust",
        "manifest_hash": None, "store_dir": str(tmp_path), "excluded": {}}


def test_write_provenance_writes_the_sidecar_next_to_the_output(store_root, tmp_path):
    _store(store_root, {"AAPL": "ok"}, ("AAPL",))
    training_data.select("alpaca")
    out = tmp_path / "res.json"
    path = training_data.write_provenance(out)
    assert path == tmp_path / "res.json.provenance.json" == training_data.provenance_path(str(out))
    assert json.loads(path.read_text(encoding="utf-8")) == training_data.provenance()


# --- the load_cached seam and the CLI helpers ----------------------------------------------

def test_load_cached_delegates_to_the_switch(monkeypatch):
    seen = []
    monkeypatch.setattr(training_data, "load_daily", lambda t: seen.append(t) or "frame")
    assert fbd.load_cached("AAPL") == "frame"
    assert seen == ["AAPL"]


def test_data_source_arg_defaults_to_none_and_rejects_unknown():
    ap = argparse.ArgumentParser()
    fbd.add_data_source_arg(ap)
    assert ap.parse_args([]).data_source is None
    assert ap.parse_args(["--data-source", "yfinance"]).data_source == "yfinance"
    with pytest.raises(SystemExit):
        ap.parse_args(["--data-source", "polygon"])


def test_apply_data_source_selects_and_prints(store_root, capsys):
    _store(store_root, ENTRIES, ("AAPL", "MSFT"))
    assert fbd.apply_data_source(argparse.Namespace(data_source=None)) == "alpaca"
    assert "training data: alpaca (2 excluded)" in capsys.readouterr().out
    assert fbd.apply_data_source(argparse.Namespace(data_source="yfinance")) == "yfinance"
    assert "training data: yfinance (0 excluded)" in capsys.readouterr().out
```

- [ ] **Step 6: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_training_data.py`
Expected: FAIL at collection with `ImportError: cannot import name 'training_data' from 'swingbot.core.marketdata'`.

- [ ] **Step 7: Write the switch**

Create `$WT/swingbot/core/marketdata/training_data.py`:

```python
"""v162 training-data switch: which daily bars backtests, grids and the admin
Tuning page train on.

`alpaca` reads the history store (data/market_data/daily/, through
history_store); `yfinance` reads the legacy data/backtest_cache/ exactly as
scripts/data/fetch_backtest_data.load_cached always did. The default is
config.TRAINING_DATA_SOURCE, except that a set BACKTEST_CACHE_DIR (an explicit
yfinance-shaped cache: the ext-cache screens, the §5 snapshot legs) means
yfinance. A script's --data-source names the source outright.

One selection per process, and a run never mixes sources: there is no
per-ticker fallback. `alpaca` with no daily manifest raises
history_store.MissingStoreError on first use -- never a zero-ticker run. A
ticker the manifest marks skipped/flagged, or whose file is missing or empty,
is left out and recorded with its reason (excluded(), provenance()).

Training only: the live scan, data_refresh and backtest_cache.ensure_cached
never import this module.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from swingbot import config
from swingbot.core.marketdata import backtest_cache, history_store

log = logging.getLogger(__name__)

DATA_SOURCES = ("alpaca", "yfinance")
PROVENANCE_SUFFIX = ".provenance.json"
NO_FILE = "no file"
EMPTY_FILE = "empty file"
NOT_IN_STORE = "not in store"


@dataclass
class _Selection:
    source: str
    manifest: dict | None = None
    excluded: dict[str, str] = field(default_factory=dict)


_SELECTION: _Selection | None = None


def reset() -> None:
    """Forget the selection; the next use selects the default again."""
    global _SELECTION
    _SELECTION = None


def _default_source() -> str:
    if os.environ.get("BACKTEST_CACHE_DIR", "").strip():
        return "yfinance"
    return str(config.TRAINING_DATA_SOURCE)


def _manifest_exclusions(manifest: dict) -> dict[str, str]:
    """Every manifest ticker that cannot be trained on, with its reason."""
    out: dict[str, str] = {}
    for ticker, entry in (manifest.get("tickers") or {}).items():
        status = (entry or {}).get("status") or "missing"
        if status != "ok":
            out[ticker] = status
        elif not history_store.file_path(ticker, "daily").is_file():
            out[ticker] = NO_FILE
    return out


def select(name: str | None = None) -> str:
    """Select the training source for this process and return it."""
    global _SELECTION
    _SELECTION = None
    source = (name or _default_source()).strip().lower()
    if source not in DATA_SOURCES:
        raise ValueError(f"unknown training data source {source!r}; expected one of {DATA_SOURCES}")
    if source == "yfinance":
        _SELECTION = _Selection("yfinance")
        return source
    manifest = history_store.require_manifest("daily")
    _SELECTION = _Selection("alpaca", manifest, _manifest_exclusions(manifest))
    log.info("training data: alpaca store %s, %d ticker(s) excluded",
             history_store.store_root(), len(_SELECTION.excluded))
    return source


def _selection() -> _Selection:
    if _SELECTION is None:
        select(None)
    return _SELECTION


def active() -> str:
    return _selection().source


def _load_yfinance(ticker: str) -> pd.DataFrame | None:
    """The pre-v162 fetch_backtest_data.load_cached, unchanged."""
    p = backtest_cache.cache_path(ticker)
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col="Date", parse_dates=True)
    return df if len(df) else None


def _exclude(sel: _Selection, ticker: str, reason: str) -> None:
    if ticker not in sel.excluded:
        log.info("training data: excluded %s (%s)", ticker, reason)
    sel.excluded[ticker] = reason
    return None


def _load_alpaca(sel: _Selection, ticker: str) -> pd.DataFrame | None:
    if ticker in sel.excluded:
        return None
    if ticker not in (sel.manifest.get("tickers") or {}):
        return _exclude(sel, ticker, NOT_IN_STORE)
    frame = history_store.load(ticker, "daily")
    if frame is None:
        exists = history_store.file_path(ticker, "daily").is_file()
        return _exclude(sel, ticker, EMPTY_FILE if exists else NO_FILE)
    return frame


def load_daily(ticker: str) -> pd.DataFrame | None:
    """Daily bars (Date index, Open..Volume) from the selected source, or None."""
    sel = _selection()
    if sel.source == "yfinance":
        return _load_yfinance(ticker)
    return _load_alpaca(sel, ticker.upper().strip())


def available_tickers() -> list[str]:
    """Tickers the selected source can serve: the manifest's trainable tickers,
    or the file stems of the yfinance cache (safe names, as a glob gives them)."""
    sel = _selection()
    if sel.source == "yfinance":
        folder = backtest_cache.CACHE_DIR
        return sorted(p.stem for p in folder.glob("*.csv")) if folder.is_dir() else []
    return sorted(t for t in (sel.manifest.get("tickers") or {}) if t not in sel.excluded)


def excluded() -> dict[str, str]:
    return dict(sorted(_selection().excluded.items()))


def exclusion_lines() -> list[str]:
    return [f"excluded {ticker}: {reason}" for ticker, reason in excluded().items()]


def provenance() -> dict:
    """What a result was trained on: written next to every --json output."""
    sel = _selection()
    if sel.source == "yfinance":
        return {"data_source": "yfinance", "feed": "yfinance", "adjustment": "auto_adjust",
                "manifest_hash": None, "store_dir": str(backtest_cache.CACHE_DIR), "excluded": {}}
    return {"data_source": "alpaca", "feed": sel.manifest.get("feed"),
            "adjustment": sel.manifest.get("adjustment"), "manifest_hash": sel.manifest.get("hash"),
            "store_dir": str(history_store.store_root()), "excluded": excluded()}


def provenance_path(out_path: str | Path) -> Path:
    """The sidecar of a --json output: '<out>.provenance.json'."""
    return Path(str(out_path) + PROVENANCE_SUFFIX)


def write_provenance(out_path: str | Path) -> Path:
    path = provenance_path(out_path)
    path.write_text(json.dumps(provenance(), indent=1, sort_keys=True), encoding="utf-8")
    return path
```

- [ ] **Step 8: Delegate `load_cached` and add the CLI helpers**

In `$WT/scripts/data/fetch_backtest_data.py`, add after the line `from swingbot.core.marketdata.backtest_cache import CACHE_DIR, cache_path, normalize_ohlcv` (:49):

```python
from swingbot.core.marketdata import training_data
```

Replace `load_cached` (:68-73) with:

```python
def load_cached(ticker: str) -> pd.DataFrame | None:
    """Daily training bars for one ticker from the selected source (v162):
    TRAINING_DATA_SOURCE, a script's --data-source, or yfinance when
    BACKTEST_CACHE_DIR is set. Every backtest script that imports this reads
    through swingbot.core.marketdata.training_data."""
    return training_data.load_daily(ticker)


def add_data_source_arg(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--data-source", choices=training_data.DATA_SOURCES, default=None,
                    help="training bars: 'alpaca' (data/market_data/ history store) or "
                         "'yfinance' (data/backtest_cache/); default TRAINING_DATA_SOURCE")


def apply_data_source(args: argparse.Namespace) -> str:
    """Select the run's training source and say which one, before any bar is read."""
    source = training_data.select(getattr(args, "data_source", None))
    print(f"training data: {source} ({len(training_data.excluded())} excluded)")
    return source
```

`cache_path` stays imported: `main()` and `write_coverage` still write the yfinance cache. The module docstring is AH18's.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_training_data.py`
Expected: PASS (19 tests).

Then: `python -m radon cc -s -n C $WT/swingbot/core/marketdata/training_data.py $WT/scripts/data/fetch_backtest_data.py` prints nothing, and `python -m radon cc -s -n C $WT/swingbot/config.py` lists no function that was not listed before this task (`_cast` and `_cast_mode` gain no branch).

- [ ] **Step 10: Check the tests that reach the real loader**

Run: `python $WT/scripts/dev/testrun.py changed`
Expected: `0 failed`. With the default now `alpaca` and no store in the worktree, a test that calls the **real** `load_cached` (not monkeypatched) gets `MissingStoreError` instead of `None`. For each such failure, pin that test to the legacy source by adding these two lines at the top of the test body (add a `monkeypatch` argument if the test has none):

```python
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")   # v162: no store in tests
    training_data.reset()
```

with `from swingbot import config` and `from swingbot.core.marketdata import training_data` imported, and re-run that file alone (`testrun.py file <test>`). If the test does not reset the switch afterwards itself, also call `training_data.reset()` at its end (or use `monkeypatch` plus an autouse reset fixture in that file) so no selection leaks into the next test. Record each pinned test in the commit body. Never change the default or catch `MissingStoreError` in the loader to make a test pass.

- [ ] **Step 11: Commit**

```bash
git -C $WT add swingbot/config.py .env.example swingbot/core/marketdata/training_data.py scripts/data/fetch_backtest_data.py tests/history_store/test_training_data.py tests/test_config_v162_keys.py
git -C $WT commit -m "feat(v162): AH10 TRAINING_DATA_SOURCE switch, training_data seam, load_cached delegates to it"
```

(Add any test files Step 10 pinned to the same `git add`.)
