# v130 — Swing significance tiers and BOS/CHoCH events: Implementation Plan (part 2: report, measurement and close-out)

> **For agentic workers:** this is part 2 of 2. The header block, Preconditions, Spec corrections and frozen readings, Global Constraints, File map, Review Focus and Parallelisation live in [`2026-10-03-v130-swing-significance-structure-events_0-index.md`](./2026-10-03-v130-swing-significance-structure-events_0-index.md) and apply to every task here. Read the index first, then pull one task (V130-6 .. V130-8) with `/task-brief <id>`; never read this file whole.

# Phase 3 — Descriptive report

### Task V130-6: `structure_tier_report.py`

**Files:**
- Create: `scripts/reports/structure_tier_report.py`
- Modify: `.gitignore` (add `data/v130_*.json` beside `data/v121_*.json`)
- Test: `tests/scripts/test_structure_tier_report.py`

**Interfaces:**
- Consumes (v121's `scripts/reports/volume_context_report.py`, imported as `vcr`): `ReportRow(source, direction, outcome, r_multiple, context)` (frozen dataclass), `window_refusal(start, end) -> str | None`, `quintile_edges(rows, key) -> list[float] | None`, `bucket_table(rows, key, edges) -> list[dict]` (dict keys `source`, `direction`, `bucket`, `n`, `win_rate`, `expectancy_r`), `replay_all(tickers, horizons, window, *, workers=1) -> list[ReportRow]`, `live_rows(trades)`, `load_live_trades()`, `load_frame(ticker)`, `cached_universe()`, `_fmt(value, spec)`, `acceptance`, `TRAIN_START`, `TRAIN_END`, `LIVE_WARNING`. Consumes (V130-1): `pivot_tiers(df)`, fixtures `DOWN`, `tier_frame`. Consumes: `arms.windows.ALL_HORIZONS`.
- Produces: `THIN_N = 30`; `MORE`, `NOT_MORE` (the two verdict strings); `event_bucket(context) -> str | None`; `derived(rows) -> list[ReportRow]` (adds `event_bucket` and `reaction_atr` to each context); `reaction_edges(rows) -> {"bullish": edges, "bearish": edges}`; `table_lines(rows, key, edges=None) -> list[str]`; `alignment_lines(rows) -> list[str]`; `spread(rows, key) -> {"n_aligned", "n_not_aligned", "thin", "spread"}`; `verdict(rows) -> {"verdict", "conditions", "k3", "major", "major_by_direction"}`; `census_of(df, window) -> (pivot_count, lags)`; `census_all(tickers, window) -> dict`; `render(rows, edges, census, *, source) -> str`; `main(argv) -> int`.

Every monkeypatch in the tests targets the `vcr` module (`vcr.replay_all`, `vcr.load_live_trades`, `vcr.load_frame`), because the script calls those through the `vcr.` attribute. Do not rebind them as local names in the script, or the tests stop intercepting them.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/scripts/test_structure_tier_report.py
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
import structure_tier_report as tier  # noqa: E402
import volume_context_report as vcr  # noqa: E402

from tests.market.structure_tier_fixtures import DOWN, tier_frame  # noqa: E402


def _row(direction, r, *, source="confluence", **context):
    outcome = "win" if r > 0 else "loss"
    return vcr.ReportRow(source=source, direction=direction, outcome=outcome, r_multiple=r, context=context)


def _population(direction, n, *, k3, major, r, source="confluence"):
    return [_row(direction, r, source=source, structure_aligned=k3, structure_aligned_major=major)
            for _ in range(n)]


def _separating(direction="bullish", n=30):
    """Major alignment separates outcomes (+1R vs -1R); k=3 alignment does not."""
    return (_population(direction, n, k3=True, major=True, r=1.0)
            + _population(direction, n, k3=False, major=True, r=1.0)
            + _population(direction, n, k3=True, major=False, r=-1.0)
            + _population(direction, n, k3=False, major=False, r=-1.0))


def _swap_keys(row):
    """Exchange the k=3 and major alignment flags, so k=3 becomes the one that separates."""
    context = {"structure_aligned": row.context["structure_aligned_major"],
               "structure_aligned_major": row.context["structure_aligned"]}
    return vcr.ReportRow(row.source, row.direction, row.outcome, row.r_multiple, context)


@pytest.mark.parametrize("start,end", [("2020-01-01", "2024-01-01"), ("2020-01-01", "2025-06-30"),
                                       ("2019-06-01", "2023-12-31")])
def test_replay_refuses_any_window_outside_train(start, end, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    assert tier.main(["--source", "replay", "--start", start, "--end", end]) == 1
    assert "refused" in capsys.readouterr().out


@pytest.mark.parametrize("age,label", [(0, "0-5"), (5, "0-5"), (6, "6-20"), (20, "6-20"), (21, "21+"), (300, "21+")])
def test_event_bucket_uses_the_fixed_age_edges(age, label):
    context = {"struct_event_last": "choch_against", "struct_event_bars_ago": age}
    assert tier.event_bucket(context) == f"choch_against {label}"


def test_event_bucket_is_none_without_an_event_or_on_an_old_record():
    assert tier.event_bucket({"struct_event_last": None, "struct_event_bars_ago": None}) is None
    assert tier.event_bucket({"vol_ratio_20": 1.2}) is None


def test_reaction_uses_the_swing_low_for_longs_and_the_swing_high_for_shorts():
    rows = tier.derived([_row("bullish", 1.0, last_sl_reaction_atr=2.5, last_sh_reaction_atr=9.0),
                         _row("bearish", 1.0, last_sl_reaction_atr=9.0, last_sh_reaction_atr=1.5),
                         _row("unknown", 1.0, last_sl_reaction_atr=9.0)])
    assert [row.context["reaction_atr"] for row in rows] == [2.5, 1.5, None]


def test_reaction_edges_are_per_direction():
    rows = tier.derived([_row("bullish", 1.0, last_sl_reaction_atr=v) for v in (1, 2, 3, 4, 5)]
                        + [_row("bearish", 1.0, last_sh_reaction_atr=v) for v in (10, 20, 30, 40, 50)])
    assert tier.reaction_edges(rows) == {"bullish": [1.8, 2.6, 3.4, 4.2], "bearish": [18.0, 26.0, 34.0, 42.0]}


def test_a_bucket_under_thirty_prints_thin_and_no_expr():
    rows = _population("bullish", 29, k3=True, major=True, r=1.0)
    out = "\n".join(tier.table_lines(rows, "structure_aligned_major"))
    assert "N=   29  thin" in out and "ExpR" not in out
    full = "\n".join(tier.table_lines(rows + rows[:1], "structure_aligned_major"))
    assert "N=   30" in full and "ExpR +1.0000" in full


def test_spread_is_aligned_minus_not_aligned():
    result = tier.spread(_separating(), "structure_aligned_major")
    assert result == {"n_aligned": 60, "n_not_aligned": 60, "thin": False, "spread": 2.0}
    assert tier.spread(_separating(), "structure_aligned")["spread"] == 0.0


def test_verdict_more_informative_when_all_three_conditions_hold():
    result = tier.verdict(_separating("bullish") + _separating("bearish"))
    assert result["verdict"] == tier.MORE
    assert all(result["conditions"].values())


def test_verdict_passes_condition_three_when_the_bearish_side_is_thin():
    result = tier.verdict(_separating("bullish") + _separating("bearish", n=5))
    assert result["major_by_direction"]["bearish"]["thin"] is True
    assert result["verdict"] == tier.MORE


def test_verdict_fails_when_a_spread_bucket_is_thin():
    result = tier.verdict(_separating("bullish", n=14))            # 28 per alignment bucket
    assert result["conditions"]["all_four_buckets_n30"] is False
    assert result["verdict"] == tier.NOT_MORE


def test_verdict_fails_when_the_major_spread_is_not_larger():
    rows = [_swap_keys(row) for row in _separating("bullish") + _separating("bearish")]
    result = tier.verdict(rows)                                    # k=3 now separates, major does not
    assert result["conditions"]["major_spread_larger"] is False
    assert result["verdict"] == tier.NOT_MORE


def test_verdict_fails_when_the_directions_disagree_in_sign():
    flipped = [vcr.ReportRow(r.source, r.direction, "loss" if r.outcome == "win" else "win", -r.r_multiple,
                             r.context) for r in _separating("bearish", n=30)]
    result = tier.verdict(_separating("bullish", n=90) + flipped)
    assert result["conditions"]["major_spread_larger"] is True
    assert result["conditions"]["same_sign_both_directions"] is False
    assert result["verdict"] == tier.NOT_MORE


def test_verdict_ignores_strategy_sourced_rows():
    strategy = [vcr.ReportRow("strategy", r.direction, r.outcome, r.r_multiple, r.context)
                for r in _separating("bullish")]
    assert tier.verdict(strategy)["verdict"] == tier.NOT_MORE


def test_alignment_table_puts_k3_beside_major():
    lines = tier.alignment_lines(_separating("bullish"))
    true_line = next(line for line in lines if line.startswith("confluence bullish  True"))
    assert true_line.count("N=   60") == 2 and "k3" in true_line and "| major" in true_line
    assert "ExpR +0.0000" in true_line and "ExpR +1.0000" in true_line
    assert any(line.startswith("confluence bullish  None") and "thin" in line for line in lines)


def test_census_counts_pivots_and_bars_to_major():
    df = tier_frame(DOWN)                                          # dates start 2019-01-01
    pivots, lags = tier.census_of(df, ("2019-01-01", "2023-12-31"))
    assert (pivots, sorted(lags)) == (13, [5, 5, 5, 6, 6, 6, 6, 6, 6, 6])
    late, _ = tier.census_of(df, (str(df.index[50].date()), "2023-12-31"))
    assert late == 7                                               # only pivots formed inside the window
    cut, cut_lags = tier.census_of(df, ("2019-01-01", str(df.index[60].date())))
    assert (cut, len(cut_lags)) == (7, 4)                          # reads no bar after the window end


def test_census_all_pools_tickers_and_skips_missing_frames(monkeypatch):
    frames = {"AAA": tier_frame(DOWN), "BBB": tier_frame(DOWN, mirror=True), "CCC": None}
    monkeypatch.setattr(vcr, "load_frame", frames.get)
    census = tier.census_all(["AAA", "BBB", "CCC"], ("2019-01-01", "2023-12-31"))
    assert census == {"pivots": 26, "major": 20, "major_share_pct": 76.92, "median_bars_to_major": 6.0}
    assert tier.census_all(["CCC"], ("2019-01-01", "2023-12-31"))["major_share_pct"] is None


def test_replay_writes_edges_and_json_and_prints_the_verdict(tmp_path, monkeypatch, capsys):
    rows = _separating("bullish") + _separating("bearish")
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: rows)
    monkeypatch.setattr(tier, "census_all", lambda tickers, window: {"pivots": 0})
    edges, blob = tmp_path / "edges.json", tmp_path / "verdict.json"
    assert tier.main(["--source", "replay", "--tickers", "AAA", "--edges", str(edges), "--json", str(blob)]) == 0
    out = capsys.readouterr().out
    assert "DESCRIPTIVE ONLY" in out and f"VERDICT (confluence-sourced, pre-registered): {tier.MORE}" in out
    assert "Table 4" in out
    assert json.loads(edges.read_text(encoding="utf-8"))["window"] == ["2020-01-01", "2023-12-31"]
    saved = json.loads(blob.read_text(encoding="utf-8"))
    assert saved["verdict"] == tier.MORE and saved["closed"] == 240 and saved["census"] == {"pivots": 0}


def test_replay_refuses_to_overwrite_a_recorded_verdict(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vcr, "replay_all", lambda *a, **k: pytest.fail("computed"))
    blob = tmp_path / "verdict.json"
    blob.write_text("{}", encoding="utf-8")
    assert tier.main(["--source", "replay", "--tickers", "AAA", "--json", str(blob)]) == 1
    assert "refused" in capsys.readouterr().out and blob.read_text(encoding="utf-8") == "{}"


def test_live_refuses_without_train_edges(tmp_path, capsys):
    assert tier.main(["--source", "live", "--edges", str(tmp_path / "missing.json")]) == 1
    assert "refused" in capsys.readouterr().out


def test_live_prints_the_holdout_warning_and_no_verdict(tmp_path, monkeypatch, capsys):
    edges = tmp_path / "edges.json"
    edges.write_text('{"window": ["2020-01-01", "2023-12-31"], "edges": {"bullish": null, "bearish": null}}',
                     encoding="utf-8")
    old = {"status": "win", "source": "confluence", "direction": "bullish", "entry": 100.0,
           "stop_loss": 95.0, "exit_price": 110.0, "entry_context": {"vol_ratio_20": 1.2}}
    monkeypatch.setattr(vcr, "load_live_trades", lambda: [old])
    assert tier.main(["--source", "live", "--edges", str(edges)]) == 0
    out = capsys.readouterr().out
    assert "holdout" in out and "VERDICT" not in out and "Table 4" not in out and "p=" not in out
    assert "confluence bullish  None" in out                       # an old record buckets as None, no KeyError
```

- [ ] **Step 2:** Run `python scripts/dev/testrun.py file tests/scripts/test_structure_tier_report.py`; expect FAIL (`ModuleNotFoundError: structure_tier_report`).

- [ ] **Step 3: Implement the script.**

```python
#!/usr/bin/env python3
"""v130 descriptive report: does structure read off MAJOR swings separate closed trades better than k=3 structure?

DESCRIPTIVE ONLY. Its one verdict decides whether a follow-on expectancy spec
is written; it must never pick that spec's thresholds. ``--source replay`` is
TRAIN-only (2020-01-01..2023-12-31) and refuses any other window.
``--source live`` reads the production book, which overlaps the 2026 holdout:
monitoring only -- no verdict and no inferential statistic is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "reports")]

import volume_context_report as vcr  # noqa: E402  (v121's bucketing helpers: imported, not copied)

THIN_N = 30
DEFAULT_EDGES = ROOT / "data" / "v130_train_quintiles.json"
ALIGN_KEYS = ("structure_aligned", "structure_aligned_major")       # k=3 (v121) vs major (v130)
ALIGN_BUCKETS = ("True", "False", "None")
EVENT_AGES = ((5, "0-5"), (20, "6-20"))                              # anything older is "21+"
REACTION_KEY = {"bullish": "last_sl_reaction_atr", "bearish": "last_sh_reaction_atr"}
MORE, NOT_MORE = "major tier more informative", "not more informative"
HEADER = ("v130 structure-tier report -- DESCRIPTIVE ONLY. The verdict decides whether a follow-on "
          "spec is written, never its thresholds. No inferential statistic is printed.")


def event_bucket(context: dict) -> str | None:
    """``struct_event_last`` x the fixed age buckets 0-5 / 6-20 / 21+."""
    kind, age = context.get("struct_event_last"), context.get("struct_event_bars_ago")
    if kind is None or age is None:
        return None
    label = next((name for limit, name in EVENT_AGES if age <= limit), "21+")
    return f"{kind} {label}"


def derived(rows) -> list:
    """Rows with the two report-only keys added: ``event_bucket`` and the
    direction's own ``reaction_atr`` (swing low for bullish, swing high for bearish)."""
    return [replace(row, context={**row.context, "event_bucket": event_bucket(row.context),
                                  "reaction_atr": row.context.get(REACTION_KEY.get(row.direction, ""))})
            for row in rows]


def reaction_edges(rows) -> dict:
    """TRAIN quintile edges of ``reaction_atr``, one set per trade direction."""
    return {direction: vcr.quintile_edges([row for row in rows if row.direction == direction], "reaction_atr")
            for direction in REACTION_KEY}


def _stats(line: dict | None) -> str:
    """N, then win rate and ExpR -- or ``thin`` (no ExpR) under N = 30."""
    count = line["n"] if line else 0
    if count < THIN_N:
        return f"N={count:>5}  thin"
    return (f"N={count:>5}  WR {vcr._fmt(line['win_rate'], '6.2f')}%  "
            f"ExpR {vcr._fmt(line['expectancy_r'], '+.4f')}")


def table_lines(rows, key: str, edges=None) -> list[str]:
    return [f"{line['source']:<10} {line['direction']:<8} {line['bucket']:<18} {_stats(line)}"
            for line in vcr.bucket_table(rows, key, edges)]


def alignment_lines(rows) -> list[str]:
    """Table 1: per (source, direction, bucket), the k=3 cell beside the major cell."""
    tables = [{(line["source"], line["direction"], line["bucket"]): line
               for line in vcr.bucket_table(rows, key, None)} for key in ALIGN_KEYS]
    groups = sorted({key[:2] for table in tables for key in table})
    return [f"{source:<10} {direction:<8} {bucket:<6} k3 {_stats(tables[0].get((source, direction, bucket))):<42}"
            f"| major {_stats(tables[1].get((source, direction, bucket)))}"
            for source, direction in groups for bucket in ALIGN_BUCKETS]


def spread(rows, key: str) -> dict:
    """ExpR(aligned) - ExpR(not aligned) and the N of each bucket."""
    aligned = [row for row in rows if row.context.get(key) is True]
    opposed = [row for row in rows if row.context.get(key) is False]
    thin = min(len(aligned), len(opposed)) < THIN_N
    exp_a, exp_o = vcr.acceptance.expectancy_r(aligned), vcr.acceptance.expectancy_r(opposed)
    value = None if thin or exp_a is None or exp_o is None else round(exp_a - exp_o, 6)
    return {"n_aligned": len(aligned), "n_not_aligned": len(opposed), "thin": thin, "spread": value}


def _same_sign(bullish: dict, bearish: dict) -> bool:
    if bearish["thin"]:
        return True
    if bullish["spread"] is None or bearish["spread"] is None:
        return False
    return bool(np.sign(bullish["spread"]) == np.sign(bearish["spread"]))


def verdict(rows) -> dict:
    """The pre-registered verdict on the confluence-sourced population."""
    confluence = [row for row in rows if row.source == "confluence"]
    k3, major = (spread(confluence, key) for key in ALIGN_KEYS)
    by_direction = {direction: spread([row for row in confluence if row.direction == direction], ALIGN_KEYS[1])
                    for direction in ("bullish", "bearish")}
    conditions = {
        "all_four_buckets_n30": not (k3["thin"] or major["thin"]),
        "major_spread_larger": (k3["spread"] is not None and major["spread"] is not None
                                and major["spread"] > k3["spread"]),
        "same_sign_both_directions": _same_sign(by_direction["bullish"], by_direction["bearish"]),
    }
    return {"verdict": MORE if all(conditions.values()) else NOT_MORE, "conditions": conditions,
            "k3": k3, "major": major, "major_by_direction": by_direction}


def census_of(df, window) -> tuple[int, list[int]]:
    """Confirmed k=3 pivots formed inside ``window`` and, for those that became
    major, the bars from pivot to major bar. Reads no bar after ``window``'s end."""
    from swingbot.core.market.structure import pivot_tiers
    start, end = window
    frame = df.loc[:end]
    tiers = pivot_tiers(frame)
    dates = frame.index[tiers["pos"].to_numpy(int)]
    inside = tiers[np.asarray(dates >= start)]
    major = inside[inside["major_pos"].notna()]
    return len(inside), (major["major_pos"] - major["pos"]).astype(int).tolist()


def census_all(tickers, window) -> dict:
    pivots, lags = 0, []
    for ticker in tickers:
        df = vcr.load_frame(ticker)
        if df is None or df.empty:
            continue
        count, ticker_lags = census_of(df, window)
        pivots, lags = pivots + count, lags + ticker_lags
    return {"pivots": pivots, "major": len(lags),
            "major_share_pct": round(100.0 * len(lags) / pivots, 2) if pivots else None,
            "median_bars_to_major": float(np.median(lags)) if lags else None}


def _verdict_lines(result: dict) -> list[str]:
    lines = [f"\n== VERDICT (confluence-sourced, pre-registered): {result['verdict']} =="]
    lines += [f"{name}: {'PASS' if passed else 'FAIL'}" for name, passed in result["conditions"].items()]
    lines += [f"spread k3    {result['k3']}", f"spread major {result['major']}"]
    lines += [f"spread major {direction} {value}" for direction, value in result["major_by_direction"].items()]
    return lines


def render(rows, edges: dict, census: dict | None, *, source: str) -> str:
    rows = derived(rows)
    lines = [HEADER] + ([vcr.LIVE_WARNING] if source == "live" else []) + [f"closed trades: {len(rows)}"]
    lines += ["\n== Table 1: structure_aligned (k=3) vs structure_aligned_major =="] + alignment_lines(rows)
    lines += ["\n== Table 2: struct_event_last x bars ago =="] + table_lines(rows, "event_bucket")
    for direction, key in REACTION_KEY.items():
        lines.append(f"\n== Table 3: {key} ({direction} trades)  edges={edges.get(direction)} ==")
        lines += table_lines([row for row in rows if row.direction == direction], "reaction_atr",
                             edges.get(direction))
    if census is not None:
        lines += ["\n== Table 4: tier census (daily frames; identical for every horizon) ==", str(census)]
    if source == "replay":
        lines += _verdict_lines(verdict(rows))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("replay", "live"), required=True)
    ap.add_argument("--start", default=vcr.TRAIN_START)
    ap.add_argument("--end", default=vcr.TRAIN_END)
    ap.add_argument("--tickers", default=None, help="comma list; default every cached ticker")
    ap.add_argument("--edges", default=str(DEFAULT_EDGES),
                    help="TRAIN reaction quintile edges: written by replay, required by live")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--json", default=None, help="replay only: also write verdict + census here")
    return ap


