# v244 — Bear-regime evidence: SPY base-rate study and shadow report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V244-2" -A 400 <this file>`); never read the plan whole.

**Bump:** none (two research/report scripts and a results doc; no running bot or UI code changes)
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v239-bear-regime-engine-shadow-design.md](../specs/2026-11-23-v239-bear-regime-engine-shadow-design.md) — § Evidence the shadow produces; its `## Code reconciliation` section overrides the text above it. This plan is that spec's **second plan**, cut from v239 by the partner on 2026-11-23 (v239 index `## What follows` and `## Handoff`, `2026-11-23-v239-bear-regime-engine-shadow_0-index.md`).
**Results doc:** `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md`. It supersedes the spec's literal `2026-11-23-v239-regime-base-rates.md`, because the study moved from v239 to this plan; ledger row `v244-regime-base-rates`, verdict `DESCRIPTION` (the v190 `v190-v3-rebaseline` precedent).
**Runs after:** v239. The study (V244-1, V244-2) imports V239-1 (`fetch_regime_data`), V239-2/2b (`bear_regime`) and V239-3 (`regime_episodes`) and needs V239-1's real fetch on disk. The shadow report (V244-3) imports no v239 code, but it only has rows once trades stamped by V239-9 (`entry_context.regime_action`) have closed during the shadow soak; until then it prints every row as `too few` with N 0 and the line `No stamped trades yet`, and exits 0.
**Brief:** `.superpowers/briefs/2026-11-23-v239-bear-regime-engine-shadow.md`; seed drafts `.superpowers/plan-drafts-v239/V239-17-study-draft.md`, `.superpowers/plan-drafts-v239/shadow-report-draft.md` (gitignored).

## Goal

v239 gives the bot a daily trend label (`BEAR`, `CORRECTION`, `NORMAL`,
`UNKNOWN`, plus a VIX `stress` flag and a `pullback_trigger`) and runs it in
shadow: it labels, stamps and shows, and never acts. Three live actions wait
on it (slate rows B7 bear short, B8 pullback long, B9 long veto), and each
needs its own screen. Two questions stand between the label and those screens,
and v239 answers neither. First, the label lags by design (the SMA200 slope
turns late): how often does a confirmed CORRECTION in fact become a BEAR, and
how many sessions does the switch take? Second, while the shadow runs, do the
longs it *would* have vetoed actually do worse than the rest?

This plan builds the two tools that answer them. The **base-rate study**
(`scripts/research/regime_base_rates.py`) labels every SPY session from 1993
to the fixed end 2026-11-20 with v239's frozen rules, groups the labels into
the same two-session confirmed episodes the live pass uses, and writes one
results doc. The doc holds episodes per state with median and IQR duration,
the CORRECTION → BEAR conversion rate and the sessions it took, and the
outcome of each named episode (2000, 2008, 2022 expected to convert; 2010,
2011, 2018, 2020 to be checked). It also holds SPY's forward 5/20/60-session
returns from each episode's first day and from pullback days, plus the same
table split by stress. The **shadow report**
(`scripts/reports/regime_shadow_report.py`) joins closed main-ledger trades
with their stamped `regime_action` and prints N, WR, ExpR and sum R per
action. Every row under N = 30 prints as `too few`.

What it leaves alone: no gate, threshold, strategy or plan changes. The study
**describes SPY, not a strategy**: it moves no gate, selects nothing and
spends no validation budget. It is the same kind of result as the v190
re-baseline, a DESCRIPTION (`backtest-methodology.md` § Windows). The shadow
report is **live monitoring, not a screen**: no figure from it licenses
B7–B9. v239's rules, constants and episode definition are inputs here, never
edited.

Success: the study reruns byte-identically from the hash-pinned cache,
refuses a changed cache, and resumes after a kill without relabelling a
finished year. Its committed doc carries the command, the end date and both
input hashes. The report prints every action row, even with no stamped trades,
and never counts an unstamped trade as `none`.

## Architecture

- **Study, inputs and labels (V244-1).** `check_hashes` compares the cache
  CSVs' SHA-256 with `manifest.json` (V239-1) and with `hashes.json`, recorded
  in the work dir at the first run; any difference refuses. Sessions come from
  the SPY bar index (the NYSE calendar covers only 2018–2030; spec
  reconciliation 2). Session `D = index[i]` is labelled from
  `s = index[i − 1]` by `bear_regime.classify` on the last `WINDOW_BARS` bars
  up to `s`, with ^VIX cut to the same dates. `labelled` checkpoints one
  `JsonlCheckpoint` line per calendar year of `D` under
  `data/reports/v244_regime_base_rates/`; a restart skips finished years.
- **Study, reports and doc (V244-2).** `episodes` reuses
  `regime_episodes.confirmed_episodes`, so the study, the live notice and the
  banner's "since" count share one episode rule. Spells, conversion, named
  rows and forward returns are pure functions over the labelled days. `render`
  builds the Markdown and `main` writes it (`utf-8`, `\n`) to
  `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md`.
- **Shadow report (V244-3).** A read-only script over
  `TradeLog().get_trades(status="closed", limit=None, ledger="main")` (or a
  `--trades` JSON file). R comes from `performance.closed_r_multiple`.
- **Docs (V244-4).** The `scripts/research/README.md` row, the v239 bullet in
  `docs/claude/architecture.md` and the `AGENTS.md` Commands block name both
  scripts.

**Tech stack:** Python 3.11, pandas/numpy, pytest.

## Definitions this plan fixes (spec silent)

- **Sessions** come from the SPY bar index. `D = index[i]` for every
  `i ≥ MIN_BARS` through `END` is labelled from `s = index[i − 1]`.
- **Correction spell:** a maximal run of consecutive confirmed episodes keyed
  `CORRECTION` or `CORRECTION_STRESS`. Its outcome is the next confirmed
  episode: `bear`, `normal`, `unknown` (an UNKNOWN episode) or `open` (none
  before `END`). **Conversion rate** = converted ÷ resolved (`bear` +
  `normal`). **Sessions to switch** = the spell's labelled sessions up to the
  BEAR episode's first day.
- **Named episode `Y`:** every spell that starts in `Y`, or converts to BEAR
  in `Y`. A year with none prints `no confirmed CORRECTION`. The `expected`
  column is the spec's label, never an assertion.
- **Forward return** (amended by the partner, 2026-11-26, after the V244-2
  review; this overrides the task text below): episode-first-day rows measure
  SPY's adjusted close from `D` to `D + h`, because `D` is confirmed only once
  `D+1`'s label has read close `D`. `PULLBACK` rows measure from `s` (the close
  the label read) to `s + h`. A horizon past the last bar drops that day for
  that `h` only.
- **Stress split:** the forward table grouped by `(episode key, stress on its
  first day)` and `(PULLBACK, stress that day)`; `stress` None is its own
  group (`stress None`), never folded into calm.

## Global Constraints

- **Shadow and description only.** No gate, threshold, constant, strategy or
  plan behaviour changes. v239's `bear_regime` rules, `Final` constants and
  `regime_episodes.CONFIRM_SESSIONS` are read, never edited. A surprising
  study row (2008 or 2022 not converting) is a finding to report, never a
  reason to edit the rules, the definitions or the doc.
- **Study reproducibility** (spec § Evidence; v239 Global Constraints): fixed
  end `END = "2026-11-20"`. Inputs come only from `data/backtest_cache_regime/`
  (V239-1). The study refuses when a CSV's SHA-256 differs from `manifest.json`
  or from the hashes recorded at its first run. The command, the end date and
  both hashes go in the doc, written with `encoding="utf-8", newline="\n"`. A
  rerun rewrites the same bytes.
- **Checkpoint each finished unit** (CLAUDE.md § Long runs): one fsynced
  `JsonlCheckpoint` line per year of `D`; a restart skips finished years; a
  torn last line is dropped and that year relabelled. The work dir is
  gitignored (`data/reports/`). Never delete `hashes.json` to get past a
  refusal.
- **No lookahead:** the label for `D` reads only bars dated `≤ s`; forward
  returns start at the first close at which the row's membership is known
  (episode rows `D`, pullback rows `s`). One test pins
  the windowed labels to full-frame `classify`; another appends bars and
  asserts no earlier label changes.
