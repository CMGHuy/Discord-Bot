# v226 — Stop-width attribution, part 3: report, run and close-out (V226-10..V226-14)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v226 — Stop-width attribution](../specs/2026-11-12-v226-stop-width-attribution-design.md) (§ The pre-registered verdict, § What each verdict buys, § Disclosures, § Data, § Code, § Tests)
**Index:** [`_0-index.md`](2026-11-12-v226-stop-width-attribution_0-index.md) — Goal, Global Constraints, Parallelisation, the task ledger and its cross-task contracts. Every task below implicitly includes the index's Global Constraints.

Part 2 left the study as pure functions in
`swingbot/core/analytics/expectancy_attribution.py`: rows, frozen edges, the
verdict and the disclosures. This part turns them into one report with its own
file (V226-10) and its own Markdown (V226-10b), routes the attribution script to it behind
`--study stop-width` while the default report stays byte-identical (V226-11),
runs the preflight, the TRAIN replay and the study exactly once (V226-12),
writes the results doc and the records its verdict calls for (V226-13), and
ships it (V226-14).

All work happens in worktree `.claude/worktrees/2026-11-12-v226-stop-width-attribution`
(branch of the same name). Run every command below from that worktree root.
V226-10, V226-10b and V226-11 follow V226-9 strictly in order (same module); V226-12..V226-14 need
every earlier task (parts 1 and 2) committed on the worktree branch.

# Phase 3 — Report, flag, run, record

### Task V226-10: Report and run for the stop-width study

**Model:** sonnet — assembles V226-6..V226-9's finished functions into one report and a writer; no statistics are decided here.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (one import at the top; new section appended after V226-9's `stop_width_disclosures`)
- Create: `tests/analytics/test_stop_width_report.py`

**Interfaces:**
- Consumes: `load_stop_width_train_rows(path, *, source=None) -> list[dict]`, `load_stop_width_live_rows() -> list[dict]` (V226-6); `stop_width_groups(train_rows, live_rows) -> {"edges", "labels", "train", "live"}`, `frozen_edges` (V226-7); `stop_width_verdict(train_groups, *, seed) -> {"verdict", "candidates", "family_size", "powered", "n_needed", "looks"}`, `STUDY_VERDICTS` (V226-8); `stop_width_disclosures(groups) -> {"train": DISC, "live": DISC}`, `VOLATILITY_RHO` (V226-9); existing `_file_sha256(path)` (:694), `LIVE_FILLS_INCLUDE_FRICTIONS` (:451), `commission_r` (imported at :32), `N_RESAMPLES`, `WEEK_BOOTSTRAP_SEED` (:452); `swingbot.core.infra.jsonio.atomic_write_json(path: str, obj)` (creates the parent directory; temp file + `os.replace`); `swingbot.core.marketdata.training_data.provenance_path(out_path) -> Path` (`<out>.provenance.json`; lazy import, the module pulls the history store).
- Produces (V226-10b, V226-11, V226-12 and V226-13 read these exact names):
  - `STUDY_ID = "v226-stop-width"`
  - `stop_width_report_path() -> Path` = `Path(config.DATA_DIR) / "reports" / "stop-width-attribution.json"`, resolved at call time
  - `build_stop_width_report(train_rows, live_rows, *, seed: int, generated_at: str | None = None) -> dict`, keys in this order: `generated_at, study, seed, edges, labels, verdict, disclosures, volatility_note, provenance` (`verdict` is `stop_width_verdict(groups["train"], seed=seed)` whole; `volatility_note = TRAIN rho is not None and abs(rho) >= VOLATILITY_RHO`; `provenance` is `{}` until `run_stop_width` fills it)
  - `run_stop_width(train_jsonl, *, seed: int = WEEK_BOOTSTRAP_SEED, write: bool = True) -> dict`; `provenance` keys in this order: `train_rows {path, rows, sha256}`, `run_sidecar` (parsed `<train_jsonl>.run.json` or None), `store_provenance` (parsed `<train_jsonl>.provenance.json` or None), `frictions {slippage_bps, commission_r}`, `live_fills_include_frictions`, `n_resamples`; writes through `jsonio.atomic_write_json` only, **never** `write_latest`
  - test helpers `stop_width_rows(n, *, live=False, atr=True) -> list[dict]` and `STAMP` in `tests/analytics/test_stop_width_report.py` (imported by V226-10b's and V226-11's tests)

**Why not `write_latest`.** `expectancy_attribution_store.write_latest` writes
`expectancy-attribution.json` and carries v146's `verdict_of_record` forward.
The stop-width study has its own file and never touches v146's record. The
tests make both `ea.write_latest` and `store.write_latest` raise.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_stop_width_report.py`:

```python
"""v226: the stop-width report -- one TRAIN verdict, disclosures for both
populations, provenance with both replay sidecars, and its own file under
data/reports (never expectancy-attribution.json)."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.analytics import expectancy_attribution as ea
from swingbot.core.infra import expectancy_attribution_store as store

REPO = Path(__file__).resolve().parents[2]
REPORT_KEYS = ["generated_at", "study", "seed", "edges", "labels", "verdict",
               "disclosures", "volatility_note", "provenance"]
PROVENANCE_KEYS = ["train_rows", "run_sidecar", "store_provenance", "frictions",
                   "live_fills_include_frictions", "n_resamples"]
STAMP = "2026-11-12T00:00:00+00:00"


def stop_width_rows(n: int, *, live: bool = False, atr: bool = True) -> list[dict]:
    """Synthetic stop-width rows over 200 TRAIN weeks: tight stops
    (stop_atr < 0.35) lose, the rest earn; atr_pct = 1.9 / stop_atr (so
    Spearman rho is -1) unless ``atr`` is False. Imported by the V226-10b
    and V226-11 tests."""
    rows = []
    for i in range(n):
        stop_atr = round(0.2 + (i % 8) * 0.1, 2)
        row = {"r": (-0.6 if stop_atr < 0.35 else 0.1) + ((i * 37) % 11 - 5) / 50.0,
               "r_gross": 0.05,
               "week": (dt.date(2020, 1, 6) + dt.timedelta(weeks=i % 200)).isoformat(),
               "direction": "bearish" if i % 3 == 0 else "bullish", "horizon": "2w",
               "risk_reward_ratio": 2.0, "stop_atr": stop_atr,
               "atr_pct": round(1.9 / stop_atr, 6) if atr else None,
               "stop_clamped": i % 2 == 0}
        if live:
            row.update(opened_at="2026-11-03T14:30:00+00:00",
                       closed_at=f"2026-11-0{3 + i % 2}T20:00:00+00:00",
                       strategy="Fibonacci" if i % 2 else "FVG")
        rows.append(row)
    return rows


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)


def _report(train=None, live=None) -> dict:
    return ea.build_stop_width_report(
        stop_width_rows(800) if train is None else train,
        stop_width_rows(120, live=True) if live is None else live,
        seed=42, generated_at=STAMP)


# --- path and constants ---------------------------------------------------------

def test_the_report_path_is_its_own_file_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    assert ea.stop_width_report_path() == tmp_path / "reports" / "stop-width-attribution.json"
    assert ea.stop_width_report_path().name != Path(store.REPORT_PATH).name
    assert ea.STUDY_ID == "v226-stop-width"


def test_the_run_sidecar_path_matches_the_replay_script():
    sys.path.insert(0, str(REPO / "scripts" / "backtest"))
    import run_backtest_range as rr
    assert ea._run_sidecar_of("x/rows.jsonl") == rr._run_sidecar_path("x/rows.jsonl")


# --- build_stop_width_report ----------------------------------------------------

def test_the_report_has_the_contract_shape():
    train = stop_width_rows(800) + [dict(stop_width_rows(1)[0], stop_atr=None)]
    live = stop_width_rows(120, live=True)
    report = ea.build_stop_width_report(train, live, seed=42, generated_at=STAMP)
    assert list(report) == REPORT_KEYS
    assert report["generated_at"] == STAMP and report["study"] == ea.STUDY_ID
    assert report["seed"] == 42 and report["provenance"] == {}
    groups = ea.stop_width_groups(train, live)
    assert report["edges"] == groups["edges"] == ea.frozen_edges(train, "stop_atr")
    assert report["labels"] == groups["labels"]
    assert report["verdict"] == ea.stop_width_verdict(groups["train"], seed=42)
    assert report["disclosures"] == ea.stop_width_disclosures(groups)
    assert report["disclosures"]["train"]["unknown"] == 1
    json.dumps(report)                                   # plain JSON types only


def test_generated_at_defaults_to_now_in_utc():
    report = ea.build_stop_width_report(stop_width_rows(80), [], seed=42)
    assert report["generated_at"].endswith("+00:00")


def test_the_verdict_and_edges_read_train_only():
    train = stop_width_rows(800)
    quiet = _report(train=train, live=[])
    loud = _report(train=train, live=stop_width_rows(400, live=True))
    assert quiet["verdict"] == loud["verdict"]
    assert quiet["edges"] == loud["edges"]
    assert quiet["verdict"]["verdict"] in ea.STUDY_VERDICTS


def test_a_perfectly_collinear_atr_pct_raises_the_volatility_note():
    assert _report(train=stop_width_rows(160))["volatility_note"] is True
    assert _report(train=stop_width_rows(160, atr=False))["volatility_note"] is False


@pytest.mark.parametrize(("rho", "flag"),
                         [(0.8, True), (-0.8, True), (0.7999, False), (-0.7999, False),
                          (None, False)])
def test_the_volatility_note_boundary_is_inclusive(monkeypatch, rho, flag):
    real = ea.stop_width_disclosures

    def fake(groups):
        out = real(groups)
        out["train"]["rho"] = rho
        out["live"]["rho"] = 0.99                        # live never sets the note
        return out

    monkeypatch.setattr(ea, "stop_width_disclosures", fake)
    assert _report(train=stop_width_rows(80), live=[])["volatility_note"] is flag


# --- run_stop_width -------------------------------------------------------------

def _stub_loaders(monkeypatch, train, live):
    monkeypatch.setattr(ea, "load_stop_width_train_rows", lambda path: train)
    monkeypatch.setattr(ea, "load_stop_width_live_rows", lambda: live)


def _forbid_v146_writes(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the stop-width study must never write the v146 report")

    monkeypatch.setattr(ea, "write_latest", refuse)
    monkeypatch.setattr(store, "write_latest", refuse)


def _files(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_run_writes_only_its_own_report_and_quotes_both_sidecars(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    _forbid_v146_writes(monkeypatch)
    _stub_loaders(monkeypatch, stop_width_rows(160), stop_width_rows(40, live=True))
    train = tmp_path / "rows.jsonl"
    train.write_text('{"ticker": "AAA"}\n', encoding="utf-8")
    Path(str(train) + ".run.json").write_text(json.dumps({"git_head": "abc"}), encoding="utf-8")
    Path(str(train) + ".provenance.json").write_text(json.dumps({"data_source": "alpaca"}),
                                                     encoding="utf-8")
    report = ea.run_stop_width(train, seed=7)
    assert _files(data) == ["reports/stop-width-attribution.json"]
    target = data / "reports" / "stop-width-attribution.json"
    assert json.loads(target.read_text(encoding="utf-8")) == json.loads(json.dumps(report))
    prov = report["provenance"]
    assert list(prov) == PROVENANCE_KEYS
    assert prov["train_rows"]["path"] == str(train) and prov["train_rows"]["rows"] == 160
    assert len(prov["train_rows"]["sha256"]) == 64
    assert prov["run_sidecar"] == {"git_head": "abc"}
    assert prov["store_provenance"] == {"data_source": "alpaca"}
    assert prov["live_fills_include_frictions"] is ea.LIVE_FILLS_INCLUDE_FRICTIONS
    assert list(prov["frictions"]) == ["slippage_bps", "commission_r"]
    assert prov["n_resamples"] == 200 and report["seed"] == 7


def test_missing_sidecars_are_none_and_no_write_writes_nothing(monkeypatch, tmp_path):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    _forbid_v146_writes(monkeypatch)
    _stub_loaders(monkeypatch, stop_width_rows(80), [])
    train = tmp_path / "rows.jsonl"
    train.write_text("\n", encoding="utf-8")
    report = ea.run_stop_width(train, write=False)
    assert report["seed"] == ea.WEEK_BOOTSTRAP_SEED
    assert report["provenance"]["run_sidecar"] is None
    assert report["provenance"]["store_provenance"] is None
    assert _files(data) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_report.py`
Expected: FAIL with `AttributeError: ... has no attribute 'stop_width_report_path'` (and the same for `STUDY_ID`, `build_stop_width_report`, `run_stop_width`, `_run_sidecar_of`).

- [ ] **Step 3: Implement**

At the top of `swingbot/core/analytics/expectancy_attribution.py`, directly
below the `swingbot.core.infra.expectancy_attribution_store` import, add:

```python
from swingbot.core.infra import jsonio
```

Append after V226-9's `stop_width_disclosures`:

```python


# --- v226 report and run --------------------------------------------------------

#: The report's ``study`` field and the pre-registration ledger id.
STUDY_ID = "v226-stop-width"
_RUN_SIDECAR_SUFFIX = ".run.json"     # run_backtest_range._run_sidecar_path (V226-3)


def stop_width_report_path() -> Path:
    """data/reports/stop-width-attribution.json, resolved at call time so a
    test's DATA_DIR wins. Never the v146 expectancy-attribution.json."""
    return Path(config.DATA_DIR) / "reports" / "stop-width-attribution.json"


