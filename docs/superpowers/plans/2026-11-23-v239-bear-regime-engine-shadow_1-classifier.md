# v239 — Bear-regime engine (shadow): Part 1, data fetch, classifier, episodes, calendar

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-2" -A 400 <this file>`); never read the file whole.

**Bump:** bot minor, ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md)
**Index:** [2026-11-23-v239-bear-regime-engine-shadow_0-index.md](2026-11-23-v239-bear-regime-engine-shadow_0-index.md). Its Goal, Global Constraints, Parallelisation and Task ledger apply to every task here.

This part builds everything the live engine and the study share and that
needs no database, no Flask and no Angular: the one-time SPY and ^VIX fetch
for the 1993 study (V239-1), the pure classifier and its replay of the week
of 11-16 (V239-2), confirmed episodes and the one vocabulary every surface
renders through (V239-3), and the half-day-aware `(s, D)` session pair with
the completed-bar cut (V239-4). Every test lands in the new `tests/regime/`
directory, which V239-1 adds to suite `market-signals`.

Run each task's tests with `python scripts/dev/testrun.py file <test>`. No
task here runs the full suite and none reaches Postgres.

# Phase 1 — Data and the pure core

### Task V239-1: Study data fetch, `scripts/research/` and the `tests/regime/` suite

**Model:** sonnet — a new standalone CLI with injected I/O and a suite edit; no live-path code.

**Why:** the base-rate study (V239-17) needs adjusted SPY daily from
1993-01-29 and ^VIX daily through 2026-11-20. No local cache holds either
(spec § Code reconciliation 3): `data/backtest_cache_ext/^VIX.csv` is a pinned
2009–2019 context file that is never refetched. This task writes a fetch
script into a **new** cache directory, records SHA-256 hashes in a manifest so
the study can refuse a changed file, creates `scripts/research/`, and opens
the `tests/regime/` directory every later v239 test uses. It also pins the
routing fact the live pass relies on: `^VIX` is not Alpaca-eligible, so
`get_daily_data("^VIX")` is served by yfinance (spec reconciliation 1).

**Files:**
- Create: `scripts/data/fetch_regime_data.py`
- Create: `scripts/research/README.md`
- Create: `tests/regime/__init__.py` (empty)
- Create: `tests/regime/test_fetch_regime_data.py`
- Modify: `tests/suites.toml` (suite `market-signals`, lines 25-27)
- Modify: `.gitignore` (add `data/backtest_cache_regime/` under `data/backtest_cache_ext/`, line 41; the new directory is not ignored today)

**Interfaces:**
- Consumes: `swingbot.core.marketdata.backtest_cache.normalize_ohlcv(df) -> DataFrame | None` (flattens yfinance MultiIndex columns, keeps `Open,High,Low,Close,Volume`, index named `Date`); `swingbot.core.marketdata.providers.base.is_alpaca_eligible(ticker) -> bool`; `swingbot.core.marketdata.ticker_utils.candidate_symbols(ticker) -> list[str]`.
- Produces (ledger contract, final):
  - `fetch_regime_data.CACHE_DIR = ROOT / "data/backtest_cache_regime"`
  - `START = "1993-01-01"`, `END = "2026-11-20"`, `SYMBOLS = ("SPY", "^VIX")`, `MANIFEST = "manifest.json"`
  - `csv_path(cache_dir: Path, symbol: str) -> Path`: `cache_dir / f"{symbol}.csv"` (the caret stays, `^VIX.csv`, as `fetch_backtest_data.vix_context_path` does). V239-2 and V239-17 read the CSVs through it.
  - CSV shape: header `Date,Open,High,Low,Close,Volume`, adjusted floats, LF line endings, last row dated `END`.
  - Manifest JSON: `{"symbols": {sym: {"sha256": str, "rows": int, "first": "YYYY-MM-DD", "last": "YYYY-MM-DD"}}, "command": str, "fetched_at": ISO-8601 UTC}`
  - `sha256_file(path: Path) -> str`; `write_manifest(cache_dir: Path, frames: dict[str, DataFrame], command: str) -> dict`; `main(argv: list[str] | None = None) -> int` (0 written, 2 refused)

- [ ] **Step 1: Open the suite and the test package**

Create an empty `tests/regime/__init__.py`. In `tests/suites.toml` replace the
`market-signals` block (lines 25-27):

```toml
[suites.market-signals]
description = "the market layer: indicators, entry signals, ATR band, the v239 bear-regime engine"
paths = ["tests/market/", "tests/regime/"]
```

In `.gitignore`, directly under the `data/backtest_cache_ext/` line (41), add:

```gitignore
# v239 study cache (SPY + ^VIX 1993 -> 2026-11-20), hash-pinned by manifest.json
data/backtest_cache_regime/
```

Run: `git check-ignore -v data/backtest_cache_regime/SPY.csv`
Expected: one line naming `.gitignore` and the new pattern.

- [ ] **Step 2: Write the failing tests**

Create `tests/regime/test_fetch_regime_data.py`:

```python
"""v239 V239-1: the base-rate study's SPY + ^VIX cache is fetched once into
data/backtest_cache_regime/, cut at END, written with LF endings, and pinned
by a SHA-256 manifest. No test touches the network: `_download` is faked."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "data"))

import fetch_regime_data as frd  # noqa: E402
from swingbot.core.marketdata.providers.base import is_alpaca_eligible  # noqa: E402
from swingbot.core.marketdata.ticker_utils import candidate_symbols  # noqa: E402

FIRST = {"SPY": "1993-01-29", "^VIX": "1993-01-04"}


def _frame(start: str, end: str) -> pd.DataFrame:
    index = pd.bdate_range(start, end, name="Date")
    close = np.linspace(40.0, 600.0, len(index))
    return pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0,
                         "Close": close, "Volume": np.full(len(index), 1e6)}, index=index)


class _Fake:
    def __init__(self, end: str = "2026-11-20", empty: tuple = ()):
        self.end, self.empty, self.calls = end, empty, []

    def __call__(self, symbol, start, end):
        self.calls.append((symbol, start, end))
        if symbol in self.empty:
            return None
        return _frame(FIRST[symbol], self.end)


@pytest.fixture
def fake(monkeypatch):
    stub = _Fake()
    monkeypatch.setattr(frd, "_download", stub)
    return stub


def test_constants_are_the_ledger_contract():
    assert frd.START == "1993-01-01" and frd.END == "2026-11-20"
    assert frd.SYMBOLS == ("SPY", "^VIX") and frd.MANIFEST == "manifest.json"
    assert frd.CACHE_DIR == frd.ROOT / "data" / "backtest_cache_regime"
    assert frd.csv_path(Path("x"), "^VIX") == Path("x") / "^VIX.csv"


def test_vix_is_served_by_yfinance_not_the_alpaca_router():
    # spec reconciliation 1: the live pass reads ^VIX through get_daily_data,
    # which only reaches yfinance because the caret fails the Alpaca shape.
    assert is_alpaca_eligible("^VIX") is False
    assert is_alpaca_eligible("SPY") is True
    assert candidate_symbols("^VIX") == ["^VIX"]


def test_main_writes_both_csvs_and_a_manifest_whose_hashes_match(tmp_path, fake):
    assert frd.main(["--cache-dir", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["symbols"]) == {"SPY", "^VIX"}
    for symbol in frd.SYMBOLS:
        path = frd.csv_path(tmp_path, symbol)
        entry = manifest["symbols"][symbol]
        assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        written = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
        assert entry["rows"] == len(written)
        assert entry["first"] == FIRST[symbol] and entry["last"] == "2026-11-20"
        assert list(written.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert manifest["command"].startswith("python scripts/data/fetch_regime_data.py")
    assert manifest["fetched_at"].endswith("+00:00")


def test_end_is_requested_exclusive_and_later_rows_are_cut(tmp_path, monkeypatch):
    stub = _Fake(end="2026-11-24")
    monkeypatch.setattr(frd, "_download", stub)
    assert frd.main(["--cache-dir", str(tmp_path)]) == 0
    assert {c[2] for c in stub.calls} == {"2026-11-21"}  # yfinance `end` is exclusive
    assert {c[1] for c in stub.calls} == {"1993-01-01"}
    written = pd.read_csv(frd.csv_path(tmp_path, "SPY"), parse_dates=["Date"], index_col="Date")
    assert written.index[-1] == pd.Timestamp("2026-11-20")


def test_csv_files_are_lf_only(tmp_path, fake):
    frd.main(["--cache-dir", str(tmp_path)])
    for symbol in frd.SYMBOLS:
        assert b"\r\n" not in frd.csv_path(tmp_path, symbol).read_bytes()


def test_refuses_when_the_manifest_exists_and_fetches_nothing(tmp_path, fake, capsys):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    assert frd.main(["--cache-dir", str(tmp_path)]) == 2
    assert fake.calls == []
    assert "refusing" in capsys.readouterr().out


def test_force_overwrites_an_existing_cache(tmp_path, fake):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    assert frd.main(["--cache-dir", str(tmp_path), "--force"]) == 0
    assert "symbols" in json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("stub", [_Fake(end="2026-11-19"), _Fake(empty=("^VIX",))])
def test_a_short_or_empty_symbol_writes_nothing_at_all(tmp_path, monkeypatch, stub):
    monkeypatch.setattr(frd, "_download", stub)
    assert frd.main(["--cache-dir", str(tmp_path)]) == 2
    assert list(tmp_path.iterdir()) == []


def test_a_late_first_bar_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(frd, "_download", lambda s, a, b: _frame("1999-01-04", "2026-11-20"))
    assert frd.main(["--cache-dir", str(tmp_path)]) == 2
    assert not (tmp_path / "manifest.json").exists()


def test_sha256_file_matches_hashlib(tmp_path):
    path = tmp_path / "x.csv"
    path.write_bytes(b"Date,Close\n2026-11-20,1.0\n")
    assert frd.sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()


def test_write_manifest_returns_what_it_wrote(tmp_path):
    frame = _frame("1993-01-29", "1993-03-01")
    frame.to_csv(frd.csv_path(tmp_path, "SPY"), lineterminator="\n")
    out = frd.write_manifest(tmp_path, {"SPY": frame}, "python scripts/data/fetch_regime_data.py")
    assert out == json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert out["symbols"]["SPY"]["rows"] == len(frame)
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_fetch_regime_data.py`
Expected: collection error, `ModuleNotFoundError: No module named 'fetch_regime_data'`.

- [ ] **Step 4: Write the fetch script**

Create `scripts/data/fetch_regime_data.py`:

```python
#!/usr/bin/env python3
"""v239 V239-1: one-time SPY + ^VIX daily cache for the bear-regime base-rate
study (scripts/research/regime_base_rates.py).

Fetches adjusted daily bars (yfinance, auto_adjust=True: the same adjusted
series the live scan's daily frames carry) from START through the study's
fixed END into data/backtest_cache_regime/, one CSV per symbol with LF line
endings, plus manifest.json holding each file's SHA-256, row count and first
and last dates. The study refuses to run when a file's hash differs from the
manifest, so this script refuses to overwrite an existing cache unless
--force is passed. Nothing is written unless both symbols pass their checks.

    python scripts/data/fetch_regime_data.py
    python scripts/data/fetch_regime_data.py --force          # refetch on purpose

^VIX is not Alpaca-eligible (the caret fails the US-symbol shape), so the
live engine also reads it from yfinance through get_daily_data; SPY goes to
the Alpaca router first there. This cache is yfinance for both, which is the
gap the v239 parity check (scripts/reports/regime_parity.py) measures."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
import warnings
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.marketdata.backtest_cache import normalize_ohlcv  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache_regime"
START = "1993-01-01"
END = "2026-11-20"
SYMBOLS = ("SPY", "^VIX")
MANIFEST = "manifest.json"
LATEST_FIRST_BAR = "1993-02-01"  # SPY lists 1993-01-29; ^VIX history starts in 1990
_OHLC = ["Open", "High", "Low", "Close"]


def csv_path(cache_dir: Path, symbol: str) -> Path:
    """One CSV per symbol; the caret stays (``^VIX.csv``)."""
    return Path(cache_dir) / f"{symbol}.csv"


def _download(symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """Adjusted daily bars [start, end) from yfinance (``end`` is exclusive)."""
    import yfinance as yf  # local import: the tests never reach the network

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = yf.download(symbol, start=start, end=end, interval="1d",
                          auto_adjust=True, progress=False)
    return normalize_ohlcv(raw)


def _clean(frame: pd.DataFrame, end: str) -> pd.DataFrame:
    frame = frame[_OHLC + ["Volume"]].dropna(subset=_OHLC).copy()
    frame["Volume"] = frame["Volume"].fillna(0.0)
    index = pd.DatetimeIndex(frame.index)
    frame.index = (index.tz_localize(None) if index.tz is not None else index).normalize()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    frame = frame[frame.index <= pd.Timestamp(end)]
    frame.index.name = "Date"
    return frame


def _problem(symbol: str, frame: pd.DataFrame | None) -> str | None:
    if frame is None or frame.empty:
        return f"{symbol}: the fetch returned no rows"
    first, last = frame.index[0].date().isoformat(), frame.index[-1].date().isoformat()
    if first > LATEST_FIRST_BAR:
        return f"{symbol}: first bar {first} is later than {LATEST_FIRST_BAR}"
    if last != END:
        return f"{symbol}: last bar {last} is not the study end {END}"
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(cache_dir: Path, frames: dict[str, pd.DataFrame], command: str) -> dict:
    """Hash the CSVs already on disk and write manifest.json next to them."""
    symbols = {}
    for symbol, frame in frames.items():
        symbols[symbol] = {"sha256": sha256_file(csv_path(cache_dir, symbol)),
                           "rows": int(len(frame)),
                           "first": frame.index[0].date().isoformat(),
                           "last": frame.index[-1].date().isoformat()}
    manifest = {"symbols": symbols, "command": command,
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    with open(Path(cache_dir) / MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return manifest


def _fetch_all(end_exclusive: str) -> tuple[dict[str, pd.DataFrame], str | None]:
    frames = {}
    for symbol in SYMBOLS:
        raw = _download(symbol, START, end_exclusive)
        frame = None if raw is None or raw.empty else _clean(raw, END)
        problem = _problem(symbol, frame)
        if problem is not None:
            return {}, problem
        frames[symbol] = frame
    return frames, None


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(description="Fetch SPY + ^VIX daily for the v239 base-rate study")
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    cache_dir = Path(args.cache_dir)
    if (cache_dir / MANIFEST).exists() and not args.force:
        print(f"refusing: {cache_dir / MANIFEST} exists; the study is pinned to it "
              "(pass --force to refetch on purpose)")
        return 2
    end_exclusive = (pd.Timestamp(END) + pd.Timedelta(days=1)).date().isoformat()
    frames, problem = _fetch_all(end_exclusive)
    if problem is not None:
        print(f"error: {problem}; nothing written")
        return 2
    cache_dir.mkdir(parents=True, exist_ok=True)
    for symbol, frame in frames.items():
        frame.to_csv(csv_path(cache_dir, symbol), lineterminator="\n")
    command = " ".join(["python", "scripts/data/fetch_regime_data.py", *argv])
    manifest = write_manifest(cache_dir, frames, command)
    for symbol, entry in manifest["symbols"].items():
        print(f"+ {symbol}: {entry['rows']} bars ({entry['first']} -> {entry['last']}) "
              f"sha256 {entry['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_fetch_regime_data.py`
