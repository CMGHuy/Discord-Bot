# v222 — Market-shock detector: index + VIX entry path — Part 3b: Stage 2 adapter, report and run

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Global Constraints, plan-time readings, Parallelisation and the task ledger live there; every task below implicitly includes them.
**Continues:** [`2026-11-09-v222-shock-index-vix-path_3-stage2-intraday.md`](2026-11-09-v222-shock-index-vix-path_3-stage2-intraday.md) (V222-6d, V222-7, V222-7b). Part 3 of the ledger is carried by both files only because one file would pass the 1500-line cap; no task is split.

Tasks V222-7c, V222-8: the adapter that hands the frozen day list to A1's
builder and the Stage 2 report and CLI, then the one Stage 2 run, its Results
and gate 2.

**Plan-time readings Part 3 fixes (same text as in `_3-stage2-intraday.md`) (index § plan-time readings, extended here
before any Stage 2 data is read; the controller checks them):**

- **Slot filling.** A slot's candidates are its pick followed by its reserves,
  in ranking order. The first candidate whose fixture status is `ok` fills it;
  `unbuildable`, `synthetic` and `no_vix` candidates are skipped (listed in the
  result). A candidate without a fixture on disk stops the slot: the run is
  `INCOMPLETE` and names the day to build next. A slot whose candidates are all
  skipped is **exhausted** and scores against the cell, like A1's unbuildable
  days: an exhausted counted shock slot neither survives nor leads, an exhausted
  quiet or near-miss slot counts as a fire.
- **Fixture source.** A day on the list that has an A1 fixture (in
  `tests/fixtures/shock_replay/`) reuses it as is; every other day is built into
  `tests/fixtures/shock_replay_v222/`.
- **Drop still ahead.** `(SPY at t − close) / (prior close − close)` with
  `SPY at t` = the reading's `spy_last` at `t`. A day whose close is at or above
  its prior close, or whose reading at `t` has no `spy_last`, has no share and
  does not lead. A1 never firing gives `t_A1` = the fixture's `close_utc` and a
  share of 0.
- **Builder inputs.** The adapter takes each day's SPY and `^VIX` open, close and
  previous close from the Stage 1 files `data/v222/SPY.csv` and `data/v222/^VIX.csv`
  (each series' own previous row, as A1's `day_table` does); it does not call
  `shock_validation_days.day_table`, which keeps only 2023–2025 and needs QQQ.
- **Stage 3 prior.** The 2026-11-04 `^VIX` close is read only once the Stage 2
  day list is committed in Results (2026-11-04 is itself a possible candidate).

**Paths used in every task.**

```bash
M=E:/Documents/Private/Projects/Discord-Bot                                   # main tree
W=$M/.claude/worktrees/2026-11-09-v222-shock-index-vix-path                   # worktree (all code)
D=$M/data/v222                                                                 # stage data (gitignored, main tree)
```

`scripts/dev/testrun.py` resolves test paths against its own checkout, so
`python "$W/scripts/dev/testrun.py" file tests/...` runs the worktree's tests.
Never `cd`; use `git -C "$W"` and absolute paths.

# Phase 3 (continued) — Stage 2 adapter, report and run

### Task V222-7c: Day-list adapter for the builder; Stage 2 report and CLI

**Model:** sonnet — an adapter and a report over fixed contracts; the gate logic is V222-7b's.

**Files:**
- Create: `scripts/data/shock_stage2_days.py`
- Create: `tests/scripts/test_shock_stage2_days.py` (suite `tooling`)
- Modify: `scripts/backtest/shock_index_intraday.py` (append)
- Modify: `tests/backtest_scripts/test_shock_index_intraday.py` (append)