def build_stop_width_report(train_rows: list[dict], live_rows: list[dict], *, seed: int,
                            generated_at: str | None = None) -> dict:
    """The whole stop-width report, pure: TRAIN-frozen edges, the
    pre-registered verdict on TRAIN only, disclosures for both populations
    (live on the TRAIN edges, never gating). ``provenance`` is filled by
    ``run_stop_width``."""
    groups = stop_width_groups(train_rows, live_rows)
    outcome = stop_width_verdict(groups["train"], seed=seed)
    disclosures = stop_width_disclosures(groups)
    rho = disclosures["train"]["rho"]
    return {
        "generated_at": generated_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        "study": STUDY_ID,
        "seed": seed,
        "edges": groups["edges"],
        "labels": groups["labels"],
        "verdict": outcome,
        "disclosures": disclosures,
        "volatility_note": rho is not None and abs(rho) >= VOLATILITY_RHO,
        "provenance": {},
    }


def _run_sidecar_of(train_jsonl) -> Path:
    return Path(str(train_jsonl) + _RUN_SIDECAR_SUFFIX)


def _json_or_none(path) -> dict | None:
    path = Path(path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def run_stop_width(train_jsonl, *, seed: int = WEEK_BOOTSTRAP_SEED, write: bool = True) -> dict:
    """Load both stop-width populations, build the report, quote both replay
    sidecars, and write it to its own file (unless ``write=False``). Never
    ``write_latest``: v146's verdict of record is not touched."""
    from swingbot.core.marketdata import training_data
    train_rows = load_stop_width_train_rows(train_jsonl)
    live_rows = load_stop_width_live_rows()
    report = build_stop_width_report(train_rows, live_rows, seed=seed)
    report["provenance"] = {
        "train_rows": {"path": str(train_jsonl), "rows": len(train_rows),
                       "sha256": _file_sha256(train_jsonl)},
        "run_sidecar": _json_or_none(_run_sidecar_of(train_jsonl)),
        "store_provenance": _json_or_none(training_data.provenance_path(train_jsonl)),
        "frictions": {"slippage_bps": getattr(config, "SLIPPAGE_BPS", 5.0),
                      "commission_r": commission_r()},
        "live_fills_include_frictions": LIVE_FILLS_INCLUDE_FRICTIONS,
        "n_resamples": N_RESAMPLES,
    }
    if write:
        jsonio.atomic_write_json(str(stop_width_report_path()), report)
    return report
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_report.py`
Expected: all passed.

Then: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
Expected: 3 passed (the default report and summary are still byte-identical).

Then: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_report.py`
Expected: all passed (v146's `run`, its `write_latest` path and the script test are unchanged).

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function 3 or below).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_stop_width_report.py
git commit -m "feat(v226): stop-width report and run -- own file, both sidecars quoted, never write_latest (V226-10)"
```

### Task V226-10b: Markdown renderer for the stop-width report

**Model:** sonnet — a pure renderer over V226-10's fixed report shape; the wording is quoted from the spec.

**Files:**
- Modify: `swingbot/core/analytics/expectancy_attribution.py` (append after V226-10's `run_stop_width`)
- Create: `tests/analytics/test_stop_width_markdown.py`

**Interfaces:**
- Consumes: V226-10 `build_stop_width_report(...)` and its report shape (`generated_at, study, seed, edges, labels, verdict, disclosures, volatility_note, provenance`); V226-8 `CLAUSE_KEYS`, `VETO_YEARS`, `STUDY_VERDICTS` and the `LOOK` keys (`n, exp_r, delta, ci_low, ci_high, p, q, years, years_negative, clauses, candidate`); V226-9 `BUCKET` keys (`n, win_rate, exp_r, exp_r_gross, median_rr, direction_share, horizon_share, delta_by_direction, clamped_share, clamped_none, removal`, live `family_share, same_day_loss_share`); test helpers `stop_width_rows`, `STAMP` from `tests/analytics/test_stop_width_report.py` (V226-10).
- Produces (V226-11 prints it; V226-13 pastes it into the results doc): `stop_width_markdown(report: dict) -> str`. First line `# v226 stop-width attribution (<generated_at[:10]>, seed <seed>)`; sections in order `## Verdict` (line `**Verdict: <VERDICT>** -- <what it buys>`, `Candidates: <labels or none>.`, `Powered buckets (N ≥ 300): <k> of <family_size>; ...`, the frozen edges), `## TRAIN: the six pre-registered clauses` (clause table, then a per-year Δ table), `## TRAIN buckets`, `## Live buckets (TRAIN edges; printed beside TRAIN, never gates)` (each: unknown count, bucket table, removal table, mix lines), `## stop_atr against atr_pct (disclosed, never a look)` (+ the volatility sentence when `volatility_note`), `## What this is`, `## What each verdict buys`. `None` renders as `n/a`, bools as `yes`/`no`, R to 4 decimals.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_stop_width_markdown.py`:

```python
"""v226: the Markdown body of the stop-width results doc -- verdict, the six
clauses per bucket, both populations side by side (live never gates), the
volatility sentence only when flagged, and the two fixed paragraphs."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from tests.analytics.test_stop_width_report import STAMP, stop_width_rows


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)


def _report(train=None, live=None) -> dict:
    return ea.build_stop_width_report(
        stop_width_rows(800) if train is None else train,
        stop_width_rows(120, live=True) if live is None else live,
        seed=42, generated_at=STAMP)


def test_the_markdown_carries_verdict_clauses_both_populations_and_the_tail():
    report = _report()
    md = ea.stop_width_markdown(report)
    assert md.startswith("# v226 stop-width attribution (2026-11-12, seed 42)\n")
    assert f"**Verdict: {report['verdict']['verdict']}**" in md
    for label in report["labels"]:
        # clause table, year table, TRAIN and live bucket tables, two removal tables
        assert md.count(f"| {label} |") == 6
    assert "| Bucket | N | ExpR | Δ | 95% CI | p | q | years Δ<0 |" in md
    assert "| Bucket | 2020 | 2021 | 2022 | 2023 |" in md
    assert "same-day loss share" in md and "never gates" in md
    assert "## What this is" in md and "Descriptive, not a veto." in md
    assert "## What each verdict buys" in md
    for name in ea.STUDY_VERDICTS:
        assert f"- **{name}**" in md
    assert md == ea.stop_width_markdown(report)          # deterministic


def test_sections_come_in_the_fixed_order():
    md = ea.stop_width_markdown(_report())
    order = ["## Verdict", "## TRAIN: the six pre-registered clauses", "## TRAIN buckets",
             "## Live buckets", "## stop_atr against atr_pct", "## What this is",
             "## What each verdict buys"]
    positions = [md.index(heading) for heading in order]
    assert positions == sorted(positions)


def test_the_markdown_names_the_candidates_or_none():
    report = _report()
    first = report["labels"][0]
    report["verdict"] = dict(report["verdict"], verdict="VETO-CANDIDATE", candidates=[first])
    md = ea.stop_width_markdown(report)
    assert f"Candidates: {first}." in md
    assert "**Verdict: VETO-CANDIDATE** -- licenses a veto idea, not a veto" in md
    report["verdict"] = dict(report["verdict"], verdict="NO CANDIDATE", candidates=[])
    assert "Candidates: none." in ea.stop_width_markdown(report)


def test_the_markdown_states_the_power_line():
    report = _report()
    report["verdict"] = dict(report["verdict"], verdict="UNDERPOWERED", powered=1)
    md = ea.stop_width_markdown(report)
    assert "**Verdict: UNDERPOWERED** -- leaves the question open" in md
    assert f"Powered buckets (N ≥ 300): 1 of {report['verdict']['family_size']}" in md


def test_the_edges_line_prints_two_decimals_or_none():
    report = _report()
    report["edges"] = [0.4149, 0.6]
    assert "outcome-blind): 0.41, 0.60." in ea.stop_width_markdown(report)
    report["edges"] = []
    assert "outcome-blind): none." in ea.stop_width_markdown(report)


def test_the_volatility_sentence_appears_only_when_flagged():
    sentence = "about ticker volatility, not stop placement"
    assert sentence in ea.stop_width_markdown(_report(train=stop_width_rows(800)))
    assert sentence not in ea.stop_width_markdown(_report(train=stop_width_rows(800, atr=False)))


def test_missing_numbers_render_as_n_a_and_bools_as_words():
    md = ea.stop_width_markdown(_report(live=[]))
    assert "n/a" in md
    assert "None" not in md.replace("clamped None", "").replace("None rows", "")
    assert "| yes |" in md or "| no |" in md
    assert "True" not in md and "False" not in md
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_markdown.py`
Expected: FAIL with `AttributeError: ... has no attribute 'stop_width_markdown'`.

- [ ] **Step 3: Implement**

Append after V226-10's `run_stop_width`:

```python


# --- v226 Markdown (the results doc body) ---------------------------------------

_VERDICT_BUYS = (
    ("VETO-CANDIDATE", "licenses a veto idea, not a veto: it must earn a SCREEN-AVOID-PASS "
                       "from a Stage -2 avoid idea before its spec, and that spec measures "
                       "the veto on the bot's own replay with replacement trades included "
                       "(paired)."),
    ("NO CANDIDATE", "closes \"tight stops in ATR terms\" as measured "
                     "(backtest-methodology.md § Closed pre-registrations)."),
    ("UNDERPOWERED", "leaves the question open and names the N that would power it."),
)
_DESCRIPTIVE_TEXT = (
    "Descriptive, not a veto. Each bucket's filled TRAIN rows are compared with the "
    "rest; this does not estimate what a veto would do to pooled ExpR, because a "
    "vetoed plan frees a slot that a different plan would take. A VETO-CANDIDATE only "
    "licenses the Stage -2 screen and the paired replay that would measure that.")
_VOLATILITY_TEXT = ("|rho| between stop_atr and atr_pct is {rho} on TRAIN (>= 0.8): this "
                    "verdict is about ticker volatility, not stop placement.")
_CLAUSE_HEADERS = ("1 Δ≤−0.10", "2 CI<0", "3 ExpR<0", "4 ≥3/4 yrs", "5 N≥300", "6 q<0.10")
_BUCKET_HEADERS = ("Bucket", "N", "Win%", "ExpR", "ExpR gross", "median RR",
                   "clamped share", "clamped None", "Δ long", "Δ short")
_REMOVAL_HEADERS = ("Bucket", "pooled ExpR", "ExpR without", "ΔTotal R", "N removed")


def _fmt(value, spec: str = ".4f") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return format(value, spec)


def _table(headers, rows) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return out + ["| " + " | ".join(cells) + " |" for cells in rows]


def _md_verdict(report: dict) -> list[str]:
    outcome = report["verdict"]
    edges = ", ".join(f"{edge:.2f}" for edge in report["edges"]) or "none"
    return ["## Verdict", "",
            f"**Verdict: {outcome['verdict']}** -- {dict(_VERDICT_BUYS)[outcome['verdict']]}", "",
            f"Candidates: {', '.join(outcome['candidates']) or 'none'}.",
            f"Powered buckets (N ≥ {outcome['n_needed']}): {outcome['powered']} of "
            f"{outcome['family_size']}; BH family size {outcome['family_size']} (this "
            "study's bucket looks only). Computed once on TRAIN; VALIDATION never read.", "",
            f"Edges (TRAIN quartiles of stop_atr, frozen, outcome-blind): {edges}.", ""]


def _clause_cells(label: str, look: dict) -> list[str]:
    return [label, str(look["n"]), _fmt(look["exp_r"]), _fmt(look["delta"]),
            f"[{_fmt(look['ci_low'])}, {_fmt(look['ci_high'])}]", _fmt(look["p"]),
            _fmt(look["q"]), f"{look['years_negative']}/{len(VETO_YEARS)}",
            *(_fmt(look["clauses"][key]) for key in CLAUSE_KEYS), _fmt(look["candidate"])]


def _md_clauses(report: dict) -> list[str]:
    looks, labels = report["verdict"]["looks"], report["labels"]
    headers = ("Bucket", "N", "ExpR", "Δ", "95% CI", "p", "q", "years Δ<0",
               *_CLAUSE_HEADERS, "candidate")
    years = [[label, *(_fmt(looks[label]["years"][year]) for year in VETO_YEARS)]
             for label in labels]
    return (["## TRAIN: the six pre-registered clauses", ""]
            + _table(headers, [_clause_cells(label, looks[label]) for label in labels])
            + ["", "Δ per TRAIN year (bucket ExpR − rest ExpR; n/a = no rows that year, "
                   "which counts against clause 4):", ""]
            + _table(("Bucket", *VETO_YEARS), years) + [""])


def _bucket_cells(label: str, bucket: dict, live: bool) -> list[str]:
    deltas = bucket["delta_by_direction"]
    cells = [label, str(bucket["n"]), _fmt(bucket["win_rate"], ".1f"), _fmt(bucket["exp_r"]),
             _fmt(bucket["exp_r_gross"]), _fmt(bucket["median_rr"], ".2f"),
             _fmt(bucket["clamped_share"], ".3f"), str(bucket["clamped_none"]),
             _fmt(deltas.get("bullish")), _fmt(deltas.get("bearish"))]
    if live:
        cells.append(_fmt(bucket["same_day_loss_share"], ".3f"))
    return cells


def _removal_cells(label: str, bucket: dict) -> list[str]:
    removal = bucket["removal"]
    return [label, _fmt(removal["pooled_exp_r"]), _fmt(removal["without_exp_r"]),
            _fmt(removal["delta_total_r"]), str(removal["n_removed"])]


def _shares_text(shares: dict) -> str:
    return ", ".join(f"{key} {value:.2f}" for key, value in shares.items()) or "none"


def _mix_line(label: str, bucket: dict, live: bool) -> str:
    line = (f"- {label}: direction {_shares_text(bucket['direction_share'])}; "
            f"horizon {_shares_text(bucket['horizon_share'])}")
    if live:
        line += f"; family {_shares_text(bucket['family_share'])}"
    return line


def _md_population(title: str, disc: dict, labels: list[str], *, live: bool) -> list[str]:
    buckets = disc["buckets"]
    headers = _BUCKET_HEADERS + (("same-day loss share",) if live else ())
    return ([f"## {title}", "",
             f"Unknown stop_atr rows (outside the edges and the bootstrap base): "
             f"{disc['unknown']}. The clamped share is a lower-bound provenance flag "
             "(identity-based, read at run time); None rows leave its denominator.", ""]
            + _table(headers, [_bucket_cells(label, buckets[label], live) for label in labels])
            + ["", "Removal arithmetic (descriptive; ignores replacement trades):", ""]
            + _table(_REMOVAL_HEADERS, [_removal_cells(label, buckets[label]) for label in labels])
            + ["", "Mix:", ""] + [_mix_line(label, buckets[label], live) for label in labels]
            + [""])


def _md_volatility(report: dict) -> list[str]:
    disc = report["disclosures"]
    lines = ["## stop_atr against atr_pct (disclosed, never a look)", ""]
    for name, key in (("TRAIN", "train"), ("Live", "live")):
        lines.append(f"- {name}: Spearman rho {_fmt(disc[key]['rho'])}, mirrored-bucket "
                     f"overlap {_fmt(disc[key]['overlap'], '.3f')}")
    lines.append("")
    if report["volatility_note"]:
        lines += [_VOLATILITY_TEXT.format(rho=_fmt(abs(disc["train"]["rho"]))), ""]
    return lines


def _md_tail() -> list[str]:
    return (["## What this is", "", _DESCRIPTIVE_TEXT, "", "## What each verdict buys", ""]
            + [f"- **{name}** {text}" for name, text in _VERDICT_BUYS])


def stop_width_markdown(report: dict) -> str:
    """The printed body of the results doc: verdict, clause table, both
    populations' disclosures (live beside TRAIN, never gating), rho and the
    two fixed paragraphs."""
    disc, labels = report["disclosures"], report["labels"]
    lines = [f"# v226 stop-width attribution ({report['generated_at'][:10]}, "
             f"seed {report['seed']})", ""]
    lines += _md_verdict(report) + _md_clauses(report)
    lines += _md_population("TRAIN buckets", disc["train"], labels, live=False)
    lines += _md_population("Live buckets (TRAIN edges; printed beside TRAIN, never gates)",
                            disc["live"], labels, live=True)
    lines += _md_volatility(report) + _md_tail()
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_markdown.py`
Expected: all passed.

Then: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
Expected: 3 passed.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function 4 or below).

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/expectancy_attribution.py tests/analytics/test_stop_width_markdown.py
git commit -m "feat(v226): stop-width Markdown -- clause table, live beside TRAIN, volatility sentence, verdict paragraphs (V226-10b)"
```

### Task V226-11: `--study stop-width` flag on the attribution script

**Model:** sonnet — one argparse choice and one branch in a thin wrapper, pinned by the existing script test and V226-5's golden hashes.

**Files:**
- Modify: `scripts/reports/expectancy_attribution.py` (module docstring, `main`)
- Modify: `tests/analytics/test_expectancy_attribution_report.py` (append three script tests; `test_the_script_parses_calls_and_prints` stays byte-for-byte as it is)

**Interfaces:**
- Consumes: V226-10 `run_stop_width(train_jsonl, *, seed, write) -> dict`, `stop_width_report_path()`; V226-10b `stop_width_markdown(report) -> str`; test helper `stop_width_rows(n, *, live=False, atr=True)` from `tests/analytics/test_stop_width_report.py`; the existing helpers `_script()`, `_write_jsonl(path, rows)`, `_replay_row(**over)`, `population(kind)` and the autouse `cheap_and_costed` fixture in the file being modified.
- Produces: CLI `--study {stop-width}` (default None). With it, `main` calls `study.run_stop_width(args.train_jsonl, seed=seed, write=not args.no_write)` and prints `study.stop_width_markdown(report)`; it never calls `study.run` or `summary`. Without it, the call `study.run(args.train_jsonl, seed=seed, write=not args.no_write)` and `print(summary(report))` are unchanged.

`main` stays far below complexity 15 (one added `if`). The `--no-write` help
text widens to name both files; help text is not part of the printed report,
so V226-5's summary hash is untouched.

- [ ] **Step 1: Write the failing tests**

Append to `tests/analytics/test_expectancy_attribution_report.py`:

```python


