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

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
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


def episodes(days: list[br.RegimeDay]) -> list[ep.Episode]:
    return ep.confirmed_episodes([(d.session_date, ep.episode_key(d.state, d.stress)) for d in days])


def episode_table(eps: list[ep.Episode]) -> list[dict]:
    rows = []
    for key in ep.EPISODE_KEYS:
        lengths = [e.sessions for e in eps if e.key == key]
        q1, median, q3 = (float(v) for v in np.percentile(lengths, [25, 50, 75])) if lengths else (None,) * 3
        rows.append({"key": key, "count": len(lengths), "median": median, "q1": q1, "q3": q3})
    return rows


_OUTCOME = {ep.BEAR_KEY: "bear", ep.NORMAL_KEY: "normal"}


def _spell(run: list[ep.Episode], after: ep.Episode | None) -> dict:
    return {"start": run[0].start, "end": run[-1].end, "sessions": sum(e.sessions for e in run),
            "stress": any(e.key == ep.CORRECTION_STRESS_KEY for e in run),
            "outcome": "open" if after is None else _OUTCOME.get(after.key, "unknown"),
            "switch": None if after is None else after.start}


def correction_spells(eps: list[ep.Episode]) -> list[dict]:
    spells, run = [], []
    for episode in [*eps, None]:
        if episode is not None and episode.key in CORRECTION_KEYS:
            run.append(episode)
            continue
        if run:
            spells.append(_spell(run, episode))
        run = []
    return spells


def conversion(spells: list[dict]) -> dict:
    resolved = [s for s in spells if s["outcome"] in ("bear", "normal")]
    converted = [s["sessions"] for s in resolved if s["outcome"] == "bear"]
    return {"spells": len(spells), "resolved": len(resolved), "converted": len(converted),
            "rate": round(len(converted) / len(resolved), 3) if resolved else None,
            "median_sessions": float(np.median(converted)) if converted else None}


def _in_year(spell: dict, year: int) -> bool:
    return spell["start"].year == year or (spell["outcome"] == "bear" and spell["switch"].year == year)


def named_rows(spells: list[dict]) -> list[dict]:
    rows = []
    for year, expected in NAMED.items():
        hits = [{"year": year, "expected": expected, **s} for s in spells if _in_year(s, year)]
        rows.extend(hits or [{"year": year, "expected": expected, "start": None, "sessions": None,
                              "outcome": "no confirmed CORRECTION", "switch": None}])
    return rows


PULLBACK = "PULLBACK"


def forward_returns(spy: pd.DataFrame, dates, horizons=HORIZONS, lag: int = 1) -> dict[int, list[float]]:
    """Percent return from the close ``lag`` bars before D to ``h`` bars after it.

    lag=1 anchors at s, the bar before D (pullback days: the trigger reads bars <= s).
    lag=0 anchors at D itself (episode first days: D is known only once D+1's label,
    which reads close D, confirms the episode)."""
    closes = spy["Close"].to_numpy(dtype=float)
    position = {ts.date(): i for i, ts in enumerate(spy.index)}
    out: dict[int, list[float]] = {h: [] for h in horizons}
    for day in dates:
        if day not in position or position[day] < lag:
            continue
        s = position[day] - lag
        for h in horizons:
            if s + h < len(closes):
                out[h].append(100.0 * (closes[s + h] / closes[s] - 1.0))
    return out


def _stats(vals: list[float]) -> list[str]:
    if not vals:
        return ["n/a"] * 3
    up = 100.0 * sum(1 for v in vals if v > 0) / len(vals)
    return [f"{float(np.mean(vals)):+.2f}", f"{float(np.median(vals)):+.2f}", f"{up:.1f}"]


def forward_rows(spy: pd.DataFrame, groups: dict) -> list[list[str]]:
    rows = []
    for name, dates in groups.items():
        fwd = forward_returns(spy, dates, lag=1 if name.startswith(PULLBACK) else 0)
        rows.extend([name, str(h), str(len(fwd[h])), *_stats(fwd[h])] for h in HORIZONS)
    return rows


def _groups(days: list[br.RegimeDay], eps: list[ep.Episode]) -> tuple[dict, dict]:
    by_date = {d.session_date: d for d in days}
    pullbacks = [d.session_date for d in days if d.pullback_trigger]
    plain = {key: [e.start for e in eps if e.key == key] for key in ep.EPISODE_KEYS}
    plain[PULLBACK] = pullbacks
    split: dict[str, list] = {}
    for e in eps:
        split.setdefault(f"{e.key} / stress {by_date[e.start].stress}", []).append(e.start)
    for day in pullbacks:
        split.setdefault(f"{PULLBACK} / stress {by_date[day].stress}", []).append(day)
    return plain, dict(sorted(split.items()))