**Interfaces:**
- Consumes: `shock_index_screen.read_daily` (V222-1b); the day-list dict (V222-4c); the builder's day file `{"days": {iso: info}}` (info keys `class, spy_prev_close, spy_open, spy_close, vix_prev_close, vix_open, vix_close`, read by `_day_header` and `daily_vix_path`); V222-7/7b functions and test helpers `_fx`, `_lead_fx`, `_world`, `K`.
- Produces: `shock_stage2_days.classes_of(stage2: dict) -> dict[str, str]`; `a1_days(stage2: dict) -> set[str]`; `default_isos(stage2: dict) -> list[str]` (main picks without an A1 fixture, sorted); `stage2_info(stage2: dict, isos: list[str], *, spy: pd.DataFrame, vix: pd.DataFrame) -> dict` (info adds `spy_ret`, `vix_chg`; the ledger's two positional arguments plus the daily frames as keywords); CLI `--stage2-json --spy --vix --out [--only iso,...]` (merges into an existing `--out`; exit 2 on a day off the list, an A1 day or a missing bar). `shock_index_intraday.step_rows(rs, k: float, th=ShockThresholds()) -> list[dict]`; `render_md(result: dict) -> str`; `main(argv=None) -> int` CLI `--days-json --v222-dir [--a1-dir] --out-json --out-md` (exit 0 complete, 3 incomplete, 2 bad input); a complete run's JSON adds `steps: {iso: {"group", "rows"}}` (picked and A1 shock days).

The adapter lists the main picks without an A1 fixture by default; reserves are
built only when `evaluate` names them (`--only`). Per-step tables sit under
`## Per-step tables`, one `### <iso> (<group>)` each.

- [ ] **Step 1: Write the failing adapter tests**

Create `tests/scripts/test_shock_stage2_days.py`:

```python
"""v222 V222-7c: the frozen Stage 2 day list as the builder's day file."""
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "data"))
import build_shock_replay_fixture as bsr  # noqa: E402
import shock_stage2_days as ssd  # noqa: E402

STAGE2 = {"cell": [1.5, 20.0], "alpaca_from": "2016-01-04",
          "shock": ["2020-03-16"], "shock_reserve": ["2020-03-18"],
          "quiet": ["2020-04-13"], "quiet_reserve": [["2020-04-14"]],
          "near_miss": ["2024-08-05"], "near_miss_reserve": [],
          "a1_shock": ["2024-08-05"], "a1_negative": {"calm": [], "rotation": [], "hard": []}}


def _frame(rows):
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d, *_ in rows], name="Date")
    return pd.DataFrame([r[1:] for r in rows], index=idx, columns=["Open", "High", "Low", "Close"])


SPY = _frame([("2020-03-13", 0, 0, 0, 270.0), ("2020-03-16", 241.0, 0, 0, 240.0),
              ("2020-03-18", 239.0, 0, 0, 241.0)])
VIX = _frame([("2020-03-12", 0, 0, 0, 75.0), ("2020-03-13", 0, 0, 0, 57.8),
              ("2020-03-16", 70.0, 0, 0, 82.7)])


def test_classes_and_the_default_list_leave_out_reserves_and_a1_days():
    assert ssd.classes_of(STAGE2) == {"2020-03-16": "shock", "2020-03-18": "shock",
                                      "2020-04-13": "quiet", "2020-04-14": "quiet",
                                      "2024-08-05": "near_miss"}
    assert ssd.a1_days(STAGE2) == {"2024-08-05"}
    assert ssd.default_isos(STAGE2) == ["2020-03-16", "2020-04-13"]


def test_info_uses_each_series_own_previous_row():
    info = ssd.stage2_info(STAGE2, ["2020-03-16"], spy=SPY, vix=VIX)["days"]["2020-03-16"]
    assert info == {"class": "shock", "spy_prev_close": 270.0, "spy_open": 241.0,
                    "spy_close": 240.0, "spy_ret": round((240 / 270 - 1) * 100, 4),
                    "vix_prev_close": 57.8, "vix_open": 70.0, "vix_close": 82.7,
                    "vix_chg": round((82.7 / 57.8 - 1) * 100, 4)}
    header = bsr._day_header(date(2020, 3, 16), info)                  # the builder reads it
    assert header["spy_daily"] == {"prev_close": 270.0, "open": 241.0, "close": 240.0}


@pytest.mark.parametrize("isos, match", [
    (["2024-08-05"], "A1"),        # reused, never built
    (["2020-05-01"], "A1"),        # not on the list
    (["2020-03-18"], "no daily"),  # no ^VIX bar
])
def test_refusals(isos, match):
    with pytest.raises(ValueError, match=match):
        ssd.stage2_info(STAGE2, isos, spy=SPY, vix=VIX)


def test_the_cli_writes_then_merges_on_demand_reserves(tmp_path):
    SPY.to_csv(tmp_path / "SPY.csv")
    pd.concat([VIX, _frame([("2020-03-18", 80.0, 0, 0, 76.4)])]).to_csv(tmp_path / "VIX.csv")
    (tmp_path / "s2.json").write_text(json.dumps(STAGE2), encoding="utf-8")
    base = ["--stage2-json", str(tmp_path / "s2.json"), "--spy", str(tmp_path / "SPY.csv"),
            "--vix", str(tmp_path / "VIX.csv"), "--out", str(tmp_path / "info.json")]
    assert ssd.main([*base, "--only", "2020-03-16"]) == 0
    assert ssd.main([*base, "--only", "2020-03-18"]) == 0
    days = json.loads((tmp_path / "info.json").read_text(encoding="utf-8"))["days"]
    assert sorted(days) == ["2020-03-16", "2020-03-18"]
    assert ssd.main([*base, "--only", "2024-08-05"]) == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_stage2_days.py`
Expected: `ModuleNotFoundError: No module named 'shock_stage2_days'`.

- [ ] **Step 3: Implement the adapter**

Create `scripts/data/shock_stage2_days.py`:

```python
"""v222 V222-7c: the frozen Stage 2 day list as the builder's --validation-days file.

Prices come from the Stage 1 daily files (data/v222/SPY.csv, ^VIX.csv), each
series' own previous row being the prior close (shock_validation_days.day_table
keeps only 2023-2025 and needs QQQ, so it is not called). Days with an A1
fixture are never built: Stage 2 reuses those fixtures.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shock_index_screen import read_daily  # noqa: E402


def classes_of(stage2: dict) -> dict[str, str]:
    """Every pick and reserve -> its class; the first group naming a day wins."""
    groups = (("shock", [*stage2["shock"], *stage2["shock_reserve"]]),
              ("quiet", [*stage2["quiet"], *(d for s in stage2["quiet_reserve"] for d in s)]),
              ("near_miss", [*stage2["near_miss"], *stage2["near_miss_reserve"]]))
    out: dict[str, str] = {}
    for cls, isos in groups:
        for iso in isos:
            out.setdefault(iso, cls)
    return out


def a1_days(stage2: dict) -> set[str]:
    return {*stage2["a1_shock"], *(d for ds in stage2["a1_negative"].values() for d in ds)}


def default_isos(stage2: dict) -> list[str]:
    """The main picks without an A1 fixture; reserves are built only on demand."""
    return sorted({*stage2["shock"], *stage2["quiet"], *stage2["near_miss"]} - a1_days(stage2))


def _info(spy: pd.DataFrame, vix: pd.DataFrame, iso: str, cls: str) -> dict:
    t = pd.Timestamp(iso)
    if t not in spy.index or t not in vix.index:
        raise ValueError(f"{iso}: no daily SPY or ^VIX bar")
    s, w = spy.index.get_loc(t), vix.index.get_loc(t)
    if s == 0 or w == 0:
        raise ValueError(f"{iso}: no daily bar before it")
    sp, sd, vp, vd = spy.iloc[s - 1], spy.iloc[s], vix.iloc[w - 1], vix.iloc[w]
    row = {"spy_prev_close": sp["Close"], "spy_open": sd["Open"], "spy_close": sd["Close"],
           "spy_ret": (sd["Close"] / sp["Close"] - 1) * 100,
           "vix_prev_close": vp["Close"], "vix_open": vd["Open"], "vix_close": vd["Close"],
           "vix_chg": (vd["Close"] / vp["Close"] - 1) * 100}
    return {"class": cls, **{k: round(float(x), 4) for k, x in row.items()}}


def stage2_info(stage2: dict, isos: list[str], *, spy: pd.DataFrame,
                vix: pd.DataFrame) -> dict:
    classes, reused = classes_of(stage2), a1_days(stage2)
    bad = [iso for iso in isos if iso not in classes or iso in reused]
    if bad:
        raise ValueError(f"not built (off the list, or an A1 fixture day): {bad}")
    return {"days": {iso: _info(spy, vix, iso, classes[iso]) for iso in sorted(isos)}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v222: Stage 2 day list -> builder day file")
    ap.add_argument("--stage2-json", required=True)
    ap.add_argument("--spy", required=True)
    ap.add_argument("--vix", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=None)
    args = ap.parse_args(argv)
    stage2 = json.loads(Path(args.stage2_json).read_text(encoding="utf-8"))
    isos = ([s.strip() for s in args.only.split(",") if s.strip()] if args.only
            else default_isos(stage2))
    try:
        new = stage2_info(stage2, isos, spy=read_daily(Path(args.spy)),
                          vix=read_daily(Path(args.vix)))["days"]
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    out = Path(args.out)
    days = json.loads(out.read_text(encoding="utf-8"))["days"] if out.exists() else {}
    days.update(new)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"days": dict(sorted(days.items()))}, indent=1) + "\n",
                   encoding="utf-8")
    print(f"wrote {out}: {len(new)} day(s) added, {len(days)} in all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_stage2_days.py`
Expected: all pass.

```bash
git -C "$W" add scripts/data/shock_stage2_days.py tests/scripts/test_shock_stage2_days.py
git -C "$W" commit -m "feat(v222): adapter from the Stage 2 day list to the replay builder's day file"
```

- [ ] **Step 4: Write the failing report and CLI tests**

Append to `tests/backtest_scripts/test_shock_index_intraday.py`:

```python
# --- V222-7c: step rows, report, CLI ----------------------------------------

def test_step_rows_show_both_halves():
    rows = sii.step_rows(sii.readings(_lead_fx()), K)
    assert rows[0]["t"] == "13:45" and rows[0]["index"] is True and rows[0]["a1"] is False
    assert rows[-1]["a1"] is True and rows[-1]["spy_atr"] == -5.6


def test_render_md_carries_the_gate_and_lead_tables():
    md = sii.render_md(sii.evaluate(*_world()))
    assert "verdict **PASS**" in md
    assert "| survival | 8 of 8 | >= 6 of 8 | yes |" in md
    assert "| lead | 8 of 8 | >= 5 of 8 | yes |" in md
    assert "| quiet | 0 of 4 | <= 0 of 4 | yes |" in md
    assert "rotation 1/1 (A1 1)" in md and "Ramp VIX" in md
    assert "| 2024-08-05 | 15:30Z | 14:00Z |" in md                  # A1 shock row, reported


def test_render_md_of_an_incomplete_run_names_the_next_build():
    days, fixtures = _world()
    del fixtures["2020-01-03"]
    assert "Incomplete: build 2020-01-03 next." in sii.render_md(sii.evaluate(days, fixtures))


def _write_world(tmp_path, drop=()):
    days, fixtures = _world()
    a1, v222 = tmp_path / "a1", tmp_path / "v222"
    a1.mkdir(), v222.mkdir()
    a1_list = {*days["a1_shock"], *(d for ds in days["a1_negative"].values() for d in ds)}
    for iso, fx in fixtures.items():
        if iso not in drop:
            path = (a1 if iso in a1_list else v222) / f"{iso}.json.gz"
            path.write_bytes(gzip.compress(json.dumps(fx).encode()))
    (tmp_path / "days.json").write_text(json.dumps(days), encoding="utf-8")
    return ["--days-json", str(tmp_path / "days.json"), "--v222-dir", str(v222),
            "--a1-dir", str(a1), "--out-json", str(tmp_path / "s2.json"),
            "--out-md", str(tmp_path / "s2.md")]


def test_main_writes_json_and_markdown_with_per_step_tables(tmp_path):
    assert sii.main(_write_world(tmp_path)) == 0
    result = json.loads((tmp_path / "s2.json").read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS" and result["steps"]["2020-01-01"]["group"] == "shock"
    assert result["steps"]["2024-08-05"]["group"] == "a1_shock"
    md = (tmp_path / "s2.md").read_text(encoding="utf-8")
    assert "## Per-step tables" in md and "### 2020-02-01 (quiet)" in md


def test_main_exit_codes(tmp_path):
    (tmp_path / "x").mkdir()
    assert sii.main(_write_world(tmp_path / "x", drop={"2020-01-03"})) == 3
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    args = ["--days-json", str(bad), "--v222-dir", str(tmp_path), "--out-json",
            str(tmp_path / "o.json"), "--out-md", str(tmp_path / "o.md")]
    assert sii.main(args) == 2
```

Run: `python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py`
Expected: the five new tests FAIL (`AttributeError`: `step_rows`, `render_md`, `main`).

- [ ] **Step 5: Implement the report and CLI**

In `scripts/backtest/shock_index_intraday.py` add `import argparse` to the stdlib imports and append:

```python
A1_DIR = ROOT / "tests" / "fixtures" / "shock_replay"
BARS = {"survival": ">= {min} of {of}", "quiet": "<= {max} of {of}",
        "near_miss": "<= {max} of {of}", "lead": ">= {min} of {of}"}


def _r(x: float | None, nd: int = 3):
    return None if x is None else round(x, nd)


def step_rows(rs, k: float, th: ShockThresholds = ShockThresholds()) -> list[dict]:
    """One row per reading: SPY ATR move, VIX change, breadth, A1 entry, forced index half."""
    return [{"t": r.as_of.strftime("%H:%M"), "spy_atr": _r(r.spy_atr_move),
             "vix_chg": _r(r.vix_chg_pct, 2), "breadth": _r(r.breadth_frac),
             "settled": shock._settled(r, th), "insufficient": r.insufficient,
             "a1": shock.entry_condition(r, th), "index": index_half(r, k, FORCE_VIX_BAR)}
            for r in rs]


def _hm(iso: str | None) -> str:
    return iso[11:16] + "Z" if iso else "never"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _yes(flag: bool) -> str:
    return "yes" if flag else "NO"


def _gate_table(r: dict) -> list[str]:
    out = ["| Gate | Observed | Bar | Pass |", "|---|---|---|---|"]
    for g in ("survival", "quiet", "near_miss", "lead"):
        row = r[g]
        out.append(f"| {g} | {row['n']} of {row['of']} | {BARS[g].format(**row)} | "
                   f"{_yes(row['pass'])} |")
    a1 = r["a1_false_fires"]
    seen = ", ".join(f"{c} {x['with_index']}/{x['of']} (A1 {x['recorded']})"
                     for c, x in a1["rows"].items())
    out.append(f"| a1_false_fires | {seen} | no class above A1's row | {_yes(a1['pass'])} |")
    return out


def _lead_table(rows: list[dict]) -> list[str]:
    out = ["| Day | t_A1 | t_idx | ahead at t_A1 | ahead at t_idx | leads |",
           "|---|---|---|---|---|---|"]
    out += [f"| {x['day']} | {_hm(x['t_a1'])} | {_hm(x['t_idx'])} | {_pct(x['ahead_a1'])} | "
            f"{_pct(x['ahead_idx'])} | {'yes' if x['leads'] else 'no'} |" for x in rows]
    return out


def _ramp_line(ramp: dict) -> str:
    gates = ", ".join(f"{g} {ramp[g]['n']}/{ramp[g]['of']}"
                      for g in ("survival", "quiet", "near_miss", "lead"))
    a1 = ", ".join(f"{c} {x['with_index']}/{x['of']}"
                   for c, x in ramp["a1_false_fires"]["rows"].items())
    return f"Ramp VIX (descriptive; the ramp uses the daily close): {gates}; A1 days {a1}."


def _step_md(steps: dict) -> list[str]:
    out = ["## Per-step tables", ""]
    for iso, day in steps.items():
        out += [f"### {iso} ({day['group']})", "",
                "| UTC | SPY ATR | VIX % | breadth | A1 | index | note |",
                "|---|---|---|---|---|---|---|"]
        for x in day["rows"]:
            note = "insufficient" if x["insufficient"] else ("" if x["settled"] else "settle")
            out.append(f"| {x['t']} | {x['spy_atr']} | {x['vix_chg']} | {x['breadth']} | "
                       f"{'x' if x['a1'] else '-'} | {'x' if x['index'] else '-'} | {note} |")
        out.append("")
    return out


def render_md(result: dict) -> str:
    k, v = result["cell"]
    head = [f"Stage 2 -- cell index_atr_k = {k}, index_vix_chg = {v}; "
            f"verdict **{result['verdict']}**", ""]
    if not result["complete"]:
        return "\n".join([*head, f"Incomplete: build {', '.join(result['missing'])} next."]) + "\n"
    picked = "; ".join(f"{g}: {', '.join(isos) or 'none'}" for g, isos in result["picked"].items())
    lines = [*head, f"Days: {picked}.", f"Skipped (replaced from the ranking): "
             f"{result['skipped'] or 'none'}.", "",
             "Every gate runs with the VIX half forced true (spec § Frozen).", "",
             *_gate_table(result), "", "Lead over A1, counted shock days:", "",
             *_lead_table(result["lead"]["rows"]), "",
             "A1 shock fixtures (reported, never counted):", "",
             *_lead_table(result["a1_shock_report"]), "", _ramp_line(result["ramp"]), ""]
    if result.get("steps"):
        lines += _step_md(result["steps"])
    return "\n".join(lines) + "\n"


def _with_steps(result: dict, days: dict, fixtures: dict) -> None:
    k = result["cell"][0]
    groups = {iso: ("quiet" if g.startswith("quiet") else g)
              for g, isos in result["picked"].items() for iso in isos}
    groups.update({iso: "a1_shock" for iso in days["a1_shock"]})
    result["steps"] = {iso: {"group": g, "rows": step_rows(readings(fixtures[iso]), k)}
                       for iso, g in groups.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="v222 Stage 2: intraday gates for the winner cell")
    ap.add_argument("--days-json", required=True)
    ap.add_argument("--v222-dir", required=True)
    ap.add_argument("--a1-dir", default=str(A1_DIR))
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-md", required=True)
    args = ap.parse_args(argv)
    try:
        days = json.loads(Path(args.days_json).read_text(encoding="utf-8"))
        fixtures = load_fixtures(days, Path(args.v222_dir), Path(args.a1_dir))
        result = evaluate(days, fixtures)
    except (OSError, KeyError, ValueError) as exc:
        print(f"bad input: {exc}", file=sys.stderr)
        return 2
    if result["complete"]:
        _with_steps(result, days, fixtures)
    Path(args.out_json).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    Path(args.out_md).write_text(render_md(result), encoding="utf-8")
    nxt = f"; build next: {','.join(result['missing'])}" if result["missing"] else ""
    print(f"verdict {result['verdict']}{nxt}")
    return 0 if result["complete"] else 3


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py
python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_stage2_days.py
python "$W/scripts/dev/complexity_gate.py"
```

Expected: all pass; no function at or above 15.

- [ ] **Step 7: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_intraday.py tests/backtest_scripts/test_shock_index_intraday.py
git -C "$W" commit -m "feat(v222): Stage 2 report and CLI (gate, lead and per-step tables)"
```

### Task V222-8: Build Stage 2 fixtures, run, write Results, freeze the cell, gate 2

**Model:** sonnet — runs finished tools once and copies their output; no new logic. The **controller runs it in the main session**, like V222-5: gate 2 is an `AskUserQuestion`, which a subagent cannot ask, and the Results commits land on `main`.

**Files:**
- Create: `tests/fixtures/shock_replay_v222/days.json` (byte copy of `data/v222/stage2_days.json`) and `tests/fixtures/shock_replay_v222/<iso>.json.gz` (one per built day)
- Modify: `tests/backtest_scripts/test_shock_index_intraday.py` (append the committed-fixture test)
- Modify: `scripts/dev/select_tests.py` (row `("tests/fixtures/shock_replay_v222/", ("tests/backtest_scripts/test_shock_index_intraday.py",))`)
- Modify: `docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md` (**main tree**, `## Results` § `### Stage 2`; committed on `main`)
- Outputs (main tree, gitignored): `data/v222/stage2_info.json`, `data/v222/stage2.json`, `data/v222/stage2.md`, `data/v222/build.log`; raw bar cache `market_data/shock_replay_v222/` (gitignored, never committed)

**Interfaces:**
- Consumes: gate 1 = go on and Results § Stage 2 day list committed (V222-5); `data/v222/stage2_days.json`, `SPY.csv`, `^VIX.csv` (V222-1, V222-5); `shock_stage2_days.py` CLI and `shock_index_intraday.py` CLI (V222-7c); `build_shock_replay_fixture.py --validation-days FILE --out-dir DIR [--cache-dir] [--unbuildable ISO --reason TEXT]` (A1, on `main`); `sii._listed`, `sii.load_fixtures`, `sii.evaluate` (V222-7b).
- Produces: Results § Stage 2 (frozen day list as used, per-day lead table, the five gate rows, the ramp line, per-step tables of the counted shock days, the verdict); on PASS the line **`Frozen cell: FROZEN_K = <k>, FROZEN_V = <v>.`** that V222-12, V222-13 and V222-14 read; the gate 2 answer.

**Order is the rule (spec § Frozen, index § Data hygiene).** The day list was
committed in Results by V222-5; nothing here changes it. Stage 2 runs **once**
on complete fixtures: `evaluate` scores nothing while a slot still lacks its
fixture (exit 3), so the build loop below never shows a gate value before the
run is complete. No gate is re-run, no day is swapped by hand, no cell other
than the Stage 1 winner is replayed, and a failed gate is NO-LIFT.

- [ ] **Step 1: Preconditions**

```bash
grep -n "^Gate 1 (" "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md"
grep -n "^### Stage 2$" -A 2 "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md"
ls "$D/stage2_days.json" "$D/SPY.csv" "$D/^VIX.csv"
git -C "$W" log --oneline main..HEAD | head -20
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py
python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_stage2_days.py
```

Expected: a gate 1 line saying go on; `### Stage 2` followed by `Pending V222-8.`;
the three files; the V222-7, V222-7b and V222-7c commits; both test files green.
Anything else: stop and report.

- [ ] **Step 2: Freeze the day list beside the fixtures**

```bash
mkdir -p "$W/tests/fixtures/shock_replay_v222"
cp "$D/stage2_days.json" "$W/tests/fixtures/shock_replay_v222/days.json"
cmp "$D/stage2_days.json" "$W/tests/fixtures/shock_replay_v222/days.json" && echo identical
python -c "import json; d = json.load(open(r'$W/tests/fixtures/shock_replay_v222/days.json', encoding='utf-8')); print(d['cell'], len(d['shock']), len(d['quiet']), len(d['near_miss']))"
git -C "$W" add tests/fixtures/shock_replay_v222/days.json
git -C "$W" commit -m "data(v222): the frozen Stage 2 day list beside its fixtures"
```

Expected: `identical`; the cell equals the Stage 1 winner in Results; `8 4 4`.

- [ ] **Step 3: Write the builder's day file**

```bash
python "$W/scripts/data/shock_stage2_days.py" --stage2-json "$W/tests/fixtures/shock_replay_v222/days.json" --spy "$D/SPY.csv" --vix "$D/^VIX.csv" --out "$D/stage2_info.json"
```

Expected: `wrote .../stage2_info.json: N day(s) added, N in all`, N ≤ 16 (main
picks that are A1 fixture days are reused, not built). Exit 2: stop and report
the message.

- [ ] **Step 4: Build the fixtures (background)**

Alpaca keys come from the main tree's `.env` (config's `load_dotenv` fallback
walks up from the worktree); never print, echo or log them. Run with
`run_in_background`:

```bash
python "$W/scripts/data/build_shock_replay_fixture.py" --validation-days "$D/stage2_info.json" --out-dir "$W/tests/fixtures/shock_replay_v222" --cache-dir "$M/market_data/shock_replay_v222" > "$D/build.log" 2>&1
```

Expected: progress lines `[i/N pct%] <iso> <class> alpaca|unbuildable <n> steps`
in `build.log`, no traceback. Exit 2 with `alpaca keys unavailable`: stop and
report (nothing was written). Any other traceback: rerun the same command
(finished days and cached tickers are skipped). A day that raises on three
consecutive runs is recorded, never skipped:

```bash
python "$W/scripts/data/build_shock_replay_fixture.py" --validation-days "$D/stage2_info.json" --out-dir "$W/tests/fixtures/shock_replay_v222" --unbuildable <iso> --reason "<exception class>: <message>"
```

Do not open the fixtures, compute breadth or replay them by hand.

- [ ] **Step 5: Run Stage 2 until complete**

```bash
python "$W/scripts/backtest/shock_index_intraday.py" --days-json "$W/tests/fixtures/shock_replay_v222/days.json" --v222-dir "$W/tests/fixtures/shock_replay_v222" --a1-dir "$W/tests/fixtures/shock_replay" --out-json "$D/stage2.json" --out-md "$D/stage2.md"; echo "exit $?"
```

