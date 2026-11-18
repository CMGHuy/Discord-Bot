# v234, Part 3 — `screen_idea` on the v2 null, the v2 placebo acceptance and the fifth clause

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V234-8" -A 400 <this file>`).

**Spec:** [2026-11-16-v230-screen-v2-ladder-additive-gate-design.md](../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md) (A1 under `v2`: acceptance and the planted edge; A2 "What a v2 delta means"; A3 the fifth clause; A4 instrument and ids; Found while briefing: `INSTRUMENTS`, one BH family, descriptive blocks)
**Index:** [2026-11-17-v234-screen-v2-null_0-index.md](2026-11-17-v234-screen-v2-null_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there; every task below obeys them.
**Tasks:** V234-7, V234-7b, V234-8, V234-9

What this part builds: V234-7 names the `screen-v2` instrument and writes
the v2 report blocks in a new `screen/v2_report.py`. V234-7b makes
`screen_idea.py` run the v2 null (`run_v2` behind a `TickerScreen` adapter),
prints the null version, scope and v2 blocks, and pins the pre-v230 script
tests to v1 through one fixture. V234-8 adds the v2 runner and the planted
check to the placebo CLI and runs stop gate 2. V234-9 adds the fifth clause
to `verdict.py` and makes the context diagnostics' q one ledger-wide family.

**Runs only if V230-5 recorded `BIAS`** (plan v230's index `## Handoff`);
V234-9 runs only if V234-8 recorded `ACCEPT` (this plan's index `## Handoff`).

**Contracts this part adds beyond the ledger rows** (Part 4, V234-10..V234-12, relies on them):

- `screen_idea._run_info(args, q)` adds `"null": NULL_VERSION` and
  `"instrument": instrument()` to the run dict; `_render_head` reads both with
  v1 defaults (`run.get("null", "v1")`, `run.get("instrument", INSTRUMENT)`),
  so a run dict without them (`long_golden.py`) renders the v1 head byte for byte.
- `screen_idea._run_screens(args, ...)` dispatches on `NULL_VERSION` at call
  time; under v2 it skips `with_shock_blocks`, adds `summary["v2"]`
  (`_v2_blocks`) and, from V234-9, calls
  `with_event_clause(summary, idea, gating=not getattr(args, "rescreen_v1", False))`.
  V234-10 only has to add the `--rescreen-v1` flag for the fifth clause to turn
  reported-only.
- `screen_idea.SECTOR_MAP = Path(config.DATA_DIR) / "universe" / "sp500_pit.json"`
  (monkeypatched in tests).
- Placebo: `screen_placebo.PLANTED_JSON = "placebo-planted.json"` in
  `--json-dir`, `{"base": "<gbm label>", "value": float | None, "cell": Cell.to_dict()}`;
  the planted universe lives at `<work-dir>/universes/planted-<gbm label>/`.
  `main` prints `acceptance: <ACCEPT|STOP|ENLARGE>` as its last line once v2 cells exist.
- V234-9: `summary["event_bound"]` (a `verdict.EventBound`) exists on every v2
  edge run; `render_results` prints it as `## Fifth clause (v230 A3)` right
  after the verdict table, saying "gates this verdict" or "reported only".

# Phase 3 — v2 wiring, stop gate 2, the fifth clause

### Task V234-7: `screen-v2` instrument and the v2 report blocks

**Model:** opus — the report text is what a v2 Δ is read as (spec A2); the instrument tuple is read in order by the admin research API and the ledger CLI, so the edit is append-only.

**Files:**
- Modify: `swingbot/core/backtesting/instrument/stats.py` (`INSTRUMENTS`, ~:126)
- Modify: `tests/backtesting/test_instrument_stats_ledger.py` (:24, the `INSTRUMENTS` pin)
- Create: `swingbot/core/backtesting/screen/v2_report.py`
- Create: `tests/backtesting/screen/test_v2_report.py`

**Interfaces:**
- Consumes: nothing from earlier v234 tasks (pure functions over event-row dicts; the row keys `ticker`, `entry_date`, `r_event`, `r_null`, `cost_event`, `cost_null` are V234-6's `V2Ticker.events` shape).
- Produces: `"screen-v2"` as the last member of `stats.INSTRUMENTS`; `v2_report.REGIMES`, `REST = "rest"`, `OMITTED_V2_BLOCKS: tuple[tuple[str, str], ...]`, `MEANING: dict[str, str]` (keys `"ticker"`, `"market"`), `LOOKAHEAD: str`, `load_sectors(path) -> dict[str, str] | None`, `v2_summary(events, *, scope, sectors) -> dict` (keys `scope`, `cost`, `regimes`, `sectors`), `render_v2(block) -> list[str]`. V234-7b calls `load_sectors`, `v2_summary` and `render_v2`.

Index Decisions this task implements: `restricted`, `stressed`, `repriced`, `shock` and `control` are omitted under v2 and listed in every v2 doc (`OMITTED_V2_BLOCKS`). The blocks are descriptive and never gate.

- [ ] **Step 1: `screen-v2` joins `stats.INSTRUMENTS`**

In `tests/backtesting/test_instrument_stats_ledger.py:24` change the pin to:

```python
    assert stats.INSTRUMENTS == ("v1", "v2", "screen-v1", "v3", "screen-v2")
```

Run `python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py` — FAIL on that line. In `swingbot/core/backtesting/instrument/stats.py` append `"screen-v2"` as the last member of `INSTRUMENTS` (append only: the admin research API and `preregistration_ledger.py --instrument` read the tuple in order). Re-run: PASS. Also run `python scripts/dev/testrun.py file tests/admin/test_api_v1_research.py` (it compares against `list(stats.INSTRUMENTS)`): PASS.

```bash
git add swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_ledger.py
git commit -m "feat(v234): screen-v2 joins the ledger instruments"
```

- [ ] **Step 2: Write the failing `v2_report` tests**

Create `tests/backtesting/screen/test_v2_report.py`:

```python
"""v230 A2: what a v2 Δ means -- cost, regime and sector blocks, never gating."""
import json

import pytest

from swingbot.core.backtesting.screen import v2_report


def _row(day, ticker="AAA", r_event=0.2, r_null=0.1, cost_event=0.05, cost_null=0.04):
    return {"ticker": ticker, "entry_date": day, "r_event": r_event, "r_null": r_null,
            "cost_event": cost_event, "cost_null": cost_null}


@pytest.mark.parametrize("day, regime", [
    ("2011-01-03", "2011–2017"), ("2017-12-29", "2011–2017"), ("2018-09-28", "rest"),
    ("2018-10-01", "2018 Q4"), ("2018-12-31", "2018 Q4"), ("2019-01-02", "rest")])
def test_each_entry_date_falls_in_one_regime(day, regime):
    block = v2_report.v2_summary([_row(day)], scope="ticker", sectors=None)
    assert block["regimes"][regime] == (1, pytest.approx(0.2), pytest.approx(0.1))
    assert sum(n for n, _, _ in block["regimes"].values()) == 1
    assert list(block["regimes"]) == ["2011–2017", "2018 Q4", "rest"]


def test_mean_costs_and_the_sector_mix_of_both_arms():
    rows = [_row("2012-01-03", "AAA", 0.4, 0.0, 0.06, 0.02),
            _row("2012-01-04", "BBB", 0.0, 0.2, 0.04, 0.04), _row("2012-01-05", "CCC")]
    block = v2_report.v2_summary(rows, scope="market", sectors={"AAA": "Tech", "BBB": "Tech"})
    assert block["cost"]["event"] == pytest.approx(0.05)
    assert block["cost"]["null"] == pytest.approx(0.1 / 3)
    assert block["sectors"] == {"Tech": (2, pytest.approx(0.2), pytest.approx(0.1)),
                                "unmapped": (1, pytest.approx(0.2), pytest.approx(0.1))}
    assert block["scope"] == "market"


def test_an_empty_book_and_no_sector_map_render_as_such():
    block = v2_report.v2_summary([], scope="ticker", sectors=None)
    assert block["cost"] == {"event": None, "null": None} and block["sectors"] is None
    text = "\n".join(v2_report.render_v2(block))
    assert "**Sector mix:** omitted" in text and "| rest | 0 | — | — |" in text


def test_load_sectors_drops_unknown_and_missing_sectors(tmp_path):
    path = tmp_path / "pit.json"
    path.write_text(json.dumps([{"symbol": "A", "sector": "Health Care"},
                                {"symbol": "AAL", "sector": "Unknown"}, {"symbol": "X"}]),
                    encoding="utf-8")
    assert v2_report.load_sectors(path) == {"A": "Health Care"}
    assert v2_report.load_sectors(tmp_path / "missing.json") is None


def test_render_states_the_meaning_and_every_omitted_block():
    block = v2_report.v2_summary([_row("2012-01-03")], scope="ticker", sectors={"AAA": "Tech"})
    text = "\n".join(v2_report.render_v2(block))
    assert v2_report.MEANING["ticker"] in text and v2_report.LOOKAHEAD in text
    assert {n for n, _ in v2_report.OMITTED_V2_BLOCKS} == {
        "restricted", "stressed", "repriced", "shock", "control"}
    assert all(f"`{name}`" in text for name, _ in v2_report.OMITTED_V2_BLOCKS)
    assert "| Tech | 1 | +0.2000 | +0.1000 |" in text
    assert set(v2_report.MEANING) == {"ticker", "market"}
```

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_v2_report.py`
Expected: FAIL — `ImportError: cannot import name 'v2_report'`.

- [ ] **Step 3: Write `v2_report.py`**

Create `swingbot/core/backtesting/screen/v2_report.py`:

```python
"""v230 A2: what a v2 Δ means, and the v2 descriptive blocks (mean cost per
arm, per-regime means, sector mix). Printed in every v2 results doc; never gating."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

#: (label, first (year, month), last (year, month)); any other entry is REST.
REGIMES = (("2011–2017", (2011, 1), (2017, 12)), ("2018 Q4", (2018, 10), (2018, 12)))
REST = "rest"

#: v1 blocks that re-read the event ticker's own null draw; v2 has none of them.
OMITTED_V2_BLOCKS: tuple[tuple[str, str], ...] = (
    ("restricted", "the v174 null restricted off shock windows redraws from the event "
                   "ticker's own bars"),
    ("stressed", "the v163 2 x slippage trail book re-races the v1 null groups"),
    ("repriced", "the v182 3 x slippage level book re-races the v1 null groups"),
    ("shock", "the v211 shock-day null draws from the event ticker's own SHOCK days"),
    ("control", "the v182 trend-only control book needs a v2 draw of its own, not built "
                "in v230"))

MEANING: dict[str, str] = {
    "ticker": ("Each event's null is K bars from other tickers on the event's own date, in "
               "the same trend state and the same ATR% tercile of that date's eligible "
               "cross-section. Market timing is removed: a pass says the trigger picks "
               "better names than its peers on that day, a different question from v1's "
               "same-ticker, same-month null."),
    "market": ("The trigger fires for every member on one date, so each event's null is the "
               "same ticker in the same trend state on dates in the 252 sessions before the "
               "event, none within the time cap of any of its event dates: a pass says the "
               "event date beats that ticker's own recent dates. No null bar postdates its "
               "event.")}

LOOKAHEAD = ("Every pool value at a date reads that ticker's bars up to that date only, "
             "except race completeness (the race must finish inside the ticker's data), "
             "which reads the data end exactly as v1 does.")


def load_sectors(path) -> dict[str, str] | None:
    """{symbol: sector} from a list of {symbol, sector}; "Unknown" and missing
    sectors are left out. None when the file does not exist."""
    path = Path(path)
    if not path.is_file():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["symbol"]: r["sector"] for r in rows
            if r.get("sector") and r["sector"] != "Unknown"}


def _regime(day: str) -> str:
    key = (int(day[:4]), int(day[5:7]))
    for label, first, last in REGIMES:
        if first <= key <= last:
            return label
    return REST


def _mean(rows, key: str) -> float | None:
    return float(np.mean([r[key] for r in rows])) if rows else None


def _arms(rows) -> tuple:
    return len(rows), _mean(rows, "r_event"), _mean(rows, "r_null")


def _grouped(events, key) -> dict[str, list]:
    groups: dict[str, list] = {}
    for row in events:
        groups.setdefault(key(row), []).append(row)
    return groups


def v2_summary(events, *, scope: str, sectors: dict[str, str] | None) -> dict:
    """``events`` are the kept event rows (``r_event``, ``r_null``, ``cost_event``,
    ``cost_null``, ``entry_date``, ``ticker``). Per regime and sector: (N, mean
    R event, mean R null); the sector is the event ticker's, "unmapped" if absent."""
    by_regime = _grouped(events, lambda r: _regime(r["entry_date"]))
    labels = [label for label, _, _ in REGIMES] + [REST]
    sector_mix = None
    if sectors is not None:
        by_sector = _grouped(events, lambda r: sectors.get(r["ticker"], "unmapped"))
        sector_mix = {s: _arms(rows) for s, rows in sorted(by_sector.items())}
    return {"scope": scope,
            "cost": {"event": _mean(events, "cost_event"), "null": _mean(events, "cost_null")},
            "regimes": {label: _arms(by_regime.get(label, [])) for label in labels},
            "sectors": sector_mix}


def _f(x) -> str:
    return "—" if x is None else f"{x:+.4f}"


def _table(title: str, rows: dict) -> list[str]:
    return [title, "", "| | N | mean R event | mean R null |", "|---|---:|---:|---:|",
            *(f"| {k} | {n} | {_f(e)} | {_f(nl)} |" for k, (n, e, nl) in rows.items()), ""]


def render_v2(block: dict) -> list[str]:
    cost = block["cost"]
    lines = ["## Null v2 (v230): what this Δ means", "", MEANING[block["scope"]], "",
             LOOKAHEAD, "",
             f"**Mean cost in R** (gross R − net R): event arm {_f(cost['event'])}, null arm "
             f"{_f(cost['null'])}.", "",
             *_table("**Per regime** (by entry date):", block["regimes"])]
    if block["sectors"] is None:
        lines += ["**Sector mix:** omitted — no sector map was found.", ""]
    else:
        lines += _table("**Sector mix** (the event ticker's sector; `unmapped` = not in the "
                        "map; the null column is those events' nulls):", block["sectors"])
    return lines + ["**Omitted under v2** (each re-reads the v1 same-ticker null draw; none "
                    "gates):", "", *(f"- `{name}`: {why}." for name, why in OMITTED_V2_BLOCKS)]
```

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_v2_report.py` — PASS. Run `python scripts/dev/testrun.py file tests/backtesting/screen/test_import_guard.py` — PASS.

```bash
git add swingbot/core/backtesting/screen/v2_report.py tests/backtesting/screen/test_v2_report.py
git commit -m "feat(v234): v2 report blocks -- meaning, cost, regime and sector mix"
```

### Task V234-7b: `screen_idea` v2 wiring and the v1 test pins

**Model:** opus — moves the screen's main path to v2 while every v1 script test and the long golden stay byte-identical.

**Files:**
- Modify: `scripts/backtest/screen_idea.py` (imports, constants, `_render_head`, `render_results`, `ledger_row`, `_run_info`, `_run_screens`, `main`; new functions after `screen_universe`)
- Create: `tests/backtest_scripts/conftest.py`
- Create: `tests/backtest_scripts/test_screen_v2_wiring.py`
- Modify (one `pytestmark` line each): `tests/backtest_scripts/test_screen_avoid_mode.py`, `test_screen_checkpoint.py`, `test_screen_context_runner.py`, `test_screen_idea.py`, `test_screen_level_context.py`, `test_screen_preflight.py`, `test_screen_shock_blocks.py`

**Interfaces:**
- Consumes: V230-1 `Idea.scope`; V230-4 `event_start=`; V234-2 `NullRefusal`; V234-6 `V2Inputs`, `V2Ticker`, `run_v2`, `_ENTRY_OFFSET` and the index's Part 4 contracts; V234-7 `v2_report`, `"screen-v2"`.
- Produces: the ledger row's names, run dict keys `null`/`instrument`, and `_run_screens` / `_v2_blocks`, which V234-9 extends. V234-8 calls `screen_universe_v2`.

Implements the index Decisions on v2 blocks, `--count-only` and a dry run's `--tickers`.

- [ ] **Step 1: Pin the pre-v230 script tests to v1, and write the failing wiring tests**

Create `tests/backtest_scripts/conftest.py`:

```python
"""Shared fixtures for tests/backtest_scripts/."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))


@pytest.fixture
def screen_null_v1(monkeypatch):
    """v230: screen_idea on the frozen v1 null -- the pre-v230 tests pin v1 output."""
    import screen_idea
    monkeypatch.setattr(screen_idea, "NULL_VERSION", "v1")
```

In each of the seven modules under **Files**, add directly after the import block (and `import pytest` to `test_screen_preflight.py`, which lacks it):

```python
pytestmark = pytest.mark.usefixtures("screen_null_v1")   # v230: these pin the v1 null
```

Create `tests/backtest_scripts/test_screen_v2_wiring.py`:

```python
"""v230 A2/A4: screen_idea runs the v2 null -- the screen-v2 instrument, the null
version and scope in the head, a starved pool refused with exit 2, the adapter."""
import functools
import json
from collections import Counter
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import screen_idea  # on sys.path via conftest.py

from swingbot.core.backtesting.screen import screen_v2, verdict
from swingbot.core.backtesting.screen.errors import IdeaError
from swingbot.core.backtesting.screen.ideas import IDEAS, Idea
from tests.backtesting.screen.helpers import random_walk

IDEA = IDEAS["turn_of_month"]       # market scope: three tickers are a whole pool


def _quiet(*_args, **_kwargs):
    return None


@pytest.fixture(autouse=True)
def fast_bootstrap(monkeypatch):
    monkeypatch.setattr(screen_idea.verdict, "decide",
                        functools.partial(verdict.decide, n_resamples=500))


def _universe(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    for seed, ticker in enumerate(("AAA", "BBB", "DDD"), start=1):
        random_walk(2700, seed=seed).rename_axis("Date").to_csv(cache / f"{ticker}.csv")
    membership = tmp_path / "membership.csv"
    membership.write_text("ticker,start_date,end_date\n" + "".join(
        f"{t},2000-01-01,\n" for t in ("AAA", "BBB", "DDD")), encoding="utf-8")
    return cache, screen_idea.load_universe(cache, membership)


def _argv(tmp_path, cache, idea, *extra):
    return ["--idea", idea, "--cache-dir", str(cache),
            "--membership", str(tmp_path / "membership.csv"),
            "--ledger", str(tmp_path / "ledger.jsonl"),
            "--results-dir", str(tmp_path / "results"), "--date", "2026-11-20",
            "--dry-run", *extra]


def test_the_entry_offsets_match_the_v2_orchestration():
    assert screen_v2._ENTRY_OFFSET == screen_idea._ENTRY_OFFSET


def test_v2_is_the_default_and_names_its_instrument(monkeypatch):
    assert screen_idea.NULL_VERSION == "v2" and screen_idea.instrument() == "screen-v2"
    row = screen_idea.ledger_row(IDEA, verdict.decide([]), "r.md", "2026-11-20")
    assert row["instrument"] == "screen-v2"
    monkeypatch.setattr(screen_idea, "NULL_VERSION", "v1")
    assert screen_idea.instrument() == screen_idea.INSTRUMENT == "screen-v1"


def test_screen_universe_v2_adapts_every_event_ticker(tmp_path):
    cache, universe = _universe(tmp_path)
    screens, skipped = screen_idea.screen_universe_v2(IDEA, universe, cache, out=_quiet)
    assert [s.ticker for s in screens] == ["AAA", "BBB", "DDD"] and not skipped
    s = screens[0]
    assert isinstance(s, screen_idea.TickerScreen) and len(s.rank) and s.events
    assert {"cost_event", "cost_null"} <= set(s.events[0])
    assert (s.restricted, s.stressed, s.repriced, s.control, s.shock, s.avoid) == (None,) * 6
    summary = screen_idea.summarise(screens, skipped)
    assert summary["verdict"].n == sum(len(x.events) for x in screens)


def test_tickers_restrict_the_event_book_only(tmp_path):
    cache, universe = _universe(tmp_path)
    screens, _ = screen_idea.screen_universe_v2(IDEA, universe, cache, tickers=["BBB", "ZZZ"],
                                                out=_quiet, checkpoint_dir=tmp_path / "ck")
    assert [s.ticker for s in screens] == ["BBB"]
    saved = json.loads((tmp_path / "ck" / "panel" / "manifest.json").read_text(encoding="utf-8"))
    assert (saved["null_version"], saved["scope"]) == ("v2", "market")


def test_a_dry_run_prints_the_null_version_scope_and_the_v2_blocks(tmp_path, monkeypatch,
                                                                    capsys):
    cache, _ = _universe(tmp_path)
    sectors = tmp_path / "pit.json"
    sectors.write_text(json.dumps([{"symbol": "AAA", "sector": "Tech"}]), encoding="utf-8")
    monkeypatch.setattr(screen_idea, "SECTOR_MAP", sectors)
    assert screen_idea.main(_argv(tmp_path, cache, "turn_of_month")) == 0
    text = capsys.readouterr().out
    for needle in ("(instrument `screen-v2`)", "**Null:** v2, scope `market`",
                   "## Null v2 (v230)", "same ticker in the same trend state", "| Tech |",
                   "- `shock`:"):
        assert needle in text, needle
    assert text.index("## Forward drift") < text.index("## Null v2")


def test_the_v1_fixture_keeps_the_v1_head(tmp_path, capsys, screen_null_v1):
    cache, _ = _universe(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, "turn_of_month")) == 0
    text = capsys.readouterr().out
    assert "(instrument `screen-v1`)" in text and "**Null:**" not in text
    assert "## Null v2" not in text


def test_a_starved_ticker_scope_pool_is_refused_with_exit_2(tmp_path, capsys):
    cache, _ = _universe(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, "uptrend_pullback")) == 2
    assert "refused: SCOPE_MISMATCH:" in capsys.readouterr().err


def _v2_ticker(**kw):
    base = dict(ticker="AAA", counters=Counter({"dropped_no_match": 1, "control_below_floor": 2}),
                events=[{"ticker": "AAA", "entry_date": "2012-03-02"},
                        {"ticker": "AAA", "entry_date": "2012-04-02"}],
                null_outcomes=Counter({"stop": 3}), excess={5: [0.1]},
                extras={"rank": pd.DataFrame(), "overlap": None,
                        "avoid": {"excluded": 7, "population": 70,
                                  "overnight_dates": ["2012-03-02", "2013-01-02"]}},
                null_timeout_r=[], null_slots=40, null_unfilled=0, depths=None,
                avoid_control=[{"ticker": "AAA"}])
    return screen_v2.V2Ticker(**{**base, **kw})


def test_the_adapter_carries_the_avoid_counts_and_the_overlap():
    s = screen_idea._v2_screen(_v2_ticker())
    assert s.avoid == {"control": [{"ticker": "AAA"}], "below_floor": 2, "kept": 2,
                       "excluded": 7, "population": 70, "overnight": 1}
    assert s.null_slots == 40 and s.counters["dropped_no_match"] == 1
    overlap = {"own": 1, "other": 2, "both": 0}
    plain = screen_idea._v2_screen(_v2_ticker(extras={"rank": pd.DataFrame(), "overlap": overlap},
                                              avoid_control=None))
    assert plain.avoid is None and plain.overlap == overlap


def test_collect_counts_empty_frames_and_idea_errors():
    found = [_v2_ticker(), _v2_ticker(ticker="BBB", extras={"idea_error": "bad bar"})]
    screens, skipped = screen_idea._v2_collect(found, 3)
    assert [s.ticker for s in screens] == ["AAA"]
    assert skipped == Counter({"empty_frame": 1, "idea_error": 1, "idea_error:BBB": 1})


def test_avoid_extras_read_the_pre_draw_book():
    df = random_walk(300, seed=4)
    n = len(df)
    bottom = np.full(n, -np.inf)
    bottom[20] = np.inf                               # bar 10 reaches its bottom, bar 20 never
    ctx = {"member": np.ones(n, bool), "warm": np.ones(n, bool),
           "condition": np.arange(n) < 5, "bottom": bottom,
           "book": SimpleNamespace(event_pos=np.array([10, 20]))}
    assert screen_idea._avoid_extras(df, ctx) == {
        "excluded": 5, "population": n, "overnight_dates": [df.index[11].strftime("%Y-%m-%d")]}


def _broken_states(df):
    raise IdeaError("bad bar")


def test_an_avoid_idea_error_leaves_the_ticker_out_of_both_arms(tmp_path):
    _, universe = _universe(tmp_path)
    idea = Idea(name="av", events=lambda df: df["Close"] > 0, time_cap_bars=10, mode="avoid",
                states=_broken_states)
    df = random_walk(300, seed=1)
    ctx = screen_idea._v2_context(idea, universe, None, screen_idea.EVENT_START, _quiet)("AAA", df)
    assert "bad bar" in ctx["idea_error"]
    assert not ctx["member"].any() and not ctx["raw"].any()
    extras = screen_idea._v2_extras(idea)("AAA", df, {**ctx, "book": None})
    assert extras == {"idea_error": ctx["idea_error"]}
```

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_v2_wiring.py`
Expected: FAIL — `AttributeError: module 'screen_idea' has no attribute 'NULL_VERSION'` (and the other new names).

- [ ] **Step 2: Wire `screen_idea.py`**

Imports (beside the other screen imports):

```python
from swingbot.core.backtesting.screen import null_v2, screen_v2, v2_report  # noqa: E402
```

Directly after `INSTRUMENT = "screen-v1"`:

```python
#: v230 A4: the screen runs the v2 null; "v1" only through the tests' screen_null_v1 fixture.
NULL_VERSION = "v2"
INSTRUMENT_V2 = "screen-v2"
SECTOR_MAP = Path(config.DATA_DIR) / "universe" / "sp500_pit.json"


def instrument() -> str:
    """The ledger instrument of this run's null (v230 A4)."""
    return INSTRUMENT_V2 if NULL_VERSION == "v2" else INSTRUMENT
```

After `screen_universe` (it stays the v1 path, unchanged):

```python
def _dead_context(df: pd.DataFrame, context, error: str) -> dict:
    """v230: an avoid ticker whose states(df) raised -- no event, never in a pool."""
    off = np.zeros(len(df), dtype=bool)
    return {"raw": off, "member": off, "warm": off, "atr": indicators.atr(df),
            "trend": null.trend_state(df, indicators.sma(df["Close"], 200)), "levels": None,
            "context": context, "control_condition": off, "condition": off,
            "bottom": np.full(len(df), np.nan), "idea_error": error}


def _v2_context(idea: Idea, universe: Universe, context, event_start: str, out):
    """The v2 per-ticker context: ticker_context, an avoid idea error caught as v1 does."""
    def build(name: str, df: pd.DataFrame) -> dict:
        try:
            return ticker_context(idea, df, universe.intervals.get(name, []), context,
                                  event_start=event_start)
        except _guarded_errors(idea) as exc:
            out(f"[{idea.name}] {name}: idea error: {exc}", flush=True)
            return _dead_context(df, context, str(exc))
    return build


def _avoid_extras(df: pd.DataFrame, ctx: dict) -> dict:
    """v214 read-outs from the pre-draw book; overnight is kept to the drawn events later."""
    population = ctx["member"] & ctx["warm"]
    pos = np.asarray(ctx["book"].event_pos, dtype=int)
    opens = df["Open"].to_numpy(dtype=float)
    hit = pos[opens[pos + 1] >= ctx["bottom"][pos]] if len(pos) else pos
    return {"excluded": int((ctx["condition"] & population).sum()),
            "population": int(population.sum()),
            "overnight_dates": [df.index[p + 1].strftime("%Y-%m-%d") for p in hit]}


def _v2_extras(idea: Idea):
    """The event-side blocks that read no null: rank, overlap, the avoid read-outs."""
    def extras(name: str, df: pd.DataFrame, ctx: dict) -> dict:
        if "idea_error" in ctx:
            return {"idea_error": ctx["idea_error"]}
        fwd = {h: forward.forward_atr(df, ctx["atr"], h, direction=idea.direction)
               for h in forward.HORIZONS}
        out = {"rank": _rank_frame(df.index, ctx["raw"], ctx["member"] & ctx["warm"], fwd),
               "overlap": _overlap(idea, df, ctx)}
        if idea.mode == "avoid":
            out["avoid"] = _avoid_extras(df, ctx)
        return out
    return extras


def _v2_avoid(t) -> dict | None:
    a = t.extras.get("avoid")
    if a is None:
        return None
    overnight = set(a["overnight_dates"])
    return {"control": t.avoid_control or [],
            "below_floor": int(t.counters.get("control_below_floor", 0)),
            "kept": len(t.events), "excluded": a["excluded"], "population": a["population"],
            "overnight": sum(row["entry_date"] in overnight for row in t.events)}


def _v2_screen(t) -> TickerScreen:
    """v230: a screen_v2.V2Ticker as the TickerScreen summarise reads; the v1-null
    blocks stay None (v2_report.OMITTED_V2_BLOCKS)."""
    return TickerScreen(ticker=t.ticker, counters=Counter(t.counters), events=t.events,
                        null_outcomes=t.null_outcomes, excess=t.excess, rank=t.extras["rank"],
                        null_timeout_r=t.null_timeout_r, null_slots=t.null_slots,
                        null_unfilled=t.null_unfilled, depths=t.depths,
                        overlap=t.extras.get("overlap"), avoid=_v2_avoid(t))


def _v2_collect(found, n_events: int) -> tuple[list, Counter]:
    """TickerScreens, with empty frames and idea-error tickers counted as v1 counts them."""
    screens, skipped = [], Counter()
    for t in found:
        if "idea_error" in t.extras:
            skipped["idea_error"] += 1
            skipped[f"idea_error:{t.ticker}"] = 1
        else:
            screens.append(_v2_screen(t))
    if n_events > len(found):
        skipped["empty_frame"] = n_events - len(found)
    return screens, skipped


def screen_universe_v2(idea: Idea, universe: Universe, cache_dir, *,
                       start: str = WINDOW_START, end: str = WINDOW_END, tickers=None,
                       out=print, context: Mapping | None = None,
                       checkpoint_dir: Path | None = None,
                       event_start: str = EVENT_START) -> tuple[list, Counter]:
    """v230 A2: the v2 screen. Every cached member is in the pool (the cross-section);
    ``tickers`` restricts the event book only. Raises null_v2.NullRefusal before any race."""
    context = _universe_context(idea, cache_dir, end, context)
    names = list(universe.cached)
    events = names if tickers is None else [t for t in tickers if t in universe.cached]
    manifest = _checkpoint_manifest(idea, start, end, names, context, universe.intervals)
    if event_start != EVENT_START:
        manifest["event_start"] = event_start
    inputs = screen_v2.V2Inputs(
        load=lambda t: load_frame(Path(cache_dir) / f"{t}.csv", start, end),
        context=_v2_context(idea, universe, context, event_start, out),
        extras=_v2_extras(idea))
    found = screen_v2.run_v2(idea, names, inputs,
                             costs={"slippage_bps": None, "commission": None},
                             checkpoint_dir=checkpoint_dir, manifest=manifest, out=out,
                             event_tickers=None if tickers is None else events)
    return _v2_collect(found, len(events))
```

`_render_head`: the ledger-id line reads `(instrument `{run.get('instrument', INSTRUMENT)}`)` instead of `{INSTRUMENT}`, and `*_null_line(idea, run)` goes between the `""` after that line and the `**Run:**` line. New helper above it:

```python
def _null_line(idea, run) -> list:
    """v230 A4: a v2 doc names its null version and scope; a v1 head is unchanged."""
    if run.get("null", "v1") == "v1":
        return []
    return [f"**Null:** {run['null']}, scope `{idea.scope}`; K = {null.K} per event, floor "
            f"{null.MIN_CANDIDATES}; seed `null_seed(idea + \":v2\", date)` (ticker scope) or "
            "`null_seed(idea + \":v2\", ticker)` (market scope); see \"Null v2\" below.", ""]
```

`render_results`: after `sections += [_render_years(v), _render_drift(summary)]` add:

```python
    if "v2" in summary:
        sections.append(v2_report.render_v2(summary["v2"]))
```

`ledger_row`: `"instrument": instrument(),`. `_run_info` adds `"null": NULL_VERSION, "instrument": instrument()` to the dict it returns.

`_run_screens` and its v2 helper:

```python
def _v2_blocks(summary: dict, idea: Idea) -> dict:
    """v230 A2: the v2 doc's meaning, cost, regime and sector blocks."""
    return {**summary, "v2": v2_report.v2_summary(
        summary["events"], scope=idea.scope, sectors=v2_report.load_sectors(SECTOR_MAP))}


def _run_screens(args, idea: Idea, universe: Universe, data, spy) -> dict:
    """The summary ``main`` publishes (screen, diagnostics, short blocks, v2 blocks)."""
    tickers = args.tickers.split(",") if args.tickers else None
    screen = screen_universe if NULL_VERSION == "v1" else screen_universe_v2
    screens, skipped = screen(idea, universe, args.cache_dir, start=args.start,
                              end=args.end, tickers=tickers,
                              context=None if data is None else data.frames,
                              checkpoint_dir=args.checkpoint_dir)
    summary = with_diagnostics(summarise(screens, skipped, mode=idea.mode), screens, idea,
                               data, end=args.end)
    summary = with_short_blocks(summary, screens, idea, spy)
    if NULL_VERSION == "v1":
        summary = with_shock_blocks(summary, screens, idea)
    else:
        summary = _v2_blocks(summary, idea)
    return with_avoid_blocks(summary, screens, idea)
```

`main`: replace the last two lines (`idea = IDEAS[args.idea]` / `return publish(...)`) with:

```python
    idea = IDEAS[args.idea]
    try:
        summary = _run_screens(args, idea, universe, data, spy)
    except null_v2.NullRefusal as exc:       # v230: SCOPE_MISMATCH / NULL_STARVED, before any race
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    return publish(args, idea, universe, summary, rows, data=data)
```

- [ ] **Step 3: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py suite backtest-scripts
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/testrun.py file tests/backtesting/instrument/test_date_literal_guard.py
python scripts/dev/complexity_gate.py
```

Expected: 0 failed, 0 xfailed (the suite holds the new tests and the seven v1-pinned modules; the golden renders a run dict without `null`). `main` and `render_results` stay under 15.

- [ ] **Step 4: Commit**

The fixture needs `NULL_VERSION`, so the pins ship with the wiring:

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/conftest.py tests/backtest_scripts/test_screen_{avoid_mode,checkpoint,context_runner,idea,level_context,preflight,shock_blocks}.py
git commit -m "feat(v234): screen_idea runs the v2 null; pre-v230 script tests pin v1"
git add tests/backtest_scripts/test_screen_v2_wiring.py
git commit -m "test(v234): v2 wiring -- instrument, head, refusal, adapter"
```

### Task V234-8: Placebo under v2: planted check and acceptance (stop gate 2)

**Model:** opus — the run decides whether the plan continues; refusals, noisy cells and the planted check each have a fixed reading.

**Files:**
- Modify (created by plan v230's V230-4): `scripts/backtest/screen_placebo.py` (imports, `RUNNERS`, `run_cell_v1`, `_run_cells`, `_detail`, `build_parser`, `main`)
- Modify (created by plan v230's V230-4): `tests/backtest_scripts/test_screen_placebo.py`
- Modify (run, rendered by the CLI): `docs/superpowers/results/<D>-v230-null-placebo.md`, where `<D>` is the date V230-5 used
- Create (run): `docs/superpowers/results/v230/placebo-v2.json`, `docs/superpowers/results/v230/placebo-planted.json`
- Modify (run): `docs/superpowers/plans/2026-11-17-v234-screen-v2-null_0-index.md` (`## Handoff` only)

**Interfaces:**
- Consumes: V230-3/3b `placebo` (`plant_universe`, `planted_trigger`, `planted_value`, `cell_from_rows`, `acceptance`, `Cell`); V230-4/4b `screen_placebo` and its test helpers (`_argv`, `_source`, `_write_csv`); V234-2 `NullRefusal(code, detail)`; V234-7b `screen_universe_v2`.
- Produces: `RUNNERS["v2"] = run_cell_v2`; `run_cell_v2(universe_dir, trigger, *, checkpoint_dir) -> list[dict]`; `PLANTED_JSON = "placebo-planted.json"`; `load_planted(json_dir) -> dict | None`; `run_planted(universes, args) -> dict`; flag `--planted`; `acceptance: <ACCEPT|STOP|ENLARGE>` as `main`'s last stdout line once v2 cells exist; a refused cell prints `refused: <label>/<trigger>: <code>: ...` on stderr and `main` exits 2. Gate outcome in the index `## Handoff`: `ACCEPT` (V234-9 runs next), `STOP` (V234-9..12 do not run) or a recorded refusal (partner asked).

**Refusals are record-and-ask** (index `## Handoff`, partner to confirm): a `SCOPE_MISMATCH` / `NULL_STARVED` cell is no cell and no verdict; the run carries on with the other cells, prints every refusal and exits 2; the task records them and asks, never reading a refusal as `STOP` or `ENLARGE`. Expect one: `p_month_turn` races with cap 10, and the market pool keeps only bars more than 10 bars from every month-end, which leaves at most about one bar per month in its 252-session window.

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtest_scripts/test_screen_placebo.py` (add `from swingbot.core.backtesting.screen import null_v2  # noqa: E402` to its imports):

```python
def _fake_rows(delta, *, r_event=0.1, n=320):
    """n weekly events from 2011 with a constant Δ: half-width 0, the rule reads Δ alone."""
    days = pd.bdate_range("2011-01-03", periods=n * 5)[::5]
    return [{"ticker": "G000", "entry_date": d.strftime("%Y-%m-%d"), "r_event": r_event,
             "r_null": r_event - delta} for d in days]


def _fake_v2(deltas, *, gain=0.4, refuse=()):
    """A v2 runner: Δ per trigger, +gain R on the planted universe only."""
    def run(universe_dir, trigger, *, checkpoint_dir):
        if trigger.name in refuse:
            raise null_v2.NullRefusal(null_v2.NULL_STARVED, "9 of 12 event dates starved")
        if trigger.name == "p_high20_planted":
            g = gain if Path(universe_dir).name.startswith("planted-") else 0.0
            return _fake_rows(g, r_event=0.1 + g)
        return _fake_rows(deltas.get(trigger.name, 0.0))
    return run


def _v2_argv(tmp_path, *extra):
    return _argv(tmp_path, "--null", "v2", "--triggers", "p_high20", "p_month_turn", *extra)


def _last_line(capsys):
    return capsys.readouterr().out.strip().splitlines()[-1]


def test_v2_with_the_planted_check_accepts_and_a_restart_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(screen_placebo.RUNNERS, "v2", _fake_v2({}))
    argv = _v2_argv(tmp_path, "--planted")
    assert screen_placebo.main(argv) == 0
    assert _last_line(capsys) == "acceptance: ACCEPT"
    cells = screen_placebo.load_cells(tmp_path / "json" / "placebo-v2.json")
    assert sorted(c.universe for c in cells) == ["gbm-3", "gbm-3", "shuffled-c1", "shuffled-c1"]
    record = screen_placebo.load_planted(tmp_path / "json")
    assert record["base"] == "gbm-3" and record["value"] == pytest.approx(0.4)
    assert (record["cell"]["universe"], record["cell"]["null"]) == ("planted-gbm-3", "v2")
    assert (tmp_path / "work" / "universes" / "planted-gbm-3" / placebo.PLANTED_FILE).is_file()
    doc = (tmp_path / "results" / "2026-11-20-v230-null-placebo.md").read_text(encoding="utf-8")
    for needle in ("## Planted edge", "Verdict: **ACCEPT**", "| planted-gbm-3 | planted | 3 |",
                   "planted on gbm, +0.5 ATR14 over 10 bars"):
        assert needle in doc, needle
    monkeypatch.setitem(screen_placebo.RUNNERS, "v2", lambda *a, **k: pytest.fail("re-ran"))
    assert screen_placebo.main(argv) == 0
    assert _last_line(capsys) == "acceptance: ACCEPT"


def test_a_failing_v2_cell_stops(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(screen_placebo.RUNNERS, "v2", _fake_v2({"p_month_turn": 0.05}))
    assert screen_placebo.main(_v2_argv(tmp_path, "--planted")) == 0
    assert _last_line(capsys) == "acceptance: STOP"


def test_v2_cells_without_a_planted_check_read_enlarge(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(screen_placebo.RUNNERS, "v2", _fake_v2({}))
    assert screen_placebo.main(_v2_argv(tmp_path)) == 0
    assert _last_line(capsys) == "acceptance: ENLARGE"


def test_a_refused_cell_is_recorded_and_the_other_cells_still_run(tmp_path, monkeypatch,
                                                                   capsys):
    monkeypatch.setitem(screen_placebo.RUNNERS, "v2", _fake_v2({}, refuse=("p_month_turn",)))
    assert screen_placebo.main(_v2_argv(tmp_path, "--planted")) == 2
    out, err = capsys.readouterr()
    assert "refused: gbm-3/p_month_turn: NULL_STARVED: 9 of 12" in err
    assert "refused: shuffled-c1/p_month_turn: NULL_STARVED" in err
    assert "acceptance:" not in out
    cells = screen_placebo.load_cells(tmp_path / "json" / "placebo-v2.json")
    assert sorted((c.universe, c.trigger) for c in cells) == [
        ("gbm-3", "p_high20"), ("shuffled-c1", "p_high20")]
    assert screen_placebo.load_planted(tmp_path / "json") is not None


@pytest.mark.parametrize("extra", [("--planted",),
                                   ("--null", "v2", "--planted", "--universes", "shuffled")])
def test_planted_needs_v2_and_the_gbm_universe(tmp_path, capsys, extra):
    assert screen_placebo.main(_argv(tmp_path, *extra)) == 2
    assert "refused: --planted needs" in capsys.readouterr().err


def _long_source(tmp_path):
    """SPY plus three tickers, 1300 sessions: room for a trailing 252-session pool."""
    src = tmp_path / "long"
    src.mkdir()
    for seed, ticker in enumerate(("SPY", "AAA", "BBB", "CCC"), start=1):
        _write_csv(src / f"{ticker}.csv", random_walk(1300, seed=seed))
    return src


def test_run_cell_v2_races_a_market_trigger_and_refuses_a_starved_ticker_pool(tmp_path):
    args = SimpleNamespace(source_cache=_long_source(tmp_path), work_dir=tmp_path / "work",
                           universes=["gbm"], gbm_tickers=3, shuffled_copies=1)
    gbm = screen_placebo.build_universes(args)["gbm-3"]
    rows = screen_placebo.run_cell_v2(gbm, placebo.TRIGGERS["p_market_down"],
                                      checkpoint_dir=tmp_path / "ck")
    assert rows and {"ticker", "entry_date", "r_event", "r_null", "cost_null"} <= set(rows[0])
    assert min(r["entry_date"] for r in rows) >= screen_idea.EVENT_START
    saved = json.loads((tmp_path / "ck" / "panel" / "manifest.json").read_text(encoding="utf-8"))
    assert (saved["null_version"], saved["scope"]) == ("v2", "market")
    with pytest.raises(null_v2.NullRefusal, match="SCOPE_MISMATCH"):     # 2 peers < floor 5
        screen_placebo.run_cell_v2(gbm, placebo.TRIGGERS["p_high20"],
                                   checkpoint_dir=tmp_path / "ck2")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_placebo.py`
Expected: FAIL — `AttributeError: ... 'load_planted'` (and `run_cell_v2`, `--planted`); the V230-4/4b tests still pass.

- [ ] **Step 3: Write the implementation**

In `scripts/backtest/screen_placebo.py`, change the placebo import to `from swingbot.core.backtesting.screen import null_v2, placebo  # noqa: E402` and add `PLANTED_JSON = "placebo-planted.json"` below `DEFAULT_JSON`.

Replace `run_cell_v1` and the `RUNNERS` line with (a behaviour-preserving extraction of `run_cell_v1`'s setup, shared with the v2 runner):

```python
def _cell_setup(universe_dir, trigger):
    """The trigger as an Idea on the universe's own index calendar, and the universe."""
    udir = Path(universe_dir)
    manifest = json.loads((udir / placebo.MANIFEST_FILE).read_text(encoding="utf-8"))
    index = screen_idea.load_context(udir, (), end=screen_idea.WINDOW_END,
                                     context_start=manifest["calendar_start"]).calendar
    universe = screen_idea.load_universe(udir, udir / placebo.MEMBERSHIP_FILE)
    return placebo.placebo_idea(trigger, index), universe


def run_cell_v1(universe_dir, trigger, *, checkpoint_dir) -> list[dict]:
    """One placebo trigger through the v1 screen pipeline; its event rows."""
    idea, universe = _cell_setup(universe_dir, trigger)
    screens, _ = screen_idea.screen_universe(
        idea, universe, Path(universe_dir), start=screen_idea.WINDOW_START,
        end=screen_idea.WINDOW_END, checkpoint_dir=Path(checkpoint_dir),
        event_start=screen_idea.EVENT_START)
    return [row for screen in screens for row in screen.events]


def run_cell_v2(universe_dir, trigger, *, checkpoint_dir) -> list[dict]:
    """One placebo trigger through the v2 screen, every stage checkpointed under
    ``checkpoint_dir``. Raises null_v2.NullRefusal when the pool starves."""
    idea, universe = _cell_setup(universe_dir, trigger)
    screens, _ = screen_idea.screen_universe_v2(
        idea, universe, Path(universe_dir), start=screen_idea.WINDOW_START,
        end=screen_idea.WINDOW_END, checkpoint_dir=Path(checkpoint_dir),
        event_start=screen_idea.EVENT_START)
    return [row for screen in screens for row in screen.events]


RUNNERS: dict[str, Callable] = {"v1": run_cell_v1, "v2": run_cell_v2}
```

Replace `_run_cells` (it now returns the refused cells instead of stopping at the first):

```python
def _run_cells(universes: dict[str, Path], args) -> list[str]:
    path = Path(args.json_dir) / f"placebo-{args.null}.json"
    done = {(c.universe, c.trigger) for c in load_cells(path)}
    todo = [(label, name) for label in universes for name in args.triggers]
    refused: list[str] = []
    for i, (label, name) in enumerate(todo, start=1):
        tag = f"[placebo {args.null}] cell {i}/{len(todo)} {label}/{name}"
        if (label, name) in done:
            print(f"{tag}: finished earlier, skipped", flush=True)
            continue
        print(f"{tag} ({100.0 * (i - 1) / len(todo):.0f}% of cells done)", flush=True)
        ckpt = Path(args.work_dir) / "checkpoints" / args.null / label / name
        try:
            rows = RUNNERS[args.null](universes[label], placebo.TRIGGERS[name],
                                      checkpoint_dir=ckpt)
        except null_v2.NullRefusal as exc:     # record-and-ask: no cell, no verdict
            refused.append(f"{label}/{name}: {exc}")
            print(f"{tag}: refused: {exc}", flush=True)
            continue
        save_cell(path, placebo.cell_from_rows(label, name, args.null, rows))
    return refused
```

Add the planted check and the acceptance read below `_run_cells`:

```python
def load_planted(json_dir) -> dict | None:
    path = Path(json_dir) / PLANTED_JSON
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _save_planted(json_dir, record: dict) -> None:
    path = Path(json_dir) / PLANTED_JSON
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def run_planted(universes: dict[str, Path], args) -> dict:
    """The planted trigger under v2 on this run's gbm universe and on its planted
    copy; value = the event-arm gain on events booked in both (index Decisions)."""
    base = universe_label("gbm", args.gbm_tickers)
    done = load_planted(args.json_dir)
    if done is not None and done["base"] == base:
        print(f"[placebo planted] {base}: finished earlier, skipped", flush=True)
        return done
    label = f"planted-{base}"
    planted_dir = Path(args.work_dir) / "universes" / label
    if not (planted_dir / placebo.MANIFEST_FILE).is_file():
        placebo.plant_universe(universes[base], planted_dir)
    trigger = placebo.planted_trigger(planted_dir)
    ckpt = Path(args.work_dir) / "checkpoints" / "v2" / label
    print(f"[placebo planted] {label}: base, then planted", flush=True)
    base_rows = RUNNERS["v2"](universes[base], trigger, checkpoint_dir=ckpt / "base")
    rows = RUNNERS["v2"](planted_dir, trigger, checkpoint_dir=ckpt / "planted")
    record = {"base": base, "value": placebo.planted_value(base_rows, rows),
              "cell": placebo.cell_from_rows(label, trigger.name, "v2", rows).to_dict()}
    _save_planted(args.json_dir, record)
    return record


def _planted_step(universes: dict[str, Path], args) -> list[str]:
    if not args.planted:
        return []
    try:
        run_planted(universes, args)
    except null_v2.NullRefusal as exc:
        return [f"planted-{universe_label('gbm', args.gbm_tickers)}: {exc}"]
    return []


def _acceptance(args) -> tuple[Cell | None, dict | None]:
    """Stop gate 2 over the latest v2 cells and the planted record; (None, None)
    before any v2 cell exists. A missing planted record reads as noisy (ENLARGE)."""
    cells = [c for c in latest_cells(_all_cells(args.json_dir)) if c.null == "v2"]
    if not cells:
        return None, None
    record = load_planted(args.json_dir)
    planted = None if record is None else Cell.from_dict(record["cell"])
    value = None if record is None else record["value"]
    return planted, placebo.acceptance(cells, planted, value)


def _refusal(args) -> str | None:
    if args.null not in RUNNERS:
        return f"no {args.null} runner"
    if args.planted and (args.null != "v2" or "gbm" not in args.universes):
        return "--planted needs --null v2 and the gbm universe"
    return None
```

In `_detail`, first line of the body:

```python
    if m.get("kind") == "planted":
        return (f"planted on {m['base']}, +{m['plant_atr']} ATR14 over {m['cap']} bars, "
                f"spacing {m['spacing']}")
```

In `build_parser`, before `return p`:

```python
    p.add_argument("--planted", action="store_true",
                   help="v2 only: also run the planted-edge check on the gbm universe")
```

Replace `main`:

```python
def main(argv=None) -> int:
    screen_idea._utf8_stdout()
    args = build_parser().parse_args(argv)
    reason = _refusal(args)
    if reason:
        print(f"refused: {reason}", file=sys.stderr)
        return 2
    universes = build_universes(args)
    refused = _run_cells(universes, args) + _planted_step(universes, args)
    planted, verdict = (None, None) if refused else _acceptance(args)
    print(f"[placebo] wrote {write_doc(args, planted=planted, acceptance=verdict)}", flush=True)
    gate = v1_gate(_all_cells(args.json_dir))
    if gate is not None:
        print(f"gate: {gate}", flush=True)
    if refused:
        for line in refused:
            print(f"refused: {line}", file=sys.stderr)
        return 2
    if verdict is not None:
        print(f"acceptance: {verdict['verdict']}", flush=True)
    return 0
```

`_all_cells` globs `placebo-v*.json`, so the planted record is never read as a cell.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_placebo.py
python scripts/dev/complexity_gate.py
```

Expected: PASS, 0 failed, 0 xfailed (V230-4/4b tests included); `main` and `_run_cells` stay under 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/screen_placebo.py tests/backtest_scripts/test_screen_placebo.py
git commit -m "feat(v234): placebo v2 runner, planted check and stop gate 2"
```

- [ ] **Step 6: Run the v2 placebo (long, checkpointed)**

Read `<D>` from plan v230's index: `grep -n "V230-5" docs/superpowers/plans/implemented/2026-11-16-v230-screen-v2-rescreen_0-index.md` (its `## Handoff` names the date the doc was rendered with). Dispatch `backtest-runner` (one at a time, in the plan's worktree, named explicitly), in the background; after a crash it re-runs the identical command (finished cells and planted record skipped, a cell in progress resumes from its stage checkpoints, V230-5's universes in `data/v230-placebo/` reused):

```bash
mkdir -p logs
python scripts/backtest/screen_placebo.py --null v2 --planted --date <D> > logs/v234-placebo-v2.log 2>&1
```

The runner reports back only the exit code and the last 8 log lines.

- [ ] **Step 7: Read the outcome by the fixed rule**

```bash
python - <<'EOF'
import json
cells = json.load(open("docs/superpowers/results/v230/placebo-v2.json", encoding="utf-8"))
for c in sorted(cells, key=lambda c: (c["universe"], c["trigger"])):
    print(c["universe"], c["trigger"], c["n"], c["delta"], c["ci_low"], c["ci_high"])
print(json.load(open("docs/superpowers/results/v230/placebo-planted.json", encoding="utf-8")))
EOF
grep -n "^Verdict:\|^| .*/.* | \(PASS\|FAIL\|NOISY\) |" docs/superpowers/results/<D>-v230-null-placebo.md
```

- **Exit 2 with `refused:` lines:** record each refused cell in the Handoff and stop; the controller asks the partner. No re-run with other parameters, no trigger dropped.
- **`acceptance: ACCEPT`:** record it; V234-9 runs next.
- **`acceptance: STOP`:** record the failing cells (or the unrecovered planted value); V234-9..V234-12 do not run, and no fallback null is tried.
- **`acceptance: ENLARGE`:** re-run only the noisy kind at double size, same `--date`: a noisy `gbm` cell or a noisy planted cell → `--universes gbm --gbm-tickers 400 --triggers <noisy gbm triggers, or p_high20>` plus `--planted` when the planted cell was noisy; a noisy `shuffled` cell → `--universes shuffled --shuffled-copies 2 --triggers <noisy triggers>`. The larger universe gets its own label and supersedes the noisy cell (`latest_cells`). Read the new last line again. A cell still NOISY after two doublings is recorded and the partner is asked; it is never waved through.

- [ ] **Step 8: Record stop gate 2 in the index `## Handoff`**

Append to `docs/superpowers/plans/2026-11-17-v234-screen-v2-null_0-index.md` under `## Handoff` (never edit other sections):

```markdown
- **V234-8 (<YYYY-MM-DD>): stop gate 2 = <ACCEPT | STOP | REFUSED>.** v2 placebo cells
  <list label/trigger Δ [ci_low, ci_high] rule>; enlargements: <none | labels>; planted
  on <base>: value <v> R, cell Δ <Δ> [<lo>, <hi>], recovered <yes|no>. Doc
  `docs/superpowers/results/<D>-v230-null-placebo.md`.
- <ACCEPT:> Next task V234-9.
- <STOP:> V234-9..V234-12 do not run; no fallback null; the controller decides the close-out.
- <REFUSED:> refused cells <label/trigger: code: detail>; waiting on the partner.
```

Fill every `<...>` from Step 7; keep only the bullet that applies.

- [ ] **Step 9: Commit (worktree branch)**

```bash
git add docs/superpowers/results/*-v230-null-placebo.md docs/superpowers/results/v230/placebo-v2.json docs/superpowers/results/v230/placebo-planted.json docs/superpowers/plans/2026-11-17-v234-screen-v2-null_0-index.md
git commit -m "results(v234): v2 null placebo -- stop gate 2 <ACCEPT|STOP|REFUSED>"
```

Leave out `placebo-planted.json` if a refusal stopped it.

### Task V234-9: The fifth clause and one BH family

**Model:** opus — a new gating clause on the screen's verdict that must gate first shots, stay reported-only for re-screens and leave v1's `decide`, `label` and clause functions untouched.

**Runs only if V234-8 recorded `ACCEPT`** (index `## Handoff`).

**Files:**
- Modify: `swingbot/core/backtesting/screen/verdict.py` (module docstring, `dataclasses` import, new code after `decide`)
- Create: `tests/backtesting/screen/test_verdict_event.py`
- Modify: `swingbot/core/backtesting/screen/diagnostics.py` (`screen_family_q` :62, `_render_family` :263)
- Modify: `tests/backtesting/screen/test_diagnostics.py` (new test after :130; the needle at :243)
- Modify: `scripts/backtest/screen_idea.py` (`_context_run` ~:1860, `render_results`, `_run_screens`; new `with_event_clause` and `_render_event_bound`)
- Modify: `tests/backtest_scripts/test_screen_v2_wiring.py`
- Modify: `tests/backtest_scripts/test_screen_context_runner.py` (:559, :581)

**Interfaces:**
- Consumes: `verdict.bootstrap`, `mean_d`, `label`, `Verdict`, `PairedEvent` (existing); V234-7b `_run_screens` (v2 branch), `_v2_blocks`, the wiring test helpers `_universe`, `_argv`, `IDEA`.
- Produces: `verdict.EVENT_CLAUSE = "event_r"`; `EventBound(n, mean, ci_low, ci_high, p, holds, gating)`; `event_clause(low) -> bool`; `event_bound(events, *, gating, n_resamples=..., seed=...) -> EventBound`; `apply_event_clause(v, bound) -> Verdict`; `diagnostics.screen_family_q(rows, row, instrument=None)` (None = every ledger row); `screen_idea.with_event_clause(summary, idea, *, gating) -> dict` (adds `summary["event_bound"]`); `_render_event_bound(b) -> list`. V234-10 adds `--rescreen-v1`, which `_run_screens` already reads through `getattr(args, "rescreen_v1", False)`.

Spec A3: under `screen-v2` a first-shot edge idea also needs the week-clustered lower 95% bound of mean R_event, net of costs, above zero. A5: for the twelve `screen2-` re-screens it is reported and never gates (their event arm was already read). Avoid mode has no fifth clause. The bound is computed by the same `bootstrap` (week clusters, seed 42) over `PairedEvent(entry_date, r_event)`. A gating clause enters `Verdict.clauses`, so `label` reads it; a reported-only one stays out of `clauses` (`label` passes only when every clause holds).

One BH family (spec "Found while briefing"): every q a results doc prints runs over all ledger rows, as `publish` computes the head line's q; `screen_family_q` keeps its `instrument` argument (default None), and `_context_run` passes none.

- [ ] **Step 1: Write the failing verdict tests**

Create `tests/backtesting/screen/test_verdict_event.py`:

```python
"""v230 A3: the fifth clause -- the week-clustered lower 95% bound of mean R_event,
net of costs, above zero. Gates a first-shot edge idea, reported only for a screen2-
re-screen, absent in avoid mode; v1's decide and label are untouched."""
from datetime import date, timedelta

import pytest

from swingbot.core.backtesting.screen import verdict

FAST = 500   # resamples in tests; the screen itself uses the default 10,000


def _events(n, d=0.25, years=verdict.YEARS):
    """n events, one per ISO week, cycling through ``years``."""
    out = []
    for i in range(n):
        day = date(years[i % len(years)], 1, 4) + timedelta(weeks=i // len(years))
        out.append(verdict.PairedEvent(day.isoformat(), d(i) if callable(d) else d))
    return out


def _passing():
    v = verdict.decide(_events(300), n_resamples=FAST)
    assert v.verdict == verdict.SCREEN_PASS
    return v


def _bound(n=300, d=0.25, gating=True):
    return verdict.event_bound(_events(n, d), gating=gating, n_resamples=FAST)


@pytest.mark.parametrize("low, holds", [(1e-9, True), (0.0, False), (-0.01, False),
                                        (None, False)])
def test_event_clause_boundary(low, holds):
    assert verdict.event_clause(low) is holds


def test_event_bound_reads_the_event_arm_alone():
    b = _bound(d=0.2)
    assert (b.n, b.gating, b.holds) == (300, True, True)
    assert b.mean == pytest.approx(0.2) and b.ci_low == pytest.approx(0.2) and b.p == 0.0


def test_an_empty_book_has_no_bound_and_does_not_hold():
    b = verdict.event_bound([], gating=False, n_resamples=FAST)
    assert (b.n, b.mean, b.ci_low, b.ci_high, b.p, b.holds) == (0, None, None, None, None,
                                                                 False)


def test_a_gating_bound_that_fails_turns_a_pass_into_a_fail():
    v = _passing()
    losing = _bound(d=lambda i: 0.4 if i % 2 else -0.6)       # mean R_event -0.1
    assert not losing.holds
    out = verdict.apply_event_clause(v, losing)
    assert out.verdict == verdict.SCREEN_FAIL
    assert out.clauses == {**v.clauses, verdict.EVENT_CLAUSE: False}
    assert (out.n, out.delta_exp_r, out.ci_low, out.p) == (v.n, v.delta_exp_r, v.ci_low, v.p)


def test_a_gating_bound_that_holds_keeps_the_pass_with_five_clauses():
    out = verdict.apply_event_clause(_passing(), _bound(d=0.3))
    assert out.verdict == verdict.SCREEN_PASS
    assert set(out.clauses) == {"exp_r", "ci", "years", "n", "event_r"}


def test_a_reported_only_bound_never_changes_the_verdict():
    v = _passing()
    assert verdict.apply_event_clause(v, _bound(d=-0.2, gating=False)) is v


def test_n_under_300_stays_underpowered_whatever_the_bound():
    v = verdict.decide(_events(299), n_resamples=FAST)
    assert verdict.apply_event_clause(v, _bound(n=299)).verdict == verdict.SCREEN_UNDERPOWERED


def test_avoid_mode_has_no_fifth_clause():
    v = verdict.decide(_events(300, -0.25), mode="avoid", control=_events(300, -0.25),
                       n_resamples=FAST)
    with pytest.raises(ValueError, match="edge mode only"):
        verdict.apply_event_clause(v, _bound())


def test_decide_still_returns_the_four_v1_clauses():
    assert set(_passing().clauses) == {"exp_r", "ci", "years", "n"}
```

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict_event.py`
Expected: FAIL — `AttributeError: module ... 'verdict' has no attribute 'event_clause'`.

- [ ] **Step 2: Write the verdict code**

In `swingbot/core/backtesting/screen/verdict.py` change `from dataclasses import dataclass` to `from dataclasses import dataclass, replace`, append to the module docstring:

```
v230 A3 adds a fifth clause under screen-v2: the week-clustered lower 95%
bound of mean R_event (net of costs) is above zero. It gates a first-shot edge
idea and is reported only for a screen2- re-screen; avoid mode has none.
decide, label and the four clause functions are unchanged.
```

and append after `decide`:

```python
EVENT_CLAUSE = "event_r"


@dataclass(frozen=True)
class EventBound:
    """v230 A3: the week-clustered bound of mean R_event, net of costs."""
    n: int
    mean: float | None
    ci_low: float | None
    ci_high: float | None
    p: float | None
    holds: bool
    gating: bool


def event_clause(low) -> bool:
    return low is not None and low > 0


def event_bound(events, *, gating: bool, n_resamples: int = stats.WEEK_BOOTSTRAP_RESAMPLES,
                seed: int = stats.WEEK_BOOTSTRAP_SEED) -> EventBound:
    """``events`` are PairedEvent(entry_date, r_event): the event arm alone, through
    the same week-clustered bootstrap and seed as the four clauses."""
    events = list(events)
    low, high, p = bootstrap(events, n_resamples=n_resamples, seed=seed)
    return EventBound(len(events), mean_d([], events), low, high, p, event_clause(low), gating)


def apply_event_clause(v: Verdict, bound: EventBound) -> Verdict:
    """A gating bound joins the clauses and relabels the verdict; a reported-only
    bound (a screen2- re-screen, spec A5) returns ``v`` itself."""
    if v.mode != "edge":
        raise ValueError("the fifth clause applies to edge mode only")
    if not bound.gating:
        return v
    clauses = {**v.clauses, EVENT_CLAUSE: bound.holds}
    return replace(v, verdict=label(clauses), clauses=clauses)
```

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict_event.py` — PASS. Run `python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict.py` and `... file tests/backtesting/screen/test_verdict_avoid.py` — PASS, untouched.

```bash
git add swingbot/core/backtesting/screen/verdict.py tests/backtesting/screen/test_verdict_event.py
git commit -m "feat(v234): the fifth clause -- lower bound of mean R_event"
```

- [ ] **Step 3: One BH family in the diagnostics**

In `tests/backtesting/screen/test_diagnostics.py` add after `test_the_screen_family_q_is_none_without_a_p`:

```python
def test_the_screen_family_q_defaults_to_every_ledger_row():
    rows = [{"id": "v139-arm-d", "instrument": "v1", "p": 0.001},
            {"id": "screen-a", "instrument": "screen-v1", "p": 0.04}]
    row = {"id": "screen2-a", "instrument": "screen-v2", "p": 0.03}
    whole = stats.ledger_qvalues(rows + [row])["screen2-a"]
    assert diagnostics.screen_family_q(rows, row) == pytest.approx(whole)
    assert diagnostics.screen_family_q(rows, row, "screen-v2") == pytest.approx(0.03)
```

and change the needle `"BH q = 0.0421 across the `screen-v1` family"` (~:243) to `"BH q = 0.0421 across the whole ledger (one family since v230"`. In `tests/backtest_scripts/test_screen_context_runner.py` change :559 to `assert out["screen_q"] == pytest.approx(stats.ledger_qvalues(rows + [row])[row["id"]])` and the needle `"across the `screen-v1` family"` (~:581) to `"across the whole ledger (one family since v230"`.

Run: `python scripts/dev/testrun.py file tests/backtesting/screen/test_diagnostics.py` — FAIL (`screen_family_q()` missing `instrument`; the old text).

In `swingbot/core/backtesting/screen/diagnostics.py`:

```python
def screen_family_q(rows: list[dict], row: dict, instrument: str | None = None) -> float | None:
    """BH q of ``row`` over every ledger row (v230: one family, as the head line's q);
    over one instrument's rows only when ``instrument`` is given (the § 5.5 reading)."""
    family = [r for r in [*rows, row] if instrument is None or r["instrument"] == instrument]
    return stats.ledger_qvalues(family).get(row["id"])
```

and in `_render_family` replace the text after the q with:

```python
            f"BH q = {_fmt(screen_q, '.4f')} across the whole ledger (one family since "
            "v230, the same family as the head line's q). Reported, never gating."]
```

In `scripts/backtest/screen_idea.py` `_context_run`, the last line becomes `"screen_q": diagnostics.screen_family_q(rows, row)}`.

Run both test files (`test_diagnostics.py`, `test_screen_context_runner.py`) — PASS.

```bash
git add swingbot/core/backtesting/screen/diagnostics.py tests/backtesting/screen/test_diagnostics.py scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_context_runner.py
git commit -m "feat(v234): the context q runs over the one ledger-wide BH family"
```

- [ ] **Step 4: Write the failing wiring tests**

In `tests/backtest_scripts/test_screen_v2_wiring.py` add `from datetime import date, timedelta` to the imports, add to the `fast_bootstrap` fixture body:

```python
    monkeypatch.setattr(screen_idea.verdict, "event_bound",
                        functools.partial(verdict.event_bound, n_resamples=500))
```

and append:

```python
def _edge_summary(r_event):
    """300 events, one per ISO week across 2011..2019, every Δ = +0.25R (a v1 pass)."""
    rows = []
    for i in range(300):
        day = date(verdict.YEARS[i % 9], 1, 4) + timedelta(weeks=i // 9)
        rows.append({"entry_date": day.isoformat(), "r_event": r_event(i),
                     "r_null": r_event(i) - 0.25})
    paired = [verdict.PairedEvent(r["entry_date"], r["r_event"] - r["r_null"]) for r in rows]
    return {"verdict": verdict.decide(paired), "events": rows}


def test_the_fifth_clause_gates_a_first_shot_and_is_reported_for_a_rescreen():
    summary = _edge_summary(lambda i: 0.4 if i % 2 else -0.6)      # mean R_event -0.1
    assert summary["verdict"].verdict == verdict.SCREEN_PASS
    gated = screen_idea.with_event_clause(summary, IDEA, gating=True)
    assert gated["verdict"].verdict == verdict.SCREEN_FAIL
    assert gated["event_bound"].gating and not gated["event_bound"].holds
    reported = screen_idea.with_event_clause(summary, IDEA, gating=False)
    assert reported["verdict"] is summary["verdict"]
    assert not reported["event_bound"].gating


def test_an_avoid_summary_gets_no_fifth_clause():
    summary = {"verdict": None, "events": []}
    assert screen_idea.with_event_clause(summary, IDEAS["fvg_overhead_aged"],
                                         gating=True) is summary


def test_run_screens_reads_gating_from_the_rescreen_flag(tmp_path, monkeypatch):
    cache, universe = _universe(tmp_path)
    seen = []

    def spy(summary, idea, *, gating):
        seen.append(gating)
        return summary

    monkeypatch.setattr(screen_idea, "with_event_clause", spy)
    args = screen_idea.build_parser().parse_args(_argv(tmp_path, cache, "turn_of_month"))
    screen_idea._run_screens(args, IDEA, universe, None, None)
    args.rescreen_v1 = True
    screen_idea._run_screens(args, IDEA, universe, None, None)
    assert seen == [True, False]


def test_a_dry_run_prints_the_gating_fifth_clause(tmp_path, capsys):
    cache, _ = _universe(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, "turn_of_month")) == 0
    text = capsys.readouterr().out
    assert "This clause gates this verdict" in text
    assert (text.index("## Verdict:") < text.index("## Fifth clause (v230 A3)")
            < text.index("## Forward drift"))


def test_the_v1_path_has_no_fifth_clause(tmp_path, capsys, screen_null_v1):
    cache, _ = _universe(tmp_path)
    assert screen_idea.main(_argv(tmp_path, cache, "turn_of_month")) == 0
    assert "## Fifth clause" not in capsys.readouterr().out
```

Run: `python scripts/dev/testrun.py file tests/backtest_scripts/test_screen_v2_wiring.py`
Expected: FAIL — `AttributeError: module 'screen_idea' has no attribute 'with_event_clause'`.

- [ ] **Step 5: Wire the fifth clause into `screen_idea.py`**

Below `_v2_blocks`:

```python
def with_event_clause(summary: dict, idea: Idea, *, gating: bool) -> dict:
    """v230 A3: the fifth clause on an edge idea's v2 summary -- gating for a first
    shot, reported only for a screen2- re-screen; avoid mode has none."""
    if idea.mode != "edge":
        return summary
    events = [verdict.PairedEvent(r["entry_date"], r["r_event"]) for r in summary["events"]]
    bound = verdict.event_bound(events, gating=gating)
    return {**summary, "verdict": verdict.apply_event_clause(summary["verdict"], bound),
            "event_bound": bound}
```

In `_run_screens` the v2 branch becomes:

```python
    else:
        summary = with_event_clause(_v2_blocks(summary, idea), idea,
                                    gating=not getattr(args, "rescreen_v1", False))
```

Beside `_render_edge_verdict` (which stays unchanged):

```python
def _render_event_bound(b) -> list:
    """v230 A3: the fifth clause, and whether it gates this verdict."""
    role = ("gates this verdict (a first-shot edge idea under `screen-v2`)" if b.gating else
            "is reported only and never gates: a `screen2-` re-screen whose event arm "
            "was already read under v1 (spec v230 A5)")
    return ["## Fifth clause (v230 A3): mean R_event net of costs", "",
            "| Clause | Measured | Rule | Holds |", "|---|---|---|---|",
            f"| lower 95% bound of mean R_event, week-clustered bootstrap | "
            f"{_fmt(b.ci_low)}R (mean {_fmt(b.mean)}R, upper {_fmt(b.ci_high)}R, N {b.n}) | "
            f"> 0 | {_yes(b.holds)} |", "", f"This clause {role}."]
```

In `render_results`, directly after the `sections = [...]` assignment:

```python
    if "event_bound" in summary:
        sections.insert(3, _render_event_bound(summary["event_bound"]))
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py suite backtest-scripts
python scripts/dev/testrun.py file tests/backtesting/screen/test_verdict_event.py
python scripts/dev/testrun.py file tests/backtesting/screen/test_long_byte_identical.py
python scripts/dev/complexity_gate.py
```

Expected: 0 failed, 0 xfailed. The long golden stays byte-identical (it renders v1 summaries, which carry no `event_bound`); `render_results` and `_run_screens` stay under 15.

- [ ] **Step 7: Commit**

```bash
git add scripts/backtest/screen_idea.py tests/backtest_scripts/test_screen_v2_wiring.py
git commit -m "feat(v234): screen-v2 gates first shots on the fifth clause, re-screens report it"
```