# --- v226: --study stop-width ----------------------------------------------------

def test_the_stop_width_flag_routes_to_the_stop_width_study_only(monkeypatch, capsys):
    calls = []

    def fake_stop_width(train_jsonl, *, seed, write):
        calls.append((train_jsonl, seed, write))
        return {"marker": len(calls)}

    monkeypatch.setattr(ea, "run", lambda *a, **k: pytest.fail("--study must not run the v146 study"))
    monkeypatch.setattr(ea, "run_stop_width", fake_stop_width)
    monkeypatch.setattr(ea, "stop_width_markdown", lambda report: f"MD {report['marker']}\n")
    script = _script()
    assert script.main(["--train-jsonl", "rows.jsonl", "--study", "stop-width"]) == 0
    assert script.main(["--train-jsonl", "rows.jsonl", "--study", "stop-width",
                        "--seed", "9", "--no-write"]) == 0
    assert calls == [("rows.jsonl", ea.WEEK_BOOTSTRAP_SEED, True), ("rows.jsonl", 9, False)]
    assert capsys.readouterr().out == "MD 1\nMD 2\n"


def test_an_unknown_study_is_refused(capsys):
    with pytest.raises(SystemExit) as exc:
        _script().main(["--train-jsonl", "rows.jsonl", "--study", "atr-pct"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_without_the_flag_the_stop_width_study_never_runs(monkeypatch, capsys):
    report = ea.build_report([], population("predictive"), seed=42,
                             generated_at="2026-10-12T08:00:00+00:00")
    monkeypatch.setattr(ea, "run", lambda train_jsonl, *, seed, write: report)
    monkeypatch.setattr(ea, "run_stop_width",
                        lambda *a, **k: pytest.fail("no --study, no stop-width run"))
    script = _script()
    assert script.main(["--train-jsonl", "rows.jsonl"]) == 0
    assert capsys.readouterr().out == script.summary(report) + "\n"


def test_the_stop_width_flag_writes_only_its_own_file(monkeypatch, tmp_path, capsys):
    from tests.analytics.test_stop_width_report import stop_width_rows
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data))
    monkeypatch.setattr(store, "REPORT_PATH", data / "reports" / "expectancy-attribution.json")
    monkeypatch.setattr(ea, "load_stop_width_train_rows", lambda path: stop_width_rows(160))
    monkeypatch.setattr(ea, "load_stop_width_live_rows", lambda: stop_width_rows(40, live=True))
    monkeypatch.setattr(ea, "run", lambda *a, **k: pytest.fail("--study must not run the v146 study"))
    rows = _write_jsonl(tmp_path / "rows.jsonl", [_replay_row()])
    assert _script().main(["--train-jsonl", str(rows), "--study", "stop-width"]) == 0
    files = sorted(p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file())
    assert files == ["reports/stop-width-attribution.json"]
    written = json.loads((data / "reports" / "stop-width-attribution.json").read_text(encoding="utf-8"))
    assert written["study"] == ea.STUDY_ID
    out = capsys.readouterr().out
    assert f"**Verdict: {written['verdict']['verdict']}**" in out
    assert "Expectancy attribution" not in out          # the v146 summary is not printed
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_report.py`
Expected: FAIL in the three `--study` tests with `SystemExit: 2` (`unrecognized arguments: --study stop-width`); `test_without_the_flag_the_stop_width_study_never_runs` and every existing test pass.

- [ ] **Step 3: Implement**

In `scripts/reports/expectancy_attribution.py`, replace the module docstring's
last paragraph:

```python
Run: python scripts/reports/expectancy_attribution.py \
         --train-jsonl data/reports/v146-train-scenarios.jsonl