- **No closed pre-registration is re-run, no validation budget is spent.**
  The window spans TRAIN and VALIDATION and selects nothing
  (`backtest-methodology.md` § Windows). Like the v190 re-baseline it gets one
  pre-registration ledger row, `v244-regime-base-rates`, verdict `DESCRIPTION`
  (`p` and `exp_r` null, outside the BH family). The row and the doc say it
  describes base rates, is never a lift and selects nothing; a later spec may
  cite only its N and coverage columns, never as evidence for a gate.
- **Shadow report is monitoring:** `MIN_N = 30`. Every `ROWS` entry prints,
  even when empty. Only trades whose `entry_context.regime_action` names a
  `ROWS` entry for their direction count. Legacy (unstamped) and off-mode
  trades are coverage, never `none`. Stamped trades whose R is None count in
  `no_r`. The header says "live monitoring, not a screen".
- **Complexity < 15** on every function (`python -m radon cc -s -n C <file>`
  prints nothing).
- **Tests and suites.** Tests go in `tests/regime/` (suite `market-signals`,
  joined by V239-1), never `tests/scripts/` (near its cap). Scripts import as
  namespace packages (`from scripts.research import regime_base_rates`), as
  `tests/regime/test_regime_parity.py` does; `scripts/` has no `__init__.py`
  and needs none.
- **Verification is narrow:** `python scripts/dev/testrun.py file <test>` per
  task. **No task runs the full suite**; CI does after the push, and Claude
  watches the run until green.
- **Commits:** one subject line, no body, no trailer; scoped per task in the
  plan's worktree. `docs/claude/` edits ship the `AGENTS.md` mirror in the
  same commit.

## Review Focus

1. **The cache was refetched after the first run** (new hashes, matching
   manifest): the study must refuse with exit 2 and write nothing, never mix
   two datasets. V244-1 `test_hashes_are_recorded_on_the_first_run_then_enforced`,
   V244-2 `test_main_refuses_a_refetched_cache_and_writes_nothing`.
2. **The run is killed mid-year** (torn last checkpoint line): the restart
   relabels only the torn year and never raises. V244-1
   `test_labelled_survives_a_torn_last_line`.
3. **A cache shorter than `MIN_BARS`** (no session can be labelled): `main`
   exits 2 with a reason, never an `IndexError` or an empty doc. V244-2
   `test_main_refuses_a_cache_too_short_to_label`.
4. **No stamped trade has closed yet** (the report runs before or early in
   the soak): every row prints `too few` with N 0, the header says
   `No stamped trades yet`, exit 0. V244-3
   `test_no_stamped_trades_yet_prints_every_row_and_says_so`.
5. **An empty forward group** (no pullback day in the window, or a horizon
   past the last bar): the row prints `n/a`, never a division by zero. V244-2
   `test_forward_rows_print_na_for_an_empty_group`.

## Parallelisation

At most 2 implementers at once (session rule). v239's V239-1..V239-3 are
merged first, because V244-1 and V244-2 import them.

- **V244-1 → V244-2 (sequential).** Same module and same test file; V244-2
  appends to both, and its `main` calls V244-1's `check_hashes`, `load_cache`
  and `labelled`.
- **V244-3 ∥ V244-1, V244-2.** Disjoint files
  (`scripts/reports/regime_shadow_report.py`,
  `tests/regime/test_regime_shadow_report.py`) and no contract with the study.
- **V244-4 after V244-2 and V244-3 (sequential).** It cites both scripts'
  final paths and the committed results doc, and smoke-runs the report.

## Task ledger

| ID | Title | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|
| V244-1 | Study inputs: hash refusal, cache load, windowed labels, per-year checkpoint | opus | C `scripts/research/regime_base_rates.py`, C `tests/regime/test_regime_base_rates.py` | `END = "2026-11-20"`; `HORIZONS = (5, 20, 60)`; `NAMED: dict[int, str]`; `WINDOW_BARS = br.MIN_BARS + 40`; `CORRECTION_KEYS`; `WORK_DIR = ROOT / "data/reports/v244_regime_base_rates"`; `OUT = ROOT / "docs/superpowers/results/2026-11-23-v244-regime-base-rates.md"`; `HASHES = "hashes.json"`; `CHECKPOINT = "labels.jsonl"`; `check_hashes(cache_dir: Path, work_dir: Path) -> str \| None`; `load_cache(cache_dir: Path) -> tuple[DataFrame, DataFrame]`; `label_series(spy, vix) -> list[RegimeDay]`; `label_year(spy, vix, year: int) -> list[RegimeDay]`; `labelled(spy, vix, work_dir: Path) -> list[RegimeDay]` (sorted by `session_date`); test helpers `_frames(n=300, start="2024-01-01")`, `_cache(tmp_path, n=300)` |
| V244-2 | Study reports, results doc and `main`; the real run | opus | M `scripts/research/regime_base_rates.py`, M `tests/regime/test_regime_base_rates.py`, C `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md` | `episodes(days) -> list[Episode]`; `episode_table(eps) -> list[dict]`; `correction_spells(eps) -> list[dict]`; `conversion(spells) -> dict`; `named_rows(spells) -> list[dict]`; `forward_returns(spy, dates, horizons=HORIZONS) -> dict[int, list[float]]`; `forward_rows(spy, groups: dict[str, list]) -> list[list[str]]`; `render(days, eps, spells, spy, hashes, command) -> str`; `main(argv=None) -> int` (0 written, 2 refused) |
| V244-3 | Regime shadow report (live monitoring, never a screen) | sonnet | C `scripts/reports/regime_shadow_report.py`, C `tests/regime/test_regime_shadow_report.py` | `MIN_N = 30`; `ROWS`; `summarise(trades) -> list[dict]`; `coverage(trades) -> dict` (`closed`, `stamped`, `no_r`); `render(rows, cover=None) -> str`; `main(argv=None) -> int` |
| V244-4 | Ledger DESCRIPTION row, research README, architecture map, Codex mirror; report smoke run and pipeline handoff | haiku | M `docs/superpowers/results/preregistration-ledger.jsonl`, M `tests/regime/test_regime_base_rates.py`, M `scripts/research/README.md` (created by v239 V239-1), M `docs/claude/architecture.md`, M `AGENTS.md` | ledger row `v244-regime-base-rates` |

## Handoff

- 2026-11-23: plan written as one file (4 tasks). The results doc is named
  for this plan (`v244`), following the v239 index's What follows
  (`<date>-<vN>-regime-base-rates.md`); the spec's literal
  `2026-11-23-v239-regime-base-rates.md` predates the cut.
- 2026-11-26: CLOSED OUT, all four tasks merged. Panel (veteran-trader,
  quant-engineer, ux-designer) found nothing blocking; advisories are in the
  SDD progress ledger. Study cache and work dir copied to the main tree's
  `data/`. Finding: no confirmed CORRECTION spell leads into the 2008 BEAR.
- 2026-11-26: V244-1 and V244-2 done. Partner moved episode-row forward returns
  to start at close `D` (Definitions). The study's cache and `hashes.json` are
  gitignored: copy them to the main tree before removing the worktree.

# Phase 1 — Base-rate study

### Task V244-1: Study inputs: hash refusal, cache load, windowed labels, per-year checkpoint

**Model:** opus — the window cut decides what each label could see (no-lookahead territory), and a resume that mixes two caches silently corrupts every number B7–B9 will be argued from.

**Why:** the label is a guess until its episode resolves (spec § Risks: "the label lags"). Before any rate can be measured, every SPY session since 1993 needs v239's label, computed only from bars dated `≤ s`, from one hash-pinned dataset, and resumable per year. This task builds that labelled series; V244-2 turns it into the reports.

**Files:**
- Create: `scripts/research/regime_base_rates.py`
- Create: `tests/regime/test_regime_base_rates.py` (suite `market-signals`)