def _table(header: list[str], rows: list[list]) -> list[str]:
    cells = [header, ["---"] * len(header)] + [["n/a" if c is None else str(c) for c in r] for r in rows]
    return ["| " + " | ".join(r) + " |" for r in cells] + [""]


def _head(days, hashes: dict, command: str) -> list[str]:
    first, last = days[0].session_date, days[-1].session_date
    return [f"# v244 — SPY base rates under the v239 bear-regime rules (to {END})", "",
            "**Kind:** DESCRIPTION (ledger row `v244-regime-base-rates`). Describes SPY base rates, "
            "not a strategy: never a lift, selects nothing, moves no gate and spends no validation "
            "budget. The window spans TRAIN and VALIDATION; no figure here licenses B7–B9 (their "
            "screens decide). A later spec may cite only its N and coverage columns, never as "
            "evidence for a gate.",
            f"**Command:** `{command}`",
            f"**End:** {END} (fixed) · **Labelled sessions:** {first} → {last} ({len(days)})",
            "**Inputs:** `data/backtest_cache_regime/` · "
            + " · ".join(f"{s} sha256 `{h}`" for s, h in sorted(hashes.items())),
            "**Rules:** `swingbot/core/market/bear_regime.py` (frozen, v239); episodes confirmed after "
            f"{ep.CONFIRM_SESSIONS} sessions (`regime_episodes`).",
            "**Forward return:** percent change of SPY's adjusted close over `h` sessions. Episode "
            "rows run from the close of D (the episode's first day) to D + h: D is selected only "
            "once D+1 confirms it, and D+1's label reads close D. Pullback rows run from `s` (the "
            "bar before D, the close the label read) to `s + h`: the trigger reads only bars <= s. "
            "A day whose `h` runs past the last bar is dropped for that `h` only.", ""]


_FORWARD_HEADER = ["Group", "h", "N", "Mean %", "Median %", "Up %"]


def _episode_section(eps: list[ep.Episode]) -> list[str]:
    rows = [[r["key"], r["count"], r["median"], r["q1"], r["q3"]] for r in episode_table(eps)]
    return ["## Episodes per state", "",
            *_table(["Episode", "Count", "Median sessions", "Q1", "Q3"], rows)]


def _conversion_section(spells: list[dict]) -> list[str]:
    c = conversion(spells)
    rows = [[s["start"], s["end"], s["sessions"], s["stress"], s["outcome"], s["switch"]] for s in spells]
    return ["## CORRECTION → BEAR conversion", "",
            f"Spells {c['spells']} · resolved {c['resolved']} · converted {c['converted']} · "
            f"rate {c['rate']} · median sessions to switch {c['median_sessions']}", "",
            *_table(["Start", "End", "Sessions", "Stress", "Outcome", "Next episode"], rows)]


def _named_section(spells: list[dict]) -> list[str]:
    rows = [[r["year"], r["expected"], r["start"], r["sessions"], r["outcome"], r["switch"]]
            for r in named_rows(spells)]
    return ["## Named episodes", "",
            *_table(["Year", "Expected", "Spell start", "Sessions", "Outcome", "Next episode"], rows)]


def render(days, eps, spells, spy, hashes: dict, command: str) -> str:
    plain, split = _groups(days, eps)
    return "\n".join([
        *_head(days, hashes, command),
        *_episode_section(eps),
        *_conversion_section(spells),
        *_named_section(spells),
        "## SPY forward returns from episode first days and pullback days", "",
        *_table(_FORWARD_HEADER, forward_rows(spy, plain)),
        "## The same, split by stress", "",
        *_table(_FORWARD_HEADER, forward_rows(spy, split)),
    ])


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-dir", type=Path, default=frd.CACHE_DIR)
    parser.add_argument("--work-dir", type=Path, default=WORK_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse(argv)
    problem = check_hashes(args.cache_dir, args.work_dir)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    spy, vix = load_cache(args.cache_dir)
    days = labelled(spy, vix, args.work_dir)
    if not days:
        print(f"error: no session to label: the cache holds fewer than {br.MIN_BARS + 1} SPY bars",
              file=sys.stderr)
        return 2
    eps = episodes(days)
    hashes = json.loads((args.work_dir / HASHES).read_text(encoding="utf-8"))
    command = " ".join(["python scripts/research/regime_base_rates.py",
                        *(sys.argv[1:] if argv is None else argv)])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(days, eps, correction_spells(eps), spy, hashes, command),
                        encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
