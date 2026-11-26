"""v244: SPY base rates under the v239 bear-regime rules, 1993 -> END (v239 spec § Evidence).

    python scripts/research/regime_base_rates.py [--cache-dir DIR] [--work-dir DIR] [--out PATH]

DESCRIBES SPY, NOT A STRATEGY: it moves no gate, selects nothing and spends no
validation budget. Labels every session D = index[i], i >= MIN_BARS, from
s = index[i - 1] (sessions come from the SPY bar index: the NYSE calendar only
covers 2018-2030) through END. Inputs: data/backtest_cache_regime/
(scripts/data/fetch_regime_data.py). Refuses to run when a CSV's SHA-256
differs from manifest.json or from the hashes recorded at its first run.
Checkpointed per year of D; a restart skips finished years.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data")]

import fetch_regime_data as frd  # noqa: E402
from scripts.reports.reconcile.checkpoint import JsonlCheckpoint  # noqa: E402
from swingbot.core.market import bear_regime as br  # noqa: E402
from swingbot.core.market import regime_episodes as ep  # noqa: E402

END = "2026-11-20"
HORIZONS = (5, 20, 60)
NAMED = {2000: "convert", 2008: "convert", 2022: "convert",
         2010: "check", 2011: "check", 2018: "check", 2020: "check"}
WINDOW_BARS = br.MIN_BARS + 40
CORRECTION_KEYS = (ep.CORRECTION_KEY, ep.CORRECTION_STRESS_KEY)
WORK_DIR = ROOT / "data" / "reports" / "v244_regime_base_rates"
OUT = ROOT / "docs" / "superpowers" / "results" / "2026-11-23-v244-regime-base-rates.md"
HASHES = "hashes.json"
CHECKPOINT = "labels.jsonl"
_REFETCH = "a new fetch needs a new --work-dir and a new results doc"


def _current_hashes(cache_dir: Path) -> tuple[dict, str | None]:
    hashes = {}
    for symbol in frd.SYMBOLS:
        path = frd.csv_path(cache_dir, symbol)
        if not path.exists():
            return {}, f"{path} is missing; run scripts/data/fetch_regime_data.py"
        hashes[symbol] = frd.sha256_file(path)
    return hashes, None


def check_hashes(cache_dir: Path, work_dir: Path) -> str | None:
    """None to go on; otherwise why the study refuses to run.

    Order: a missing file, then the manifest, then the first-run record. The
    record is written only when everything before it agrees."""
    current, problem = _current_hashes(Path(cache_dir))
    if problem:
        return problem
    manifest = Path(cache_dir) / frd.MANIFEST
    if manifest.exists():
        listed = {s: v["sha256"] for s, v in
                  json.loads(manifest.read_text(encoding="utf-8"))["symbols"].items()}
        if listed != current:
            return f"the cache CSVs differ from {manifest}; refusing"
    recorded = Path(work_dir) / HASHES
    if recorded.exists():
        if json.loads(recorded.read_text(encoding="utf-8")) != current:
            return (f"cache hashes differ from those recorded at its first run ({recorded}); "
                    f"refusing: {_REFETCH}")
        return None
    recorded.parent.mkdir(parents=True, exist_ok=True)
    recorded.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
    return None


def load_cache(cache_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    def read(symbol: str) -> pd.DataFrame:
        frame = pd.read_csv(frd.csv_path(cache_dir, symbol), parse_dates=["Date"], index_col="Date")
        return frame.sort_index().loc[:END]
    return read(br.SPY), read(br.VIX)


def _label_at(spy: pd.DataFrame, vix: pd.DataFrame | None, i: int) -> br.RegimeDay:
    """D = spy.index[i], labelled from the WINDOW_BARS bars ending at s = index[i - 1]."""
    lo = max(0, i - WINDOW_BARS)
    first, s = spy.index[lo], spy.index[i - 1]
    return br.classify(spy.iloc[lo:i], None if vix is None else vix.loc[first:s],
                       last_session=s.date(), session_date=spy.index[i].date(),
                       spy_provider="yfinance", vix_provider="yfinance")


def label_series(spy: pd.DataFrame, vix: pd.DataFrame | None) -> list[br.RegimeDay]:
    return [_label_at(spy, vix, i) for i in range(br.MIN_BARS, len(spy))]


def label_year(spy: pd.DataFrame, vix: pd.DataFrame | None, year: int) -> list[br.RegimeDay]:
    return [_label_at(spy, vix, i) for i in range(br.MIN_BARS, len(spy)) if spy.index[i].year == year]


def _years(spy: pd.DataFrame) -> list[int]:
    return sorted({ts.year for ts in spy.index[br.MIN_BARS:]})


def _to_json(day: br.RegimeDay) -> dict:
    return {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in day.to_row().items()}


def labelled(spy: pd.DataFrame, vix: pd.DataFrame | None, work_dir: Path) -> list[br.RegimeDay]:
    """Every label, checkpointed per year of D; labels always come back through
    the checkpoint, so a fresh run and a resumed run return equal lists."""
    checkpoint = JsonlCheckpoint(Path(work_dir) / CHECKPOINT)
    years = _years(spy)
    done = checkpoint.done()
    for n, year in enumerate(years, start=1):
        if str(year) in done:
            continue
        checkpoint.append(str(year), {"days": [_to_json(d) for d in label_year(spy, vix, year)]})
        print(f"labelled {year} ({n}/{len(years)}, {100 * n // len(years)}%)", flush=True)
    days = [br.RegimeDay.from_row(day) for row in checkpoint.rows() for day in row["days"]]
    return sorted(days, key=lambda d: d.session_date)