- `exit 3` (`verdict INCOMPLETE; build next: <isos>`): an unbuildable,
  synthetic or no-VIX pick moved its slot to a reserve without a fixture yet.
  Add the named days and build them, then rerun this step:

  ```bash
  python "$W/scripts/data/shock_stage2_days.py" --stage2-json "$W/tests/fixtures/shock_replay_v222/days.json" --spy "$D/SPY.csv" --vix "$D/^VIX.csv" --out "$D/stage2_info.json" --only <isos>
  ```

  then the Step 4 build command again (it skips finished days).
- `exit 0`: the run is complete; it printed `verdict PASS` or `verdict NO-LIFT`.
  This is the one Stage 2 result. Exhausted slots (every candidate skipped) are
  already scored against the cell.
- `exit 2`: stop and report the `bad input` message (an A1 mismatch means the
  replica no longer reproduces A1's recorded row: never adjust anything to make
  it match).

- [ ] **Step 6: Commit the fixtures, the committed-fixture test and the routing**

Append to `tests/backtest_scripts/test_shock_index_intraday.py`, replacing
`<VERDICT>` with the verdict Step 5 printed (`PASS` or `NO-LIFT`; it pins the
one run, it is not a target):

```python
# --- V222-8: the committed Stage 2 fixtures ---------------------------------

V222_DIR = ROOT / "tests" / "fixtures" / "shock_replay_v222"
RECORDED_VERDICT = "<VERDICT>"          # V222-8 Step 5, Results § Stage 2


def test_the_committed_stage2_fixtures_match_the_frozen_day_list():
    days = json.loads((V222_DIR / "days.json").read_text(encoding="utf-8"))
    assert (len(days["shock"]), len(days["quiet"]), len(days["near_miss"])) == (8, 4, 4)
    assert len(days["quiet_reserve"]) == 4 and len(days["a1_shock"]) == 6
    assert sum(map(len, days["a1_negative"].values())) == 20
    reused = {*days["a1_shock"], *(d for ds in days["a1_negative"].values() for d in ds)}
    listed = set(sii._listed(days))
    for path in sorted(V222_DIR.glob("*.json.gz")):
        iso, fx = path.name[:10], _read(path)
        assert iso in listed and iso not in reused, iso
        assert fx["session_date"] == iso and fx["source"] in ("alpaca", "unbuildable")
        assert fx["class"] in ("shock", "quiet", "near_miss") and "spy_daily" in fx


def test_the_stage2_run_reproduces_its_recorded_verdict():
    days = json.loads((V222_DIR / "days.json").read_text(encoding="utf-8"))
    result = sii.evaluate(days, sii.load_fixtures(days, V222_DIR, A1_DIR))
    assert result["complete"] is True and result["cell"] == days["cell"]
    assert result["verdict"] == RECORDED_VERDICT
```