def _run_replay(args):
    refusal = vcr.window_refusal(args.start, args.end)
    if not refusal and args.json and Path(args.json).exists():
        refusal = f"refused: {args.json} already holds the recorded verdict; the measurement runs once"
    if refusal:
        print(refusal)
        return None
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    window = (args.start, args.end)
    tickers = args.tickers.split(",") if args.tickers else vcr.cached_universe()
    rows = vcr.replay_all(tickers, ALL_HORIZONS, window, workers=args.workers)
    edges, census = reaction_edges(derived(rows)), census_all(tickers, window)
    path = Path(args.edges)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"window": list(window), "edges": edges}, indent=1), encoding="utf-8")
    if args.json:
        blob = {"window": list(window), "closed": len(rows), "census": census, **verdict(derived(rows))}
        Path(args.json).write_text(json.dumps(blob, indent=1), encoding="utf-8")
    return rows, edges, census


def _run_live(args):
    path = Path(args.edges)
    if not path.exists():
        print(f"refused: live needs TRAIN reaction edges at {path}; run --source replay first")
        return None
    edges = json.loads(path.read_text(encoding="utf-8"))["edges"]
    return vcr.live_rows(vcr.load_live_trades()), edges, None


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    result = (_run_replay if args.source == "replay" else _run_live)(args)
    if result is None:
        return 1
    rows, edges, census = result
    print(render(rows, edges, census, source=args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add to `.gitignore`, next to `data/v121_*.json`:

```
data/v130_*.json
```

- [ ] **Step 4:** Run `python scripts/dev/testrun.py file tests/scripts/test_structure_tier_report.py`; expect PASS (27 tests). Run `python scripts/dev/testrun.py file tests/scripts/test_volume_context_report.py`; expect PASS unchanged. Run `python -m radon cc -s -n C scripts/reports/structure_tier_report.py`; the only line allowed is `verdict - C (11)`.
- [ ] **Step 5 (optional smoke, not a result):** only if the CSV cache exists, invoke `backtest-gate` first, then `python scripts/reports/structure_tier_report.py --source replay --tickers AAPL,MSFT --edges logs/v130_smoke_edges.json`. **Do not pass `--json`** (that is the one-shot record). Expect the header, four tables and a verdict block that is almost certainly `not more informative` on two tickers because the buckets are thin. Do not quote, commit or act on any figure from it.
- [ ] **Step 6:** Commit.

```bash
git add scripts/reports/structure_tier_report.py tests/scripts/test_structure_tier_report.py .gitignore
git commit -m "feat(v130): structure-tier report -- k=3 vs major alignment, events, reaction, census, verdict"
```

# Phase 4 — Measurement and close-out

### Task V130-7: The one TRAIN replay run and its recorded verdict

**Files:**
- Create: `docs/superpowers/results/2026-10-03-v130-structure-tier.txt`, `docs/superpowers/results/2026-10-03-v130-structure-tier.json` (keep the spec's date in the names, whatever day the run happens, so they sort beside the spec)

**Interfaces:** Consumes `scripts/reports/structure_tier_report.py` (V130-6). Produces the verdict string V130-8 branches on: the JSON's `"verdict"` field, one of `major tier more informative` / `not more informative`.

This is a pre-registered measurement. It runs **once**, on TRAIN, over the full cached universe and every horizon. The verdict rule is frozen in "Spec corrections and frozen readings" item 7 and in the script; nothing in it may change after this task starts.

- [ ] **Step 1:** Invoke the `backtest-gate` skill. Confirm the window is `2020-01-01..2023-12-31`, that no VALIDATION or 2026 bar is read, and that the CSV cache is populated (`python scripts/data/fetch_backtest_data.py` if not).
- [ ] **Step 2:** Confirm the result does not exist yet: `ls docs/superpowers/results/2026-10-03-v130-structure-tier.json` must fail. If it exists, the measurement has already been spent — read it and go to V130-8. Never delete it to re-run.
- [ ] **Step 3:** Dispatch the `backtest-runner` agent with exactly this command, from the v130 worktree:

```bash
python scripts/reports/structure_tier_report.py --source replay --workers 4 \
  --json docs/superpowers/results/2026-10-03-v130-structure-tier.json \
  > docs/superpowers/results/2026-10-03-v130-structure-tier.txt
```

Progress is the percent line in `logs/volume_context_report.progress` (v121's `replay_all` writes and removes it). Ask the agent to return only: exit code, the `closed trades:` line, Table 4's line, and the whole `== VERDICT` block. If the run crashes before writing the JSON, fix the crash and run again — a run that produced no verdict has spent nothing. If it wrote the JSON, it is final.
- [ ] **Step 4:** Read the verdict block. Sanity-check the population before trusting it: `closed` in the JSON is in the thousands, and Table 1 shows both `confluence` and `strategy` rows. A run with zero confluence rows means the replay did not stamp snapshots (a wiring bug in V130-4), not a "not more informative" result — report BLOCKED in that case, delete nothing, and ask the partner whether the record stands.
- [ ] **Step 5:** Commit both files on the branch. Quote the verdict and the two pooled spreads in the commit body exactly as printed (the `pooled-numbers` skill applies: copy from the file, do not retype from memory).

```bash
git add docs/superpowers/results/2026-10-03-v130-structure-tier.txt docs/superpowers/results/2026-10-03-v130-structure-tier.json
git commit -m "docs(v130): record the TRAIN structure-tier verdict"
```

### Task V130-8: Full-suite verification and verdict-dependent close-out

**Files:** No new feature files; fix only failures attributable to this plan, with their narrow tests. The release path touches `VERSION.json` and `swingbot/admin/version_history.json`.

- [ ] **Step 1:** Run `python scripts/dev/testrun.py full` once (or dispatch the `test-runner` subagent) over everything this plan implemented. Green requires `0 failed`, `0 xfailed`. **If it is not green, fix forward from the failures it names** — they are this plan's regressions. A changed pass count alone is not a failure. Before blaming this plan for an unrelated red test, check the diff scope and run that file alone (`testing-cost.md`).
- [ ] **Step 2:** Watch replay-heavy tests: every stamped plan now also computes the tier scan (about 27 ms on a 2500-bar frame). If a test's runtime regresses noticeably, measure before optimising, and never change the tier or event semantics to save time. The safe optimisation, if one is needed, is to have `entry_context` compute `atr(df, 14)` once and pass it down — that is a refactor with its own witness run, not part of this task.
- [ ] **Step 3:** Run `python -m radon cc -s -n C swingbot/core/market/structure.py swingbot/core/edge/context.py scripts/reports/structure_tier_report.py`. Only `entry_context - C (17)` (pre-existing) and `verdict - C (11)` may appear.
- [ ] **Step 4:** Read the verdict from `docs/superpowers/results/2026-10-03-v130-structure-tier.json` and follow exactly one branch.

**Branch A — `major tier more informative`:**

- [ ] Merge the branch to `main` with the `worktree-lifecycle` skill. Do not re-run the suite after a conflict-free merge.
- [ ] Release per `working-conventions.md` § Versioning: read `VERSION.json` as it is on disk now, bump the **bot** line at **patch** level, set `bot_updated` (UTC `YYYY-MM-DD HH-MM-SS`), commit `release(bot): <new> -- v130 major-tier structure snapshot`. Then run `python scripts/dev/build_version_matrix.py`, commit `swingbot/admin/version_history.json`, and run `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`.
- [ ] Close out with `/close-out`: all three plan files and the spec move to `implemented/` per `document-lifecycle.md`.
- [ ] Tell the partner the verdict permits a follow-on `expectancy` spec (a `structure_aligned_major` gate or a `choch_against` cooldown). That spec is **not** part of this plan. It must freeze its grid without reading this report's buckets, state why it is not a re-run of v17 or v33, and clear the v72 and v92 gates on TRAIN → VALIDATION.

**Branch B — `not more informative`:**

- [ ] Do **not** merge. On the branch, add a closing commit whose body states the verdict and that the branch is deliberately left unmerged. Never delete the branch.
- [ ] On `main`: copy the two results files from the worktree into `docs/superpowers/results/`, amend this plan's and the spec's `Bump:` line to `none` with one clause ("measurement closed not-more-informative; no code reached main"), add a closing note at the end of the index file (`_0-index.md`) naming the branch `2026-10-03-v130-swing-significance-structure-events` and stating that not merging was a considered decision, then `git mv` all three plan files and the spec into `docs/superpowers/plans/no-lift/` and `docs/superpowers/specs/no-lift/`. One commit: `docs(v130): close out not-more-informative into no-lift/`.
- [ ] No release, no version bump, no follow-on spec. Remove the worktree per `document-lifecycle.md` (the branch stays).

- [ ] **Step 5:** Append the outcome to `.superpowers/sdd/progress.md` (verdict, branch taken, commits).