**Interfaces:**
- Consumes: `bear_regime.classify(spy, vix, *, last_session, session_date, spy_provider=None, vix_provider=None) -> RegimeDay`; `RegimeDay` (`to_row() -> dict` with the row columns plus `doc`, `RegimeDay.from_row(row)`; fields `session_date`, `last_bar_date`, `state`, `stress`, `pullback_trigger`, `sma200`, `sma50_lag5`, `vix_max5`); `MIN_BARS = 220`, `SPY = "SPY"`, `VIX = "^VIX"` (v239 V239-2/2b, `swingbot/core/market/bear_regime.py`). `regime_episodes.CORRECTION_KEY`, `CORRECTION_STRESS_KEY` (V239-3, `swingbot/core/market/regime_episodes.py`). `fetch_regime_data.CACHE_DIR`, `END`, `SYMBOLS = ("SPY", "^VIX")`, `MANIFEST = "manifest.json"` (`{"symbols": {sym: {"sha256", "rows", "first", "last"}}, "command", "fetched_at"}`), `csv_path(cache_dir, symbol) -> Path`, `sha256_file(path) -> str`, `write_manifest(cache_dir, frames, command) -> dict` (V239-1, `scripts/data/fetch_regime_data.py`). `scripts.reports.reconcile.checkpoint.JsonlCheckpoint(path)` (existing: `done() -> set[str]`, `append(key, row)` fsynced with `allow_nan=False`, `rows() -> list[dict]` latest row per key; a torn last line is truncated on open).
- Produces (ledger contract, final): `END = "2026-11-20"`; `HORIZONS = (5, 20, 60)`; `NAMED = {2000: "convert", 2008: "convert", 2022: "convert", 2010: "check", 2011: "check", 2018: "check", 2020: "check"}`; `WINDOW_BARS = br.MIN_BARS + 40`; `CORRECTION_KEYS = (ep.CORRECTION_KEY, ep.CORRECTION_STRESS_KEY)`; `WORK_DIR`, `OUT`, `HASHES = "hashes.json"`, `CHECKPOINT = "labels.jsonl"`; `check_hashes(cache_dir, work_dir) -> str | None` (None = go; a string = the refusal reason); `load_cache(cache_dir) -> (spy, vix)` cut at `END`; `label_series(spy, vix) -> list[RegimeDay]`; `label_year(spy, vix, year) -> list[RegimeDay]`; `labelled(spy, vix, work_dir) -> list[RegimeDay]`. Test helpers `_frames`, `_cache` (V244-2 reuses them in the same file).

- [ ] **Step 1: Check the v239 inputs exist**

Run: `git grep -nE "^def (classify|csv_path|sha256_file|write_manifest|confirmed_episodes|episode_key)\b|^(MIN_BARS|CORRECTION_STRESS_KEY|SYMBOLS)\b" -- swingbot/core/market scripts/data`
Expected: a hit for each of the nine names. A missing one means v239 is not merged: stop and report it, never stub it.

- [ ] **Step 2: Write the failing test**

Create `tests/regime/test_regime_base_rates.py`:

```python
"""v244 V244-1/V244-2: the SPY base-rate study (spec v239 § Evidence) on
synthetic series: hash refusal, windowed labels, per-year checkpoint, reports."""
import json

import numpy as np
import pandas as pd
import pytest

from scripts.research import regime_base_rates as rbr
from swingbot.core.market import bear_regime as br


def _frames(n=300, start="2024-01-01"):
    idx = pd.bdate_range(start, periods=n, name="Date")
    close = np.concatenate([np.linspace(100, 160, 240), np.linspace(160, 140, 30),
                            np.linspace(140, 152, max(n - 270, 0))])[:n]
    vix = np.concatenate([np.full(240, 15.0), np.linspace(15, 32, 30),
                          np.linspace(32, 18, max(n - 270, 0))])[:n]
    spy = pd.DataFrame({"Open": close, "High": close + 1.0, "Low": close - 1.0, "Close": close,
                        "Volume": 1e6}, index=idx)
    vix = pd.DataFrame({"Open": vix, "High": vix, "Low": vix, "Close": vix, "Volume": 0.0}, index=idx)
    return spy, vix


def _cache(tmp_path, n=300, start="2024-01-01"):
    spy, vix = _frames(n, start)
    cache = tmp_path / "cache"
    cache.mkdir()
    for symbol, frame in ((br.SPY, spy), (br.VIX, vix)):
        frame.to_csv(rbr.frd.csv_path(cache, symbol), lineterminator="\n")
    rbr.frd.write_manifest(cache, {br.SPY: spy, br.VIX: vix}, "test")
    return cache


def test_constants():
    assert rbr.END == "2026-11-20" == rbr.frd.END
    assert rbr.HORIZONS == (5, 20, 60)
    assert list(rbr.NAMED) == [2000, 2008, 2022, 2010, 2011, 2018, 2020]
    assert {y for y, e in rbr.NAMED.items() if e == "convert"} == {2000, 2008, 2022}
    assert rbr.WINDOW_BARS == br.MIN_BARS + 40
    assert rbr.WORK_DIR.name == "v244_regime_base_rates"
    assert rbr.OUT.name == "2026-11-23-v244-regime-base-rates.md"


def test_windowed_labels_equal_full_frame_classify():
    spy, vix = _frames(320)
    days = rbr.label_series(spy, vix)
    assert days[0].session_date == spy.index[br.MIN_BARS].date()
    assert days[-1].session_date == spy.index[-1].date()
    for i in (br.MIN_BARS, 265, 300, len(spy) - 1):
        got = days[i - br.MIN_BARS]
        full = br.classify(spy, vix, last_session=spy.index[i - 1].date(),
                           session_date=spy.index[i].date(),
                           spy_provider="yfinance", vix_provider="yfinance")
        assert (got.state, got.stress, got.pullback_trigger, got.last_bar_date) == (
            full.state, full.stress, full.pullback_trigger, full.last_bar_date)
        assert (got.sma200, got.sma50_lag5, got.vix_max5) == pytest.approx(
            (full.sma200, full.sma50_lag5, full.vix_max5))


def test_appending_bars_never_changes_earlier_labels():
    spy, vix = _frames(320)
    short = rbr.label_series(spy.iloc[:290], vix.iloc[:290])
    longer = rbr.label_series(spy, vix)[:len(short)]
    assert [d.to_row() for d in short] == [d.to_row() for d in longer]


def test_label_series_on_a_frame_shorter_than_min_bars_is_empty():
    spy, vix = _frames(br.MIN_BARS)
    assert rbr.label_series(spy, vix) == []


def test_label_year_keeps_only_that_year():
    spy, vix = _frames()
    assert {d.session_date.year for d in rbr.label_year(spy, vix, 2025)} == {2025}
    assert rbr.label_year(spy, vix, 2030) == []


def test_load_cache_cuts_at_end(tmp_path):
    cache = _cache(tmp_path, n=300, start="2026-01-01")
    spy, vix = rbr.load_cache(cache)
    assert spy.index[-1] <= pd.Timestamp(rbr.END) and vix.index[-1] <= pd.Timestamp(rbr.END)
    assert spy.index.is_monotonic_increasing


def test_hashes_are_recorded_on_the_first_run_then_enforced(tmp_path):
    cache, work = _cache(tmp_path), tmp_path / "work"
    assert rbr.check_hashes(cache, work) is None
    recorded = json.loads((work / rbr.HASHES).read_text(encoding="utf-8"))
    assert recorded[br.SPY] == rbr.frd.sha256_file(rbr.frd.csv_path(cache, br.SPY))
    assert rbr.check_hashes(cache, work) is None
    (work / rbr.HASHES).write_text(json.dumps({**recorded, br.SPY: "0" * 64}), encoding="utf-8")
    assert "recorded at its first run" in rbr.check_hashes(cache, work)


def test_a_cache_that_differs_from_its_manifest_is_refused(tmp_path):
    cache = _cache(tmp_path)
    with open(rbr.frd.csv_path(cache, br.VIX), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("2025-12-31,1,1,1,1,0\n")
    assert "manifest.json" in rbr.check_hashes(cache, tmp_path / "work")
    assert not (tmp_path / "work" / rbr.HASHES).exists()


def test_a_missing_cache_file_is_refused(tmp_path):
    assert "fetch_regime_data.py" in rbr.check_hashes(tmp_path / "none", tmp_path / "work")


def test_labelled_checkpoints_per_year_and_resumes(tmp_path, monkeypatch):
    spy, vix = _frames()
    work = tmp_path / "work"
    first = rbr.labelled(spy, vix, work)
    assert first == rbr.label_series(spy, vix)
    lines = (work / rbr.CHECKPOINT).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["key"] for line in lines] == ["2024", "2025"]
    calls = []
    monkeypatch.setattr(rbr, "label_year", lambda *a: calls.append(a) or [])
    assert rbr.labelled(spy, vix, work) == first
    assert calls == []


def test_labelled_survives_a_torn_last_line(tmp_path):
    spy, vix = _frames()
    work = tmp_path / "work"
    first = rbr.labelled(spy, vix, work)
    path = work / rbr.CHECKPOINT
    kept = path.read_text(encoding="utf-8").splitlines()[0]
    path.write_text(kept + "\n" + '{"key": "2025", "row": {"da', encoding="utf-8", newline="\n")
    assert rbr.labelled(spy, vix, work) == first
    assert [json.loads(line)["key"] for line in path.read_text(encoding="utf-8").splitlines()] == [
        "2024", "2025"]
```

