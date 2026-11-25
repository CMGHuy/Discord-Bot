# v239 — Bear-regime engine (shadow): Part 5 — evidence and docs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V239-17" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md) — its `## Code reconciliation` section overrides the text above it.
**Index:** [2026-11-23-v239-bear-regime-engine-shadow_0-index.md](2026-11-23-v239-bear-regime-engine-shadow_0-index.md) — Global Constraints, Parallelisation, the task ledger and the eight "Decisions this index fixes" apply to every task here.

Tasks: V239-16 (live-vs-replay parity, spec § Parity) and V239-17 (alert-surface skill, architecture map, guide chapters and the Codex mirror). V239-16 needs V239-1, V239-2b and V239-6b; V239-17 runs last, because it cites the final names every other task creates. The spec's base-rate study and shadow report moved to a follow-on evidence plan (partner, 2026-11-23; index § What follows).

**Script tests import as a namespace package** (`from scripts.reports import regime_parity`), the way `tests/scripts/test_cohort_separation_report.py` does; `scripts/` has no `__init__.py` and needs none. They live in `tests/regime/` (suite `market-signals`), never `tests/scripts/` (near its cap).

# Phase 5 — Evidence and docs

### Task V239-16: Live-vs-replay parity check

**Model:** sonnet — an argparse report script over fixed inputs; the rules it compares are V239-2's and the tolerance is the spec's.

**Why:** parity keeps the shadow from drifting from the rules B7–B9 will screen (spec § Parity). It replays `bear_regime.classify` on cached bars for every stored `market_regime_days` row and compares states. A mismatch is tolerated only on a boundary day, where any compared quantity sits within 0.1% of its right-hand side. A non-boundary mismatch fails and prints both input closes. Stored rows are never rewritten.

**Scope moved (partner, 2026-11-23):** the shadow report the spec lists beside parity (spec § Evidence) left v239 with the base-rate study for a follow-on evidence plan (index § What follows). This task is parity only.

**Files:**
- Create: `scripts/reports/regime_parity.py`
- Create: `tests/fixtures/regime/market_regime_days_export.json` (generated in Step 1, committed)
- Test: `tests/regime/test_regime_parity.py` (suite `market-signals`)

**Interfaces:**
- Consumes: `bear_regime.RegimeDay` (`from_row`, `to_row`, fields `session_date`, `last_bar_date`, `state`, `stress`, `spy_close`, `sma50`, `sma200`, `sma50_lag5`, `sma200_lag20`, `vix_close`, `spy_provider`, `vix_provider`), `ROW_COLUMNS`, `STRESS_VIX`, `UNKNOWN`, `SPY`, `VIX`, `classify(...)` (V239-2/2b); `tests/fixtures/regime/spy_vix_replay.csv` (V239-2b: columns `Date,spy_high,spy_close,vix_close`); `fetch_regime_data.CACHE_DIR`, `csv_path(cache_dir, symbol)` (V239-1); `market_regime.market_regime_repo().recent(limit, *, conn=None) -> list[dict]` (V239-6b, oldest first).
- Produces (ledger contract, final; nothing later in this plan consumes them): `regime_parity.BOUNDARY_PCT = 0.001`; `boundary_day(day: RegimeDay) -> bool`; `@dataclass ParityResult(matches: int, boundary: list, failures: list, uncovered: list = [])` (`uncovered` is additive to the ledger shape, default empty: rows the cache cannot replay); `compare(stored: list[dict], spy: DataFrame, vix: DataFrame | None) -> ParityResult`; `main(argv=None) -> int` (0 clean, 1 a non-boundary mismatch, 2 cannot run).

**Rules this task fixes (spec silent):**
- Parity compares `state`, and `stress` when both sides carry a value. The spec's boundary list includes `V − 25`, so stress is part of what parity guards.
- A stored row is replayed with `last_session = last_bar_date`. Stored rows are never stale (index decision 1).
- A row whose `last_bar_date` is missing or later than the cache's last SPY bar is `uncovered`, never a failure.
- Without `--rows` the rows come from the table. `--export PATH` writes them to JSON and stops, so a VM export can be replayed on a machine that holds the cache.

- [ ] **Step 1: Generate the export fixture**

It needs only V239-2b's committed replay CSV. Save this as a throwaway script outside the repo, run it from the repo root with `python <path>`, then delete it:

```python
import json
from datetime import date
from pathlib import Path
import pandas as pd
from swingbot.core.market import bear_regime as br

raw = pd.read_csv("tests/fixtures/regime/spy_vix_replay.csv", parse_dates=["Date"], index_col="Date")
spy = raw.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
vix = raw[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
sessions = [ts.date() for ts in spy.index]
rows = []
for s, d in zip(sessions, sessions[1:] + [date(2026, 11, 23)]):
    if d < date(2026, 10, 15):
        continue
    day = br.classify(spy, vix, last_session=s, session_date=d,
                      spy_provider="alpaca", vix_provider="yfinance")
    row = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in day.to_row().items()}
    row["computed_at"] = f"{s.isoformat()}T21:05:00+00:00"
    rows.append(row)
path = Path("tests/fixtures/regime/market_regime_days_export.json")
path.write_text(json.dumps(rows, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
print(len(rows), rows[0]["session_date"], rows[-1]["session_date"])
```

Expected: `28 2026-10-15 2026-11-23` (one row per NYSE session in the span). `test_main_clean_run` below asserts this count. If another count prints, put the printed one in that assertion.

- [ ] **Step 2: Write the failing parity test**

Create `tests/regime/test_regime_parity.py`:

```python
"""v239 V239-16: live-vs-replay parity (spec § Parity) on the committed export."""
import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.reports import regime_parity as rp
from swingbot.core.market import bear_regime as br

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "regime"
EXPORT = FIXTURES / "market_regime_days_export.json"
REPLAY = FIXTURES / "spy_vix_replay.csv"


@pytest.fixture(scope="module")
def frames():
    raw = pd.read_csv(REPLAY, parse_dates=["Date"], index_col="Date")
    spy = raw.rename(columns={"spy_high": "High", "spy_close": "Close"})[["High", "Close"]]
    vix = raw[["vix_close"]].rename(columns={"vix_close": "Close"}).dropna()
    return spy, vix


@pytest.fixture
def stored():
    return json.loads(EXPORT.read_text(encoding="utf-8"))


def _pick(stored, **want):
    """The first non-boundary row whose fields equal ``want``."""
    for row in stored:
        if not rp.boundary_day(br.RegimeDay.from_row(row)) and all(
                row[k] == v for k, v in want.items()):
            return row
    raise AssertionError(f"the export has no non-boundary row with {want}")


def test_export_fixture_is_a_table_export(stored):
    assert set(br.ROW_COLUMNS) | {"doc", "computed_at"} <= set(stored[0])
    assert (stored[0]["session_date"], stored[-1]["session_date"]) == ("2026-10-15", "2026-11-23")


def test_the_export_replays_clean(stored, frames):
    result = rp.compare(stored, *frames)
    assert (result.matches, result.boundary, result.failures, result.uncovered) == (
        len(stored), [], [], [])


def test_a_non_boundary_state_mismatch_fails_and_names_both_closes(stored, frames):
    row = dict(_pick(stored, state="CORRECTION"), state="NORMAL")
    result = rp.compare([row], *frames)
    assert result.matches == 0 and result.boundary == []
    (failure,) = result.failures
    assert failure["session_date"] == row["session_date"]
    assert (failure["stored"], failure["replayed"]) == ("NORMAL", "CORRECTION")
    assert failure["stored_spy_close"] == row["spy_close"]
    assert failure["replayed_spy_close"] == pytest.approx(row["spy_close"])
    assert (failure["spy_provider"], failure["last_bar_date"]) == ("alpaca", row["last_bar_date"])


def test_a_stress_mismatch_fails(stored, frames):
    row = dict(_pick(stored, stress=True), stress=False)
    assert len(rp.compare([row], *frames).failures) == 1


def test_a_missing_stress_on_one_side_is_not_compared(stored, frames):
    row = dict(_pick(stored, stress=True), stress=None)
    assert rp.compare([row], *frames).matches == 1


def test_a_boundary_mismatch_is_reported_not_failed(stored, frames, monkeypatch):
    row = dict(stored[-1], state="BEAR" if stored[-1]["state"] != "BEAR" else "NORMAL")
    monkeypatch.setattr(rp, "boundary_day", lambda day: True)
    result = rp.compare([row], *frames)
    assert (result.matches, len(result.boundary), result.failures) == (0, 1, [])


def test_rows_the_cache_cannot_replay_are_uncovered(stored, frames):
    late = dict(stored[-1], session_date="2026-11-25", last_bar_date="2026-11-24")
    blank = dict(stored[-1], last_bar_date=None)
    result = rp.compare([late, blank], *frames)
    assert (result.matches, result.failures, len(result.uncovered)) == (0, [], 2)


@pytest.mark.parametrize("fields, boundary", [
    (dict(spy_close=100.05, sma200=100.0), True),          # C within 0.1% of SMA200
    (dict(spy_close=100.2, sma50=100.1), True),            # C within 0.1% of SMA50
    (dict(sma200=100.0, sma200_lag20=99.95), True),        # slow slope flat
    (dict(sma50=100.0, sma50_lag5=100.05), True),          # fast slope flat
    (dict(sma50=100.0, sma200=100.09), True),              # SMA50 at SMA200
    (dict(vix_close=25.02), True),                         # V within 0.1% of 25
    (dict(vix_close=25.03), False),
])
def test_boundary_day(fields, boundary):
    far = dict(spy_close=90.0, sma50=120.0, sma50_lag5=110.0, sma200=150.0,
               sma200_lag20=140.0, vix_close=15.0)
    day = br.RegimeDay(session_date=None, last_bar_date=None, state="NORMAL", **{**far, **fields})
    assert rp.boundary_day(day) is boundary


def test_an_unknown_day_is_never_a_boundary_day():
    assert rp.boundary_day(br.RegimeDay(None, None, br.UNKNOWN)) is False


def _cache(tmp_path, frames):
    spy, vix = frames
    spy.rename_axis("Date").to_csv(tmp_path / "SPY.csv", lineterminator="\n")
    vix.rename_axis("Date").to_csv(tmp_path / "^VIX.csv", lineterminator="\n")
    return tmp_path


def test_main_clean_run(tmp_path, frames, capsys):
    assert rp.main(["--rows", str(EXPORT), "--cache-dir", str(_cache(tmp_path, frames))]) == 0
    assert "parity: 28 match · 0 boundary · 0 fail · 0 uncovered" in capsys.readouterr().out


def test_main_fails_on_a_mismatch_and_prints_the_inputs(tmp_path, frames, stored, capsys):
    row = dict(_pick(stored, state="CORRECTION"), state="NORMAL")
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps([row]), encoding="utf-8")
    assert rp.main(["--rows", str(rows), "--cache-dir", str(_cache(tmp_path, frames))]) == 1
    out = capsys.readouterr().out
    assert f"FAIL {row['session_date']}" in out and "spy_provider=alpaca" in out


def test_main_export_writes_the_rows_and_stops(tmp_path, monkeypatch):
    rows = [{"session_date": "2026-11-23", "state": "CORRECTION"}]
    monkeypatch.setattr(rp, "_stored_rows", lambda args: rows)
    out = tmp_path / "export.json"
    assert rp.main(["--export", str(out), "--cache-dir", str(tmp_path / "none")]) == 0
    assert json.loads(out.read_text(encoding="utf-8")) == rows
    assert b"\r\n" not in out.read_bytes()


def test_main_cannot_run_without_the_cache(tmp_path):
    assert rp.main(["--rows", str(EXPORT), "--cache-dir", str(tmp_path / "none")]) == 2
```

