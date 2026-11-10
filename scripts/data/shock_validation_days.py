"""Pick the v209 A1 validation days from daily SPY, QQQ and VIX rows.

Reads data/market_data_pit/daily/SPY.csv, data/market_data_pit/daily/QQQ.csv and
market_data/vix/VIX_daily.csv only (never a detector output or a fixture) and
selects 26 days in the 2023-01-02..2025-12-31 window: 6 shock, 4 hard
negatives, 4 rotation, 12 calm. The result is frozen once committed (spec
Amendment A1): the CLI refuses to overwrite an existing list.

Usage: python scripts/data/shock_validation_days.py [--data-root <main repo>] [--out <path>]
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent

SPY_CSV = "data/market_data_pit/daily/SPY.csv"
QQQ_CSV = "data/market_data_pit/daily/QQQ.csv"
VIX_CSV = "market_data/vix/VIX_daily.csv"

WINDOW = (date(2023, 1, 2), date(2025, 12, 31))
SEED = 209
SPACING = 5
YEAR_CAP = 4
CLASS_ORDER = ("shock", "hard", "rotation", "calm")
CLASS_SIZES = {"shock": 6, "hard": 4, "rotation": 4, "calm": 12}
DEFAULT_OUT = ROOT / "tests/fixtures/shock_replay/validation_days.json"

RULES = (
    "Close-to-close moves use each series own previous row, taken before the window. "
    "Only dates present in SPY, QQQ and VIX are selectable. Shock: largest SPY drops "
    "(spy_ret < 0), skipping any day within 5 sessions of a chosen one. Hard: "
    "-2.5 <= spy_ret <= -1.5 and vix_chg < 15, largest drops first. Rotation: "
    "spy_ret >= -1.5 and vix_chg < 15, most negative qqq_ret - spy_ret first. Calm: "
    "|spy_ret| < 0.5 and vix_chg < 3, pool sorted by date, random.Random(209).shuffle, "
    "at most 4 per year. Classes are disjoint, picked in the order shock, hard, "
    "rotation, calm; ties fall to the earlier date."
)

_ROW_COLS = ("spy_prev_close", "spy_open", "spy_close", "spy_ret", "qqq_ret",
             "vix_prev_close", "vix_open", "vix_close", "vix_chg")


def main_repo_root() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return Path(out).parent


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["Date", "Open", "Close"])
    df["Date"] = pd.to_datetime(df["Date"]).dt.date
    df = df.drop_duplicates("Date", keep="last").sort_values("Date").set_index("Date")
    return df[["Open", "Close"]].astype(float)


def _returns(df: pd.DataFrame) -> pd.Series:
    return (df["Close"] / df["Close"].shift(1) - 1) * 100


def day_table(spy: pd.DataFrame, qqq: pd.DataFrame, vix: pd.DataFrame) -> pd.DataFrame:
    table = pd.DataFrame({
        "session_no": range(len(spy)),
        "spy_prev_close": spy["Close"].shift(1), "spy_open": spy["Open"],
        "spy_close": spy["Close"], "spy_ret": _returns(spy)}, index=spy.index)
    table["qqq_ret"] = _returns(qqq)
    table["vix_prev_close"] = vix["Close"].shift(1)
    table["vix_open"] = vix["Open"]
    table["vix_close"] = vix["Close"]
    table["vix_chg"] = _returns(vix)
    table = table.loc[table.index.isin(qqq.index) & table.index.isin(vix.index)].dropna()
    keep = [WINDOW[0] <= d <= WINDOW[1] for d in table.index]
    return table.loc[keep]


def _ordered(table: pd.DataFrame, mask, key) -> list[date]:
    """Dates under mask sorted by (key, date) so ties fall to the earlier date."""
    sub = table.loc[mask]
    return [d for _, d in sorted((key(sub).loc[d], d) for d in sub.index)]


def pick_shock(table: pd.DataFrame, n: int = 6, spacing: int = SPACING) -> list[date]:
    chosen: list[date] = []
    for d in _ordered(table, table["spy_ret"] < 0, lambda t: t["spy_ret"]):
        no = table.loc[d, "session_no"]
        if all(abs(no - table.loc[c, "session_no"]) > spacing for c in chosen):
            chosen.append(d)
        if len(chosen) == n:
            break
    return chosen


def pick_hard(table: pd.DataFrame, taken: set, n: int = 4) -> list[date]:
    mask = table["spy_ret"].between(-2.5, -1.5) & (table["vix_chg"] < 15)
    return [d for d in _ordered(table, mask, lambda t: t["spy_ret"]) if d not in taken][:n]


def pick_rotation(table: pd.DataFrame, taken: set, n: int = 4) -> list[date]:
    mask = (table["spy_ret"] >= -1.5) & (table["vix_chg"] < 15)
    ranked = _ordered(table, mask, lambda t: t["qqq_ret"] - t["spy_ret"])
    return [d for d in ranked if d not in taken][:n]


def calm_pool(table: pd.DataFrame, taken: set) -> list[date]:
    mask = (table["spy_ret"].abs() < 0.5) & (table["vix_chg"] < 3)
    return sorted(d for d in table.index[mask] if d not in taken)


def pick_calm(table: pd.DataFrame, taken: set, n: int = 12, seed: int = SEED,
              year_cap: int = YEAR_CAP) -> list[date]:
    pool = calm_pool(table, taken)
    random.Random(seed).shuffle(pool)
    per_year: dict[int, int] = {}
    chosen: list[date] = []
    for d in pool:
        if per_year.get(d.year, 0) >= year_cap:
            continue
        per_year[d.year] = per_year.get(d.year, 0) + 1
        chosen.append(d)
        if len(chosen) == n:
            break
    return chosen


_PICKERS = {
    "shock": lambda t, taken, n: pick_shock(t, n),
    "hard": lambda t, taken, n: pick_hard(t, taken, n),
    "rotation": lambda t, taken, n: pick_rotation(t, taken, n),
    "calm": lambda t, taken, n: pick_calm(t, taken, n),
}


def _day_row(table: pd.DataFrame, d: date, cls: str) -> dict:
    row = {c: round(float(table.loc[d, c]), 4) for c in _ROW_COLS}
    return {"class": cls, **row}


def select_days(table: pd.DataFrame) -> dict:
    taken: set = set()
    classes: dict[str, list[str]] = {}
    days: dict[str, dict] = {}
    for cls in CLASS_ORDER:
        n = CLASS_SIZES[cls]
        got = _PICKERS[cls](table, taken, n)
        if len(got) < n:
            raise ValueError(f"{cls}: {len(got)} of {n} days")
        taken.update(got)
        classes[cls] = [d.isoformat() for d in got]
        for d in got:
            days[d.isoformat()] = _day_row(table, d, cls)
    return {"window": [d.isoformat() for d in WINDOW], "seed": SEED, "rules": RULES,
            "classes": classes, "days": days}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    if args.out.exists():
        print(f"frozen: {args.out} exists; the A1 day list is never regenerated",
              file=sys.stderr)
        return 2
    root = args.data_root or main_repo_root()
    table = day_table(load_daily(root / SPY_CSV), load_daily(root / QQQ_CSV),
                      load_daily(root / VIX_CSV))
    out = select_days(table)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    for cls, dates in out["classes"].items():
        print(f"{cls}: {', '.join(dates)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