"""
```

with:

```python
Run: python scripts/reports/expectancy_attribution.py \
         --train-jsonl data/reports/v146-train-scenarios.jsonl

v226: --study stop-width runs the stop-width study instead (its own report,
data/reports/stop-width-attribution.json, and its Markdown on stdout); the
default report and the v146 verdict of record are never touched by it.
"""
```

Replace `main` with:

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--train-jsonl", required=True,
                        help="rows written by run_backtest_range.py --scenarios --train --trades-jsonl")
    parser.add_argument("--seed", type=int, default=None,
                        help="bootstrap seed (default: the instrument's WEEK_BOOTSTRAP_SEED)")
    parser.add_argument("--no-write", action="store_true",
                        help="do not replace data/reports/expectancy-attribution.json "
                             "(with --study stop-width: stop-width-attribution.json)")
    parser.add_argument("--study", choices=("stop-width",), default=None,
                        help="v226: run the stop-width study and print its Markdown "
                             "instead of the v146 report")
    args = parser.parse_args(argv)

    from swingbot.core.analytics import expectancy_attribution as study
    seed = study.WEEK_BOOTSTRAP_SEED if args.seed is None else args.seed
    if args.study == "stop-width":
        report = study.run_stop_width(args.train_jsonl, seed=seed, write=not args.no_write)
        print(study.stop_width_markdown(report), end="")
        return 0
    report = study.run(args.train_jsonl, seed=seed, write=not args.no_write)
    print(summary(report))
    return 0
```