In `scripts/dev/select_tests.py`, below the V222-6d rows, add:

```python
    # v222 V222-8: the Stage 2 fixtures and their frozen day list.
    ("tests/fixtures/shock_replay_v222/",
     ("tests/backtest_scripts/test_shock_index_intraday.py",)),
```

```bash
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_intraday.py
python "$W/scripts/dev/testrun.py" file tests/dev/test_select_tests.py
git -C "$W" add tests/fixtures/shock_replay_v222/
git -C "$W" commit -m "data(v222): Stage 2 fixtures -- <a> alpaca, <u> unbuildable"
git -C "$W" add tests/backtest_scripts/test_shock_index_intraday.py scripts/dev/select_tests.py
git -C "$W" commit -m "test(v222): pin the committed Stage 2 fixtures and the recorded verdict"
```

Expected: both green (fill `<a>`/`<u>` from `build.log`). `git -C "$W" status
--short` is clean; `git check-ignore "$M/market_data/shock_replay_v222"` prints the path.

- [ ] **Step 7: Write Results § Stage 2 and commit on `main`**

The spec stays under 1500 lines: Results take the summary and the per-step
tables of the 8 counted shock days; the tables of every other day stay in
`data/v222/stage2.md`, reproducible from the committed fixtures with the
Step 5 command.

