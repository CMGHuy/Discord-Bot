# v162 Alpaca history store, part 3b: `--cache-dir` scripts, ledger field, badge lookup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task AH14:" -A 500 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_3b-cache-dir-ledger-badge.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md) (§3 training switch, § Research discipline, Amendments "Ledger field is optional", "Registry rows are keyed by source", "One loader seam")
**Bump:** bot patch
**Edge:** none (integrity)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md) carries the Global Constraints, `## Parallelisation`, the shared contracts and the task ledger. Every task below implicitly includes them. Ledger part 3 outgrew the 1500-line cap: AH11 and AH12 are in [`2026-10-15-v162-alpaca-history-store_3-script-wiring-registry.md`](2026-10-15-v162-alpaca-history-store_3-script-wiring-registry.md), AH13–AH15 are here.

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store`, `$R` = the main tree. Never `cd`; use `git -C $WT` and absolute paths. After each task `git -C $R status --short` shows the main tree unchanged.
- The switch is AH10's `swingbot/core/marketdata/training_data.py`. The names this part uses, exactly as AH10 defines them: `DATA_SOURCES`, `select(name=None) -> str` (a `None` name means `"yfinance"` when env `BACKTEST_CACHE_DIR` is set, else `config.TRAINING_DATA_SOURCE`; `"alpaca"` raises `history_store.MissingStoreError` when the `daily` manifest is absent), `active()`, `reset()`, `load_daily(ticker)`, `available_tickers()` (sorted), `excluded()`, `exclusion_lines()`, `provenance()`, `provenance_path(out)`, `write_provenance(out)`; and in `scripts/data/fetch_backtest_data.py`: `add_data_source_arg(ap)` (`--data-source {alpaca,yfinance}`, default `None`) and `apply_data_source(args) -> str`.
- **Process pools.** A pool worker started with `spawn` (Windows) re-imports `training_data` and would select the config default instead of the run's `--data-source`. Every pool whose workers read bars gets `initializer=training_data.select, initargs=(training_data.active(),)`.
- Tests in `tests/history_store/` rely on AH2's `conftest.py` (`scripts/data` and `scripts/ops` on `sys.path`; fixture `store_root` points `HISTORY_STORE_DIR` at `tmp_path/"market_data"` and returns it). They build the store by hand in the index's manifest shape and reset the switch around each test exactly like AH10's `_fresh_switch` fixture. AH14 and AH15 tests live in `tests/backtesting/` and `tests/scripts/`, next to the files they cover.
- **Guardrail.** `.claude/hooks/guardrails.py` `_rule_closed_preregistration` denies a Bash command that names `run_backtest_range.py` or `tune_strategy.py` together with a closed knob name, and the list includes the literal registry status word for a passing row. No command below does that. Edit files with the Edit tool rather than a shell heredoc that quotes code.
- Per-task runs: `python $WT/scripts/dev/testrun.py file <test>`. Complexity: `python -m radon cc -s -n C <files>` lists no new function, and every legacy function it lists keeps its score.

# Phase C (end): `--cache-dir` scripts, ledger, badge lookup

### Task AH13: `--cache-dir` scripts and `backtest_wf._frame_for`

**Model:** opus — one rule applied across nine legacy scripts, several of them dense one-line-per-statement files with resumable run directories whose `run.json` must stay comparable, plus the fold harness every walk-forward script reads through.

**Files:**
- Create: `scripts/backtest/cache_dir_source.py`. It is not in the index ledger row: it holds the `--cache-dir` rule once instead of nine times, and no other task touches it.
- Modify: `swingbot/core/backtesting/backtest_wf.py` (`_frame_for` :84-112)
- Modify: `scripts/backtest/wf_components.py` (imports :38-49; `_render` OHLCV line :182; `main` :212-255)
- Modify: `scripts/backtest/validate_component.py` (`main` :362-368)
- Modify: `scripts/backtest/measure_trend_signal_overlap.py` (`main` :383-410)
- Modify: `scripts/backtest/measure_adjacent_gate_effect.py` (import :52-55; `main` :208-235)
- Modify: `scripts/backtest/measure_dcb_veto.py` (`load_frames` :105-119; `main` :246-293)
- Modify: `scripts/backtest/measure_rs_gate_effect.py` (import :91; `main` :405-462)
- Modify: `scripts/backtest/measure_armed_entries.py` (`load_frame` :45-55; `run_meta` :114-117; `_map` :120-126; `cmd_replay` :129-160; `cmd_permute` :248-260; `main.common` :287-289)
- Modify: `scripts/backtest/measure_structure_arm.py` (`run_meta` :108-111; `_claim_run_dir` :121-130; `cmd_replay` :139-160; `cmd_permute` :262-272; `_parser.command` :293-297)
- Modify: `scripts/backtest/measure_earnings_blackout.py` (`load_frame` :16-18; `load_calendar` :19-22; `cmd_replay` :58-70; `cmd_permute` :91-95; `main.common` :99)
- Test: `tests/history_store/test_cache_dir_scripts.py`

**Interfaces:**
- Consumes (AH10): `fetch_backtest_data.add_data_source_arg`, `apply_data_source`; `training_data.select`, `active`, `reset`, `load_daily`, `available_tickers`, `write_provenance`; `history_store.MissingStoreError` (AH2); `backtest_cache.cache_path` (existing, `backtest_cache.py:59`).
- Produces (ledger AH13): `backtest_wf._frame_for(symbol)` reads through `training_data.load_daily`. The rule: **an explicit `--cache-dir` means a yfinance-shaped directory and forces `select("yfinance")`; without it, frames come from the switch** (`--data-source`, else yfinance when `BACKTEST_CACHE_DIR` is set, else `TRAINING_DATA_SOURCE`, which is AH10's `select(None)`). `--cache-dir` together with `--data-source alpaca` is an error.
- Produces (`scripts/backtest/cache_dir_source.py`, used only by this task's scripts):
  - `CACHE_DIR_HELP: str`; `add_args(ap) -> None` (adds `--data-source`; each script keeps its own `--cache-dir`, now `default=None`).
  - `as_dir(value) -> Path | None`.
  - `resolve(args) -> Path | None`: the rule above. It returns the directory or `None`, selects the source, and prints one `training data: ...` line.
  - `load_frame(cache_dir: Path | str | None, symbol: str) -> pd.DataFrame | None`: `None` gives `training_data.load_daily(symbol)`; a directory gives `<dir>/<cache_path(symbol).name>` read with a `Date` index (`None` when missing or empty).
  - `listing(cache_dir) -> list[str]`: `available_tickers()`, or the sorted CSV stems of the directory.
  - `load_all(cache_dir, limit: int | None = None) -> dict[str, pd.DataFrame]`: a directory is globbed and read exactly as the scripts did before (first `limit` paths); `None` loads the first `limit` training tickers.
  - `cache_files(cache_dir) -> list[str]`: the `run.json` `cache_files` entry. A directory gives its sorted `*.csv` names; `None` gives `"<TICKER>.csv"` per training ticker.
  - `describe(cache_dir) -> str`: the directory path, or `"the <source> training data"`.
  - `pool_kwargs() -> dict` = `{"initializer": training_data.select, "initargs": (training_data.active(),)}`.

**Why this shape:** these are the instruments of closed pre-registrations (v33, v34, v68, v82, v90, v127). An explicit `--cache-dir` reproduces their recorded runs byte for byte, because the directory is read exactly as before and the yfinance source is pinned. Without one they follow the switch like every other training reader. Re-running a closed component on Alpaca bars is still the same hypothesis and spends nothing new (spec § Research discipline): the switch changes where bars come from, never what may be re-run. Their resumable run directories keep their guard. `run.json` records `cache_files`, so a resume on a different source is refused (`REFUSED -- ... different cache`), never mixed.

The ext-cache scripts (`measure_fib_confluence.py` and the fib/v103/v104/v113 scripts) need no change. They run with `BACKTEST_CACHE_DIR=data/backtest_cache_ext`, and AH10's `select(None)` already resolves that to yfinance.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/history_store/test_cache_dir_scripts.py`:

```python
"""v162 AH13: an explicit --cache-dir is a yfinance-shaped directory and pins
yfinance; without one the measure_* scripts and the fold harness read the
training-data switch. Pools hand the selection to their workers."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_wf
from swingbot.core.marketdata import training_data
from swingbot.core.marketdata.history_store import MissingStoreError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import cache_dir_source as cds  # noqa: E402


def _load(name):
    spec = importlib.util.spec_from_file_location(f"{name}_v162",
                                                  ROOT / "scripts" / "backtest" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def _fresh_switch(monkeypatch):
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    training_data.reset()
    yield
    training_data.reset()


def _frame(n=30, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    idx = pd.DatetimeIndex(pd.bdate_range("2020-01-02", periods=n), name="Date")
    return pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close,
                         "Volume": np.full(n, 1_000_000.0)}, index=idx)


def _write_store(root, frames, statuses=None):
    statuses = statuses or {}
    folder = root / "daily"
    folder.mkdir(parents=True, exist_ok=True)
    tickers = {}
    for ticker, frame in frames.items():
        frame.to_csv(folder / f"{ticker}.csv", index_label="Date", date_format="%Y-%m-%d")
        tickers[ticker] = {"status": statuses.get(ticker, "ok"), "start": "2016-01-01",
                           "first": str(frame.index[0].date()), "last": str(frame.index[-1].date()),
                           "rows": len(frame), "sha256": "0" * 64,
                           "fetched_at": "2026-10-18T06:12:40Z",
                           "identity": {"status": "ok", "median_ratio": 1.0,
                                        "overlap": len(frame), "dropped_before": None}}
    (folder / "_manifest.json").write_text(json.dumps(
        {"timeframe": "daily", "feed": "sip", "adjustment": "all",
         "updated_at": "2026-10-18T06:31:02Z", "hash": "f" * 64, "tickers": tickers}),
        encoding="utf-8")


@pytest.fixture
def alpaca_store(store_root):
    _write_store(store_root, {"AAA": _frame(), "BBB": _frame(seed=8), "SPY": _frame(seed=9)},
                 {"BBB": "flagged: price-mismatch"})
    return store_root


@pytest.fixture
def csv_dir(tmp_path):
    folder = tmp_path / "yf"
    folder.mkdir()
    for ticker, seed in (("AAA", 1), ("CCC", 2), ("SPY", 3)):
        _frame(seed=seed).to_csv(folder / f"{ticker}.csv", index_label="Date")
    return folder


def _ns(**kw):
    base = {"cache_dir": None, "data_source": None}
    base.update(kw)
    return argparse.Namespace(**base)


# --- the rule -------------------------------------------------------------------------

def test_an_explicit_cache_dir_pins_yfinance(csv_dir, store_root):
    assert cds.resolve(_ns(cache_dir=str(csv_dir))) == csv_dir
    assert training_data.active() == "yfinance"


def test_cache_dir_with_alpaca_is_an_error(csv_dir):
    with pytest.raises(SystemExit, match="yfinance-shaped"):
        cds.resolve(_ns(cache_dir=str(csv_dir), data_source="alpaca"))


def test_no_cache_dir_follows_the_switch(alpaca_store):
    assert cds.resolve(_ns()) is None
    assert training_data.active() == "alpaca"


def test_no_cache_dir_and_no_store_is_an_error(store_root):
    with pytest.raises(MissingStoreError):
        cds.resolve(_ns(data_source="alpaca"))


# --- readers --------------------------------------------------------------------------

def test_readers_on_a_directory_match_the_old_glob(csv_dir):
    assert cds.listing(csv_dir) == ["AAA", "CCC", "SPY"]
    assert sorted(cds.load_all(csv_dir, limit=2)) == ["AAA", "CCC"]
    assert cds.cache_files(csv_dir) == ["AAA.csv", "CCC.csv", "SPY.csv"]
    assert cds.load_frame(csv_dir, "AAA").index.name == "Date"
    assert cds.load_frame(csv_dir, "ZZZ") is None
    assert cds.describe(csv_dir) == str(csv_dir)


def test_readers_without_a_directory_use_the_training_data(alpaca_store):
    training_data.select("alpaca")
    assert cds.listing(None) == ["AAA", "SPY"]
    assert sorted(cds.load_all(None)) == ["AAA", "SPY"]
    assert cds.cache_files(None) == ["AAA.csv", "SPY.csv"]
    assert cds.load_frame(None, "BBB") is None
    assert len(cds.load_frame(None, "AAA")) == 30
    assert cds.describe(None) == "the alpaca training data"


def test_pool_kwargs_carry_the_selection(alpaca_store):
    training_data.select("alpaca")
    assert cds.pool_kwargs() == {"initializer": training_data.select, "initargs": ("alpaca",)}


# --- backtest_wf._frame_for ------------------------------------------------------------

def test_frame_for_reads_the_training_data(alpaca_store):
    training_data.select("alpaca")
    assert len(backtest_wf._frame_for("AAA")) == 30
    assert backtest_wf._frame_for("BBB") is None


def test_frame_for_without_a_store_raises(store_root):
    with pytest.raises(MissingStoreError):
        backtest_wf._frame_for("AAA")


# --- every script applies the rule before reading a bar --------------------------------

SCRIPTS = [
    ("measure_trend_signal_overlap", lambda: ["--train"]),
    ("measure_adjacent_gate_effect", lambda: ["--train"]),
    ("measure_dcb_veto", lambda: ["--train"]),
    ("measure_rs_gate_effect", lambda: ["--train"]),
    ("measure_armed_entries", lambda: ["replay", "--run", "run1", "--workers", "1"]),
    ("measure_structure_arm", lambda: ["replay", "--run", "run1", "--workers", "1"]),
    ("measure_earnings_blackout", lambda: ["replay", "--run", "run1", "--workers", "1"]),
]


@pytest.mark.parametrize("name, argv", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_alpaca_without_a_store_stops_first(name, argv, store_root, tmp_path):
    module = _load(name)
    extra = ["--out-root", str(tmp_path / "out")] if argv()[0] == "replay" else []
    with pytest.raises(MissingStoreError):
        module.main([*argv(), *extra, "--data-source", "alpaca"])


@pytest.mark.parametrize("name, argv", SCRIPTS, ids=[s[0] for s in SCRIPTS])
def test_cache_dir_with_alpaca_is_refused(name, argv, csv_dir, tmp_path):
    module = _load(name)
    extra = ["--out-root", str(tmp_path / "out")] if argv()[0] == "replay" else []
    with pytest.raises(SystemExit, match="yfinance-shaped"):
        module.main([*argv(), *extra, "--cache-dir", str(csv_dir), "--data-source", "alpaca"])


def test_validate_component_and_wf_components_take_the_flag(store_root):
    for name, argv in (("validate_component", ["--stage", "selection", "--title", "t",
                                               "--window", "w"]),
                       ("wf_components", [])):
        with pytest.raises(MissingStoreError):
            _load(name).main([*argv, "--data-source", "alpaca"])


def test_earnings_calendar_comes_from_the_training_spy(alpaca_store):
    training_data.select("alpaca")
    blackout = _load("measure_earnings_blackout")
    assert len(blackout.load_calendar(None)) == 30


def test_armed_run_meta_lists_training_files(alpaca_store):
    training_data.select("alpaca")
    armed = _load("measure_armed_entries")
    meta = armed.run_meta(None, ("2020-01-01", "2023-12-31"), ["4w"])
    assert meta["cache_files"] == ["AAA.csv", "SPY.csv"]
```