`end=""` because `stop_width_markdown` already ends with a newline: stdout is
exactly the Markdown, so `> logs/v226/stop-width.md` (V226-12) is the
renderer's output byte for byte. The first test's fake renderer returns a
trailing newline for the same reason.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_report.py`
Expected: all passed, including the unchanged `test_the_script_parses_calls_and_prints`.

Then: `python scripts/dev/testrun.py file tests/analytics/test_expectancy_attribution_default_pin.py`
Expected: 3 passed (V226-5's pins: the default report and the script summary are byte-identical).

Then: `python scripts/dev/testrun.py file tests/analytics/test_stop_width_report.py`
Expected: all passed.

- [ ] **Step 5: Complexity check**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`main` 3).

- [ ] **Step 6: Commit**

```bash
git add scripts/reports/expectancy_attribution.py tests/analytics/test_expectancy_attribution_report.py
git commit -m "feat(v226): --study stop-width on the attribution script; default report unchanged (V226-11)"
```


### Task V226-12: Preflight, live replica, TRAIN replay and the study run

**Model:** sonnet — runs fixed commands in a fixed order and stops on any failed check; the long replay itself goes to `backtest-runner`.

**Files:**
- No code change. Outputs (never committed; `data/` and `logs/` are ignored):
  - `data/reports/v226-train-scenarios.jsonl` plus `.run.json`, `.provenance.json`, `.done.jsonl` (the `.progress` file is deleted on completion)
  - `data/reports/stop-width-attribution.json`
  - `logs/v226/`: `stop_settings_hash.py`, `preflight-stop-settings.txt`, `store.txt`, `store-check.log`, `tickers.txt`, `tickers.txt.sha256`, `live-rows.txt`, `replay.log`, `backtest_range_summary.txt`, `stop-width.md`, `stop-width.err`, `verdict.txt`, `sha256.txt`

**Interfaces:**
- Consumes: V226-3/4/4b `--trades-jsonl` checkpointing and the run sidecar; V226-10 `run_stop_width`, `stop_width_report_path()`; V226-11 `--study stop-width`; V226-6 `load_stop_width_live_rows()`.
- Produces for V226-13: `data/reports/stop-width-attribution.json` (the report, with `provenance.run_sidecar` and `provenance.store_provenance` quoted), `logs/v226/stop-width.md` (the Markdown body), `logs/v226/verdict.txt`, `logs/v226/sha256.txt`; copies of all of them in the main checkout's `data/reports/` and `logs/v226/` so they outlive the worktree.

**Rules for this task (Global Constraints restated where they bite).**
- Computed **once**. The verdict is never re-run to change it; a restart after an interruption is the same command and resumes, it is not a re-run.
- `.env` values are never printed, echoed, logged or quoted. The stop settings are compared as hashes held in shell variables; only `MATCH` / `MISMATCH` is printed.
- Production is read only, and only through the main checkout's `scripts/ops/ssh-hetzner.sh` (it is uncommitted, so it is not in the worktree).
- The training-data store is never refetched mid-study (`fetch_backtest_data.py` is not run). A failed store check stops the task and is reported to the controller.
- Any failed check below **stops the task**: report what failed, change nothing, and wait for the controller.
- Worktree trap: the worktree's untracked `data/watchlist.json` is a 3-ticker fixture. The replay takes its tickers from the main checkout's watchlist through `--tickers-file`, never from the worktree's file. The history store itself falls back to the main checkout's `data/market_data` from a worktree (`history_store.resolve_data_root`).

- [ ] **Step 1: Confirm every code task is on the branch**

Run: `mkdir -p logs/v226; git log --oneline main..HEAD > logs/v226/branch.txt; for id in V226-1 V226-2 V226-3 V226-4 V226-4b V226-5 V226-6 V226-7 V226-8 V226-9 V226-10 V226-10b V226-11; do grep -q "($id)" logs/v226/branch.txt || echo "missing $id"; done; rm logs/v226/branch.txt`
Expected: no output. Any `missing` line stops the task.

- [ ] **Step 2: Stage `.env` and the ticker list in the worktree**

`.env` is needed by `swingbot.config` (stop settings, `TRAINING_DATA_SOURCE`,
`DATABASE_URL`). Copy it only when the worktree has none; never `cat` it:

```bash
mkdir -p logs/v226 data/reports
MAIN=/e/Documents/Private/Projects/Discord-Bot
if [ -f .env ]; then echo "env: present"; else cp "$MAIN/.env" .env && echo "env: copied (delete in Step 10)"; fi
```

Build the ticker list from the main checkout's watchlist (a JSON list of symbols):

```bash
python - <<'EOF'
import hashlib
import json
from pathlib import Path

raw = Path("E:/Documents/Private/Projects/Discord-Bot/data/watchlist.json").read_bytes()
tickers = json.loads(raw)
Path("logs/v226/tickers.txt").write_text("".join(f"{t}\n" for t in tickers), encoding="utf-8")
Path("logs/v226/tickers.txt.sha256").write_text(
    f"watchlist.json sha256 {hashlib.sha256(raw).hexdigest()} tickers {len(tickers)}\n",
    encoding="utf-8")
print("tickers", len(tickers))
EOF
```

Expected: `tickers 7x` (the production watchlist, about 77). Fewer than 50 stops the task (wrong file).

- [ ] **Step 3: Preflight 1 — local stop settings equal production `.env`**

Write `logs/v226/stop_settings_hash.py`:

```python
"""v226 preflight: sha256 of the three stop settings; prints nothing else."""
import hashlib
import json

from swingbot import config

NAMES = ("CLAMP_STOP_TO_HARD_CAP", "MIN_STOP_DISTANCE_PCT", "MAX_STOP_LOSS_PCT")
print(hashlib.sha256(json.dumps([getattr(config, name) for name in NAMES]).encode()).hexdigest())
```

Compare (the hashes stay in shell variables and are never printed):

```bash
MAIN=/e/Documents/Private/Projects/Discord-Bot
LOCAL_SHA=$(python - < logs/v226/stop_settings_hash.py 2>/dev/null | tail -n 1)
PROD_SHA=$(bash "$MAIN/scripts/ops/ssh-hetzner.sh" "cd /opt/swing-bot && docker compose exec -T bot python -" < logs/v226/stop_settings_hash.py 2>/dev/null | tail -n 1)
if [ -n "$LOCAL_SHA" ] && [ "$LOCAL_SHA" = "$PROD_SHA" ]; then echo MATCH; else echo MISMATCH; fi | tee logs/v226/preflight-stop-settings.txt
```

Expected: `MATCH`. `MISMATCH` (or an empty side) stops the task: report it,
do not edit `.env` locally or on production (a production change needs
`mirror-prod` and the partner).

- [ ] **Step 4: Preflight 2 — the v162 training-data store is intact**

```bash
python - > logs/v226/store.txt <<'EOF'
from swingbot import config
from swingbot.core.marketdata import training_data

prov = training_data.provenance()
print("source", config.TRAINING_DATA_SOURCE, "| store", prov.get("store"),
      "| store_dir", prov.get("store_dir"), "| manifest", prov.get("manifest_hash"))
EOF
cat logs/v226/store.txt
```

Expected: `source alpaca` and a `store_dir` under the main checkout's
`data/market_data`. `source yfinance` stops the task (the spec reads the v162
store, not the legacy CSV cache).

```bash
python scripts/data/check_history_store.py --verify-hashes > logs/v226/store-check.log 2>&1; echo "store check exit $?"
```

Expected: `store check exit 0`. Any other exit stops the task; report the last
20 lines of `logs/v226/store-check.log`. The store is not refetched.

- [ ] **Step 5: Top up the live replica**

Invoke the `replicate-prod-db` skill (the shared `swing-db` container, port
56789). Then check the live rows load and carry `stop_atr`:

```bash
python - > logs/v226/live-rows.txt <<'EOF'
from swingbot.core.analytics import expectancy_attribution as ea

rows = ea.load_stop_width_live_rows()
print("live rows", len(rows), "| unknown stop_atr", sum(1 for r in rows if r["stop_atr"] is None),
      "| last closed", max((r["closed_at"] or "" for r in rows), default=None))