Expected: `12 passed`, `0 failed`.

Run: `python scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: `0 failed` (the new directory belongs to exactly one suite).

- [ ] **Step 6: Create `scripts/research/README.md`**

```markdown
# scripts/research/

One-off research scripts that **describe the market** rather than test a
strategy. Nothing here is a backtest, a screen or a gate: a figure from these
scripts never licenses a live change (`docs/claude/backtest-methodology.md`).

Rules for every script in this folder:

- A fixed end date in the script, never "today", so a rerun reproduces the
  committed results doc.
- Inputs come from a hash-pinned cache; the script refuses to run when a
  file's SHA-256 differs from the recorded value.
- Any run past a few minutes checkpoints each finished unit to disk and a
  restart skips it (CLAUDE.md § Long runs).
- Results go to `docs/superpowers/results/` as Markdown written with
  `encoding="utf-8", newline="\n"`, carrying the command, the end date and
  the input hashes.

| Script | Plan | Cache | Results |
|---|---|---|---|
| `regime_base_rates.py` | v239 | `data/backtest_cache_regime/` (`scripts/data/fetch_regime_data.py`) | `docs/superpowers/results/2026-11-23-v239-regime-base-rates.md` |
```

- [ ] **Step 7: Run the real fetch once (network)**

Run: `python scripts/data/fetch_regime_data.py`
Expected: two lines, `+ SPY: <about 8500> bars (1993-01-29 -> 2026-11-20) sha256 …`
and `+ ^VIX: <about 8530> bars (1993-01-04 -> 2026-11-20) sha256 …`, exit 0.
If it prints `error: … last bar … is not the study end 2026-11-20`, yfinance has
not published the 11-20 bar: stop and report it, never move `END`. The cache is
gitignored; V239-2 cuts its committed replay fixture from it and V239-17 checks
its hashes. Paste the two printed lines into the commit message body.

- [ ] **Step 8: Commit**

```bash
git add scripts/data/fetch_regime_data.py scripts/research/README.md tests/regime/__init__.py tests/regime/test_fetch_regime_data.py tests/suites.toml .gitignore
git commit -m "feat(v239): SPY + ^VIX study cache fetch, scripts/research, tests/regime suite"
```

### Task V239-2: Pure classifier, SPY side: `RegimeDay`, rows, state and `UNKNOWN` rules

**Model:** opus — the no-lookahead indexing and the NaN and stale rules are the spec's correctness core; an off-by-one here silently mislabels every later surface and the B7–B9 screens.

**Why:** this is the missing daily trend layer (spec § The classifier). It is pure, so the live pass (V239-8), the parity check (V239-16) and the 1993 study (V239-17) all call one function on one set of rules. This task builds the module, every constant, `RegimeDay` with its row mapping, and the SPY rules (`BEAR`, `CORRECTION`, `NORMAL`, `UNKNOWN`). V239-2b adds the ^VIX side (`stress`, `pullback_trigger`), `shadow_action` and the real-bar replay. Until then `classify` accepts `vix` and returns `stress = None`, `vix_close = None`, `pullback_trigger = False`.

**Files:**
- Create: `swingbot/core/market/bear_regime.py`
- Create: `tests/regime/test_bear_regime_rules.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (ledger contract, final; module `swingbot.core.market.bear_regime`):
  - Constants (`typing.Final`): `MIN_BARS = 220`, `SMA_FAST = 50`, `SMA_SLOW = 200`, `SLOW_SLOPE_LAG = 20`, `FAST_SLOPE_LAG = 5`, `STRESS_VIX = 25.0`, `PULLBACK_VIX_RATIO = 0.85`, `PULLBACK_VIX_WINDOW = 5`; `SPY = "SPY"`, `VIX = "^VIX"`.
  - States `BEAR`, `CORRECTION`, `NORMAL`, `UNKNOWN` (values equal names), `STATES = (BEAR, CORRECTION, NORMAL, UNKNOWN)`.
  - Actions `WOULD_VETO = "would_veto"`, `CAUTION = "caution"`, `PULLBACK_WATCH = "pullback_watch"`, `ALIGNED = "aligned"`, `NONE = "none"`.
  - `VIX_GAP = "vix_gap"`; unknown reasons `REASON_STALE = "stale"`, `REASON_SHORT = "short_history"`, `REASON_NAN = "nan"` (index decision 1: V239-8 skips the insert only for `REASON_STALE`).
  - `@dataclass(frozen=True) RegimeDay(session_date, last_bar_date, state, stress=None, pullback_trigger=False, pullback_reason=None, spy_close=None, sma50=None, sma200=None, sma50_lag5=None, sma200_lag20=None, spy_high_prev=None, vix_close=None, vix_max5=None, spy_provider=None, vix_provider=None, unknown_reason=None)`.
  - `ROW_COLUMNS: tuple[str, ...]`: every field except `unknown_reason`, in field order: the `market_regime_days` columns V239-6 creates, besides `computed_at`, `doc` and `updated_at`.
  - `RegimeDay.to_row() -> dict`: `ROW_COLUMNS` values (dates as `date`, numbers as `float`) plus `doc = {"unknown_reason": ...}`; no `computed_at`.
  - `RegimeDay.from_row(row: Mapping) -> RegimeDay`: accepts `date` / `datetime` / ISO-string dates and `Decimal` / `float` numbers, ignores extra keys (`computed_at`, `updated_at`), reads `unknown_reason` from `row["doc"]`.
  - `classify(spy: DataFrame, vix: DataFrame | None, *, last_session: date, session_date: date, spy_provider: str | None = None, vix_provider: str | None = None) -> RegimeDay`. `spy` needs `High` and `Close`; any `DatetimeIndex`, naive or tz-aware (the bar's wall date is used).

**Rule details this task fixes (spec silent, inside the rules):**
- Unknown precedence: `stale` (no frame, or SPY's last bar dated ≤ `s` is not `s`), then `short_history` (< 220 bars), then `nan` (a non-finite value among the 220 closes feeding `SMA200[s−20..s]`, or in `H[s−1]`).
- An `UNKNOWN` day carries `last_bar_date` and the providers only: no numbers, `stress = None`, `pullback_trigger = False`. Every surface then shows "No reading", never a number from a broken input.

- [ ] **Step 1: Write the failing tests**

Create `tests/regime/test_bear_regime_rules.py` (V239-2b appends its ^VIX tests to this file and reuses its helpers):

```python
"""v239 V239-2: the bear-regime rules on hand-built series whose SMAs are easy
to check by hand. Each series is 260 piecewise-flat bars ending at S, so
SMA200[s] = mean(bars 60..259), SMA200[s-20] = mean(40..239),
SMA50[s] = mean(210..259) and SMA50[s-5] = mean(205..254)."""
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import bear_regime as br

S = date(2026, 10, 21)          # s, a Wednesday
D = date(2026, 10, 22)          # the session the label is for
NEXT = pd.Timestamp("2026-10-22")

# SMA200 164 (rising from 155), SMA50 196 (falling from 198), C 180.
CORRECTION = [(60, 100), (140, 150), (50, 200), (10, 180)]
# as CORRECTION, but bar s-1 closes 176 (high 177) and C[s] = 180 > H[s-1].
CORRECTION_UP_DAY = [(60, 100), (140, 150), (50, 200), (8, 180), (1, 176), (1, 180)]
# C 170 under SMA200 187 (rising from 177), SMA50 218 above it, falling from 224.
CORRECTION_UNDER_SMA200 = [(60, 100), (100, 150), (90, 230), (10, 170)]
# SMA50 100 < SMA200 175 (still rising from 170), C 100: BEAR by the cross.
BEAR_CROSS = [(60, 50), (150, 200), (50, 100)]
# SMA200 124.55 falling from 135, SMA50 198.2 above it, C 110: BEAR by the slope.
BEAR_SLOPE = [(60, 300), (150, 100), (49, 200), (1, 110)]
# meets every CORRECTION condition and the BEAR cross: BEAR wins.
BEAR_AND_CORRECTION = [(60, 50), (150, 200), (45, 100), (5, 90)]
# CORRECTION's tail, but SMA200 falls (175 -> 164) and C 180 > SMA200: NORMAL.
FALLING_SMA200 = [(60, 300), (140, 150), (50, 200), (10, 180)]
# C 199 above SMA50 196.38: NORMAL.
ABOVE_FAST = [(60, 100), (140, 150), (50, 200), (9, 180), (1, 199)]
# C 175 under SMA50 177.3, but SMA50 rose from 170: NORMAL.
RISING_FAST = [(60, 100), (140, 150), (55, 170), (4, 260), (1, 175)]


def _spy(segments=None, *, closes=None, end=S, tz=None) -> pd.DataFrame:
    if closes is None:
        closes = np.concatenate([np.full(n, float(v)) for n, v in segments])
    closes = np.asarray(closes, dtype=float)
    index = pd.bdate_range(end=pd.Timestamp(end), periods=len(closes), name="Date", tz=tz)
    return pd.DataFrame({"High": closes + 1.0, "Close": closes}, index=index)


def _rising(n=260) -> pd.DataFrame:
    return _spy(closes=np.linspace(100.0, 200.0, n))


def _vix(spy, tail=(), base=15.0) -> pd.DataFrame:
    values = np.full(len(spy), base)
    if tail:
        values[-len(tail):] = tail
    return pd.DataFrame({"Close": values}, index=spy.index)


def _classify(spy, vix=None, **kw):
    return br.classify(spy, vix, last_session=kw.pop("last_session", S),
                       session_date=kw.pop("session_date", D), **kw)


def _with_bar_after_s(frame, value):
    extra = pd.DataFrame({c: [value] for c in frame.columns},
                         index=pd.DatetimeIndex([NEXT], name="Date"))
    return pd.concat([frame, extra])


def test_frozen_constants():
    assert (br.MIN_BARS, br.SMA_FAST, br.SMA_SLOW) == (220, 50, 200)
    assert (br.SLOW_SLOPE_LAG, br.FAST_SLOPE_LAG) == (20, 5)
    assert (br.STRESS_VIX, br.PULLBACK_VIX_RATIO, br.PULLBACK_VIX_WINDOW) == (25.0, 0.85, 5)
    assert br.STATES == ("BEAR", "CORRECTION", "NORMAL", "UNKNOWN")
    assert (br.SPY, br.VIX, br.VIX_GAP) == ("SPY", "^VIX", "vix_gap")
    assert (br.WOULD_VETO, br.CAUTION, br.PULLBACK_WATCH, br.ALIGNED, br.NONE) == (
        "would_veto", "caution", "pullback_watch", "aligned", "none")


@pytest.mark.parametrize("segments, state", [
    (CORRECTION, br.CORRECTION),
    (CORRECTION_UP_DAY, br.CORRECTION),
    (CORRECTION_UNDER_SMA200, br.CORRECTION),
    (BEAR_CROSS, br.BEAR),
    (BEAR_SLOPE, br.BEAR),
    (BEAR_AND_CORRECTION, br.BEAR),
    (FALLING_SMA200, br.NORMAL),
    (ABOVE_FAST, br.NORMAL),
    (RISING_FAST, br.NORMAL),
])
def test_state_rules(segments, state):
    day = _classify(_spy(segments))
    assert day.state == state and day.unknown_reason is None


def test_a_steady_uptrend_is_normal():
    assert _classify(_rising()).state == br.NORMAL


def test_numbers_are_the_hand_computed_smas():
    day = _classify(_spy(CORRECTION))
    assert day.spy_close == 180.0 and day.spy_high_prev == 181.0
    assert day.sma200 == pytest.approx(164.0) and day.sma200_lag20 == pytest.approx(155.0)
    assert day.sma50 == pytest.approx(196.0) and day.sma50_lag5 == pytest.approx(198.0)
    assert (day.session_date, day.last_bar_date) == (D, S)
    cross = _classify(_spy(BEAR_CROSS))
    assert (cross.sma200, cross.sma200_lag20, cross.sma50) == pytest.approx((175.0, 170.0, 100.0))


def test_no_lookahead_a_bar_after_s_never_changes_the_label():
    spy = _spy(CORRECTION)
    assert _classify(_with_bar_after_s(spy, 1.0)) == _classify(spy)


def test_a_frame_ending_in_a_partial_bar_equals_the_hand_cut_frame():
    partial = _with_bar_after_s(_spy(CORRECTION), 150.0)      # today's forming bar, dated D
    assert _classify(partial) == _classify(partial.iloc[:-1])


def test_a_tz_aware_index_reads_the_wall_date():
    assert _classify(_spy(CORRECTION, tz="UTC")) == _classify(_spy(CORRECTION))


def test_short_history_is_unknown():
    day = _classify(_rising(219))
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_SHORT)
    assert _classify(_rising(220)).state == br.NORMAL


@pytest.mark.parametrize("column, pos, value", [
    ("Close", -1, np.nan), ("Close", -100, np.nan), ("Close", -220, np.nan),
    ("High", -2, np.nan), ("Close", -5, np.inf)])
def test_a_non_finite_input_is_unknown(column, pos, value):
    spy = _rising()
    spy.iloc[pos, spy.columns.get_loc(column)] = value
    day = _classify(spy)
    assert (day.state, day.unknown_reason) == (br.UNKNOWN, br.REASON_NAN)


def test_a_nan_outside_the_window_is_ignored():
    spy = _rising()
    spy.iloc[-221, spy.columns.get_loc("Close")] = np.nan
    assert _classify(spy).state == br.NORMAL


def test_a_stale_spy_frame_is_unknown_and_says_which_bar_it_saw():
    day = _classify(_spy(CORRECTION), last_session=date(2026, 10, 22),
                    session_date=date(2026, 10, 23))
    assert (day.state, day.unknown_reason, day.last_bar_date) == (br.UNKNOWN, br.REASON_STALE, S)


@pytest.mark.parametrize("spy", [None, pd.DataFrame({"High": [], "Close": []})])
def test_no_spy_frame_is_stale(spy):
    day = _classify(spy)
    assert (day.state, day.unknown_reason, day.last_bar_date) == (br.UNKNOWN, br.REASON_STALE, None)


def test_an_unknown_day_carries_no_numbers_but_keeps_the_providers():
    spy = _rising(219)
    day = _classify(spy, _vix(spy, tail=(40.0,)), spy_provider="alpaca", vix_provider="yfinance")
    assert day.stress is None and day.pullback_trigger is False
    assert all(getattr(day, f) is None for f in ("spy_close", "sma50", "sma200", "vix_close", "vix_max5"))
    assert (day.spy_provider, day.vix_provider) == ("alpaca", "yfinance")


def test_row_round_trip_and_columns():
    day = _classify(_spy(CORRECTION), spy_provider="alpaca", vix_provider="yfinance")
    row = day.to_row()
    assert set(row) == set(br.ROW_COLUMNS) | {"doc"}
    assert "unknown_reason" not in br.ROW_COLUMNS and "computed_at" not in row
    assert row["doc"] == {"unknown_reason": None}
    assert br.RegimeDay.from_row(row) == day


def test_from_row_accepts_iso_dates_decimals_and_extra_keys():
    day = _classify(_rising(219))
    row = {**day.to_row(), "session_date": "2026-10-22", "last_bar_date": datetime(2026, 10, 21),
           "computed_at": "2026-10-22T13:00:00+00:00", "updated_at": None}
    assert br.RegimeDay.from_row(row) == day
    assert br.RegimeDay.from_row(row).unknown_reason == br.REASON_SHORT
    full = _classify(_spy(CORRECTION)).to_row()
    full["sma200"] = Decimal("164.0")
    assert br.RegimeDay.from_row(full).sma200 == 164.0


def test_regime_day_is_frozen():
    day = _classify(_spy(CORRECTION))
    with pytest.raises(Exception):
        day.state = br.BEAR  # type: ignore[misc]
    assert replace(day, state=br.BEAR).state == br.BEAR
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_bear_regime_rules.py`
Expected: collection error, `ImportError: cannot import name 'bear_regime'`.

- [ ] **Step 3: Write the classifier (SPY side)**

Create `swingbot/core/market/bear_regime.py`:

```python
"""v239: the daily bear-regime classifier, run in shadow.

Pure: completed daily SPY and ^VIX frames in, one ``RegimeDay`` out. The label
is FOR trading session ``session_date`` (D) and reads only bars dated on or
before ``last_session`` (s), the last completed session before D. ``classify``
truncates its frames to s itself, so a caller that forgot the cut cannot leak
a later bar (docs/claude/architecture.md NO-LOOKAHEAD).

Rules (spec section "The classifier"), all indexed from s:
  BEAR        C < SMA200 and (SMA200 < SMA200[s-20] or SMA50 < SMA200)
  CORRECTION  not BEAR, C < SMA50, SMA50 < SMA50[s-5] and SMA200 > SMA200[s-20]
  NORMAL      neither
  UNKNOWN     SPY's last bar is not s (stale), fewer than MIN_BARS bars, or a
              non-finite close feeding SMA200[s-20..s] or a non-finite H[s-1]
  stress      V[s] >= STRESS_VIX; None when no ^VIX bar is dated exactly s
  pullback    CORRECTION, V[s] <= PULLBACK_VIX_RATIO * max(V[s-4..s]) and
              C[s] > H[s-1]; False with reason "vix_gap" on a window hole
The day label is raw (no hysteresis): the B7-B9 screens use exactly these
rules; smoothing for people lives in regime_episodes. The constants are
frozen: changing one is a new idea under the slate rows, never a knob.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Final

import numpy as np
import pandas as pd

MIN_BARS: Final = 220
SMA_FAST: Final = 50
SMA_SLOW: Final = 200
SLOW_SLOPE_LAG: Final = 20
FAST_SLOPE_LAG: Final = 5
STRESS_VIX: Final = 25.0
PULLBACK_VIX_RATIO: Final = 0.85
PULLBACK_VIX_WINDOW: Final = 5

SPY: Final = "SPY"
VIX: Final = "^VIX"

BEAR: Final = "BEAR"
CORRECTION: Final = "CORRECTION"
NORMAL: Final = "NORMAL"
UNKNOWN: Final = "UNKNOWN"
STATES: Final = (BEAR, CORRECTION, NORMAL, UNKNOWN)

WOULD_VETO: Final = "would_veto"
CAUTION: Final = "caution"
PULLBACK_WATCH: Final = "pullback_watch"
ALIGNED: Final = "aligned"
NONE: Final = "none"

VIX_GAP: Final = "vix_gap"
REASON_STALE: Final = "stale"
REASON_SHORT: Final = "short_history"
REASON_NAN: Final = "nan"

_DATE_FIELDS = ("session_date", "last_bar_date")
_FLOAT_FIELDS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20",
                 "spy_high_prev", "vix_close", "vix_max5")


@dataclass(frozen=True)
class RegimeDay:
    """One labelled session. ``session_date`` is D; ``last_bar_date`` is the
    date of SPY's last bar the label read (s, unless the frame was stale)."""

    session_date: dt.date
    last_bar_date: dt.date | None
    state: str
    stress: bool | None = None
    pullback_trigger: bool = False
    pullback_reason: str | None = None
    spy_close: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    sma50_lag5: float | None = None
    sma200_lag20: float | None = None
    spy_high_prev: float | None = None
    vix_close: float | None = None
    vix_max5: float | None = None
    spy_provider: str | None = None
    vix_provider: str | None = None
    unknown_reason: str | None = None

    def to_row(self) -> dict:
        """The ``market_regime_days`` columns plus ``doc``; no ``computed_at``."""
        row = {name: getattr(self, name) for name in ROW_COLUMNS}
        row["doc"] = {"unknown_reason": self.unknown_reason}
        return row

    @classmethod
    def from_row(cls, row: Mapping) -> "RegimeDay":
        values = {name: row.get(name) for name in ROW_COLUMNS}
        for name in _DATE_FIELDS:
            values[name] = _as_date(values[name])
        for name in _FLOAT_FIELDS:
            values[name] = None if values[name] is None else float(values[name])
        values["pullback_trigger"] = bool(values["pullback_trigger"])
        doc = row.get("doc") or {}
        return cls(**values, unknown_reason=doc.get("unknown_reason"))


ROW_COLUMNS: Final = tuple(f.name for f in fields(RegimeDay) if f.name != "unknown_reason")


def _as_date(value) -> dt.date | None:
    if value is None or (isinstance(value, dt.date) and not isinstance(value, dt.datetime)):
        return value
    if isinstance(value, dt.datetime):
        return value.date()
    return dt.date.fromisoformat(str(value)[:10])


def _dates(df: pd.DataFrame) -> np.ndarray:
    """Each bar's wall date (a tz-aware index keeps its own calendar day)."""
    return pd.DatetimeIndex(df.index).date


def _upto(df: pd.DataFrame | None, last_session: dt.date) -> pd.DataFrame | None:
    if df is None or len(df) == 0:
        return None
    return df.loc[_dates(df) <= last_session]


def _last_date(frame: pd.DataFrame | None) -> dt.date | None:
    if frame is None or len(frame) == 0:
        return None
    return pd.Timestamp(frame.index[-1]).date()


def _column(frame: pd.DataFrame, name: str) -> np.ndarray:
    return pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)


def _finite_inputs(frame: pd.DataFrame) -> bool:
    closes = _column(frame, "Close")[-(SMA_SLOW + SLOW_SLOPE_LAG):]
    return bool(np.isfinite(closes).all()) and math.isfinite(_column(frame, "High")[-2])


def _unknown_reason(frame: pd.DataFrame | None, last_session: dt.date) -> str | None:
    if _last_date(frame) != last_session:
        return REASON_STALE
    if len(frame) < MIN_BARS:
        return REASON_SHORT
    if not _finite_inputs(frame):
        return REASON_NAN
    return None


def _sma(closes: np.ndarray, n: int, lag: int = 0) -> float:
    end = len(closes) - lag
    return float(closes[end - n:end].mean())


def _measures(frame: pd.DataFrame) -> dict:
    closes = _column(frame, "Close")
    return {"spy_close": float(closes[-1]),
            "sma50": _sma(closes, SMA_FAST),
            "sma200": _sma(closes, SMA_SLOW),
            "sma50_lag5": _sma(closes, SMA_FAST, FAST_SLOPE_LAG),
            "sma200_lag20": _sma(closes, SMA_SLOW, SLOW_SLOPE_LAG),
            "spy_high_prev": float(_column(frame, "High")[-2])}


def _state(m: dict) -> str:
    close, fast, slow = m["spy_close"], m["sma50"], m["sma200"]
    if close < slow and (slow < m["sma200_lag20"] or fast < slow):
        return BEAR
    if close < fast and fast < m["sma50_lag5"] and slow > m["sma200_lag20"]:
        return CORRECTION
    return NORMAL


def classify(spy: pd.DataFrame, vix: pd.DataFrame | None, *, last_session: dt.date,
             session_date: dt.date, spy_provider: str | None = None,
             vix_provider: str | None = None) -> RegimeDay:
    """Label session ``session_date`` from bars dated on or before ``last_session``."""
    frame = _upto(spy, last_session)
    base = {"session_date": session_date, "last_bar_date": _last_date(frame),
            "spy_provider": spy_provider, "vix_provider": vix_provider}
    reason = _unknown_reason(frame, last_session)
    if reason is not None:
        return RegimeDay(state=UNKNOWN, unknown_reason=reason, **base)
    measures = _measures(frame)
    return RegimeDay(state=_state(measures), **measures, **base)
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_bear_regime_rules.py`
Expected: `0 failed`. If a state case fails, recompute that series' SMAs by hand from the windows in the test docstring before touching the rules: the rules are the spec's and are frozen.

Run: `python -m radon cc -s -n C swingbot/core/market/bear_regime.py`
Expected: no output (every function below grade C).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/bear_regime.py tests/regime/test_bear_regime_rules.py
git commit -m "feat(v239): bear-regime classifier, SPY side -- RegimeDay rows, state and UNKNOWN rules"
```

### Task V239-2b: Pure classifier, ^VIX side: `stress`, `pullback_trigger`, `shadow_action`, real-bar replay

**Model:** opus — exact-date VIX alignment without forward fill, the pullback window and the replay pin decide what B8 and B9 will screen; a wrong match reads a later VIX bar.

**Why:** completes the classifier V239-2 started (spec § Rules, § Shadow action). It adds `stress` (`V[s] ≥ 25`), the pullback trigger (`V[s] ≤ 0.85 × max(V[s−4..s])` and `C[s] > H[s−1]`, CORRECTION only), the `vix_gap` reason, and the pure `shadow_action` table. It then commits a fixture of real SPY and ^VIX bars cut from V239-1's cache and pins the spec's replay of the week: CORRECTION from `D = 2026-10-22`, stress on `D = 11-17..11-20`, never BEAR.

**Files:**
- Modify: `swingbot/core/market/bear_regime.py` (created by V239-2)
- Modify: `tests/regime/test_bear_regime_rules.py` (created by V239-2; append)
- Create: `tests/regime/test_bear_regime_replay.py`
- Create: `tests/fixtures/regime/spy_vix_replay.csv` (generated in Step 5, committed)

**Interfaces:**
- Consumes: everything V239-2 produced in `bear_regime`; V239-1's `fetch_regime_data.csv_path` and `CACHE_DIR` (only to cut the fixture).
- Produces (ledger contract, final): `classify` now fills `stress`, `vix_close`, `vix_max5`, `pullback_trigger`, `pullback_reason`; `shadow_action(state: str, stress: bool | None, pullback_trigger: bool, direction: str) -> str` (`"bullish"` / `"bearish"`, anything else gives `NONE`). V239-3, V239-7 and V239-9 import `shadow_action`.

**Rule details this task fixes (spec silent, inside the rules):**
- The VIX window is the dates of SPY's last five bars (`s−4..s`), matched by exact date. A VIX bar on a non-SPY date, or after `s`, is never read.
- `pullback_reason` is `"vix_gap"` only when the state is `CORRECTION` and a window bar is missing or NaN, else `None`. `vix_max5` is `None` on a gap; `stress` still reads `V[s]` when that one bar exists.

- [ ] **Step 1: Append the failing ^VIX and action tests**

Append to `tests/regime/test_bear_regime_rules.py` (helpers `_spy`, `_rising`, `_vix`, `_classify`, `_with_bar_after_s` and the series constants are already there):

```python


# --- V239-2b: the ^VIX side and the shadow action -------------------------------

@pytest.mark.parametrize("vix_at_s, stress", [(25.0, True), (24.99, False), (37.6, True)])
def test_stress_threshold_is_inclusive(vix_at_s, stress):
    spy = _spy(CORRECTION)
    day = _classify(spy, _vix(spy, tail=(vix_at_s,)))
    assert day.stress is stress and day.vix_close == vix_at_s


def test_stress_is_none_without_a_vix_bar_dated_s():
    spy = _spy(CORRECTION)
    assert _classify(spy, None).stress is None
    assert _classify(spy, _vix(spy).iloc[:-1]).stress is None          # VIX lags a day
    assert _classify(spy, _vix(spy, tail=(float("nan"),))).stress is None


def test_pullback_fires_on_an_up_day_as_vix_eases():
    spy = _spy(CORRECTION_UP_DAY)
    day = _classify(spy, _vix(spy, tail=(30, 34, 36, 33, 30)))  # 30 <= 0.85 * 36 = 30.6
    assert day.state == br.CORRECTION
    assert day.pullback_trigger is True and day.pullback_reason is None
    assert day.vix_max5 == 36.0 and day.spy_high_prev == 177.0


def test_pullback_needs_vix_to_ease():
    spy = _spy(CORRECTION_UP_DAY)
    assert _classify(spy, _vix(spy, tail=(30, 34, 36, 33, 31))).pullback_trigger is False


def test_pullback_needs_a_close_above_the_prior_high():
    spy = _spy(CORRECTION)                                       # C 180, H[s-1] 181
    assert _classify(spy, _vix(spy, tail=(30, 34, 36, 33, 30))).pullback_trigger is False


def test_pullback_only_in_a_correction():
    spy = _rising()
    day = _classify(spy, _vix(spy, tail=(30, 34, 36, 33, 20)))
    assert day.state == br.NORMAL
    assert day.pullback_trigger is False and day.pullback_reason is None


def test_a_vix_hole_in_the_window_is_a_gap_never_a_trigger():
    spy = _spy(CORRECTION_UP_DAY)
    vix = _vix(spy, tail=(30, 34, 36, 33, 30)).drop(spy.index[-3])
    day = _classify(spy, vix)
    assert day.pullback_trigger is False and day.pullback_reason == br.VIX_GAP
    assert day.vix_max5 is None and day.stress is True and day.vix_close == 30.0


def test_no_vix_at_all_in_a_correction_records_the_gap():
    day = _classify(_spy(CORRECTION), None)
    assert (day.pullback_trigger, day.pullback_reason, day.vix_close) == (False, br.VIX_GAP, None)


def test_no_lookahead_a_vix_bar_after_s_is_never_read():
    spy = _spy(CORRECTION_UP_DAY)
    vix = _vix(spy, tail=(30, 34, 36, 33, 30))
    plain = _classify(spy, vix)
    assert _classify(_with_bar_after_s(spy, 1.0), _with_bar_after_s(vix, 90.0)) == plain


def test_a_vix_bar_on_a_non_spy_date_is_ignored():
    spy = _spy(CORRECTION_UP_DAY)
    vix = _vix(spy, tail=(30, 34, 36, 33, 30))
    saturday = pd.DataFrame({"Close": [99.0]}, index=pd.DatetimeIndex([pd.Timestamp("2026-10-17")]))
    assert _classify(spy, pd.concat([vix, saturday]).sort_index()) == _classify(spy, vix)


@pytest.mark.parametrize("state, stress, pullback, direction, action", [
    (br.BEAR, None, False, "bullish", br.WOULD_VETO),
    (br.BEAR, True, False, "bullish", br.WOULD_VETO),
    (br.CORRECTION, True, False, "bullish", br.WOULD_VETO),
    (br.CORRECTION, False, False, "bullish", br.CAUTION),
    (br.CORRECTION, None, False, "bullish", br.CAUTION),
    (br.CORRECTION, True, True, "bullish", br.PULLBACK_WATCH),   # pullback wins over would_veto
    (br.CORRECTION, False, True, "bullish", br.PULLBACK_WATCH),
    (br.NORMAL, True, False, "bullish", br.NONE),
    (br.UNKNOWN, None, True, "bullish", br.NONE),
    (br.BEAR, True, False, "bearish", br.ALIGNED),
    (br.CORRECTION, False, True, "bearish", br.ALIGNED),
    (br.NORMAL, None, False, "bearish", br.NONE),
    (br.UNKNOWN, None, False, "bearish", br.NONE),
    (br.BEAR, True, False, "long", br.NONE),
    (br.BEAR, True, False, "", br.NONE),
])
def test_shadow_action_table(state, stress, pullback, direction, action):
    assert br.shadow_action(state, stress, pullback, direction) == action
```

- [ ] **Step 2: Write the failing replay test**

Create `tests/regime/test_bear_regime_replay.py`:

```python
"""v239 V239-2b: the spec's replay of the 2026 decline, on real bars.

Fixture: tests/fixtures/regime/spy_vix_replay.csv, adjusted SPY high/close and
^VIX close per SPY session, 2025-08-01 -> 2026-11-20, cut from
data/backtest_cache_regime/ (scripts/data/fetch_regime_data.py, V239-1).
vix_close is blank where ^VIX had no bar that session: never filled.

Convention (spec "Replay convention"): "CORRECTION from 10-22" means
D = 2026-10-22, labelled from s = 2026-10-21's close. Each D is labelled from
the full frames; classify cuts them to s itself, so this is also a
no-lookahead check on real data. These expectations are the spec's own: if
one fails, report it, never edit it."""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.market import bear_regime as br

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "regime" / "spy_vix_replay.csv"
FIRST_D, LAST_D, NEXT_D = date(2026, 10, 22), date(2026, 11, 20), date(2026, 11, 23)
STRESS_DAYS = {date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19), date(2026, 11, 20)}


@pytest.fixture(scope="module")
def labels() -> dict:
    raw = pd.read_csv(FIXTURE, parse_dates=["Date"], index_col="Date")
    spy = raw.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
    vix = raw[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
    sessions = [ts.date() for ts in spy.index]
    out = {}
    for s, d in zip(sessions, sessions[1:] + [NEXT_D]):
        if d >= date(2026, 10, 15):
            out[d] = br.classify(spy, vix, last_session=s, session_date=d,
                                 spy_provider="yfinance", vix_provider="yfinance")
    return out


def test_fixture_covers_the_window_with_enough_history():
    raw = pd.read_csv(FIXTURE, parse_dates=["Date"], index_col="Date")
    assert list(raw.columns) == ["spy_high", "spy_close", "vix_close"]
    assert raw.index[-1] == pd.Timestamp("2026-11-20")
    assert (raw.index <= pd.Timestamp("2026-10-21")).sum() >= br.MIN_BARS + 40


def test_correction_starts_on_d_2026_10_22(labels):
    assert labels[date(2026, 10, 21)].state != br.CORRECTION
    window = {d: day.state for d, day in labels.items() if FIRST_D <= d <= LAST_D}
    assert window and set(window.values()) == {br.CORRECTION}, window


def test_never_bear_through_the_decline(labels):
    assert all(day.state != br.BEAR for d, day in labels.items() if d >= FIRST_D)
    last = labels[NEXT_D]                                # s = 11-20, SPY at its low
    assert last.sma200 > last.sma200_lag20              # SMA200 still rising
    assert last.spy_close < last.sma200                 # under SMA200, yet not BEAR


def test_stress_exactly_on_d_11_17_to_11_20(labels):
    window = {d: day for d, day in labels.items() if FIRST_D <= d <= LAST_D}
    assert {d for d, day in window.items() if day.stress} == STRESS_DAYS
    assert all(day.stress is not None for day in window.values())


def test_every_day_is_a_full_reading_from_an_earlier_bar(labels):
    for d, day in labels.items():
        assert day.state != br.UNKNOWN, (d, day.unknown_reason)
        assert day.last_bar_date < d
```

- [ ] **Step 3: Run both test files to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_bear_regime_rules.py`
Expected: the new stress, pullback and gap tests fail (`stress` is `None`) and `test_shadow_action_table` fails with `AttributeError: ... has no attribute 'shadow_action'`; the V239-2 tests still pass.

Run: `python scripts/dev/testrun.py file tests/regime/test_bear_regime_replay.py`
Expected: errors, `FileNotFoundError` for the fixture.

- [ ] **Step 4: Add the ^VIX side and the shadow action**

In `swingbot/core/market/bear_regime.py`, under `_FLOAT_FIELDS`, add:

```python
_LONG_BY_STATE = {BEAR: WOULD_VETO, CORRECTION: CAUTION}
```

Directly above `def classify`, add:

```python
def _finite_or_none(value) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _vix_window(vix: pd.DataFrame | None,
                window: list[dt.date]) -> tuple[float | None, float | None]:
    """(V[s], max(V[s-4..s])) matched by exact date, never filled; the max is
    None when any of the window's bars is missing or NaN."""
    frame = _upto(vix, window[-1])
    if frame is None or len(frame) == 0:
        return None, None
    series = pd.Series(_column(frame, "Close"), index=_dates(frame))
    series = series[~series.index.duplicated(keep="last")]
    values = [_finite_or_none(series.get(d)) for d in window]
    if any(v is None for v in values):
        return values[-1], None
    return values[-1], max(values)


def _pullback(state: str, m: dict, vix_close: float | None,
              vix_max5: float | None) -> tuple[bool, str | None]:
    if state != CORRECTION:
        return False, None
    if vix_close is None or vix_max5 is None:
        return False, VIX_GAP
    eased = vix_close <= PULLBACK_VIX_RATIO * vix_max5
    return bool(eased and m["spy_close"] > m["spy_high_prev"]), None
```

Replace the last two lines of `classify` (`measures = _measures(frame)` and the `return RegimeDay(state=_state(measures), ...)`) with:

```python
    measures = _measures(frame)
    state = _state(measures)
    vix_close, vix_max5 = _vix_window(vix, list(_dates(frame)[-PULLBACK_VIX_WINDOW:]))
    trigger, why = _pullback(state, measures, vix_close, vix_max5)
    return RegimeDay(state=state, stress=None if vix_close is None else vix_close >= STRESS_VIX,
                     pullback_trigger=trigger, pullback_reason=why, vix_close=vix_close,
                     vix_max5=vix_max5, **measures, **base)
```

At the end of the module, add:

```python
def shadow_action(state: str, stress: bool | None, pullback_trigger: bool, direction: str) -> str:
    """What the engine WOULD do with a plan of ``direction`` (spec table).

    A pullback day wins over would_veto: it is the panic easing inside a
    correction, so "would skip" and "pullback watch" never show together.
    """
    if direction == "bearish":
        return ALIGNED if state in (BEAR, CORRECTION) else NONE
    if direction != "bullish":
        return NONE
    if state == CORRECTION and pullback_trigger:
        return PULLBACK_WATCH
    if state == CORRECTION and stress is True:
        return WOULD_VETO
    return _LONG_BY_STATE.get(state, NONE)
```

Run: `python scripts/dev/testrun.py file tests/regime/test_bear_regime_rules.py`
Expected: `0 failed`.

Run: `python -m radon cc -s -n C swingbot/core/market/bear_regime.py`
Expected: no output.

- [ ] **Step 5: Cut the fixture from V239-1's cache**

V239-1's real fetch must have run (`data/backtest_cache_regime/manifest.json` exists). Run once, from the repo root:

```bash
python - <<'PY'
import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0, "scripts/data")
import fetch_regime_data as frd
spy = pd.read_csv(frd.csv_path(frd.CACHE_DIR, "SPY"), parse_dates=["Date"], index_col="Date")
vix = pd.read_csv(frd.csv_path(frd.CACHE_DIR, "^VIX"), parse_dates=["Date"], index_col="Date")
spy = spy.loc["2025-08-01":"2026-11-20"]
out = pd.DataFrame({"spy_high": spy["High"], "spy_close": spy["Close"]}, index=spy.index)
out["vix_close"] = vix["Close"].reindex(spy.index)     # exact session match, never filled
out.index.name = "Date"
path = Path("tests/fixtures/regime/spy_vix_replay.csv")
path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(path, float_format="%.6f", lineterminator="\n")
print(len(out), out.index[0].date(), out.index[-1].date(), "vix holes:", int(out["vix_close"].isna().sum()))
PY
```

Expected: about `330 2025-08-01 2026-11-20 vix holes: 0`.

- [ ] **Step 6: Run the replay test**

Run: `python scripts/dev/testrun.py file tests/regime/test_bear_regime_replay.py`
Expected: `0 failed`. If an expectation fails on the real bars, do **not** edit the expectation or the rules. Print a per-day table (D, state, stress, spy_close, sma50, sma200, sma200_lag20, vix_close) from the `labels` fixture logic and stop with `BLOCKED: replay disagrees with the spec on <dates>`: the spec's claim and the slate addendum then go back to the partner, because B7–B9 screen these exact rules.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/bear_regime.py tests/regime/test_bear_regime_rules.py tests/regime/test_bear_regime_replay.py tests/fixtures/regime/spy_vix_replay.csv
git commit -m "feat(v239): bear-regime VIX side, shadow action, real-bar replay of the 2026 decline"
```