The scripts touched here call `main(argv)`. `measure_trend_signal_overlap`, `measure_adjacent_gate_effect`, `measure_dcb_veto`, `measure_rs_gate_effect` and `wf_components` today read `sys.argv` through `ap.parse_args()`, so Step 4 gives each `main` an `argv=None` parameter passed to `parse_args`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_cache_dir_scripts.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'cache_dir_source'`.

- [ ] **Step 3: Create `cache_dir_source.py`**

Create `$WT/scripts/backtest/cache_dir_source.py`:

```python
"""v162: the --cache-dir rule shared by the measure_* scripts that take one.

`--cache-dir DIR` names a yfinance-shaped CSV directory (a Date index, one
<SYMBOL>.csv per ticker). It pins the yfinance source and every frame is read
from DIR exactly as before v162, so a closed pre-registration's recorded run
reproduces. Without it, frames come from the training-data switch: the
script's --data-source, else yfinance when BACKTEST_CACHE_DIR is set, else
TRAINING_DATA_SOURCE (training_data.select). The switch changes where bars come
from, never what may be re-run: a closed component re-measured on Alpaca bars
is the same hypothesis (backtest-methodology.md § Closed pre-registrations).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
for _path in (ROOT, ROOT / "scripts" / "data"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fetch_backtest_data import add_data_source_arg, apply_data_source  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402
from swingbot.core.marketdata.backtest_cache import cache_path  # noqa: E402

CACHE_DIR_HELP = ("a yfinance-shaped OHLCV CSV directory; pins the yfinance source. "
                  "Default: the training-data switch (--data-source, else "
                  "TRAINING_DATA_SOURCE).")


def add_args(ap) -> None:
    """--data-source; each script keeps its own --cache-dir (default None)."""
    add_data_source_arg(ap)


def as_dir(value) -> Path | None:
    return Path(value) if value else None


def resolve(args) -> Path | None:
    """Apply the rule and return the explicit directory, or None for the switch."""
    cache_dir = as_dir(getattr(args, "cache_dir", None))
    if cache_dir is None:
        apply_data_source(args)
        return None
    if getattr(args, "data_source", None) == "alpaca":
        raise SystemExit("error: --cache-dir reads a yfinance-shaped CSV directory; "
                         "drop it to read the Alpaca store")
    training_data.select("yfinance")
    print(f"training data: yfinance (--cache-dir {cache_dir})", flush=True)
    return cache_dir


def load_frame(cache_dir, symbol: str) -> pd.DataFrame | None:
    if cache_dir is None:
        return training_data.load_daily(symbol)
    path = Path(cache_dir) / cache_path(symbol).name
    if not path.exists():
        return None
    frame = pd.read_csv(path, index_col="Date", parse_dates=True)
    return frame if len(frame) else None


def listing(cache_dir) -> list[str]:
    if cache_dir is None:
        return training_data.available_tickers()
    return sorted(p.stem for p in Path(cache_dir).glob("*.csv"))


def load_all(cache_dir, limit: int | None = None) -> dict:
    """{ticker: frame}. A directory is globbed and read exactly as the scripts
    did before v162 (first `limit` paths, empty files kept); the switch gives
    the first `limit` training tickers that load."""
    if cache_dir is not None:
        paths = sorted(Path(cache_dir).glob("*.csv"))[:limit]
        return {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True) for p in paths}
    tickers = training_data.available_tickers()[:limit]
    return {t: f for t in tickers if (f := training_data.load_daily(t)) is not None}


def cache_files(cache_dir) -> list[str]:
    """What a run.json records under cache_files: a resume on other data is refused."""
    if cache_dir is None:
        return [f"{ticker}.csv" for ticker in training_data.available_tickers()]
    return sorted(p.name for p in Path(cache_dir).glob("*.csv"))


def describe(cache_dir) -> str:
    return str(cache_dir) if cache_dir is not None else f"the {training_data.active()} training data"


def pool_kwargs() -> dict:
    """Hand a spawned pool worker the parent's selection (spawn re-imports)."""
    return {"initializer": training_data.select, "initargs": (training_data.active(),)}
```

(`list[:None]` is the whole list, so `limit=None` needs no branch.)

- [ ] **Step 4: The glob scripts: `measure_trend_signal_overlap.py` and `measure_adjacent_gate_effect.py`**

In `measure_trend_signal_overlap.py`, add after `from swingbot.core.scanning.regime import _HTF_EMA_PERIOD, get_htf_bias`:

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache_dir_source  # noqa: E402
```

In `main`: change `def main() -> int:` to `def main(argv=None) -> int:`. Change the `--cache-dir` argument's `help=` to `help=cache_dir_source.CACHE_DIR_HELP` (keep `default=None`). Directly before `args = ap.parse_args()` add `cache_dir_source.add_args(ap)`, and change that line to `args = ap.parse_args(argv)`. Replace

```python
    cache = Path(args.cache_dir) if args.cache_dir else CACHE_DIR
    paths = sorted(cache.glob("*.csv"))
    if args.limit:
        paths = paths[:args.limit]
    if not paths:
        print(f"No CSVs in {cache} -- run scripts/data/fetch_backtest_data.py "
              f"first, or pass --cache-dir.", file=sys.stderr)
        return 1
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in paths}
```

with

```python
    cache = cache_dir_source.resolve(args)
    frames = cache_dir_source.load_all(cache, limit=args.limit)
    if not frames:
        print(f"No frames in {cache_dir_source.describe(cache)} -- run "
              f"scripts/data/fetch_backtest_data.py first, or pass --cache-dir.",
              file=sys.stderr)
        return 1
```

The `CACHE_DIR` constant stays defined (`make_v68_fixture.py` style importers may name it). In `measure_adjacent_gate_effect.py`, remove `CACHE_DIR, ` from the `from measure_trend_signal_overlap import (` list and add `import cache_dir_source  # noqa: E402` after that import block. Apply the same `main` changes there: `def main(argv=None) -> int:`, `help=cache_dir_source.CACHE_DIR_HELP`, `cache_dir_source.add_args(ap)` before `parse_args(argv)`, and the identical replacement of the `cache = ...` through `frames = {...}` block (its text matches the one above word for word).

When either script writes `--json`, add `training_data.write_provenance(args.json)` directly after the line that writes it. Import it with `from swingbot.core.marketdata import training_data` next to `import cache_dir_source`. Find the write with `git -C $WT grep -n "args.json" -- scripts/backtest/measure_trend_signal_overlap.py scripts/backtest/measure_adjacent_gate_effect.py`, and add one line inside each existing `if args.json:` block.

- [ ] **Step 5: `measure_dcb_veto.py` and `measure_rs_gate_effect.py`**

`measure_dcb_veto.py`: add `sys.path.insert(0, str(Path(__file__).resolve().parent))` and `import cache_dir_source  # noqa: E402` after the `simulate_exit` import. In `load_frames`, replace the loop

```python
    for sym in symbols:
        p = cache_dir / f"{sym}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, index_col="Date", parse_dates=True)
        if len(df):
            frames[sym] = df
```

with

```python
    for sym in symbols:
        df = cache_dir_source.load_frame(cache_dir, sym)
        if df is not None:
            frames[sym] = df
```

(`load_frame` already drops missing and empty files; `make_v68_fixture.py` still passes its explicit `CACHE_DIR` and reads the same files). In `main`: `def main(argv=None) -> int:`, the `--cache-dir` help becomes `cache_dir_source.CACHE_DIR_HELP`, `cache_dir_source.add_args(ap)` goes before `args = ap.parse_args(argv)`, and replace

```python
    cache_dir = Path(args.cache_dir) if args.cache_dir else CACHE_DIR
```

with

```python
    cache_dir = cache_dir_source.resolve(args)
```