- [ ] **Step 3: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_parity.py`
Expected: errors, `ModuleNotFoundError` for `scripts.reports.regime_parity`.

- [ ] **Step 4: Write `scripts/reports/regime_parity.py`**

```python
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
```

- [ ] **Step 5: Run it to see it pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_parity.py`
Expected: `0 failed`. If `test_the_export_replays_clean` reports a mismatch, the fixture and the replay disagree on the same bars. That is a `classify` bug, because it must be a pure function of the frames: stop and report it, never loosen the test.

Run: `python -m radon cc -s -n C scripts/reports/regime_parity.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/regime_parity.py tests/fixtures/regime/market_regime_days_export.json tests/regime/test_regime_parity.py
git commit -m "feat(v239): live-vs-replay parity check for market_regime_days"
```

### Task V239-17: Skills, architecture map, guide and Codex mirror

**Model:** sonnet — doc and skill edits against names every earlier task already fixed; the only code is guide-text assertions in an existing test file.

**Why:** an implemented plan that changes anything a skill, a `docs/claude/` file or a guide chapter cites must align it before it counts as done (CLAUDE.md; `/close-out` Step 5b). The alert surface gained a `Trend` field on every alert builder. `core/market`, `core/scanning` and `core/presentation` gained the regime modules, and the plan's diff touches `sources:` paths of guide chapters 01, 03, 04, 05, 06, 07, 08 and 12. The bomeo-capital.com guide is what the partner reads to understand an alert, so the reader-visible change (the Trend line and the fact that it never changes a plan) goes into the chapters that describe the alert.

