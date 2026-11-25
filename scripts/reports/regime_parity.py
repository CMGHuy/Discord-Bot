"""v239: stored market_regime_days rows vs a replay on cached bars (spec § Parity).

    python scripts/reports/regime_parity.py [--rows export.json] [--cache-dir DIR]
        [--spy-csv PATH] [--vix-csv PATH] [--limit N] [--export PATH]

A replayed state (and stress, when both sides have one) must equal the stored
one, except on a BOUNDARY DAY: any compared quantity within BOUNDARY_PCT of its
right-hand side. A boundary mismatch is reported, not failed. A non-boundary
mismatch fails and prints both input closes plus the row's providers and
last_bar_date, which say what the live row saw. Stored rows are never rewritten.
Without --rows the rows come from the table; --export writes them to JSON and
stops, so a VM export can be replayed on this machine's cache.
"""
from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data")]

import fetch_regime_data as frd  # noqa: E402
from swingbot.core.market import bear_regime as br  # noqa: E402

BOUNDARY_PCT = 0.001


@dataclass
class ParityResult:
    matches: int
    boundary: list
    failures: list
    uncovered: list = field(default_factory=list)


def _near(value: float | None, rhs: float | None) -> bool:
    if value is None or rhs is None:
        return False
    return abs(value - rhs) <= BOUNDARY_PCT * abs(rhs)


def boundary_day(day: br.RegimeDay) -> bool:
    pairs = ((day.spy_close, day.sma200), (day.spy_close, day.sma50),
             (day.sma200, day.sma200_lag20), (day.sma50, day.sma50_lag5),
             (day.sma50, day.sma200), (day.vix_close, br.STRESS_VIX))
    return any(_near(value, rhs) for value, rhs in pairs)


def _agrees(stored: br.RegimeDay, replayed: br.RegimeDay) -> bool:
    if stored.state != replayed.state:
        return False
    return stored.stress is None or replayed.stress is None or stored.stress == replayed.stress


def _detail(stored: br.RegimeDay, replayed: br.RegimeDay) -> dict:
    return {"session_date": stored.session_date.isoformat(),
            "last_bar_date": stored.last_bar_date.isoformat(),
            "stored": stored.state, "replayed": replayed.state,
            "stored_stress": stored.stress, "replayed_stress": replayed.stress,
            "stored_spy_close": stored.spy_close, "replayed_spy_close": replayed.spy_close,
            "stored_vix_close": stored.vix_close, "replayed_vix_close": replayed.vix_close,
            "spy_provider": stored.spy_provider, "vix_provider": stored.vix_provider}


def compare(stored: list[dict], spy: pd.DataFrame, vix: pd.DataFrame | None) -> ParityResult:
    result = ParityResult(0, [], [])
    last_cached = pd.DatetimeIndex(spy.index)[-1].date()
    for row in stored:
        day = br.RegimeDay.from_row(row)
        if day.last_bar_date is None or day.last_bar_date > last_cached:
            result.uncovered.append(row.get("session_date"))
            continue
        replayed = br.classify(spy, vix, last_session=day.last_bar_date,
                               session_date=day.session_date)
        if _agrees(day, replayed):
            result.matches += 1
        elif boundary_day(day) or boundary_day(replayed):
            result.boundary.append(_detail(day, replayed))
        else:
            result.failures.append(_detail(day, replayed))
    return result


def _jsonable(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    return value


def _stored_rows(args) -> list[dict]:
    if args.rows:
        return json.loads(Path(args.rows).read_text(encoding="utf-8"))
    from swingbot.core.db.repositories.market_regime import market_regime_repo
    return [{k: _jsonable(v) for k, v in row.items()}
            for row in market_regime_repo().recent(limit=args.limit)]


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["Date"], index_col="Date").sort_index()


def _report(result: ParityResult) -> str:
    lines = [f"parity: {result.matches} match · {len(result.boundary)} boundary · "
             f"{len(result.failures)} fail · {len(result.uncovered)} uncovered"]
    for tag, rows in (("BOUNDARY", result.boundary), ("FAIL", result.failures)):
        lines += [f"{tag} {r['session_date']} stored={r['stored']}/{r['stored_stress']} "
                  f"replayed={r['replayed']}/{r['replayed_stress']} "
                  f"spy {r['stored_spy_close']} vs {r['replayed_spy_close']} "
                  f"vix {r['stored_vix_close']} vs {r['replayed_vix_close']} "
                  f"last_bar_date={r['last_bar_date']} spy_provider={r['spy_provider']} "
                  f"vix_provider={r['vix_provider']}" for r in rows]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", help="JSON export of market_regime_days rows")
    parser.add_argument("--cache-dir", type=Path, default=frd.CACHE_DIR)
    parser.add_argument("--spy-csv", type=Path)
    parser.add_argument("--vix-csv", type=Path)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--export", type=Path, help="write the table's rows to this JSON and stop")
    args = parser.parse_args(argv)
    rows = _stored_rows(args)
    if args.export:
        args.export.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
        return 0
    spy_path = args.spy_csv or frd.csv_path(args.cache_dir, br.SPY)
    vix_path = args.vix_csv or frd.csv_path(args.cache_dir, br.VIX)
    if not spy_path.exists() or not vix_path.exists():
        print(f"error: cannot run, missing {spy_path} or {vix_path}", file=sys.stderr)
        return 2
    result = compare(rows, _read_csv(spy_path), _read_csv(vix_path))
    sys.stdout.write(_report(result))
    return 1 if result.failures else 0


if __name__ == "__main__":
    sys.exit(main())