and in the "No frames loaded" message replace `{cache_dir}` with `{cache_dir_source.describe(cache_dir)}`. Move the `cache_dir = cache_dir_source.resolve(args)` line up to directly after `args = ap.parse_args(argv)`, so a missing store errors before the `--validation`/`--cell` check reads anything. Its pool receives frames, so it needs no initializer.

`measure_rs_gate_effect.py`: replace the import line `from swingbot.core.marketdata.backtest_cache import cache_path  # noqa: E402` with

```python
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cache_dir_source  # noqa: E402
```

(the only other use of `cache_path` is the `load` closure being replaced). In `main`: `def main(argv=None) -> int:`, `--cache-dir` help `cache_dir_source.CACHE_DIR_HELP`, `cache_dir_source.add_args(ap)` before `args = ap.parse_args(argv)`, and replace

```python
    cache = Path(args.cache_dir) if args.cache_dir else CACHE_DIR

    def load(sym):
        p = Path(cache) / cache_path(sym).name
        if not p.exists():
            return None
        df = pd.read_csv(p, index_col="Date", parse_dates=True)
        return df if len(df) else None
```

with

```python
    cache = cache_dir_source.resolve(args)

    def load(sym):
        return cache_dir_source.load_frame(cache, sym)
```

and move the `cache = cache_dir_source.resolve(args)` line to directly after `args = ap.parse_args(argv)` (above `window = ...`). In the "Need watchlist CSVs" message replace `in {cache}` with `in {cache_dir_source.describe(cache)}`.

- [ ] **Step 6: The run-directory scripts: `measure_armed_entries.py`, `measure_structure_arm.py`, `measure_earnings_blackout.py`**

`measure_armed_entries.py`: add `sys.path.insert(0, str(Path(__file__).resolve().parent))` and `import cache_dir_source  # noqa: E402` after the `LEGACY_HORIZONS` import. Make `load_frame` start with the switch branch (the explicit-directory body, with its unreadable-file warning, stays as it is):

```python
def load_frame(cache_dir, symbol):
    if cache_dir is None:
        return cache_dir_source.load_frame(None, symbol)
    path = Path(cache_dir) / f"{symbol}.csv"
```

In `run_meta`, replace `"cache_files": sorted(p.name for p in Path(cache_dir).glob("*.csv")),` with `"cache_files": cache_dir_source.cache_files(cache_dir),`. In `_map`, replace `with ProcessPoolExecutor(max_workers=workers) as pool:` with `with ProcessPoolExecutor(max_workers=workers, **cache_dir_source.pool_kwargs()) as pool:`. In `cmd_replay`, replace `cache = Path(args.cache_dir)` with `cache = cache_dir_source.resolve(args)`, replace `sorted(p.stem for p in cache.glob("*.csv"))` with `cache_dir_source.listing(cache)`, and in the `tasks = [...]` line replace `str(cache)` with `cache`. In `cmd_permute`, add `cache = cache_dir_source.resolve(args)` as the first line after the `REFUSED -- no run2 replay to permute` return, and in its `tasks = [...]` line replace `args.cache_dir` with `cache`. In `main.common`, replace

```python
        p.add_argument("--cache-dir", default=str(CACHE_DIR))
```

with

```python
        p.add_argument("--cache-dir", default=None, help=cache_dir_source.CACHE_DIR_HELP)
        cache_dir_source.add_args(p)
```

`measure_structure_arm.py` imports `_map` and `load_frame` from `measure_armed_entries`, so it inherits the switch branch and the pool initializer. Add `import cache_dir_source  # noqa: E402` after that import block. In `run_meta`, make the same `cache_files` replacement. In `_claim_run_dir`, replace `run_meta(Path(args.cache_dir), RUNS[args.run], horizons)` with `run_meta(cache_dir_source.as_dir(args.cache_dir), RUNS[args.run], horizons)`. In `cmd_replay`, add `cache = cache_dir_source.resolve(args)` as the first line after the `_run2_locked` refusal `return 3`. The source must be selected before `_claim_run_dir` lists `cache_files`. Then delete the later line `cache = Path(args.cache_dir)`, replace `sorted(p.stem for p in cache.glob("*.csv"))` with `cache_dir_source.listing(cache)`, and in the `tasks = [...]` line replace `str(cache)` with `cache`. In `cmd_permute`, add `cache = cache_dir_source.resolve(args)` after the `return 4` refusal and replace `args.cache_dir` in its `tasks = [...]` line with `cache`. In `_parser.command`, replace `p.add_argument("--cache-dir", default=str(CACHE_DIR))` with the same two lines as in `measure_armed_entries.main.common`.