**Files:**
- Modify: `.claude/skills/alert-surface/SKILL.md` (Step 1 "Where the code actually is" paragraph; one "Known wrong turns" row)
- Modify: `.agents/skills/alert-surface/SKILL.md` (regenerated by `python scripts/dev/sync_codex.py`, never hand-edited)
- Modify: `docs/claude/architecture.md` (one bullet after "Opex-day caution (v44)")
- Modify: `AGENTS.md` (the `architecture.md` pointer line; one line in the Commands block)
- Modify: `docs/guide/07-trade-plan.md` (new last section, five `sources:` entries, `reviewed_for`)
- Modify: `docs/guide/01-what-it-is.md` (one bullet in "What an alert is", `reviewed_for`)
- Modify: `docs/guide/03-pipeline.md` (one sentence in "Alert", `reviewed_for`)
- Test: `tests/admin/test_guide_chapter_text.py` (`CH7_ANCHORS` gains the new anchor; three new tests)

**Interfaces:**
- Consumes (cited by name; each must exist before this task starts): `bear_regime.classify`, `shadow_action`, `RegimeDay` (V239-2/2b); `regime_episodes.confirmed_episodes` (V239-3); `regime_text.alert_line` (V239-3); `regime_calendar.session_pair`, `cut_completed` (V239-4); `config.BEAR_REGIME_MODE`, `regime_scan.regime_for_pass` (V239-5/8); `market_regime_days`, `MarketRegimeRepository.insert_once` (V239-6/6b); `regime_notices.build_regime_embed` (V239-7); `params.regime_asof`, `params._merge_regime` (V239-9); `alert_embeds.REGIME_FIELD`, `alert_embeds.regime_fields` (V239-11); `tests/regime/test_regime_embeds.py` (V239-11), `tests/regime/test_regime_off_byte_identical.py` (V239-10); `api_v1/market_regime.py` (V239-12); `scripts/reports/regime_parity.py` (V239-16).
- Produces: nothing code consumes.

**Guide decisions (per chapter `guide_sources.py` flags):**

| Chapter | Why flagged | Decision |
|---|---|---|
| 07 trade-plan | `params.py`, `analyze.py`, `config.py` | **update**: new section "The trend line on the alert (shadow)" |
| 01 what-it-is | `alert_embeds.py`, `scan_run.py` | **update**: the alert gains a Trend line (one bullet) |
| 03 pipeline | `alert_embeds.py`, `analyze.py`, `scan_run.py` | **update**: the Alert stage names the line (one sentence) |
| 04 levels | `analyze.py:_horizon_scenarios`, `config.py` fields | close-out records `guide: no reader-visible change` (no level, scenario or cited setting changed) |
| 05 strategies | `scan_run.py:_maybe_run_strategy_pass`, `params.py:stamp_badge` | close-out records `guide: no reader-visible change` (strategy selection and badges unchanged; the pass only forwards `regime_day`) |
| 06 gates | `qualify.py`, `analyze.py:veto_bullish_for`, `config.py` | close-out records `guide: no reader-visible change` (the regime label gates nothing; chapter 07 says so) |
| 08 sizing-risk | `analyze.py:attach_plan_v2`, `short_run.py`, `alert_embeds.py` | close-out records `guide: no reader-visible change` (sizing, caps and heat unchanged) |
| 12 glossary | `config.py` fields | close-out records `guide: no reader-visible change` (no cited setting changed) |

If `guide_sources.py` (Step 1) names a chapter outside this table, stop and report it rather than guessing.

- [ ] **Step 1: List the touched chapters**

Run, in the plan's worktree: `python scripts/dev/guide_sources.py main..HEAD`
Expected: exit 0, naming chapters within 01, 03, 04, 05, 06, 07, 08 and 12 (and no strategy card). Keep the output for your report; `/close-out` copies the `no reader-visible change` lines from the table above into its commit.

Run: `python -c "import json; print(json.load(open('VERSION.json'))['bot'])"`
Expected: the current bot version (2.19.5 when briefed). This is the `reviewed_for` value for 01, 03 and 07: never a higher one, because `version_problems` flags a chapter reviewed for a version above the current one.

- [ ] **Step 2: Write the failing guide tests**

In `tests/admin/test_guide_chapter_text.py`, append `"the-trend-line-on-the-alert-shadow"` as the last entry of `CH7_ANCHORS` (after `"backtest-and-live-use-the-same-plan"`), and add:

```python
def test_chapter_7_trend_line_is_shadow_only():
    section = _section(_chapter("trade-plan").body, "The trend line on the alert (shadow)")
    assert "{{BEAR_REGIME_MODE}}" in section
    for word in ("Bear", "Correction", "Stress", "Pullback watch", "No reading"):
        assert word in section, word
    assert "no plan is blocked, sized, scored or cancelled" in section
    assert "`alert_embeds.regime_fields`" in section and "`bear_regime.shadow_action`" in section
    sources = set(_chapter("trade-plan").sources)
    assert {"swingbot/core/planning/params.py:regime_asof",
            "swingbot/core/market/bear_regime.py:shadow_action",
            "swingbot/core/scanning/alert_embeds.py:regime_fields",
            "swingbot/core/presentation/regime_text.py:alert_line",
            "swingbot/config.py:BEAR_REGIME_MODE"} <= sources


def test_chapter_1_alert_lists_the_trend_line():
    section = _section(_chapter("what-it-is").body, "What an alert is")
    assert "](/insights/guide/trade-plan#the-trend-line-on-the-alert-shadow)" in section


def test_chapter_3_alert_stage_names_the_trend_line_as_shadow():
    section = _section(_chapter("pipeline").body, "Alert")
    assert "Trend line" in section and "never changes the plan" in section
```

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: 4 failed (the three new tests and `test_chapter_7_sections_in_order`).

- [ ] **Step 3: Write the guide text**

`docs/guide/07-trade-plan.md`: set `reviewed_for:` to Step 1's version. Append to `sources:` (after `swingbot/config.py:PLAN_ENGINE_V2`):

```yaml
  - swingbot/core/planning/params.py:regime_asof
  - swingbot/core/market/bear_regime.py:shadow_action
  - swingbot/core/scanning/alert_embeds.py:regime_fields
  - swingbot/core/presentation/regime_text.py:alert_line
  - swingbot/config.py:BEAR_REGIME_MODE
```

Append at the end of the chapter body (no bare number before a percent sign: chapters 7–9 fail `bare_percent_problems`):

```markdown
## The trend line on the alert (shadow)

While the setting `BEAR_REGIME_MODE` is not off (it is now {{BEAR_REGIME_MODE}}), every alert carries one Trend line under its plan. It reads the market's daily trend for the session the plan is issued for, from SPY's last completed close against its 50-day and 200-day averages and from the VIX close: **Bear** when the long trend has turned down, **Correction** when it is a dip while the long trend still rises (**Correction · Stress** when the VIX closed at 25 or above), and **Pullback watch** on the day the panic eases inside a correction. A **Normal** trend, or **No reading** when the data is missing or late, adds no line.

The line says what the engine *would* do with this plan: skip a long in a bear or a stressed correction, take care with a long in a plain correction, watch a long on a pullback day, and note that a short goes with the tape (with the squeeze risk that comes with it). It is a shadow: no plan is blocked, sized, scored or cancelled because of it, and the plan's numbers above the line are the same with or without it. Whether acting on it would pay is decided later by its own screens, never by this line.

<details><summary>Under the hood</summary>

`regime_scan.regime_for_pass` labels the coming session once per scan pass with `bear_regime.classify` and stores it once in `market_regime_days`. `params.regime_asof` and `stamp_entry_context` write `bear_regime` and `regime_action` (from `bear_regime.shadow_action(state, stress, pullback_trigger, direction)`) into the plan's `entry_context`. `alert_embeds.regime_fields` renders the stored pair through `regime_text.alert_line` as the `Trend` field. With the setting off nothing is fetched, stored, stamped or shown.

</details>
```

`docs/guide/01-what-it-is.md`: set `reviewed_for:` to Step 1's version. In "What an alert is", add this bullet directly after the confidence bullet:

```markdown
- while the market-trend layer runs, a Trend line saying what the engine would do in today's market trend; it is a shadow and never changes the plan ([the trend line](/insights/guide/trade-plan#the-trend-line-on-the-alert-shadow));
```

`docs/guide/03-pipeline.md`: set `reviewed_for:` to Step 1's version. In "Alert", after its first sentence, add:

```markdown
Under the plan the alert carries a Trend line with the market's daily trend label; it records what the engine would do and never changes the plan ([chapter 7](/insights/guide/trade-plan#the-trend-line-on-the-alert-shadow)).
```