```bash
python - "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md" "$D/stage2.md" <<'PYEOF'
"""v222 V222-8: splice the Stage 2 report into the spec's Results."""
import re
import sys
from pathlib import Path

spec, report = Path(sys.argv[1]), Path(sys.argv[2]).read_text(encoding="utf-8")
summary, _, steps = report.partition("## Per-step tables")
counted = [block for block in re.split(r"(?m)^(?=### )", steps) if block.startswith("### ")
           and "(shock)" in block.splitlines()[0]]
tables = "".join("#" + block for block in counted)              # ### -> #### inside Results
body = (summary.rstrip() + "\n\n<details><summary>Per-step tables, counted shock days"
        "</summary>\n\n" + tables.rstrip() + "\n\n</details>\n\nPer-step tables of every "
        "other day: `data/v222/stage2.md` (main tree, gitignored), reproducible from the "
        "committed fixtures (`tests/fixtures/shock_replay_v222/`) with "
        "`scripts/backtest/shock_index_intraday.py`.\n")
doc = spec.read_text(encoding="utf-8")
marker = "### Stage 2\n\nPending V222-8.\n"
assert doc.count(marker) == 1, "Results § Stage 2 is not pending"
spec.write_text(doc.replace(marker, "### Stage 2\n\n" + body), encoding="utf-8")
PYEOF
wc -l "$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md"
git -C "$M" add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C "$M" commit -m "docs(v222): results -- Stage 2 (verdict <PASS|NO-LIFT>)"
```