EOF
cat logs/v226/live-rows.txt
```

Expected: several hundred live rows and a last-closed date of the replica
sync day or the day before. Zero rows stops the task (wrong database or an
empty replica).

- [ ] **Step 6: The TRAIN replay, through `backtest-runner`**

Dispatch the `backtest-runner` agent (one at a time, nothing else running)
with this brief, naming the worktree:

> Worktree `.claude/worktrees/2026-11-12-v226-stop-width-attribution` (run from its root; do not touch the main tree). Run in the background:
> `python scripts/backtest/run_backtest_range.py --scenarios --train --exit-model v2 --scale-out --tickers-file logs/v226/tickers.txt --trades-jsonl data/reports/v226-train-scenarios.jsonl > logs/v226/replay.log 2>&1`
> Report progress from `data/reports/v226-train-scenarios.jsonl.progress` (percent and tickers done). If the run is interrupted, restart it with the identical command: it resumes from `v226-train-scenarios.jsonl.done.jsonl` and skips finished tickers. A `SystemExit 2` about a differing sidecar means the arguments changed: stop and report, never delete the done file. When it exits, report: exit code, the `loaded N/M cached tickers` line, the `Wrote N trade rows` line, and whether the `.progress` file is gone.

Expected from the runner: exit 0, `loaded` about 72/77 (v146 had 72/77 with
5,558 rows; a different count is reported, not a stop), `Wrote N trade rows`,
no `.progress` file. If the script refuses `--tickers-file` together with
`--train`, stop and report — never drop the flag (the worktree watchlist is
the 3-ticker fixture).

Then check the four replay files and move the summary:

```bash
ls data/reports/v226-train-scenarios.jsonl data/reports/v226-train-scenarios.jsonl.run.json data/reports/v226-train-scenarios.jsonl.provenance.json data/reports/v226-train-scenarios.jsonl.done.jsonl
test ! -e data/reports/v226-train-scenarios.jsonl.progress && echo "progress cleared"
wc -l < data/reports/v226-train-scenarios.jsonl.done.jsonl
mv backtest_range_summary.txt logs/v226/backtest_range_summary.txt
```

Expected: the four files listed, `progress cleared`, and a done-line count
equal to the `loaded N` of the `loaded N/M` line.

- [ ] **Step 7: Run the study once**

```bash
python scripts/reports/expectancy_attribution.py --train-jsonl data/reports/v226-train-scenarios.jsonl --study stop-width > logs/v226/stop-width.md 2> logs/v226/stop-width.err; echo "study exit $?"
```

Expected: `study exit 0`. The 10,000-resample bootstrap over at most 4 looks
takes a few minutes. Then print only the verdict lines:

```bash
python - <<'EOF' | tee logs/v226/verdict.txt
import json
from pathlib import Path

report = json.loads(Path("data/reports/stop-width-attribution.json").read_text(encoding="utf-8"))
verdict = report["verdict"]
print("verdict", verdict["verdict"], "| candidates", verdict["candidates"] or "none",
      "| family", verdict["family_size"], "| powered", verdict["powered"])
print("edges", [round(edge, 4) for edge in report["edges"]],
      "| train rows", report["provenance"]["train_rows"]["rows"],
      "| train unknown", report["disclosures"]["train"]["unknown"],
      "| live unknown", report["disclosures"]["live"]["unknown"],
      "| volatility_note", report["volatility_note"])
for label in report["labels"]:
    look = verdict["looks"][label]
    print(label, "n", look["n"], "exp_r", look["exp_r"], "delta", look["delta"],
          "q", look["q"], "candidate", look["candidate"])