- [ ] **Step 3: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_base_rates.py`
Expected: errors, `ModuleNotFoundError` for `scripts.research.regime_base_rates`.

- [ ] **Step 4: Write the inputs and labels half of the study**

Create `scripts/research/regime_base_rates.py`:

```python
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
```

Then, in the same file, the functions below. Bodies are given where the window arithmetic or the refusal order matters; keep them as written.

```python
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
```

And `labelled(spy, vix, work_dir: Path) -> list[br.RegimeDay]`: open `JsonlCheckpoint(Path(work_dir) / CHECKPOINT)`; for each year from `_years(spy)` (enumerated from 1) whose `str(year)` is not in `done()`, `append(str(year), {"days": [_to_json(d) for d in label_year(spy, vix, year)]})` and print `f"labelled {year} ({n}/{len(years)}, {100 * n // len(years)}%)"` with `flush=True`. Then rebuild every day from `checkpoint.rows()` (`row["days"]`, each through `br.RegimeDay.from_row`) and return them sorted by `session_date`. Labels always come back through the checkpoint, so a fresh run and a resumed run return equal lists.

- [ ] **Step 5: Run the test to see it pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_base_rates.py`
Expected: `0 failed`. If `test_windowed_labels_equal_full_frame_classify` fails, the window cuts an input `classify` reads: widen `WINDOW_BARS`, never loosen the test. If `test_labelled_checkpoints_per_year_and_resumes` fails on `first == label_series(...)`, a field does not round-trip through `to_row`/`from_row` and JSON: report it (it is v239's contract), never compare a subset.

Run: `python -m radon cc -s -n C scripts/research/regime_base_rates.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/research/regime_base_rates.py tests/regime/test_regime_base_rates.py
git commit -m "research(v244): base-rate study inputs: hash refusal, windowed labels, per-year checkpoint"
```

### Task V244-2: Study reports, results doc and `main`; the real run

**Model:** opus — the spell, conversion and forward-return definitions are the numbers B7–B9 will be argued from, and a forward window that starts one bar late reads the future.

**Why:** spec § Evidence asks for four reports on the labelled series: episodes per state (count, median, IQR), the CORRECTION → BEAR conversion rate with sessions to switch and the named episodes, SPY forward 5/20/60-session returns from episode first days and pullback days, and the same split by stress. This task computes them over V244-1's labels, writes the results doc and runs the study once on the real cache. The doc is named for this plan (`...-v244-regime-base-rates.md`); the spec's literal `2026-11-23-v239-regime-base-rates.md` is superseded because the study moved from v239 to v244. V244-4 records its ledger row.

**Files:**
- Modify: `scripts/research/regime_base_rates.py` (append; created by V244-1)
- Modify: `tests/regime/test_regime_base_rates.py` (append; created by V244-1)
- Create: `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md` (written by the script in Step 6, committed as written)

**Interfaces:**
- Consumes: V244-1's `END`, `HORIZONS`, `NAMED`, `CORRECTION_KEYS`, `WORK_DIR`, `OUT`, `HASHES`, `check_hashes`, `load_cache`, `labelled`, test helpers `_frames`, `_cache`. v239 V239-3 `regime_episodes`: `episode_key(state, stress) -> str`, `confirmed_episodes(days: Sequence[tuple[date, str]]) -> list[Episode]` (oldest first, flicker merged), `Episode(key, start, end, sessions)`, `EPISODE_KEYS = ("BEAR", "CORRECTION_STRESS", "CORRECTION", "NORMAL", "UNKNOWN")`, `BEAR_KEY`, `NORMAL_KEY`, `CORRECTION_STRESS_KEY`, `CONFIRM_SESSIONS = 2`. `bear_regime.NORMAL`, `CORRECTION`, `BEAR`, `UNKNOWN`, `RegimeDay` (V239-2).
- Produces (ledger contract, final; V244-4 cites the script and the doc by path): `episodes(days) -> list[Episode]`; `episode_table(eps) -> list[dict]` (`key`, `count`, `median`, `q1`, `q3`; None when empty); `correction_spells(eps) -> list[dict]` (`start`, `end`, `sessions`, `stress`, `outcome` in `bear`/`normal`/`unknown`/`open`, `switch`); `conversion(spells) -> dict` (`spells`, `resolved`, `converted`, `rate`, `median_sessions`); `named_rows(spells) -> list[dict]`; `forward_returns(spy, dates, horizons=HORIZONS) -> dict[int, list[float]]`; `forward_rows(spy, groups) -> list[list[str]]`; `render(days, eps, spells, spy, hashes, command) -> str`; `main(argv=None) -> int` (0 written, 2 refused or nothing to label).

- [ ] **Step 1: Write the failing tests**

Append to `tests/regime/test_regime_base_rates.py`:

```python
CODES = {"N": (br.NORMAL, False), "C": (br.CORRECTION, False), "S": (br.CORRECTION, True),
         "c": (br.CORRECTION, None), "B": (br.BEAR, True), "U": (br.UNKNOWN, None)}
# NORMAL x5, one-day CORRECTION flicker, NORMAL x3 -> one NORMAL episode of 9; then
# CORRECTION 4 + CORRECTION_STRESS 3 (one spell of 7) -> BEAR 5; NORMAL 2; CORRECTION 3 -> NORMAL 3.
SEQ = "NNNNN" "C" "NNN" "CCCC" "SSS" "BBBBB" "NN" "CCC" "NNN"


def _days(codes, start="2008-01-02"):
    dates = pd.bdate_range(start, periods=len(codes))
    return [br.RegimeDay(session_date=d.date(), last_bar_date=None, state=CODES[c][0],
                         stress=CODES[c][1]) for d, c in zip(dates, codes)]


def test_episodes_merge_flicker():
    eps = rbr.episodes(_days(SEQ))
    assert [(e.key, e.sessions) for e in eps] == [
        ("NORMAL", 9), ("CORRECTION", 4), ("CORRECTION_STRESS", 3), ("BEAR", 5),
        ("NORMAL", 2), ("CORRECTION", 3), ("NORMAL", 3)]


def test_episode_table():
    table = {row["key"]: row for row in rbr.episode_table(rbr.episodes(_days(SEQ)))}
    assert list(table) == ["BEAR", "CORRECTION_STRESS", "CORRECTION", "NORMAL", "UNKNOWN"]
    assert (table["NORMAL"]["count"], table["NORMAL"]["median"],
            table["NORMAL"]["q1"], table["NORMAL"]["q3"]) == (3, 3.0, 2.5, 6.0)
    assert (table["CORRECTION"]["count"], table["CORRECTION"]["median"]) == (2, 3.5)
    assert table["UNKNOWN"] == {"key": "UNKNOWN", "count": 0, "median": None, "q1": None, "q3": None}


def test_correction_spells_and_conversion():
    spells = rbr.correction_spells(rbr.episodes(_days(SEQ)))
    assert [(s["sessions"], s["stress"], s["outcome"]) for s in spells] == [
        (7, True, "bear"), (3, False, "normal")]
    assert rbr.conversion(spells) == {"spells": 2, "resolved": 2, "converted": 1,
                                      "rate": 0.5, "median_sessions": 7.0}


def test_open_and_unknown_spells_are_not_resolved():
    open_spell = rbr.correction_spells(rbr.episodes(_days("NNN" "CCC")))
    unknown = rbr.correction_spells(rbr.episodes(_days("NNN" "CCC" "UUU")))
    assert [s["outcome"] for s in open_spell + unknown] == ["open", "unknown"]
    assert rbr.conversion(open_spell + unknown) == {"spells": 2, "resolved": 0, "converted": 0,
                                                    "rate": None, "median_sessions": None}
    assert rbr.conversion([]) == {"spells": 0, "resolved": 0, "converted": 0,
                                  "rate": None, "median_sessions": None}


def test_named_rows_cover_every_spec_year():
    rows = rbr.named_rows(rbr.correction_spells(rbr.episodes(_days(SEQ))))
    assert [r["year"] for r in rows if r["start"] is None] == [2000, 2022, 2010, 2011, 2018, 2020]
    assert {r["outcome"] for r in rows if r["start"] is None} == {"no confirmed CORRECTION"}
    assert [(r["outcome"], r["expected"]) for r in rows if r["year"] == 2008] == [
        ("bear", "convert"), ("normal", "convert")]


def test_forward_returns_start_at_the_close_the_label_read():
    idx = pd.bdate_range("2024-01-01", periods=80)
    spy = pd.DataFrame({"Close": np.arange(100.0, 180.0)}, index=idx)
    fwd = rbr.forward_returns(spy, [idx[10].date(), idx[70].date()])
    assert fwd[5] == pytest.approx([100 * (114 / 109 - 1), 100 * (174 / 169 - 1)])
    assert fwd[20] == pytest.approx([100 * (129 / 109 - 1)])      # s+20 past the end for D = idx[70]
    assert fwd[60] == pytest.approx([100 * (169 / 109 - 1)])


def test_forward_returns_skip_a_day_with_no_prior_bar_or_off_the_index():
    idx = pd.bdate_range("2024-01-01", periods=80)
    spy = pd.DataFrame({"Close": np.arange(100.0, 180.0)}, index=idx)
    assert rbr.forward_returns(spy, [idx[0].date(), pd.Timestamp("2023-06-01").date()]) == {
        5: [], 20: [], 60: []}


def test_forward_rows_print_na_for_an_empty_group():
    spy, _ = _frames()
    assert rbr.forward_rows(spy, {"PULLBACK": []}) == [
        ["PULLBACK", str(h), "0", "n/a", "n/a", "n/a"] for h in rbr.HORIZONS]


def test_render_keeps_stress_none_apart():
    days = _days("NNN" "cc" "NNN")
    spy = pd.DataFrame({"Close": np.arange(100.0, 100.0 + len(days) + 70)},
                       index=pd.bdate_range("2008-01-01", periods=len(days) + 70))
    eps = rbr.episodes(days)
    text = rbr.render(days, eps, rbr.correction_spells(eps), spy, {"SPY": "a" * 64}, "cmd")
    assert "CORRECTION / stress None" in text and "CORRECTION / stress False" not in text


def test_main_writes_the_doc_and_a_rerun_rewrites_the_same_bytes(tmp_path, monkeypatch):
    cache, work, out = _cache(tmp_path), tmp_path / "work", tmp_path / "doc.md"
    argv = ["--cache-dir", str(cache), "--work-dir", str(work), "--out", str(out)]
    assert rbr.main(argv) == 0
    text = out.read_text(encoding="utf-8")
    assert "v244" in text and "DESCRIPTION" in text and "moves no gate" in text and rbr.END in text
    assert "never a lift" in text and "only its N and coverage columns" in text
    assert "v244-regime-base-rates" in text
    assert rbr.frd.sha256_file(rbr.frd.csv_path(cache, br.SPY)) in text
    assert rbr.frd.sha256_file(rbr.frd.csv_path(cache, br.VIX)) in text
    assert b"\r\n" not in out.read_bytes()
    calls = []
    monkeypatch.setattr(rbr, "label_year", lambda *a: calls.append(a) or [])
    assert rbr.main(argv) == 0
    assert calls == [] and out.read_text(encoding="utf-8") == text


def test_main_refuses_a_refetched_cache_and_writes_nothing(tmp_path, capsys):
    cache, work, out = _cache(tmp_path), tmp_path / "work", tmp_path / "doc.md"
    assert rbr.check_hashes(cache, work) is None
    with open(rbr.frd.csv_path(cache, br.SPY), "a", encoding="utf-8", newline="\n") as fh:
        fh.write("2025-12-31,1,1,1,1,0\n")
    spy, vix = _frames()
    rbr.frd.write_manifest(cache, {br.SPY: spy, br.VIX: vix}, "refetch")
    assert rbr.main(["--cache-dir", str(cache), "--work-dir", str(work), "--out", str(out)]) == 2
    assert not out.exists() and "refusing" in capsys.readouterr().err


def test_main_refuses_a_cache_too_short_to_label(tmp_path, capsys):
    cache, out = _cache(tmp_path, n=200), tmp_path / "doc.md"
    argv = ["--cache-dir", str(cache), "--work-dir", str(tmp_path / "work"), "--out", str(out)]
    assert rbr.main(argv) == 2
    assert not out.exists() and "no session to label" in capsys.readouterr().err
```

`test_forward_rows_print_na_for_an_empty_group` writes the comprehension as the expected value on purpose: three rows, one per horizon, in `HORIZONS` order.

- [ ] **Step 2: Run them to see them fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_base_rates.py`
Expected: the V244-1 tests pass; the new ones fail with `AttributeError: module ... has no attribute 'episodes'` (and `main`, `render`, `forward_rows`).

- [ ] **Step 3: Add the episode, spell and return reports**

In `scripts/research/regime_base_rates.py`, add `import argparse` and `import numpy as np` to the imports, then append:

```python
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


def _in_year(spell: dict, year: int) -> bool:
    return spell["start"].year == year or (spell["outcome"] == "bear" and spell["switch"].year == year)
```

`conversion(spells)`: `resolved` = spells with outcome `bear` or `normal`; `converted` = the `sessions` of the `bear` ones; `rate = round(len(converted) / len(resolved), 3)` or None with nothing resolved; `median_sessions = float(np.median(converted))` or None.

`named_rows(spells)`: for each `(year, expected)` in `NAMED` order, one row `{"year": year, "expected": expected, **spell}` per spell with `_in_year(spell, year)`; with none, one row `{"year", "expected", "start": None, "sessions": None, "outcome": "no confirmed CORRECTION", "switch": None}`.

`forward_returns(spy, dates, horizons=HORIZONS)`: closes as a float array, `position = {ts.date(): i for i, ts in enumerate(spy.index)}`; for each day, `s = position[day] - 1`; skip the day when it is not in `position` or `s < 0`; for each `h`, append `100.0 * (closes[s + h] / closes[s] - 1.0)` only when `s + h < len(closes)`. Returns `{h: [...]}` for every `h`, empty lists included.

`forward_rows(spy, groups)`: per group name (dict order) and per `h` in `HORIZONS`, the row `[name, str(h), str(len(vals)), mean, median, up]` with mean and median formatted `f"{x:+.2f}"` and up = `f"{100.0 * count(v > 0) / len(vals):.1f}"`; with no values the three stats are `"n/a"`.

- [ ] **Step 4: Add the doc and `main`**

Append:

```python
def _groups(days: list[br.RegimeDay], eps: list[ep.Episode]) -> tuple[dict, dict]:
    by_date = {d.session_date: d for d in days}
    pullbacks = [d.session_date for d in days if d.pullback_trigger]
    plain = {key: [e.start for e in eps if e.key == key] for key in ep.EPISODE_KEYS}
    plain["PULLBACK"] = pullbacks
    split: dict[str, list] = {}
    for e in eps:
        split.setdefault(f"{e.key} / stress {by_date[e.start].stress}", []).append(e.start)
    for day in pullbacks:
        split.setdefault(f"PULLBACK / stress {by_date[day].stress}", []).append(day)
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
            "**Forward return:** percent change of SPY's adjusted close from `s` (the close the "
            "label read) to `s + h` sessions.", ""]