- [ ] **Step 4: Run the guide tests**

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_chapter_text.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/admin/test_guide_content.py`
Expected: `0 failed` (`test_the_real_guide_passes` resolves every new `sources:` symbol, the placeholder, the links and `reviewed_for`).

- [ ] **Step 5: Align the alert-surface skill and the architecture map**

`.claude/skills/alert-surface/SKILL.md`, at the end of the "Where the code actually is" paragraph (after "do not look for them."), add:

```markdown
The v239 `Trend` line is one helper, `alert_embeds.regime_fields(plan)`,
called once in `build_embed` (inside `sections["plan"]`), `build_simple_alert`
(both branches), `build_strategy_alert_embed` (after Ledger) and
`build_strategy_simple_embed` (in the description); the execution ticket
(`build_ticket_embed`) carries none. It reads only the stamped
`entry_context` keys `bear_regime` / `regime_action`; with
`BEAR_REGIME_MODE=off` nothing is stamped and every embed is byte-identical
(`tests/regime/test_regime_embeds.py`,
`tests/regime/test_regime_off_byte_identical.py`).
```

Add this row as the last row of the "Known wrong turns" table:

```markdown
| "The new builder needs the trend line, I'll fetch the regime there" | Builders never fetch: call `regime_fields(plan)`, which reads the stamped `entry_context` pair, and pin the `off` bytes in `tests/regime/test_regime_embeds.py`. A builder that reads `market_regime_days` itself breaks the `off` kill switch. |
```

`docs/claude/architecture.md`, directly after the "Opex-day caution (v44)" bullet, add:

```markdown
- **Bear-regime shadow (v239).** `core/market/bear_regime.py` (pure
  `classify` -> `RegimeDay`, frozen `Final` constants, `shadow_action`) and
  `core/market/regime_episodes.py` (two-session confirmed episodes) label the
  coming NYSE session `D` from completed daily SPY and ^VIX bars dated `<= s`.
  `scanning/regime_calendar.py` gives the half-day-aware `(s, D)` pair and
  the completed-bar cut; `scanning/regime_scan.regime_for_pass` computes or
  reads `D` once per pass, writes `market_regime_days` once
  (`MarketRegimeRepository.insert_once`) and only the winning insert enqueues
  the `bear_regime` notice (`scanning/regime_notices.py`).
  `planning/params.regime_asof` + `stamp_entry_context` stamp `bear_regime` /
  `regime_action`; `presentation/regime_text.py` is the one vocabulary for
  the alert `Trend` line, the notice, `GET /api/v1/market/regime` and the SPA
  banner/chip. Shadow only: nothing blocks, sizes, scores or cancels a plan.
  `BEAR_REGIME_MODE=off` is byte-identical (no fetch, row, stamp, line,
  notice or banner). Drift guard: `scripts/reports/regime_parity.py`.
```

- [ ] **Step 6: Mirror to Codex**

`AGENTS.md`: change the pointer line ``- `architecture.md`: changing `swingbot/core`, plan engine or scan pipeline.`` to:

```markdown
- `architecture.md`: changing `swingbot/core`, plan engine, scan pipeline or the bear-regime shadow (v239, `BEAR_REGIME_MODE`; never a gate).
```

In its Commands block, directly after the `shadow_parity_report.py` line, add:

```text
python scripts/reports/regime_parity.py               # v239: stored market_regime_days vs a cache replay (boundary days reported, not failed)
```

Run: `python scripts/dev/sync_codex.py`
Expected: exit 0; `git status --short .agents/` shows `M .agents/skills/alert-surface/SKILL.md` and nothing else under `.agents/` or `.codex/`.

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: `0 failed`.

- [ ] **Step 7: Check every cited name exists**

Run: `git grep -nE "def (regime_fields|regime_for_pass|regime_asof|shadow_action|alert_line|session_pair|cut_completed|insert_once|build_regime_embed|confirmed_episodes)\b" -- swingbot`
Expected: one hit for each of the ten names. A missing one means an earlier task is not merged: stop and report it, never edit the docs to the code as it is.

Run: `git grep -n "REGIME_FIELD\|BEAR_REGIME_MODE" -- swingbot/core/scanning/alert_embeds.py swingbot/config.py`
Expected: at least one hit in each file.

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/alert-surface/SKILL.md .agents/skills/alert-surface/SKILL.md docs/claude/architecture.md AGENTS.md docs/guide/07-trade-plan.md docs/guide/01-what-it-is.md docs/guide/03-pipeline.md tests/admin/test_guide_chapter_text.py
git commit -m "docs(v239): alert-surface skill, architecture map, guide trend line and Codex mirror"
```