`measure_earnings_blackout.py` (one statement per line is not this file's style; keep its style and change only these substrings):
- After the line `from swingbot.core.market.strategy_types import LEGACY_HORIZONS` add the line `sys.path.insert(0, str(Path(__file__).resolve().parent)); import cache_dir_source`.
- Replace the body of `load_frame` so it reads:
  ```python
  def load_frame(cache_dir, symbol):
      if cache_dir is None: return cache_dir_source.load_frame(None, symbol)
      path=Path(cache_dir) / f"{symbol}.csv"
      return pd.read_csv(path, index_col="Date", parse_dates=True) if path.exists() else None
  ```
- In `load_calendar`, replace `raise SystemExit(f"SPY.csv missing from {cache_dir}")` with `raise SystemExit(f"SPY missing from {cache_dir_source.describe(cache_dir)}")`.
- In `cmd_replay`: `cache=Path(args.cache_dir); calendar=load_calendar(cache);` becomes `cache=cache_dir_source.resolve(args); calendar=load_calendar(cache);`; `sorted(path.stem for path in cache.glob("*.csv"))` becomes `cache_dir_source.listing(cache)`; `(symbol,str(cache),str(args.csv_dir),` becomes `(symbol,cache,str(args.csv_dir),`; `ProcessPoolExecutor(max_workers=args.workers).map(_worker,tasks)` becomes `ProcessPoolExecutor(max_workers=args.workers, **cache_dir_source.pool_kwargs()).map(_worker,tasks)`.
- In `cmd_permute`: `calendar=load_calendar(args.cache_dir);` becomes `calendar=load_calendar(cache_dir_source.resolve(args));`.
- In `main.common`: `p.add_argument("--cache-dir",default=str(CACHE_DIR));` becomes `p.add_argument("--cache-dir",default=None,help=cache_dir_source.CACHE_DIR_HELP);cache_dir_source.add_args(p);`.

`_worker` receives `cache` (a `Path` or `None`) and passes it to `load_calendar` and `load_frame`, both of which now take `None`.

- [ ] **Step 7: `backtest_wf._frame_for`, `wf_components.py`, `validate_component.py`**

Replace `_frame_for` in `$WT/swingbot/core/backtesting/backtest_wf.py` (the docstring is rewritten because the old one says "Reads data/backtest_cache/"; spec § Docs):

```python
def _frame_for(symbol: str):
    """Daily bars for one symbol from the selected training data, or None.

    v162: reads through swingbot.core.marketdata.training_data -- the Alpaca
    history store (data/market_data/daily/) by default, or data/backtest_cache/
    under TRAINING_DATA_SOURCE=yfinance, a script's --data-source yfinance, or
    a set BACKTEST_CACHE_DIR. Never the root market_data/ cache: it starts
    2018-06, leaving the folds no warm-up (on AAPL 13 trades from
    backtest_cache vs 1 from market_data over identical windows). Folds compare
    a component against a baseline, so both legs read the one selected source;
    a run never mixes them. A missing Alpaca store raises MissingStoreError
    instead of producing a zero-ticker fold.
    """
    from swingbot.core.marketdata import training_data
    from swingbot.core.marketdata.history_store import MissingStoreError

    try:
        return training_data.load_daily(symbol)
    except MissingStoreError:
        raise
    except Exception as exc:
        log.warning("fold frame unreadable for %s: %s", symbol, exc, exc_info=True)
        return None
```

`wf_components.py`: add after `from swingbot.core.marketdata.watchlist import load_watchlist  # noqa: E402`:

```python
from swingbot.core.marketdata import training_data  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cache_dir_source  # noqa: E402
```

In `_render`, replace the list element

```python
        "- OHLCV: `data/backtest_cache/` (same cache the E22 baseline was measured on)",
```

with

```python
        f"- OHLCV: `{training_data.active()}` training data (v162 switch; the E22 baseline "
        "was measured on `yfinance`)",
```

In `main`: `def main(argv=None) -> int:`, add `cache_dir_source.add_args(ap)` before `args = ap.parse_args()`, change it to `args = ap.parse_args(argv)`, and directly after it add `cache_dir_source.resolve(args)`. That call selects through `--data-source`, because `wf_components` has no `--cache-dir`. After the `json.dump(...)` block, add `training_data.write_provenance(args.out.replace(".md", ".json"))`.

`validate_component.py`: add `import cache_dir_source` after its existing imports (its directory is on `sys.path` when run, and the test puts it there). In `main`, directly before `args = parser.parse_args(argv)` add `cache_dir_source.add_args(parser)`, and directly after it add `cache_dir_source.resolve(args)`. The frames it scores come through `measure_arms.load_frame`, so they are read from the selected source.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_cache_dir_scripts.py`
Expected: PASS, 0 failed.

Run: `python $WT/scripts/dev/testrun.py changed`
Expected: 0 failed. It picks up the existing tests of these scripts and of `backtest_wf`. A test that relied on the old `--cache-dir` default (`data/backtest_cache`) or on `_frame_for` reading `CACHE_DIR` directly should now pass `--cache-dir <its tmp dir>`, or monkeypatch `backtest_cache.CACHE_DIR` and call `training_data.select("yfinance")`. Change the test's fixture, never the rule.

- [ ] **Step 9: No implicit cache default is left, and complexity holds**

Run: `git -C $WT grep -n "default=str(CACHE_DIR)\|if args.cache_dir else CACHE_DIR" -- scripts/backtest`
Expected: no output.

Run: `python -m radon cc -s -n C $WT/scripts/backtest/cache_dir_source.py $WT/swingbot/core/backtesting/backtest_wf.py $WT/scripts/backtest/wf_components.py $WT/scripts/backtest/validate_component.py $WT/scripts/backtest/measure_trend_signal_overlap.py $WT/scripts/backtest/measure_adjacent_gate_effect.py $WT/scripts/backtest/measure_dcb_veto.py $WT/scripts/backtest/measure_rs_gate_effect.py $WT/scripts/backtest/measure_armed_entries.py $WT/scripts/backtest/measure_structure_arm.py $WT/scripts/backtest/measure_earnings_blackout.py`
Expected: nothing from `cache_dir_source.py` or `_frame_for`, and every listed legacy `main` or `cmd_*` scores no higher than at the task's base commit. The replacements remove branches (`if args.cache_dir else`, the closure's `if`), so scores fall or stay.

- [ ] **Step 10: Commit**

```bash
git -C $WT add scripts/backtest/cache_dir_source.py swingbot/core/backtesting/backtest_wf.py scripts/backtest/wf_components.py scripts/backtest/validate_component.py scripts/backtest/measure_trend_signal_overlap.py scripts/backtest/measure_adjacent_gate_effect.py scripts/backtest/measure_dcb_veto.py scripts/backtest/measure_rs_gate_effect.py scripts/backtest/measure_armed_entries.py scripts/backtest/measure_structure_arm.py scripts/backtest/measure_earnings_blackout.py tests/history_store/test_cache_dir_scripts.py
git -C $WT commit -m "feat(v162): --cache-dir pins yfinance, otherwise the measure scripts and the fold harness read the training-data switch

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

### Task AH14: Ledger optional `data_source` field

**Model:** sonnet — a strict validator gains one optional field. The schema rule (an added field, old rows never rewritten, an absent value means `yfinance`) is spelled out and pinned by the committed-ledger test.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/stats.py` (ledger block :105-205: `LEDGER_FIELDS` :112, `_FIELD_CHECKS` :146-150, `validate_ledger_row` :153-164, `append_ledger_row` :190-205)
- Modify: `scripts/reports/preregistration_ledger.py` (`build_parser` :36-50, `row_from_args` :53-57)
- Modify: `scripts/backtest/screen_idea.py` (`ledger_row` :362-370)
- Test: `tests/backtesting/test_instrument_stats_ledger.py` (append), `tests/scripts/test_preregistration_ledger_cli.py` (append)

**Interfaces:**
- Consumes: nothing new. It reads no AH10 contract, so it runs in parallel with everything up to AH17. The CLI reads `config.TRAINING_DATA_SOURCE` (AH10's field) only as a default, through `getattr` with a `"yfinance"` fallback, so it does not depend on AH10 landing first.
- Produces (binding for AH18 docs, AH24 results):
  - `OPTIONAL_LEDGER_FIELDS = ("data_source",)`; `LEDGER_DATA_SOURCES = ("alpaca", "yfinance")` (equal to `training_data.DATA_SOURCES`, kept literal here so the stats module imports nothing from `marketdata`).
  - `validate_ledger_row(row)` accepts exactly `LEDGER_FIELDS` plus any subset of `OPTIONAL_LEDGER_FIELDS`. A present `data_source` must be in `LEDGER_DATA_SOURCES` (`None` is refused: absent, not null, means yfinance).
  - `append_ledger_row(row)` writes `LEDGER_FIELDS` in order, then any present optional field.
  - `ledger_data_source(row: dict) -> str` gives `row["data_source"]`, or `"yfinance"` when absent. It is the one reader of the default; no stored row is rewritten.
  - CLI `preregistration_ledger.py --data-source {alpaca,yfinance}` defaults to `config.TRAINING_DATA_SOURCE`, so every new row names its source (spec § Research discipline: "Each new pre-registration names its data_source").
  - `screen_idea.ledger_row(...)` stamps `"data_source": "yfinance"`. The Stage −2 screen reads `data/backtest_cache_ext/` (yfinance, unchanged by v162).

- [ ] **Step 1: Write the failing stats tests**

Append to `$WT/tests/backtesting/test_instrument_stats_ledger.py`:

```python
# --- v162: optional data_source ----------------------------------------------------

def test_data_source_is_an_optional_field_with_the_training_sources():
    assert stats.OPTIONAL_LEDGER_FIELDS == ("data_source",)
    assert stats.LEDGER_DATA_SOURCES == ("alpaca", "yfinance")   # = training_data.DATA_SOURCES
    assert "data_source" not in stats.LEDGER_FIELDS


@pytest.mark.parametrize("source", ["alpaca", "yfinance"])
def test_a_row_with_a_data_source_validates(source):
    stats.validate_ledger_row(_row(data_source=source))


@pytest.mark.parametrize("value", ["iex", "", None, "Alpaca"])
def test_a_bad_data_source_is_refused(value):
    with pytest.raises(ValueError, match="'data_source'"):
        stats.validate_ledger_row(_row(data_source=value))


def test_a_row_without_data_source_still_validates_and_means_yfinance():
    row = _row()
    stats.validate_ledger_row(row)
    assert stats.ledger_data_source(row) == "yfinance"
    assert stats.ledger_data_source(_row(data_source="alpaca")) == "alpaca"


def test_unknown_extra_fields_are_still_refused():
    with pytest.raises(ValueError, match=r"extra \['note'\]"):
        stats.validate_ledger_row(_row(data_source="alpaca", note="x"))


def test_append_keeps_data_source_after_the_required_fields(tmp_path):
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(_row(id="old"), path=path)
    stats.append_ledger_row(_row(id="new", data_source="alpaca"), path=path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert list(json.loads(lines[0])) == list(stats.LEDGER_FIELDS)
    assert list(json.loads(lines[1])) == [*stats.LEDGER_FIELDS, "data_source"]
    assert [stats.ledger_data_source(r) for r in stats.load_ledger(path)] == ["yfinance", "alpaca"]
```

- [ ] **Step 2: Write the failing CLI tests**

Append to `$WT/tests/scripts/test_preregistration_ledger_cli.py`:

```python
# --- v162: every new row names its data source -----------------------------------------

def test_data_source_is_written_when_given(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    assert cli.main(_args(ledger, **{"--data-source": "yfinance"})) == 0
    assert stats.load_ledger(ledger)[0]["data_source"] == "yfinance"


def test_data_source_defaults_to_the_training_source(tmp_path, monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca", raising=False)
    ledger = tmp_path / "ledger.jsonl"
    assert cli.main(_args(ledger)) == 0
    assert stats.load_ledger(ledger)[0]["data_source"] == "alpaca"


def test_an_unknown_data_source_is_refused_by_argparse(tmp_path):
    with pytest.raises(SystemExit):
        cli.main(_args(tmp_path / "ledger.jsonl", **{"--data-source": "iex"}))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py`
Expected: FAIL with `AttributeError: module ... has no attribute 'OPTIONAL_LEDGER_FIELDS'` (and an `extra ['data_source']` refusal).

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py`
Expected: FAIL (`unrecognized arguments: --data-source`, `KeyError: 'data_source'`).

- [ ] **Step 4: Implement the optional field in `stats.py`**

After the `INSTRUMENTS = ("v1", "v2", "screen-v1")` line add:

```python
#: v162 adds one OPTIONAL field: the bars a verdict was measured on. Rows
#: written before v162 have none and mean yfinance (ledger_data_source); they
#: are never rewritten (schema-evolution.md: an added field, no upcasting
#: beyond that one default).
OPTIONAL_LEDGER_FIELDS = ("data_source",)
LEDGER_DATA_SOURCES = ("alpaca", "yfinance")
```

Replace `_FIELD_CHECKS` and `validate_ledger_row` with:

```python
_FIELD_CHECKS = {
    "id": _text, "date": _iso_date, "hypothesis": _text,
    "instrument": INSTRUMENTS.__contains__, "n": _count, "exp_r": _real,
    "p": _probability, "verdict": VERDICTS.__contains__, "record": _text,
    "data_source": LEDGER_DATA_SOURCES.__contains__,
}


def validate_ledger_row(row) -> None:
    """Raise ValueError unless ``row`` has exactly LEDGER_FIELDS plus any of
    OPTIONAL_LEDGER_FIELDS, each valid."""
    if not isinstance(row, dict):
        raise ValueError("a ledger row must be a JSON object")
    missing = sorted(set(LEDGER_FIELDS) - set(row))
    extra = sorted(set(row) - set(LEDGER_FIELDS) - set(OPTIONAL_LEDGER_FIELDS))
    if missing or extra:
        raise ValueError(f"ledger row {row.get('id')!r}: missing {missing}, "
                         f"extra {extra}")
    present = [name for name in (*LEDGER_FIELDS, *OPTIONAL_LEDGER_FIELDS) if name in row]
    bad = [name for name in present if not _FIELD_CHECKS[name](row[name])]
    if bad:
        raise ValueError(f"ledger row {row.get('id')!r}: invalid field(s) {bad}")


def ledger_data_source(row: dict) -> str:
    """The bars a ledger row was measured on; a row from before v162 means yfinance."""
    return row.get("data_source") or "yfinance"
```

In `append_ledger_row`, replace

```python
    ordered = {name: row[name] for name in LEDGER_FIELDS}
```

with

```python
    ordered = {name: row[name] for name in (*LEDGER_FIELDS, *OPTIONAL_LEDGER_FIELDS)
               if name in row}
```

`.claude/hooks/guardrails.py:305` and the admin research API read rows with `load_ledger`. An extra key on new rows changes nothing they compute (they read named fields), and `tests/hooks/test_guardrails.py` and `tests/admin/test_api_v1_research.py` run in Step 7.

- [ ] **Step 5: CLI and screen**

In `scripts/reports/preregistration_ledger.py`, add to `build_parser`, directly before the `--ledger` argument:

```python
    from swingbot import config
    p.add_argument("--data-source", choices=stats.LEDGER_DATA_SOURCES,
                   default=getattr(config, "TRAINING_DATA_SOURCE", "yfinance"),
                   help="bars the verdict was measured on; default TRAINING_DATA_SOURCE. "
                        "Name it in the frozen block before TRAIN is read (v162)")
```

and in `row_from_args` add `"data_source": args.data_source,` after `"record": args.record`, so the dict ends:

```python
            "verdict": args.verdict, "record": args.record,
            "data_source": args.data_source}
```

`format_report` is unchanged, so the exact-output test `test_append_prints_the_bh_q_value_across_the_ledger` still passes.

In `scripts/backtest/screen_idea.py` `ledger_row`, change the last line of the returned dict

```python
            "verdict": v.verdict, "record": record}
```

to

```python
            "verdict": v.verdict, "record": record,
            "data_source": "yfinance"}   # the Stage -2 screen reads backtest_cache_ext (v162 leaves it)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py`
Expected: PASS, 0 failed (including `test_the_committed_ledger_still_loads_unchanged`).

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py`
Expected: PASS, 0 failed.

- [ ] **Step 7: Every other ledger reader**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`
Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_research.py`
Run: `python $WT/scripts/dev/testrun.py file tests/hooks/test_guardrails.py`
Run: `git -C $WT grep -ln "ledger_row\|screen_idea" -- tests` and run each listed file with `testrun.py file`.
Expected: every run 0 failed. A test that asserts a screen row's exact key set gets `"data_source": "yfinance"` added to its expectation (that key is the change, not a regression).

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/stats.py $WT/scripts/reports/preregistration_ledger.py`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git -C $WT add swingbot/core/backtesting/instrument/stats.py scripts/reports/preregistration_ledger.py scripts/backtest/screen_idea.py tests/backtesting/test_instrument_stats_ledger.py tests/scripts/test_preregistration_ledger_cli.py
git -C $WT commit -m "feat(v162): ledger rows may name their data_source -- optional field, absent means yfinance, CLI defaults to the training source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

### Task AH15: Badge lookup prefers the active `data_source`

**Model:** opus — `get_badge` feeds every live alert's badge. The change must leave today's yfinance-only registry answering exactly as before, and must never blend the two populations once Alpaca rows exist.

**Files:**
- Modify: `swingbot/core/backtesting/registry.py` (imports :14-19; `Badge` :86-95; `reload_registry` :105-107; `get_badge` :110-141)
- Modify: `swingbot/admin/queries.py` (import :42; `_registry_rows` loop :212)
- Modify: `swingbot/core/analytics/insights.py` (`edge_decay_report` :144)
- Modify: `swingbot/core/analytics/snapshots.py` (`refresh_snapshot` :123)
- Test: `tests/backtesting/test_registry_data_source.py`

**Interfaces:**
- Consumes: `config.TRAINING_DATA_SOURCE` (AH10), read through `getattr` with a `"yfinance"` fallback; the registry row key AH11 writes (`data_source` on new rows, absent on old ones means `yfinance`).
- Produces (ledger AH15):
  - `Badge.data_source: str = "yfinance"` (last field with a default, so every existing positional or keyword construction still works).
  - `row_data_source(rec: dict) -> str`: `rec.get("data_source") or "yfinance"`.
  - `_pick(rows: list[dict], preferred: str) -> dict | None`: the first row measured on `preferred`, else the first `yfinance` row, else `None`. It never merges fields from two rows.
  - `get_badge(source, strategy, horizon_key=None)` keeps its signature and its lookup chain (exact horizon, pooled, the confluence-to-strategy fallback, `ALL`). **Each step** of the chain picks with `_pick(matching_rows, TRAINING_DATA_SOURCE)`. So an Alpaca row is used where one exists for that key, and the yfinance row of the same key otherwise. Under `TRAINING_DATA_SOURCE=yfinance` an Alpaca-only key matches nothing and the chain moves on, as if the row were absent.
  - It logs at INFO which source it used, once per `(source, strategy, horizon, used)`: `registry badge <source>/<strategy>/<horizon>: using the <used> row (preferred <preferred>)`.
  - `active_rows(records: list[dict] | None = None, preferred: str | None = None) -> list[dict]`: one row per `(source, strategy, horizon)`, chosen by `_pick` with `preferred` (default `TRAINING_DATA_SOURCE`). A key with no row for `preferred` and no yfinance row is dropped. Keys keep the file order of their first row. `records` defaults to `load_registry()`.
- **Every reader that walks registry rows goes through `active_rows`**, so none of them sees two rows per key once Alpaca rows exist. `git grep -n "load_registry()" -- swingbot scripts` finds exactly three outside `registry.py` (`cohort_registry.py` has its own unrelated `load_registry`):
  - `swingbot/admin/queries.py:212` `_registry_rows` (admin Strategies page): `for rec in active_rows(load_registry()):`
  - `swingbot/core/analytics/insights.py:144` `edge_decay_report` (`calibration.badge_drift` input): `registry.active_rows(registry.load_registry())`
  - `swingbot/core/analytics/snapshots.py:123` `refresh_snapshot` (`build_snapshot`'s `registry_entries`): `registry.active_rows(registry.load_registry())`
  Each call wraps the existing `load_registry()` call instead of replacing it, so the existing tests that patch `queries.load_registry` or `registry.load_registry` (`tests/admin/test_badge_decay_surface.py`, `tests/analytics/test_insights.py`, `tests/analytics/test_snapshots.py`) keep patching the same name.
- Today's `validation_registry.json` has no `data_source` field on any row, so every lookup returns the same row as before this task, now with `data_source="yfinance"`. Live alerts do not change until an Alpaca `--emit-registry` run adds rows.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/backtesting/test_registry_data_source.py`:

```python
"""v162 AH15: the badge comes from the row measured on TRAINING_DATA_SOURCE,
falls back to the yfinance row of the same key, and is never a blend."""
import json
import logging

import pytest

from swingbot import config
from swingbot.core.backtesting import registry


def _row(strategy="RSI", horizon=None, source="strategy", **extra):
    row = {"source": source, "strategy": strategy, "horizon": horizon, "status": "WEAK",
           "n": 40, "win_rate": 55.0, "expectancy_r": 0.1, "window": "w",
           "run_date": "2026-10-01"}
    row.update(extra)
    return row


@pytest.fixture
def use_registry(tmp_path, monkeypatch):
    def _use(rows, preferred):
        monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", preferred, raising=False)
        path = tmp_path / "reg.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        registry.load_registry(path)
    yield _use
    registry.reload_registry()


def test_row_data_source_defaults_to_yfinance():
    assert registry.row_data_source(_row()) == "yfinance"
    assert registry.row_data_source(_row(data_source=None)) == "yfinance"
    assert registry.row_data_source(_row(data_source="alpaca")) == "alpaca"


def test_pick_prefers_then_falls_back_to_yfinance_only():
    yf, al = _row(n=1), _row(n=2, data_source="alpaca")
    assert registry._pick([yf, al], "alpaca") is al
    assert registry._pick([yf, al], "yfinance") is yf
    assert registry._pick([yf], "alpaca") is yf
    assert registry._pick([al], "yfinance") is None
    assert registry._pick([], "alpaca") is None


def test_yfinance_only_registry_answers_as_before(use_registry):
    use_registry([_row(status="VALIDATED", n=99, win_rate=81.0)], "alpaca")
    badge = registry.get_badge("strategy", "RSI")
    assert (badge.status, badge.n, badge.win_rate, badge.data_source) == ("VALIDATED", 99, 81.0, "yfinance")


def test_the_active_source_row_wins_whole(use_registry):
    rows = [_row(n=10, win_rate=50.0, expectancy_r=0.05),
            _row(n=20, win_rate=60.0, expectancy_r=0.20, window="a", data_source="alpaca")]
    use_registry(rows, "alpaca")
    badge = registry.get_badge("strategy", "RSI")
    assert (badge.n, badge.win_rate, badge.expectancy_r, badge.window, badge.data_source) == \
        (20, 60.0, 0.20, "a", "alpaca")


def test_yfinance_preference_ignores_alpaca_rows(use_registry):
    use_registry([_row(n=20, data_source="alpaca")], "yfinance")
    badge = registry.get_badge("strategy", "RSI")
    assert (badge.status, badge.n) == ("WEAK", 0)            # the default badge, not the Alpaca row


def test_each_chain_step_picks_its_own_source(use_registry):
    rows = [_row(horizon="4w", n=11),                                  # exact horizon, yfinance only
            _row(horizon=None, n=22, data_source="alpaca")]           # pooled, alpaca
    use_registry(rows, "alpaca")
    assert registry.get_badge("strategy", "RSI", "4w").n == 11        # exact key wins first
    assert registry.get_badge("strategy", "RSI", "2m").n == 22        # pooled step, alpaca row


def test_the_choice_is_logged_once_per_key(use_registry, caplog):
    use_registry([_row()], "alpaca")
    with caplog.at_level(logging.INFO, logger=registry.__name__):
        registry.get_badge("strategy", "RSI")
        registry.get_badge("strategy", "RSI")
    lines = [r.getMessage() for r in caplog.records if "registry badge" in r.getMessage()]
    assert lines == ["registry badge strategy/RSI/None: using the yfinance row (preferred alpaca)"]


# --- one row per key for every reader that walks the registry -------------------------

def _pair():
    return [_row(strategy="Fibonacci", n=10, win_rate=81.6),
            _row(strategy="Fibonacci", n=20, win_rate=70.0, data_source="alpaca"),
            _row(strategy="RSI", n=30, data_source="alpaca")]


def test_active_rows_keeps_one_row_per_key():
    assert [(r["strategy"], r["n"]) for r in registry.active_rows(_pair(), "alpaca")] == \
        [("Fibonacci", 20), ("RSI", 30)]
    assert [(r["strategy"], r["n"]) for r in registry.active_rows(_pair(), "yfinance")] == \
        [("Fibonacci", 10)]                                  # RSI has no yfinance row: dropped


def test_active_rows_defaults_to_the_loaded_registry_and_config(use_registry):
    use_registry(_pair(), "alpaca")
    assert [r["n"] for r in registry.active_rows()] == [20, 30]


def test_admin_registry_rows_show_one_row_per_strategy(monkeypatch):
    from unittest.mock import patch
    from swingbot.admin import queries
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca", raising=False)
    with patch("swingbot.admin.queries.load_registry", return_value=_pair()), \
         patch("swingbot.admin.queries.load_snapshot", return_value={}), \
         patch("swingbot.admin.queries.refresh_snapshot", return_value={}):
        rows = queries._registry_rows()
    assert [(r["strategy"], r["n"]) for r in rows] == [("Fibonacci", 20), ("RSI", 30)]


def test_edge_decay_report_scores_one_row_per_key(monkeypatch):
    from unittest.mock import patch
    from swingbot.core.analytics import calibration
    from swingbot.core.analytics.insights import edge_decay_report
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance", raising=False)
    seen = []
    with patch("swingbot.core.backtesting.registry.load_registry", return_value=_pair()), \
         patch.object(calibration, "badge_drift",
                      side_effect=lambda closed, entries: seen.append(entries) or []):
        edge_decay_report([])
    assert [(r["strategy"], r["n"]) for r in seen[0]] == [("Fibonacci", 10)]


def test_snapshot_registry_entries_are_one_row_per_key(monkeypatch):
    from unittest.mock import patch
    from swingbot.core.analytics import snapshots
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca", raising=False)
    seen = []
    with patch("swingbot.core.tracking.performance.TradeLog") as log_cls, \
         patch("swingbot.core.planning.account.load_account_config",
               return_value={"base_balance": 0.0}), \
         patch("swingbot.core.backtesting.registry.load_registry", return_value=_pair()), \
         patch.object(snapshots, "build_snapshot",
                      side_effect=lambda closed, balance, entries, **kw: seen.append(entries) or {}), \
         patch.object(snapshots, "save_snapshot"):
        log_cls.return_value.get_trades.return_value = []
        snapshots.refresh_snapshot()
    assert [r["n"] for r in seen[0]] == [20, 30]
```

`refresh_snapshot` swallows exceptions and logs a warning, so if `seen` is empty the patch list is out of step with the function's imports. Read `refresh_snapshot` and patch what it actually imports, the way `tests/analytics/test_snapshots.py::test_refresh_snapshot_writes_file` does.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_registry_data_source.py`
Expected: FAIL with `AttributeError: module 'swingbot.core.backtesting.registry' has no attribute 'row_data_source'`.

- [ ] **Step 3: Implement**

In `$WT/swingbot/core/backtesting/registry.py`, add `import logging` to the stdlib imports, and below `_CACHE: list | None = None` add:

```python
log = logging.getLogger(__name__)
#: (source, strategy, horizon, used data_source) already logged -- once per key.
_LOGGED: set = set()
```

Add the field to `Badge` after `decay`:

```python
    data_source: str = "yfinance"   # v162: which population scored this badge
```

Make `reload_registry` also forget the log memory:

```python
def reload_registry() -> None:
    global _CACHE
    _CACHE = None
    _LOGGED.clear()
```

Add above `get_badge`:

```python
def row_data_source(rec: dict) -> str:
    """The bars a registry row was measured on; a row from before v162 means yfinance."""
    return rec.get("data_source") or "yfinance"


def _preferred_source() -> str:
    from swingbot import config
    return str(getattr(config, "TRAINING_DATA_SOURCE", "yfinance") or "yfinance").lower()


def _pick(rows: list[dict], preferred: str) -> dict | None:
    """The row measured on `preferred`, else the yfinance row of the same key,
    else None. One whole row is returned: a badge is never a blend of sources."""
    by_source: dict = {}
    for rec in rows:
        by_source.setdefault(row_data_source(rec), rec)
    return by_source.get(preferred) or by_source.get("yfinance")


def _find(records: list, preferred: str, src: str, strat: str, hz) -> dict | None:
    rows = [r for r in records
            if r["source"] == src and r["strategy"] == strat and r.get("horizon") == hz]
    rec = _pick(rows, preferred)
    if rec is not None:
        _log_choice(src, strat, hz, preferred, row_data_source(rec))
    return rec


def _log_choice(src: str, strat: str, hz, preferred: str, used: str) -> None:
    key = (src, strat, hz, used)
    if key in _LOGGED:
        return
    _LOGGED.add(key)
    log.info("registry badge %s/%s/%s: using the %s row (preferred %s)",
             src, strat, hz, used, preferred)
```

In `get_badge`, keep the docstring and append one paragraph to it:

```
    v162: each step of the chain picks the row measured on
    TRAINING_DATA_SOURCE, else the yfinance row of the same key (_pick).
```

Replace the body from `records = load_registry()` to the end with:

```python
    records = load_registry()
    preferred = _preferred_source()

    def find(src, strat, hz):
        return _find(records, preferred, src, strat, hz)

    rec = (find(source, strategy, horizon_key)
           or find(source, strategy, None)
           or (source == "confluence" and (
               find("strategy", strategy, horizon_key)
               or find("strategy", strategy, None)))
           or find(source, "ALL", horizon_key)
           or find(source, "ALL", None))
    if rec is None:
        return Badge(status="WEAK", n=0, win_rate=0.0, expectancy_r=0.0)
    run_date = rec.get("run_date", "")
    return Badge(status=rec["status"], n=rec["n"], win_rate=rec["win_rate"],
                 expectancy_r=rec["expectancy_r"], window=rec.get("window", ""),
                 run_date=run_date, decay=decay_for(run_date),
                 data_source=row_data_source(rec))
```

The chain is the same expression as before; only the closure now delegates to the module-level `_find`, so `get_badge` keeps its complexity.

Add after `get_badge`:

```python
def active_rows(records: list | None = None, preferred: str | None = None) -> list[dict]:
    """One registry row per (source, strategy, horizon): the row measured on
    `preferred` (default TRAINING_DATA_SOURCE), else the yfinance row of the same
    key (_pick); a key with neither is dropped. Keys keep the file order of their
    first row. Every reader that walks the registry goes through this, so none
    of them counts a key twice once Alpaca rows sit beside yfinance ones."""
    records = load_registry() if records is None else records
    preferred = preferred or _preferred_source()
    groups: dict = {}
    for rec in records:
        groups.setdefault((rec["source"], rec["strategy"], rec.get("horizon")), []).append(rec)
    return [rec for rows in groups.values() if (rec := _pick(rows, preferred)) is not None]
```

- [ ] **Step 3b: Route every registry walker through `active_rows`**

`swingbot/admin/queries.py`: change the import `from swingbot.core.backtesting.registry import decay_for, load_registry` to `from swingbot.core.backtesting.registry import active_rows, decay_for, load_registry`, and in `_registry_rows` change `for rec in load_registry():` to `for rec in active_rows(load_registry()):`. Append to its docstring: "v162: active_rows keeps one row per key, the active training source's."

`swingbot/core/analytics/insights.py`, `edge_decay_report`: change `rows = calibration.badge_drift(closed, registry.load_registry())` to `rows = calibration.badge_drift(closed, registry.active_rows(registry.load_registry()))`.

`swingbot/core/analytics/snapshots.py`, `refresh_snapshot`: change `registry_entries = registry.load_registry()` to `registry_entries = registry.active_rows(registry.load_registry())`.

Run: `git -C $WT grep -n "load_registry()" -- swingbot scripts`
Expected: only `registry.py` itself, `cohort_registry.py` (a different registry), and the three wrapped calls above. Any reader a later commit adds gets the same wrap.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_registry_data_source.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Every existing badge reader still answers as before**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_registry.py`
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_registry_decay.py`
Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_badge_decay_surface.py`
Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_insights.py`
Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_snapshots.py`
Run: `python $WT/scripts/dev/testrun.py changed`
Expected: every run 0 failed. `get_badge` callers (`core/planning/params.py`, `commands/stats.py`, `admin/api_v1/analytics.py`, `measure_factor_lift.py`, `audit_quality_score.py`) are unchanged. A test that compares a whole `Badge` by equality now needs `data_source="yfinance"` only if it built the expected `Badge` with all fields positional; the default makes that rare. Update such an expectation, not the default.

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/registry.py $WT/swingbot/admin/queries.py $WT/swingbot/core/analytics/insights.py $WT/swingbot/core/analytics/snapshots.py`
Expected: no new entry, and `get_badge` no higher than at the task's base commit.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/backtesting/registry.py swingbot/admin/queries.py swingbot/core/analytics/insights.py swingbot/core/analytics/snapshots.py tests/backtesting/test_registry_data_source.py
git -C $WT commit -m "feat(v162): badge lookup and every registry walker take the row of the active training source, fall back to yfinance, never blend

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the commit lands on the branch. The main-tree status shows no file this task touched.