```

`render(days, eps, spells, spy, hashes, command) -> str`: `"\n".join` of `_head(...)`, then these sections in order, each a `## ` heading, a blank line and a `_table`:
1. `## Episodes per state`: columns `Episode | Count | Median sessions | Q1 | Q3` from `episode_table(eps)`.
2. `## CORRECTION → BEAR conversion`: first the line `Spells {spells} · resolved {resolved} · converted {converted} · rate {rate} · median sessions to switch {median_sessions}` and a blank line, then columns `Start | End | Sessions | Stress | Outcome | Next episode` (one row per spell; `switch` is the next episode's first day).
3. `## Named episodes`: columns `Year | Expected | Spell start | Sessions | Outcome | Next episode` from `named_rows(spells)`.
4. `## SPY forward returns from episode first days and pullback days`: columns `Group | h | N | Mean % | Median % | Up %` from `forward_rows(spy, plain)`.
5. `## The same, split by stress`: the same columns from `forward_rows(spy, split)`.

Split it into helpers if radon reports C or worse; the function's complexity stays under 15 either way.

`main(argv=None) -> int`: argparse `--cache-dir` (default `frd.CACHE_DIR`), `--work-dir` (default `WORK_DIR`), `--out` (default `OUT`), all `type=Path`. Then:
1. `problem = check_hashes(...)`; on a problem print `f"error: {problem}"` to stderr and return 2.
2. `spy, vix = load_cache(...)`; `days = labelled(spy, vix, args.work_dir)`; with no days print `f"error: no session to label: the cache holds fewer than {br.MIN_BARS + 1} SPY bars"` to stderr and return 2, writing nothing.
3. `eps = episodes(days)`; hashes read back from `args.work_dir / HASHES`; `command = " ".join(["python scripts/research/regime_base_rates.py", *(sys.argv[1:] if argv is None else argv)])`.
4. Create `args.out.parent`, write `render(days, eps, correction_spells(eps), spy, hashes, command)` with `encoding="utf-8", newline="\n"`, print `f"wrote {args.out}"`, return 0.

End the file with `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_base_rates.py`
Expected: `0 failed`.

Run: `python -m radon cc -s -n C scripts/research/regime_base_rates.py`
Expected: no output.

- [ ] **Step 6: Run the real study once**

V239-1's real fetch must have run (`data/backtest_cache_regime/manifest.json` exists; if not, run `python scripts/data/fetch_regime_data.py` first, which is V239-1 Step 7). From the repo root:

Run: `python scripts/research/regime_base_rates.py`
Expected: `labelled 1993 (1/34, 2%)` … `labelled 2026 (34/34, 100%)`, then `wrote …/docs/superpowers/results/2026-11-23-v244-regime-base-rates.md`, exit 0, in well under a minute. The first labelled session is about 1993-11 (1993-01-29 plus 220 SPY bars). A rerun prints no `labelled` lines and rewrites the same bytes: `git diff --exit-code -- docs/superpowers/results/2026-11-23-v244-regime-base-rates.md` stays clean after the second run (stage the doc first). Exit 2 with `refusing` means the cache changed since the recorded run: report it, and never delete `data/reports/v244_regime_base_rates/hashes.json` to get past it.

Read the doc's **Named episodes** table. If 2008 or 2022 does not show a spell converting to BEAR, or the 2026 spell is not `open`, record that in your report as a finding. The study describes the rules as they are: never edit the doc, the rules or the definitions to make it read as expected.

- [ ] **Step 7: Commit**

```bash
git add scripts/research/regime_base_rates.py tests/regime/test_regime_base_rates.py docs/superpowers/results/2026-11-23-v244-regime-base-rates.md
git commit -m "research(v244): SPY base rates under the v239 bear-regime rules, 1993 to 2026-11-20"
```

# Phase 2 — Shadow report and docs

### Task V244-3: Regime shadow report (live monitoring, never a screen)

**Model:** sonnet — a read-only report inside one script, with the rows, the floor and the counting rule fixed by the spec and this task.

**Why:** spec § Evidence: while the shadow runs, the partner needs to see whether longs the engine *would* have vetoed do worse than the rest, without that view turning into a licence. The report joins closed main-ledger trades with their stamped `entry_context.regime_action` and prints N, WR, ExpR and sum R per action, `too few` under N = 30, and a header that says it is monitoring, not a screen.

**Files:**
- Create: `scripts/reports/regime_shadow_report.py`
- Create: `tests/regime/test_regime_shadow_report.py` (suite `market-signals`)

**Interfaces:**
- Consumes (existing): `swingbot.core.tracking.performance.closed_r_multiple(t: dict) -> float | None` (`performance.py:411`; reads `direction`, `entry`, `stop_loss`, `exit_price` or `legs`; None on a missing price or a direction other than `bullish`/`bearish`); `TradeLog().get_trades(status="closed", limit=None, ledger="main")` (`performance.py:1411`; the default `limit=20` truncates, so `limit=None` is required); `swingbot.core.tracking.ledger.is_main(trade) -> bool` (`ledger.py:28`; not weak and regular lane). The stamped keys `entry_context.bear_regime` and `entry_context.regime_action` (values `would_veto`, `caution`, `pullback_watch`, `aligned`, `none`) come from v239 V239-9 and are read by name; no v239 import.
- Produces (ledger contract, final): `MIN_N = 30`; `ROWS = (("LONG", "would_veto"), ("LONG", "caution"), ("LONG", "pullback_watch"), ("LONG", "none"), ("SHORT", "aligned"), ("SHORT", "none"))`; `summarise(trades) -> list[dict]` (one dict per `ROWS` entry, in order: `direction`, `action`, `n`, `win_rate`, `expectancy_r`, `sum_r`, `too_few`); `coverage(trades) -> dict` (`closed`, `stamped`, `no_r`); `render(rows, cover=None) -> str`; `main(argv=None) -> int` (always 0).

**Counting rule (spec silent):** a trade counts only when its `regime_action` names a `ROWS` entry for its direction (`bullish` → LONG, `bearish` → SHORT). Unstamped trades (closed before v239, or opened with `BEAR_REGIME_MODE=off`) and mismatched pairs (a SHORT with `pullback_watch`) are coverage only, never `none`. A stamped trade whose R is None counts in `no_r`, never in a row. A win is `R > 0`.

**Before the soak closes a stamped trade** (or when the report runs against a database v239 never wrote to): `stamped` is 0, every row prints `too few` with N 0, and the header adds `No stamped trades yet: no closed main-ledger trade carries regime_action.` Exit 0; an empty report is the measured answer, not an error.

- [ ] **Step 1: Write the failing test**

Create `tests/regime/test_regime_shadow_report.py`:

```python
"""v244 V244-3: the regime shadow report -- live monitoring, never a screen."""
import json

from scripts.reports import regime_shadow_report as rsr


def _trade(direction="bullish", action="would_veto", r=1.0, **extra):
    """A closed trade whose closed_r_multiple is exactly ``r`` (risk = 5)."""
    long = direction == "bullish"
    ctx = {} if action is None else {"bear_regime": "CORRECTION", "regime_action": action}
    trade = {"direction": direction, "entry": 100.0, "stop_loss": 95.0 if long else 105.0,
             "exit_price": 100.0 + (5.0 * r if long else -5.0 * r),
             "status": "closed", "entry_context": ctx}
    trade.update(extra)
    return trade


def _row(rows, direction, action):
    return next(r for r in rows if (r["direction"], r["action"]) == (direction, action))


def test_rows_and_floor_are_the_spec():
    assert rsr.MIN_N == 30
    assert rsr.ROWS == (("LONG", "would_veto"), ("LONG", "caution"), ("LONG", "pullback_watch"),
                        ("LONG", "none"), ("SHORT", "aligned"), ("SHORT", "none"))


def test_every_row_is_present_even_when_empty():
    rows = rsr.summarise([])
    assert [(r["direction"], r["action"]) for r in rows] == list(rsr.ROWS)
    assert all(r["n"] == 0 and r["too_few"] and r["sum_r"] == 0.0 for r in rows)


def test_stats_per_action():
    trades = [_trade(r=2.0)] * 10 + [_trade(r=-1.0)] * 20 + [_trade("bearish", "aligned", 1.5)] * 2
    rows = rsr.summarise(trades)
    veto = _row(rows, "LONG", "would_veto")
    assert (veto["n"], veto["win_rate"], veto["expectancy_r"], veto["sum_r"], veto["too_few"]) == (
        30, 33.33, 0.0, 0.0, False)
    aligned = _row(rows, "SHORT", "aligned")
    assert (aligned["n"], aligned["sum_r"], aligned["too_few"]) == (2, 3.0, True)


def test_a_breakeven_trade_is_not_a_win():
    rows = rsr.summarise([_trade(r=0.0)] * 30)
    assert _row(rows, "LONG", "would_veto")["win_rate"] == 0.0


def test_below_thirty_prints_too_few_instead_of_stats():
    rows = rsr.summarise([_trade("bullish", "caution", 1.0)] * 29)
    assert _row(rows, "LONG", "caution")["too_few"] is True
    line = next(l for l in rsr.render(rows).splitlines() if "caution" in l)
    assert "too few" in line and "29" in line and "ExpR" not in line


def test_thirty_prints_the_stats():
    rows = rsr.summarise([_trade("bullish", "caution", 1.0)] * 30)
    line = next(l for l in rsr.render(rows).splitlines() if "caution" in l)
    assert "too few" not in line and "ExpR +1.00R" in line and "WR 100.00%" in line


def test_unstamped_and_unpriced_trades_are_coverage_not_none():
    trades = [_trade(action=None), _trade("bearish", "pullback_watch"),
              _trade(action="none", exit_price=None), _trade(action="none", r=1.0),
              _trade("sideways", "none")]
    rows = rsr.summarise(trades)
    assert _row(rows, "LONG", "none")["n"] == 1
    assert _row(rows, "SHORT", "none")["n"] == 0
    assert rsr.coverage(trades) == {"closed": 5, "stamped": 2, "no_r": 1}


def test_render_says_it_is_not_a_screen():
    text = rsr.render(rsr.summarise([]), {"closed": 0, "stamped": 0, "no_r": 0})
    assert "live monitoring, not a screen" in text
    assert "closed 0 · stamped 0 · no R 0" in text


def test_no_stamped_trades_yet_prints_every_row_and_says_so():
    trades = [_trade(action=None)] * 4
    text = rsr.render(rsr.summarise(trades), rsr.coverage(trades))
    assert "No stamped trades yet" in text
    assert sum("too few" in line for line in text.splitlines()) == len(rsr.ROWS)
    stamped = [_trade()]
    assert "No stamped trades yet" not in rsr.render(rsr.summarise(stamped), rsr.coverage(stamped))


def test_main_reads_a_trades_file_and_keeps_the_main_ledger(tmp_path, capsys):
    trades = ([_trade(r=1.0)] * 3 + [_trade(r=1.0, ledger="weak")] * 5
              + [_trade(r=1.0, status="open")] * 2)
    path = tmp_path / "trades.json"
    path.write_text(json.dumps(trades), encoding="utf-8")
    assert rsr.main(["--trades", str(path)]) == 0
    assert "closed 3 · stamped 3" in capsys.readouterr().out


def test_main_on_an_empty_trades_file_exits_zero(tmp_path, capsys):
    path = tmp_path / "trades.json"
    path.write_text("[]", encoding="utf-8")
    assert rsr.main(["--trades", str(path)]) == 0
    out = capsys.readouterr().out
    assert "closed 0 · stamped 0 · no R 0" in out and "No stamped trades yet" in out
```

- [ ] **Step 2: Run it to see it fail**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_shadow_report.py`
Expected: errors, `ModuleNotFoundError` for `scripts.reports.regime_shadow_report`.

- [ ] **Step 3: Write the report**

Create `scripts/reports/regime_shadow_report.py`:

```python
"""v244: the bear-regime shadow report (v239 spec § Evidence the shadow produces).

    python scripts/reports/regime_shadow_report.py [--trades trades.json]

Joins closed MAIN-ledger trades with their entry_context.regime_action and
prints N, WR, ExpR and sum R per action: would_veto / caution /
pullback_watch / none (LONG), aligned / none (SHORT). Below MIN_N a row prints
"too few". This is LIVE MONITORING, NOT A SCREEN: no figure from it licenses a
gate (the B9 screen does; pooled-numbers skill).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.tracking import ledger as _ledger  # noqa: E402
from swingbot.core.tracking.performance import closed_r_multiple  # noqa: E402

MIN_N = 30
ROWS = (("LONG", "would_veto"), ("LONG", "caution"), ("LONG", "pullback_watch"),
        ("LONG", "none"), ("SHORT", "aligned"), ("SHORT", "none"))
_SIDE = {"bullish": "LONG", "bearish": "SHORT"}
NO_STAMPS = "No stamped trades yet: no closed main-ledger trade carries regime_action."


def _key(trade: dict) -> tuple[str, str] | None:
    ctx = trade.get("entry_context") or {}
    key = (_SIDE.get(trade.get("direction")), ctx.get("regime_action"))
    return key if key in ROWS else None


def _stats(direction: str, action: str, rs: list[float]) -> dict:
    n = len(rs)
    return {"direction": direction, "action": action, "n": n,
            "win_rate": round(100.0 * sum(1 for r in rs if r > 0) / n, 2) if n else 0.0,
            "expectancy_r": round(sum(rs) / n, 4) if n else 0.0,
            "sum_r": round(sum(rs), 2), "too_few": n < MIN_N}


def summarise(trades: Iterable[dict]) -> list[dict]:
    buckets: dict[tuple[str, str], list[float]] = {key: [] for key in ROWS}
    for trade in trades:
        key = _key(trade)
        r = closed_r_multiple(trade) if key else None
        if r is not None:
            buckets[key].append(r)
    return [_stats(direction, action, buckets[(direction, action)]) for direction, action in ROWS]


def coverage(trades: Iterable[dict]) -> dict:
    trades = list(trades)
    stamped = [t for t in trades if _key(t)]
    return {"closed": len(trades), "stamped": len(stamped),
            "no_r": sum(1 for t in stamped if closed_r_multiple(t) is None)}


def _line(row: dict) -> str:
    head = f"{row['direction']:<6}{row['action']:<16}{row['n']:>5}"
    if row["too_few"]:
        return f"{head}  too few"
    return (f"{head}  WR {row['win_rate']:>6.2f}%  ExpR {row['expectancy_r']:+.2f}R"
            f"  sum {row['sum_r']:+.2f}R")
```

`render(rows, cover=None) -> str`: lines `"Bear-regime shadow report -- live monitoring, not a screen."`, `f"Rows below N = {MIN_N} print 'too few'. No figure here licenses a gate."`, `""`; when `cover` is given, `f"closed {cover['closed']} · stamped {cover['stamped']} · no R {cover['no_r']}"`, then `NO_STAMPS` when `cover["stamped"] == 0`, then `""`; then the column header `f"{'side':<6}{'action':<16}{'N':>5}"` and `_line(row)` per row. Joined with `"\n"` plus a trailing `"\n"`.

`_trades(path: str | None) -> list[dict]`: with a path, the JSON list filtered to `t.get("status", "closed") == "closed" and _ledger.is_main(t)`; without one, a lazy `from swingbot.core.tracking.performance import TradeLog` and `TradeLog().get_trades(status="closed", limit=None, ledger="main")`.

`main(argv=None) -> int`: argparse with `--trades` (help `"JSON list of trade dicts instead of the trades table"`), then `trades = _trades(args.trades)`, `sys.stdout.write(render(summarise(trades), coverage(trades)))`, return 0. End with `if __name__ == "__main__": sys.exit(main())`.

- [ ] **Step 4: Run the test to see it pass**

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_shadow_report.py`
Expected: `0 failed`. If `test_stats_per_action` is off by a rounding step, `closed_r_multiple` rounds to 2 dp: fix the fixture's prices, never the stat.

Run: `python -m radon cc -s -n C scripts/reports/regime_shadow_report.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/regime_shadow_report.py tests/regime/test_regime_shadow_report.py
git commit -m "report(v244): regime shadow report, N/WR/ExpR per would-be action, too few under 30"
```

### Task V244-4: Ledger DESCRIPTION row, research README, architecture map, Codex mirror; report smoke run and pipeline handoff

**Model:** haiku — a ledger append and doc edits with the exact text given, one read-only smoke run and the pipeline note.

**Why:** the study is a recorded DESCRIPTION, so it gets one pre-registration ledger row as the v190 re-baseline did (`v190-v3-rebaseline`; `backtest-methodology.md` § Windows). v239's V239-1 created `scripts/research/README.md` with a placeholder row for this plan's study, and V239-17 wrote the bear-regime bullet in `docs/claude/architecture.md` and the `regime_parity.py` line in `AGENTS.md`. Readers and Codex should find the two evidence scripts in the same places, each labelled for what it is (a DESCRIPTION; monitoring, never a screen). This is also the plan's last task. `Bump: none` means no `VERSION.json` change; the CI pipeline is the gate.

**Files:**
- Modify (created by v239 V239-1): `scripts/research/README.md` (the `regime_base_rates.py` row)
- Modify: `docs/claude/architecture.md` (one sentence at the end of the "Bear-regime shadow (v239)" bullet, added by v239 V239-17)
- Modify: `AGENTS.md` (two lines in the Commands block)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one appended row, through the CLI)
- Modify: `tests/regime/test_regime_base_rates.py` (one test pinning the row; created by V244-1)

**Interfaces:**
- Consumes: `scripts/research/regime_base_rates.py` and `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md` (V244-2); `scripts/reports/regime_shadow_report.py` (V244-3); the v239 bullet and the `regime_parity.py` Commands line (V239-17).
- Consumes (existing): `scripts/reports/preregistration_ledger.py` (CLI: `--id --date --hypothesis --instrument --n --exp-r --p --verdict --record --data-source`; it validates the row, appends it and prints the BH table, where a `DESCRIPTION` row has q null); `swingbot.core.backtesting.instrument.stats.load_ledger(path)`, `LEDGER_PATH`, `ledger_data_source(row)`. `tests/backtesting/test_preregistration_ledger_file.py` already checks every committed row validates and its `record` file exists; no test pins the row count or the DESCRIPTION rows of the committed file, so none needs changing.
- Produces: ledger row `v244-regime-base-rates` (`instrument v1`, `verdict DESCRIPTION`, `exp_r` null, `p` null, `data_source yfinance`). The ledger has no instrument for a SPY description (`stats.INSTRUMENTS`); `v1` (yfinance bars, the closest existing value) is used, and the hypothesis names the real input.

No skill cites a path, symbol or command this plan changes: both scripts are new, and no existing file's behaviour moves. `/close-out` Step 5b confirms it. No guide chapter lists `scripts/research/` or `scripts/reports/` in `sources:`; Step 5 checks that.

- [ ] **Step 1: Check the cited names exist**

Run: `git grep -nE "^def (main|check_hashes|labelled|summarise|coverage)\b" -- scripts/research/regime_base_rates.py scripts/reports/regime_shadow_report.py`
Expected: `main`, `check_hashes`, `labelled` in the study; `main`, `summarise`, `coverage` in the report.

Run: `git grep -n "regime_base_rates.py\|Bear-regime shadow (v239)\|regime_parity.py" -- scripts/research/README.md docs/claude/architecture.md AGENTS.md`
Expected: the README placeholder row, the architecture bullet and the `AGENTS.md` Commands line. A missing one means V239-1 or V239-17 is not merged: stop and report it.

Run: `test -f docs/superpowers/results/2026-11-23-v244-regime-base-rates.md && echo present`
Expected: `present`.

- [ ] **Step 2: Update the README row**

In `scripts/research/README.md`, replace the row

```markdown
| `regime_base_rates.py` (added by the v239 follow-on evidence plan; not in v239) | follow-on | `data/backtest_cache_regime/` (`scripts/data/fetch_regime_data.py`) | written by that plan |
```

with

```markdown
| `regime_base_rates.py` (SPY base rates under the v239 bear-regime rules, 1993 → 2026-11-20; DESCRIPTION, moves no gate) | v244 | `data/backtest_cache_regime/` (`scripts/data/fetch_regime_data.py`) | `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md` |
```

- [ ] **Step 3: Extend the architecture bullet**

In `docs/claude/architecture.md`, the "Bear-regime shadow (v239)" bullet ends with ``Drift guard: `scripts/reports/regime_parity.py`.`` Append, inside the same bullet (same two-space continuation indent):

```markdown
  Evidence (v244): `scripts/research/regime_base_rates.py` labels SPY
  1993 → 2026-11-20 on a hash-pinned cache and reports episode durations,
  CORRECTION → BEAR conversion and forward returns (a DESCRIPTION, results in
  `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md`);
  `scripts/reports/regime_shadow_report.py` prints N/WR/ExpR per stamped
  `regime_action` on closed main-ledger trades, `too few` under 30. Both are
  monitoring and description: neither is a screen or licenses B7–B9.
```

- [ ] **Step 4: Mirror to Codex**

In `AGENTS.md`'s Commands block, directly after the `regime_parity.py` line, add:

```text
python scripts/research/regime_base_rates.py          # v244: SPY base rates under the bear-regime rules (DESCRIPTION; refuses a changed cache, checkpointed per year)
python scripts/reports/regime_shadow_report.py        # v244: N/WR/ExpR per stamped regime_action, closed main ledger (monitoring, never a screen)
```

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: `0 failed`.

- [ ] **Step 5: Confirm no guide chapter is touched**

Run: `python scripts/dev/guide_sources.py main..HEAD`
Expected: exit 0 and no chapter listed. If a chapter is listed, record `guide: no reader-visible change` for it in your report (the scripts change nothing a reader of the guide sees); the controller puts that line in the close-out commit.

- [ ] **Step 6: Append the ledger DESCRIPTION row**

Read the labelled-session count from the results doc's `**Labelled sessions:** … (N)` line. Then, from the repo root (`<run date>` is the date V244-2's real run wrote the doc, `YYYY-MM-DD`):

Run: `python scripts/reports/preregistration_ledger.py --id v244-regime-base-rates --date <run date> --hypothesis "SPY base rates under the v239 bear-regime rules (SPY and ^VIX daily, yfinance, hash-pinned, 1993 to 2026-11-20): describes base rates; never a lift; selects nothing; a later spec may cite only its N and coverage columns, never as evidence for a gate" --instrument v1 --n <N> --verdict DESCRIPTION --record docs/superpowers/results/2026-11-23-v244-regime-base-rates.md --data-source yfinance`
Expected: exit 0, the BH table printed with `v244-regime-base-rates` at q null, and `tail -1 docs/superpowers/results/preregistration-ledger.jsonl` showing the row with `"exp_r": null, "p": null, "verdict": "DESCRIPTION"`. Run it once: a row is never edited or re-appended (a second run would duplicate the id).

Append to `tests/regime/test_regime_base_rates.py`:

```python
def test_the_ledger_carries_the_study_as_a_description():
    from swingbot.core.backtesting.instrument import stats
    rows = [r for r in stats.load_ledger(stats.LEDGER_PATH) if r["id"] == "v244-regime-base-rates"]
    assert len(rows) == 1
    row = rows[0]
    assert (row["verdict"], row["instrument"], row["p"], row["exp_r"]) == ("DESCRIPTION", "v1", None, None)
    assert row["record"] == rbr.OUT.relative_to(rbr.ROOT).as_posix()
    assert isinstance(row["n"], int) and row["n"] > 8000
    assert "never a lift" in row["hypothesis"] and "selects nothing" in row["hypothesis"]
    assert "only its N and coverage columns" in row["hypothesis"]
    assert stats.ledger_data_source(row) == "yfinance"
```

Run: `python scripts/dev/testrun.py file tests/regime/test_regime_base_rates.py`
Expected: `0 failed`.

Run: `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`
Expected: `0 failed` (the row validates and its record exists).

- [ ] **Step 7: Smoke-run the shadow report against the replica**

Run `/replicate-prod-db` first (the report reads the trades table through `TradeLog`), in the shared `swing-db` container.

Run: `python scripts/reports/regime_shadow_report.py`
Expected: exit 0; the header `Bear-regime shadow report -- live monitoring, not a screen.`, a `closed N · stamped M · no R K` line, and six rows in `ROWS` order. Until stamped trades from the v239 shadow soak have closed and reached the replica, `stamped` is 0, the line `No stamped trades yet` prints and every row reads `too few`. That is the expected answer, not a failure. Paste the output into your report; quote no figure from it as evidence for a gate.

- [ ] **Step 8: Commit**

```bash
git add docs/superpowers/results/preregistration-ledger.jsonl tests/regime/test_regime_base_rates.py scripts/research/README.md docs/claude/architecture.md AGENTS.md
git commit -m "docs(v244): ledger DESCRIPTION row, research README, architecture map and Codex mirror for the regime evidence scripts"
```

- [ ] **Step 9: Hand off to the pipeline**

No local full suite (CI runs one job per suite from `tests/suites.toml`; `tests/regime/` runs in `market-signals`). After the controller merges the branch to `main` and pushes, Claude watches the run to its end and fixes any failing test alone (`testrun.py file`) until it is green. `Bump: none`: `/close-out` leaves `VERSION.json` alone and moves the plan to `implemented/`. Then `/panel` runs the spec's panel (veteran-trader, quant-engineer, ux-designer) over the diff and the results doc, before close-out.