EOF
```

This number is final. It is not re-run, re-seeded or re-cut.

- [ ] **Step 8: Hash every output**

```bash
sha256sum data/reports/v226-train-scenarios.jsonl data/reports/v226-train-scenarios.jsonl.run.json data/reports/v226-train-scenarios.jsonl.provenance.json data/reports/v226-train-scenarios.jsonl.done.jsonl data/reports/stop-width-attribution.json logs/v226/stop-width.md > logs/v226/sha256.txt
```

- [ ] **Step 9: Copy the outputs to the main checkout**

The worktree is removed at close-out (V226-14); the results doc cites these
files by path, so they must survive it (copy, never move or link):

```bash
MAIN=/e/Documents/Private/Projects/Discord-Bot
mkdir -p "$MAIN/data/reports" "$MAIN/logs/v226"
cp data/reports/v226-train-scenarios.jsonl data/reports/v226-train-scenarios.jsonl.run.json data/reports/v226-train-scenarios.jsonl.provenance.json data/reports/v226-train-scenarios.jsonl.done.jsonl data/reports/stop-width-attribution.json "$MAIN/data/reports/"
cp logs/v226/* "$MAIN/logs/v226/"
sed "s#  #  $MAIN/#" logs/v226/sha256.txt | sha256sum -c -
```

Expected: every line `OK`.

- [ ] **Step 10: Clean up and hand over**

If Step 2 printed `env: copied`, delete the copy: `rm .env`. Nothing is
committed in this task (`git status --short` shows no tracked change). Report
to the controller: the contents of `logs/v226/verdict.txt`,
`preflight-stop-settings.txt`, `store.txt`, `live-rows.txt`, the runner's
`loaded`/`Wrote` lines, and any restart that happened.

### Task V226-13: Results doc, pre-registration ledger row, closed-pre-registration record per verdict

**Model:** opus — writes the record of a pre-registered verdict: the observations must say only what the tables show, and the closing wording decides what may be re-opened later.

**Files:**
- Create: `docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md`
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (one row, through `scripts/reports/preregistration_ledger.py`, never by hand)
- Modify: `docs/claude/backtest-methodology.md` (§ Closed pre-registrations — **only** when the verdict is `NO CANDIDATE`)
- `AGENTS.md`: unchanged — it mirrors rules, not the closed-pre-registration table (`git grep -n "Closed pre-registrations" AGENTS.md` returns nothing). If that grep ever returns a line, mirror the row there in the same commit.

**Interfaces:**
- Consumes: V226-12's outputs in the worktree: `data/reports/stop-width-attribution.json` (report keys `generated_at, study, seed, edges, labels, verdict, disclosures, volatility_note, provenance`; `verdict.looks[label]` keys `n, exp_r, delta, ci_low, ci_high, p, q, years, years_negative, clauses, candidate`), `logs/v226/stop-width.md`, `logs/v226/sha256.txt`, `logs/v226/tickers.txt.sha256`, `logs/v226/live-rows.txt`, `logs/v226/preflight-stop-settings.txt`, `logs/v226/store.txt`. `scripts/reports/preregistration_ledger.py` flags `--id --date --hypothesis --instrument --n --exp-r --p --verdict --record --data-source` (`--n/--exp-r/--p` accept `null`; `--verdict` from `stats.VERDICTS`; `--data-source` `alpaca|yfinance`).
- Produces: the committed results doc and ledger row `v226-stop-width` (V226-14's `/panel` and `/close-out` read them).

**Verdict mapping (controller-approved).** Ledger verdict: `VETO-CANDIDATE` → `PASS`, `NO CANDIDATE` → `NO-LIFT`, `UNDERPOWERED` → `INCONCLUSIVE`. The decisive bucket for the ledger's `n / exp_r / p` is the candidate with the most negative Δ when there is a candidate, else the bucket with the most negative Δ.

- [ ] **Step 1: Generate the mechanical part of the results doc**

Run from the worktree root:

```bash
python - <<'EOF'
"""v226 results doc: header, verdict, the spec's rule verbatim, the study's
Markdown body and the provenance, all read from the run's own files."""
import json
from pathlib import Path

SPEC = Path("docs/superpowers/specs/2026-11-12-v226-stop-width-attribution-design.md")
REPORT = Path("data/reports/stop-width-attribution.json")
OUT = Path("docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md")
LOGS = Path("logs/v226")
SENTENCE = {
    "VETO-CANDIDATE": ("Licenses a Stage −2 avoid idea for {cands}, never a veto: the idea "
                       "must earn a SCREEN-AVOID-PASS before its spec, and that spec measures "
                       "the veto paired on the bot's own replay with replacement trades included."),
    "NO CANDIDATE": ("Closes \"tight stops in ATR terms\" as measured; recorded in "
                     "`docs/claude/backtest-methodology.md` § Closed pre-registrations."),
    "UNDERPOWERED": ("Leaves the question open: {powered} of {family} buckets reached N ≥ 300 "
                     "and the rule needs at least two. N ≥ 300 known TRAIN rows in each of at "
                     "least two buckets would power it."),
}


def text(name: str) -> str:
    return (LOGS / name).read_text(encoding="utf-8").strip()


report = json.loads(REPORT.read_text(encoding="utf-8"))
verdict, prov = report["verdict"], report["provenance"]
spec = SPEC.read_text(encoding="utf-8")
rule = spec[spec.index("Each bucket (at most 4 looks;"):spec.index("This bar is weaker than")].strip()
body = text("stop-width.md").split("\n", 1)[1].strip()          # drop the renderer's own title
summary = SENTENCE[verdict["verdict"]].format(
    cands=", ".join(verdict["candidates"]), powered=verdict["powered"],
    family=verdict["family_size"])
head = [
    "# v226 Stop-width attribution: result", "",
    f"**Run:** {report['generated_at'][:10]}, TRAIN confluence replay 2020-01-06..2023-12-29 "
    "(signal date) under the live stop settings, with the live book (closed production "
    "trades, read from the local replica) printed beside it and never gating. Read-only; "
    "VALIDATION never read.",
    "**Spec:** `docs/superpowers/specs/2026-11-12-v226-stop-width-attribution-design.md`",
    "**Plan:** `docs/superpowers/plans/2026-11-12-v226-stop-width-attribution_0-index.md`", "",
    f"**Verdict: {verdict['verdict']}.** {summary}", "",
    "Rule, quoted from the spec (pre-registered; computed once, in this run; later runs are "
    "descriptive and never revise it):", "",
    *(f"> {line}" if line else ">" for line in rule.splitlines()), "",
    f"All figures are as stored in `data/reports/stop-width-attribution.json`: R net of "
    f"frictions, `ExpR gross` beside it, seed {report['seed']}, {prov['n_resamples']} "
    "week-clustered bootstrap resamples.", ""]
provenance = [
    "## Provenance", "",
    f"- Code: branch `2026-11-12-v226-stop-width-attribution` at "
    f"`{(prov['run_sidecar'] or {}).get('git_head')}`.",
    f"- TRAIN rows: `{prov['train_rows']['path']}`, {prov['train_rows']['rows']} rows, "
    f"sha256 `{prov['train_rows']['sha256']}`.",
    f"- Tickers: `logs/v226/tickers.txt`, from the main checkout's watchlist ({text('tickers.txt.sha256')}).",
    f"- Live: {text('live-rows.txt')}.",
    f"- Preflight: stop settings {text('preflight-stop-settings.txt')} against production "
    "`.env` (compared as hashes; values never printed); store "
    f"`{text('store.txt')}`, `check_history_store.py --verify-hashes` exit 0.",
    f"- Frictions `{json.dumps(prov['frictions'], sort_keys=True)}`; live fills include "
    f"frictions: {prov['live_fills_include_frictions']}.", "",
    "Run sidecar (`data/reports/v226-train-scenarios.jsonl.run.json`):", "",
    "```json", json.dumps(redact_stop_settings(prov["run_sidecar"]), indent=1, sort_keys=True), "```", "",
    "Store provenance (`data/reports/v226-train-scenarios.jsonl.provenance.json`):", "",
    "```json", json.dumps(prov["store_provenance"], indent=1, sort_keys=True), "```", "",
    "Hashes (`logs/v226/sha256.txt`; copies sit in the main checkout's `data/reports/` "
    "and `logs/v226/`):", "", "```", text("sha256.txt"), "```", ""]
OUT.write_text("\n".join(head) + "\n" + body + "\n\n" + "\n".join(provenance), encoding="utf-8")
print("wrote", OUT, len(OUT.read_text(encoding="utf-8").splitlines()), "lines")
EOF
```

Expected: `wrote docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md <n> lines`.
No `.env` value appears in the doc (partner rule: never quote `.env`
values). The generator defines, above the `provenance` list,

```python
import hashlib

def redact_stop_settings(sidecar):
    """The sidecar with `stop_settings` replaced by its sha256 (sorted JSON)."""
    if not sidecar or "stop_settings" not in sidecar:
        return sidecar
    blob = json.dumps(sidecar["stop_settings"], sort_keys=True).encode("utf-8")
    return {**sidecar, "stop_settings": {"sha256": hashlib.sha256(blob).hexdigest()}}
```

so the doc carries the settings' hash and the preflight's `MATCH`, never the
values. Check after writing: `grep -c '"CLAMP_STOP_TO_HARD_CAP"' <doc>` prints
`0`.

- [ ] **Step 2: Write Observations, Caveats and What follows by hand**

Append three sections to the results doc. Every number quoted comes from the
tables already in the doc; no new statistic is computed and no threshold is
chosen from them.

`## Observations` — one bullet each, stating what the tables show:
- the TRAIN `unknown` count and its share of all TRAIN rows, and the same for live;
- whether any bucket's Δ sign differs between TRAIN and live (descriptive only; live never gates);
- the TRAIN rho and overlap and, when `volatility_note` is true, the sentence "This verdict is about ticker volatility, not stop placement." in bold;
- the `stop_clamped` share per TRAIN bucket, called a lower bound;
- any bucket whose direction or horizon mix is above 70% one way, and any Δ-by-direction that differs in sign from the bucket's Δ;
- the removal arithmetic of the decisive bucket (pooled ExpR, ExpR without, ΔTotal R, N removed), with the sentence "This ignores replacement trades: a vetoed plan frees a slot that another plan would take."
- the live same-day-loss share per bucket beside the 2026-11-12 observation in the spec (about 47% of trades stopped out the day they opened).

`## Caveats` — these five, verbatim:

```markdown
- **Descriptive, not a veto.** Each bucket's filled TRAIN rows are compared with the rest. The study does not estimate what a veto would do to pooled ExpR, because a vetoed plan frees a slot that a different plan would take.
- **`stop_atr` is measured from the signal close,** not from the planned entry or trigger (`swingbot/core/edge/context.py`); a truncation test pins it as point-in-time.
- **`stop_clamped` is a lower-bound provenance flag:** identity-based (a natural stop that lands on the clamp is flagged too) and read from `CLAMP_STOP_TO_HARD_CAP` at run time; `None` rows leave its denominator.
- **The live book never gates.** Live N is small and correlated, and the live trades fall inside the v2 instrument's sealed holdout (2026-01-01 onward): any follow-on screened from these tables has seen them and must say so.
- **Fill models differ.** The replay and the live tracker do not model gap fills identically, so live and TRAIN R compare in sign and order, not to the last decimal.
```

`## What follows` — exactly one of:
- `VETO-CANDIDATE`: "A Stage −2 avoid idea for `<candidate labels>`: skip confluence plans whose signal-bar `stop_atr` falls below `<the candidate's upper edge>` (on the TRAIN edges above). It needs a `SCREEN-AVOID-PASS` ledger row before any spec; that spec then measures the veto paired on the bot's own replay with replacement trades included. No veto ships from this result."
- `NO CANDIDATE`: "Closed. Recorded in `docs/claude/backtest-methodology.md` § Closed pre-registrations. Reopening needs a mechanism other than \"a TRAIN quartile of stop distance in ATR14 units\"."
- `UNDERPOWERED`: "Open. `<powered>` of `<family_size>` buckets reached N ≥ 300 (bucket N: `<n per label>`); the rule needs N ≥ 300 in at least two buckets. Not closed and not re-run on this replay; a new run needs a longer window or a wider universe, named in a new spec."

- [ ] **Step 3: Add the ledger row**

```bash
python - <<'EOF'
"""v226 ledger row from the report: decisive bucket = most negative delta
(among candidates when there is one)."""
import json
import subprocess
import sys
from pathlib import Path

HYPOTHESIS = (
    "stop_atr (abs(signal close - stop) / ATR14, both at the signal bar) in TRAIN quartile "
    "buckets with edges frozen from TRAIN known values: a bucket is a veto candidate when "
    "delta <= -0.10R against the rest of the known rows, upper 95% bound < 0, bucket ExpR < 0, "
    "delta < 0 in >= 3 of 2020-2023, N >= 300 and BH q < 0.10 over this study's own <= 4 "
    "looks; week-clustered bootstrap, 10,000 resamples, seed 42; TRAIN 2020-01-06..2023-12-29 "
    "confluence replay, live book printed beside it and never gating (v226 descriptive "
    "attribution; licenses a Stage -2 avoid screen at most)")
LEDGER_VERDICT = {"VETO-CANDIDATE": "PASS", "NO CANDIDATE": "NO-LIFT",
                  "UNDERPOWERED": "INCONCLUSIVE"}

report = json.loads(Path("data/reports/stop-width-attribution.json").read_text(encoding="utf-8"))
verdict = report["verdict"]
looks = verdict["looks"]
pool = verdict["candidates"] or [label for label in report["labels"]
                                 if looks[label]["delta"] is not None] or report["labels"]
decisive = min(pool, key=lambda label: looks[label]["delta"] if looks[label]["delta"] is not None else 0.0)
look = looks[decisive]
source = (report["provenance"]["store_provenance"] or {}).get("data_source")
assert source in ("alpaca", "yfinance"), f"store provenance names no data source: {source!r}"


def num(value) -> str:
    return "null" if value is None else f"{value:.4f}"


print("decisive", decisive, "n", look["n"], "exp_r", num(look["exp_r"]), "p", num(look["p"]),
      "ledger verdict", LEDGER_VERDICT[verdict["verdict"]], "source", source)
subprocess.run([sys.executable, "scripts/reports/preregistration_ledger.py",
                "--id", "v226-stop-width", "--date", report["generated_at"][:10],
                "--instrument", "v1", "--hypothesis", HYPOTHESIS,
                "--n", str(look["n"]), "--exp-r", num(look["exp_r"]), "--p", num(look["p"]),
                "--verdict", LEDGER_VERDICT[verdict["verdict"]],
                "--record", "docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md",
                "--data-source", source], check=True)
EOF
tail -n 1 docs/superpowers/results/preregistration-ledger.jsonl | cut -c1-160
```

Expected: the `decisive ...` line, then a last ledger line starting
`{"id": "v226-stop-width"`.

- [ ] **Step 4: `NO CANDIDATE` only — the closed-pre-registration row**

Skip this step for `VETO-CANDIDATE` and `UNDERPOWERED`. For `NO CANDIDATE`,
insert the row at the top of the § Closed pre-registrations table:

```bash
python - <<'EOF'
"""Insert the v226 row first in backtest-methodology.md's closed table."""
import json
from pathlib import Path

DOC = Path("docs/claude/backtest-methodology.md")
HEADING = "### Closed pre-registrations — do not re-run these"
report = json.loads(Path("data/reports/stop-width-attribution.json").read_text(encoding="utf-8"))
verdict, looks = report["verdict"], report["verdict"]["looks"]
assert verdict["verdict"] == "NO CANDIDATE", verdict["verdict"]


def fmt(value) -> str:
    return "n/a" if value is None else f"{value:+.4f}"


cells = "; ".join(
    f"{label} N={looks[label]['n']}, ExpR {fmt(looks[label]['exp_r'])}R, Δ "
    f"{fmt(looks[label]['delta'])}R [{fmt(looks[label]['ci_low'])}, "
    f"{fmt(looks[label]['ci_high'])}], q {fmt(looks[label]['q'])}"
    for label in report["labels"])
tickers = len(((report["provenance"]["run_sidecar"] or {}).get("watchlist") or {}).get("tickers") or [])
known = sum(looks[label]["n"] for label in report["labels"])
rho = report["disclosures"]["train"]["rho"]
volatility = (f"Spearman rho stop_atr vs atr_pct {rho:+.4f} on TRAIN: the verdict is about "
              "ticker volatility, not stop placement. " if report["volatility_note"] else "")
component = ("Stop width in ATR14 units: TRAIN quartile buckets of `entry_context[\"stop_atr\"]` "
             "(distance from the signal close to the stop over ATR14, both at the signal bar), "
             "each against the rest of the known rows (v226 read-only attribution)")
outcome = (f"**NO CANDIDATE; pre-registered verdict, computed once, no budget spent.** TRAIN "
           f"2020-01-06..2023-12-29 confluence replay, {tickers} tickers, {known} known rows "
           f"({report['disclosures']['train']['unknown']} unknown); edges "
           f"{', '.join(f'{edge:.2f}' for edge in report['edges'])}. {cells}. "
           f"{verdict['powered']} of {verdict['family_size']} buckets powered (N ≥ 300); BH over "
           f"this study's {verdict['family_size']} looks, seed 42, R net of frictions; live book "
           "printed beside it, never gating. Rule, all six per bucket: Δ ≤ −0.10R, upper 95% "
           "bound < 0, bucket ExpR < 0, Δ < 0 in ≥ 3 of 2020–2023, N ≥ 300, BH q < 0.10. "
           f"{volatility}Closes \"tight stops in ATR terms\" as measured. Reopening needs a "
           "mechanism other than \"a TRAIN quartile of stop distance in ATR14 units\"; another "
           "quantile cut, window, or the live-book cut 0.35 / 0.5 / 0.75 is not a new mechanism.")
row = f"| {component} | {outcome} | `results/2026-11-12-v226-stop-width-attribution.md` |"
assert "|" not in component and "|" not in outcome
lines = DOC.read_text(encoding="utf-8").split("\n")
start = lines.index(HEADING)
separator = next(i for i in range(start, len(lines)) if lines[i].startswith("|---"))
lines.insert(separator + 1, row)
DOC.write_text("\n".join(lines), encoding="utf-8")
print("inserted at line", separator + 2)
EOF
```

Expected: `inserted at line <n>`, directly under the table's `|---|---|---|` line.

- [ ] **Step 5: Run the record checks**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_preregistration_ledger_file.py`
Expected: all passed (the ledger validates, the record file exists, and a `(v226)` closed-table row has its `v226-` ledger row).

Run: `python scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`
Expected: all passed (the closed-table heading keeps its level and text).

Run: `python scripts/dev/testrun.py file tests/hooks/test_codex_mirror.py`
Expected: all passed (no mirrored rule changed).

Run: `wc -l docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md`
Expected: under 1500 lines.

- [ ] **Step 6: Commit (two scoped commits)**

```bash
git add docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(v226): stop-width attribution result and ledger row (V226-13)"
```

`NO CANDIDATE` only:

```bash
git add docs/claude/backtest-methodology.md
git commit -m "docs(v226): close tight stops in ATR terms in Closed pre-registrations (V226-13)"
```

### Task V226-14: Release (Bump none), merge, CI watch, `/panel` close-out review, `/close-out`

**Model:** sonnet — a fixed release ritual driven by skills; every judgement in it (merge, panel findings) goes to the partner or the panel.

**Files:**
- None planned. `VERSION.json` and `version_history.json` stay untouched (`Bump: none`).
- Possible follow-up commits: fixes for a red CI job (the failing test's own file and the code it names), panel BLOCKING findings, the `/close-out` move of the plan and spec, and Step 5b skill alignment if a citation needs it.

**Interfaces:**
- Consumes: every earlier task committed on branch `2026-11-12-v226-stop-width-attribution`; V226-13's results doc and ledger row.
- Produces: the branch merged on `main`, CI green, the panel findings recorded, the plan and spec under `implemented/`, the worktree removed.

- [ ] **Step 1: Pre-merge checks in the worktree**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (`run_scenario_mode` still 19 and `main` still 62 or lower, per `complexity_baseline.json`).

Run each narrow file (no full suite; CI runs it):

```bash
for f in tests/backtesting/test_scenario_stop_atr_pit.py tests/backtesting/test_scenario_ticker_hook.py tests/backtesting/test_scenario_run_sidecar.py tests/backtesting/test_scenario_checkpoint_cli.py tests/backtesting/test_scenario_trade_rows_cli.py tests/analytics/test_expectancy_attribution_default_pin.py tests/analytics/test_stop_width_rows.py tests/analytics/test_stop_width_edges.py tests/analytics/test_stop_width_verdict.py tests/analytics/test_stop_width_disclosures.py tests/analytics/test_stop_width_report.py tests/analytics/test_stop_width_markdown.py tests/analytics/test_expectancy_attribution_report.py tests/backtesting/test_preregistration_ledger_file.py; do python scripts/dev/testrun.py file "$f" > logs/v226/release-$(basename "$f" .py).log 2>&1 && echo "ok $f" || echo "FAIL $f"; done
```

Expected: every line `ok`. A `FAIL` is fixed in its own file and re-run alone
(`python scripts/dev/testrun.py file <that file>`), never by a wider run.

Run: `git diff --stat main...HEAD -- VERSION.json version_history.json`
Expected: no output (`Bump: none`).

- [ ] **Step 2: Ask the partner before merging**

Invoke the `worktree-lifecycle` skill for the merge checks (concurrent
sessions, `git fetch` and `origin/main` against local `main`). Then ask with
`AskUserQuestion`, one question, recommended option first:

> "v226 is complete on its worktree branch: <verdict from `logs/v226/verdict.txt`>, results doc and ledger row committed, narrow tests green. Merge `2026-11-12-v226-stop-width-attribution` into `main` and push?"
> Options: "Merge and push (Recommended)" / "Hold the merge".

"Hold" ends the task here with the branch intact.

- [ ] **Step 3: Merge and push**

Follow `worktree-lifecycle`'s merge procedure from the main checkout (it names
the exact commands; never `--force`, never a branch deletion here). Then:

```bash
git push origin main
```

- [ ] **Step 4: Watch CI until green**

```bash
gh run list --branch main --limit 1 --json databaseId --jq '.[0].databaseId' > logs/v226/ci-run-id.txt
gh run watch "$(cat logs/v226/ci-run-id.txt)" --exit-status > logs/v226/ci-watch.log 2>&1
```

Run the watch in the background (`run_in_background`). On a red job, read only
that job's failing test names (`gh run view <id> --log-failed | grep -E "FAILED|Error" | head -40`),
fix each in its own file, re-run it alone with `testrun.py file`, commit the
fix as its own scoped commit, push, and watch the new run. Repeat until green.

- [ ] **Step 5: `/panel` close-out review**

Invoke the `panel` skill: `quant-researcher,quant-engineer` over the merged
diff (`git diff <merge-base>..main` for the v226 commits) and
`docs/superpowers/results/2026-11-12-v226-stop-width-attribution.md`. Apply
each BLOCKING finding as its own commit (re-running the affected test file
alone); record every finding, with how it was handled, in a
`## Panel review` section at the end of the results doc, committed as
`docs(v226): close-out panel review`. A finding that would change the verdict
is never applied by re-running the study: it is reported to the partner.

- [ ] **Step 6: `/close-out`**

Invoke the `close-out` skill. `Bump: none`: no `VERSION.json` change and no
`version_history.json` regeneration. Destination `implemented/` (a measurement
with a recorded verdict is implemented, whatever the verdict). Before it
removes the worktree, confirm the V226-12 outputs exist in the main
checkout: `ls /e/Documents/Private/Projects/Discord-Bot/data/reports/stop-width-attribution.json /e/Documents/Private/Projects/Discord-Bot/logs/v226/stop-width.md`.

Step 5b (skill alignment): run
`git grep -n "trades-jsonl\|\.progress\|expectancy_attribution.py\|stop-width" -- .claude/skills .claude/agents`.
At plan time this finds nothing (`backtest-gate` cites `run_backtest_range.py`
only by name and for `--validation`), so no skill changes. If it finds a line
that names the `--trades-jsonl` outputs or the attribution script's flags,
add the new files (`.run.json`, `.done.jsonl`) or `--study stop-width` there,
run `python scripts/dev/sync_codex.py`, and commit both in one commit.