Expected: under 1500 lines. At 1500 or more, remove the `<details>` block
before the commit (the summary stays, the pointer to `stage2.md` stays).

- [ ] **Step 8: Gate 2 (partner, `AskUserQuestion`, one question, recommended option first)**

Ask exactly one of:

- **PASS:** "Stage 2 passed all five gates for k = <k>, v = <v> (Results § Stage 2: survival <n>/8, quiet <n>/4, near-miss <n>/4, no added A1 false fire, lead <n>/8). Freeze this cell and go on to the detector (V222-9)?" Options: **"Freeze the cell and go on (Recommended)"**: it becomes `FROZEN_K`/`FROZEN_V` for V222-12..V222-14; **"Hold the plan open while I read Results"**.
- **NO-LIFT:** "Stage 2 failed <the failed gates> for k = <k>, v = <v>: NO-LIFT (Results § Stage 2). Close v222 to `no-lift/`?" Options: **"Close as NO-LIFT (Recommended)"**: nothing ships; **"Hold the plan open while I read Results"**.

No option re-runs Stage 2, swaps a day, tries a neighbour cell or changes a gate.
Append under Results § Stage 2 `Gate 2 (<date>): <answer>.` and, on a freeze,
`**Frozen cell: FROZEN_K = <k>, FROZEN_V = <v>.**`; commit on `main`
(`docs(v222): results -- gate 2`). Freeze: go on to Part 4 (V222-9..V222-11).
NO-LIFT: the plan stops; the controller closes it with `/close-out` to
`no-lift/` and nothing is deployed.

```bash
git -C "$M" status --short
```

Expected: nothing of v222 beyond plan files the controller has open.

