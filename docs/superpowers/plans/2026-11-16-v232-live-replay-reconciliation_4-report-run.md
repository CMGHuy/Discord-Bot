# v232 — Live versus replay reconciliation: Part 4, report and run

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V232-14" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-16-v232-live-replay-reconciliation-design.md](../specs/2026-11-16-v232-live-replay-reconciliation-design.md) (binding: `## Clarifications from the code brief`)
**Index:** [2026-11-16-v232-live-replay-reconciliation_0-index.md](2026-11-16-v232-live-replay-reconciliation_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, the task ledger and `## Handoff` live there and bind every task below.

Tasks V232-13..V232-16: the statistics and counting module (V232-13), report assembly and the results Markdown (V232-14), the leak guard and the CLI with its manifest and resume rules (V232-15), and the two production-run guards plus the operational run that writes the results doc and the ledger row (V232-16).

**Moved between this part's tasks for the 20 KB task cap (no task split, ledger still 20 rows; the index ledger rows should follow):** `intervals.population`, `slip`, `ledger_cells` are built in V232-13 (not V232-14); `render.leaks`, `FORBIDDEN_KEYS`, `BACKTEST_R_KEYS` in V232-15 (same module and names); the CLI's `--expect-params-digest` and the `<work-dir>/run.json` claim in V232-16 (same CLI file).

Consumed from earlier parts (ledger rows, created there): `layer1_run.TradeRow` (`.scored`, `to_dict`, `from_dict`), `layer1_run.REFUSALS`, `run_layer1` (V232-9, V232-9b); `checkpoint.JsonlCheckpoint` (V232-9b); `layer1.FILL_MODELS`, `layer1.OUTCOME_CLASSES` (V232-7); `tags.TAGS` (V232-8b, 17 names); `records.Export`, `load_export`, `deploys_between`, `CLASSES` (V232-6); `sessions.ny_time` (V232-5); `raw_bars.REFUSALS`, `fetch_bars`, `load_bars`, `bars_manifest` (V232-4, V232-4b); `layer2.SIDES`, `ERAS`, `ReplaySignal`, `live_plans`, `match`, `selection_counts` (cells `counts[side][era]`), `REPLAY_ONLY_REASONS`, `LIVE_ONLY_BUCKETS` (V232-10); `layer2_run.replay_tickers`, `live_short_modes`, `reference_symbols`, `load_frames`, `coverage`, `params_digest`, `run_layer2`, `SNAPSHOT_FN` (V232-11); `table.build_table`, `self_check`, `selection_line`, `ReconcileError`, `TOLERANCE_R` (V232-12).

Row fields read here (V232-9): `side`, `era`, `klass`, `refusal`, `ticker` (populations only), `ledger` (live figures only), `entry_date`, `r_live_gross`, `cost_r`, `r_live_net`, `live_class`, `values[model]` (`r_exit_only`, `exit_only_class`, `r_as_backtest`, `r_rebased`, `stop_shift_pct`, `backtest_no_fill`), `effects[model]` (`exit`, `entry`), `tags`, `gap` (`gap_r`, `gap_pct`, `exit_vs_open_r`, `exit_vs_stop_r`), `entry_slip` and `poll_fill` (`(bps, R)`), `unfilled_reason`, `would_fill[model]`.

Test imports, every task: `sys.path.insert(0, str(REPO / "scripts" / "reports"))`, then `from reconcile import <module>`, with `REPO = Path(__file__).resolve().parents[2]`.

## Review Focus

- **Backtest R keyed by a component.** Every backtest-R aggregate lives under `report["layer1"][side][era][fill_model]`, whose keys come from a closed vocabulary; `leaks()` flags any key outside it, any `FORBIDDEN_KEYS` key anywhere, a backtest key outside `layer1`, and a Markdown heading or table header naming both a component and a backtest quantity. Pinned in V232-15 (`test_backtest_r_keyed_by_strategy_is_a_leak`, `test_a_heading_with_backtest_r_by_ticker_is_a_leak`).
- **The coverage ticker counts** (`coverage.base_missing_days`, keyed by ticker, no R; Handoff) and the refused-ticker lists stay in the report and are **not** leaks: they carry counts, never R. Pinned in V232-14 (`test_coverage_counts_and_refused_tickers_are_listed`) and V232-15 (`test_backtest_r_keyed_by_strategy_is_a_leak` asserts the clean report has no leak).
- **Rows reaching the table without `TradeRow.from_dict`** (Handoff). The CLI assembles its rows from the checkpoint file through `TradeRow.from_dict`; pinned in V232-15 (`test_trade_rows_are_checkpointed_and_hashed`).
- **A doc that does not open with the caveat** (spec anti-goal). Pinned in V232-14 (`test_the_doc_opens_with_the_caveat_and_carries_the_labels`).
- **A stale checkpoint read for another window** (reproducibility). The work dir carries a run key; a different export, window or bars root refuses. Pinned in V232-16 (`test_a_stale_work_dir_refuses`).
- **Production touched for writing, or a `.env` value printed** (V232-16). Every production command goes through `bash scripts/ops/ssh-hetzner.sh` and is read-only; the parameter comparison prints only digests and field names.

---

# Phase 4 — Report and run

### Task V232-13: Intervals, cells, confusion and distributions

**Model:** sonnet — thin wrappers over the existing week-cluster bootstrap and the autopsy's thin rule, plus counting helpers; every number pinned below.

**Files:**
- Create: `scripts/reports/reconcile/intervals.py`
- Create: `tests/scout/test_reconcile_intervals.py`

**Interfaces:**
- Consumes: existing `stats.week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed)` (`stats.py:57`; groups items by `.entry_date` ISO week, drops draws where the statistic is `None`), `stats.iso_week_key`; `autopsy.cells.is_thin(n, weeks)` (`n < 30 or weeks < 8`); `layer1.OUTCOME_CLASSES`, `FILL_MODELS` (V232-7); `tags.TAGS` (V232-8b); `records.CLASSES` (V232-6); `layer1_run.REFUSALS`, `TradeRow` (V232-9); `raw_bars.REFUSALS` (V232-4b). Runs in parallel with V232-12: it never imports `table`.
- Produces (ledger V232-13, final; consumed by V232-14): `INTERVAL_LABEL`, `WeekItem`, `one_arm_interval`, `CellStats` (+ `to_dict()`, floats to 4 places), `cell_stats`, `confusion`, `distribution`, `tag_means`, `cell_count`, with the ledger's signatures. **Beyond the ledger row** (additive, this task's own file, moved here from V232-14 for the 20 KB cap): `population(rows) -> dict`, `slip(rows) -> dict`, `ledger_cells(rows, *, n_resamples, seed) -> dict`.

**Rules this task freezes (spec `### Statistics`, `### Populations`, clarification 7):**

| Name | Rule |
|---|---|
| `one_arm_interval` | `week_cluster_bootstrap([], items, mean of the draw)`: the baseline arm is empty, so a draw is the component arm alone; the 2.5th and 97.5th percentiles; `None` below **two** entry weeks or when every draw was dropped. |
| `cell_stats` | `largest_week_share` = the largest absolute weekly total over the sum of absolute weekly totals (builder's call: a share of the signed total is undefined or above 1 when weeks cancel); `thin = is_thin(n, weeks)`; `with_interval=False` skips the bootstrap. |
| `confusion`, `tag_means` | Scored rows with values for the fill model; the full 4×4 grid and all 17 tags, zeros kept (known-traps T2); tag means carry no interval (spec). |
| `population`, `slip`, `ledger_cells` | One side and era each. Refused tickers are listed (spec; counts, no R); `would_fill` `unknown` = bars refused; slip is live against its own levels; ledger cells are live net R only (Global Constraints), no interval. |
| `cell_count` | The "cells shown" count: per `report["layer1"][side][era][fill_model]` block `len(effects) + len(tags)`, plus per `report["selection"][side][era]` cell `len(live_only.by_bucket) + len(replay_only.by_reason)`; a missing section counts 0. **This fixes the report layout V232-14 builds.** |

- [ ] **Step 1: Write the failing tests** — `tests/scout/test_reconcile_intervals.py`:

```python
"""v232 V232-13: intervals, cells, confusion, distributions, tag means, populations, slip."""
import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import intervals, layer1, layer1_run, tags  # noqa: E402

FAST = {"n_resamples": 500, "seed": 42}
MONDAYS = ["2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12"]


def _items(values, days):
    return [intervals.WeekItem(day, value) for value, day in zip(values, days)]


def _row(live="win", exit_only="loss", exit_effect=0.5, tags_=(), model="v1", scored=True):
    return layer1_run.TradeRow.from_dict({
        "plan_id": "P", "side": "long", "era": "headline",
        "klass": "closed" if scored else "manual", "entry_date": "2026-10-06",
        "live_class": live,
        "values": {model: {"exit_only_class": exit_only, "r_exit_only": 0.1}} if scored else {},
        "effects": {model: {"exit": exit_effect, "entry": 0.0}} if scored else {},
        "tags": list(tags_)})


def _full(**kw):
    base = {"plan_id": "P", "ticker": "AAA", "side": "long", "era": "headline", "klass": "closed",
            "entry_date": "2026-10-06", "ledger": "main", "r_live_net": 0.5,
            "values": {"v1": {}}, "effects": {"v1": {}}}
    return layer1_run.TradeRow.from_dict({**base, **kw})


def test_the_label_is_the_spec_text():
    assert intervals.INTERVAL_LABEL == "descriptive; under-covers below 20 clusters"


def test_one_arm_interval_brackets_the_mean_and_is_seeded():
    items = _items([1.0, 2.0, 3.0, 4.0], MONDAYS)
    low, high = intervals.one_arm_interval(items, **FAST)
    assert 1.0 <= low <= 2.5 <= high <= 4.0
    assert intervals.one_arm_interval(items, **FAST) == (low, high)


def test_one_arm_interval_needs_two_weeks():
    assert intervals.one_arm_interval(_items([1.0, 3.0], ["2026-09-21", "2026-09-23"]), **FAST) is None
    assert intervals.one_arm_interval([], **FAST) is None


def test_cell_stats_reads_n_weeks_total_share_and_thin():
    cell = intervals.cell_stats(_items([1.0, -0.5, 2.0], ["2026-09-21", "2026-09-22", "2026-09-28"]),
                                **FAST)
    assert (cell.n, cell.weeks, cell.total) == (3, 2, 2.5)
    assert cell.mean == pytest.approx(2.5 / 3)
    assert cell.largest_week_share == pytest.approx(0.8)       # |2.0| / (|0.5| + |2.0|)
    assert cell.thin is True and cell.interval is not None


def test_an_empty_cell_has_no_mean_share_or_interval():
    cell = intervals.cell_stats([], **FAST)
    assert (cell.n, cell.weeks, cell.total, cell.mean) == (0, 0, 0.0, None)
    assert (cell.largest_week_share, cell.interval, cell.thin) == (None, None, True)


def test_a_cell_without_interval_skips_the_bootstrap():
    cell = intervals.cell_stats(_items([1.0, 2.0], MONDAYS[:2]), with_interval=False, **FAST)
    assert cell.interval is None and cell.n == 2


def test_thin_follows_the_autopsy_rule():
    days = [(dt.date(2026, 8, 3) + dt.timedelta(weeks=i % 8)).isoformat() for i in range(30)]
    assert intervals.cell_stats(_items([0.1] * 30, days), **FAST).thin is False
    assert intervals.cell_stats(_items([0.1] * 29, days), **FAST).thin is True


def test_to_dict_rounds_and_lists_the_interval():
    out = intervals.cell_stats(_items([1.0, 2.0, 3.0, 4.0], MONDAYS), **FAST).to_dict()
    assert set(out) == {"n", "weeks", "total", "mean", "largest_week_share", "interval", "thin"}
    assert isinstance(out["interval"], list) and out["mean"] == 2.5


def test_confusion_is_live_against_exit_only_with_zero_cells():
    rows = [_row("win", "loss"), _row("win", "loss"), _row("loss", "loss"),
            _row("win", "loss", scored=False), _row("win", "win", model="v2")]
    grid = intervals.confusion(rows, "v1")
    assert set(grid) == set(layer1.OUTCOME_CLASSES)
    assert all(set(cols) == set(layer1.OUTCOME_CLASSES) for cols in grid.values())
    assert (grid["win"]["loss"], grid["loss"]["loss"]) == (2, 1)
    assert sum(sum(cols.values()) for cols in grid.values()) == 3


def test_distribution_reads_median_and_p90():
    assert intervals.distribution([1.0, 2.0, 3.0, 4.0, None]) == {"n": 4, "median": 2.5, "p90": 3.7}
    assert intervals.distribution([]) == {"n": 0, "median": None, "p90": None}


def test_tag_means_keep_every_tag_and_read_the_exit_effect():
    rows = [_row(exit_effect=0.5, tags_=("same_day_exit",)),
            _row(exit_effect=-0.1, tags_=("same_day_exit", "wick_missed")),
            _row(exit_effect=9.0, tags_=("same_day_exit",), scored=False)]
    means = intervals.tag_means(rows, "v1")
    assert list(means) == list(tags.TAGS) and len(means) == 17
    assert means["same_day_exit"] == {"n": 2, "mean_exit_effect": 0.2}
    assert means["wick_missed"] == {"n": 1, "mean_exit_effect": -0.1}
    assert means["gap_through"] == {"n": 0, "mean_exit_effect": None}


def test_population_counts_classes_refusals_and_would_fill():
    rows = [_full(), _full(klass="manual"), _full(refusal="split_in_window", ticker="CCC"),
            _full(klass="unfilled", unfilled_reason="expired", would_fill={"v1": True, "v2": None}),
            _full(klass="unfilled", unfilled_reason=None, would_fill={"v1": False, "v2": False})]
    pop = intervals.population(rows)
    assert pop["classes"] == {"closed": 2, "manual": 1, "still_open": 0, "unfilled": 2}
    assert pop["scored"] == 1 and pop["refusals"]["split_in_window"] == 1
    assert pop["refused_tickers"] == {"no_bars": [], "split_in_window": ["CCC"],
                                      "bars_end_early": []}
    assert pop["unfilled_reasons"] == {"expired": 1, "unknown": 1}
    assert pop["would_fill"] == {"v1": {"yes": 1, "no": 1, "unknown": 0},
                                 "v2": {"yes": 0, "no": 1, "unknown": 1}}


def test_slip_reads_both_measures_and_the_gap_detail():
    gap = {"gap_r": -1.2, "gap_pct": -2.0, "exit_vs_open_r": 0.1, "exit_vs_stop_r": -1.1}
    rows = [_full(entry_slip=[10.0, 0.06], poll_fill=[5.0, 0.02], gap=gap),
            _full(entry_slip=[20.0, 0.1]), _full(klass="manual", entry_slip=[99.0, 9.0])]
    out = intervals.slip(rows)
    assert out["entry_slip_bps"] == {"n": 2, "median": 15.0, "p90": 19.0}
    assert out["poll_fill_r"]["n"] == 1 and out["gap_pct"]["median"] == -2.0


def test_ledger_cells_are_live_only_without_interval():
    rows = [_full(), _full(ledger="weak", r_live_net=-1.0),
            _full(klass="still_open", r_live_net=None), _full(refusal="no_journal", r_live_net=None)]
    cells = intervals.ledger_cells(rows, **FAST)
    assert set(cells) == {"main", "weak"}
    assert (cells["main"]["total"], cells["weak"]["total"]) == (0.5, -1.0)
    assert cells["main"]["interval"] is None


def test_cell_count_reads_effects_tags_and_sub_reasons():
    report = {"layer1": {"long": {"headline": {"v1": {"effects": {"a": {}, "b": {}},
                                                      "tags": {"t": {}}}}}},
              "selection": {"long": {"headline": {"live_only": {"by_bucket": {"x": 0, "y": 0}},
                                                  "replay_only": {"by_reason": {"z": 0}}}}}}
    assert intervals.cell_count(report) == 6
    assert intervals.cell_count({}) == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_intervals.py`
Expected: FAIL — `ImportError: cannot import name 'intervals' from 'reconcile'`.

- [ ] **Step 3: Implement `scripts/reports/reconcile/intervals.py`**

```python
"""v232 statistics (spec ### Statistics): one-arm week-cluster intervals and the cells around them.

Intervals come only from instrument/stats.week_cluster_bootstrap (clarification 7: an empty
baseline arm and a statistic over the drawn rows), clustered by entry week. Tag means and
distributions carry no interval.
"""
from __future__ import annotations

import dataclasses
from collections import Counter, defaultdict

import numpy as np

from autopsy import cells as autopsy_cells
from swingbot.core.backtesting.instrument import stats

from . import layer1, layer1_run, raw_bars, records, tags

INTERVAL_LABEL = "descriptive; under-covers below 20 clusters"
_GAP_KEYS = ("gap_r", "gap_pct", "exit_vs_open_r", "exit_vs_stop_r")


@dataclasses.dataclass(frozen=True)
class WeekItem:
    entry_date: str
    value: float


def _r4(value):
    return None if value is None else round(float(value), 4)


def _draw_mean(_baseline, draw) -> float | None:
    return float(np.mean([item.value for item in draw])) if draw else None


def _week_totals(items) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for item in items:
        totals[stats.iso_week_key(item.entry_date)] += item.value
    return dict(totals)


def one_arm_interval(items, *, n_resamples: int, seed: int) -> tuple[float, float] | None:
    """2.5/97.5 percentiles of the week-resampled mean; None below two entry weeks."""
    items = list(items)
    if len(_week_totals(items)) < 2:
        return None
    draws = stats.week_cluster_bootstrap([], items, _draw_mean,
                                         n_resamples=n_resamples, seed=seed)
    if draws.size == 0:
        return None
    low, high = np.percentile(draws, [2.5, 97.5])
    return float(low), float(high)


@dataclasses.dataclass(frozen=True)
class CellStats:
    n: int
    weeks: int
    total: float
    mean: float | None
    largest_week_share: float | None
    interval: tuple[float, float] | None
    thin: bool

    def to_dict(self) -> dict:
        return {"n": self.n, "weeks": self.weeks, "total": _r4(self.total),
                "mean": _r4(self.mean), "largest_week_share": _r4(self.largest_week_share),
                "interval": None if self.interval is None else [_r4(v) for v in self.interval],
                "thin": self.thin}


def _largest_share(week_totals: dict) -> float | None:
    spread = sum(abs(v) for v in week_totals.values())
    return max(abs(v) for v in week_totals.values()) / spread if spread else None


def cell_stats(items, *, n_resamples: int, seed: int, with_interval: bool = True) -> CellStats:
    """N, entry weeks, total, mean, the largest week's share, the interval and the thin flag."""
    items = list(items)
    weeks = _week_totals(items)
    total = float(sum(item.value for item in items))
    interval = (one_arm_interval(items, n_resamples=n_resamples, seed=seed)
                if with_interval else None)
    return CellStats(n=len(items), weeks=len(weeks), total=total,
                     mean=total / len(items) if items else None,
                     largest_week_share=_largest_share(weeks), interval=interval,
                     thin=autopsy_cells.is_thin(len(items), len(weeks)))


def _scored(rows, fill_model: str) -> list:
    return [r for r in rows if r.scored and fill_model in r.values]


def confusion(rows, fill_model: str) -> dict[str, dict[str, int]]:
    """Live outcome class (rows) against the exit-only class (columns), zeros kept."""
    grid = {live: dict.fromkeys(layer1.OUTCOME_CLASSES, 0) for live in layer1.OUTCOME_CLASSES}
    for row in _scored(rows, fill_model):
        grid[row.live_class][row.values[fill_model]["exit_only_class"]] += 1
    return grid


def distribution(values) -> dict:
    """Median and 90th percentile of the non-None values."""
    kept = [float(v) for v in values if v is not None]
    if not kept:
        return {"n": 0, "median": None, "p90": None}
    return {"n": len(kept), "median": _r4(np.median(kept)), "p90": _r4(np.percentile(kept, 90))}


def tag_means(rows, fill_model: str) -> dict[str, dict]:
    """Per tag: how many scored rows carry it and their mean exit effect (no interval)."""
    scored = _scored(rows, fill_model)
    out = {}
    for tag in tags.TAGS:
        exits = [r.effects[fill_model]["exit"] for r in scored if tag in r.tags]
        out[tag] = {"n": len(exits), "mean_exit_effect": _r4(np.mean(exits)) if exits else None}
    return out


def _yes_no(rows, fill_model: str) -> dict:
    got = [r.would_fill.get(fill_model) for r in rows]
    return {"yes": sum(g is True for g in got), "no": sum(g is False for g in got),
            "unknown": sum(g is None for g in got)}


def population(rows) -> dict:
    """Class counts, refusals (refused tickers listed), unfilled reasons and would-fill."""
    unfilled = [r for r in rows if r.klass == "unfilled"]
    reasons = Counter(r.unfilled_reason or "unknown" for r in unfilled)
    return {"classes": {k: sum(r.klass == k for r in rows) for k in records.CLASSES},
            "scored": sum(r.scored for r in rows),
            "refusals": {k: sum(r.refusal == k for r in rows) for k in layer1_run.REFUSALS},
            "refused_tickers": {k: sorted({r.ticker for r in rows if r.refusal == k})
                                for k in raw_bars.REFUSALS},
            "unfilled_reasons": dict(sorted(reasons.items())),
            "would_fill": {m: _yes_no(unfilled, m) for m in layer1.FILL_MODELS}}


def _parts(rows, attr: str, i: int) -> dict:
    return distribution([getattr(r, attr)[i] for r in rows if getattr(r, attr) is not None])


def slip(rows) -> dict:
    """entry_slip and poll_fill (bps, R) and the gap detail, as distributions over scored rows."""
    scored = [r for r in rows if r.scored]
    out = {f"{attr}_{unit}": _parts(scored, attr, i)
           for attr in ("entry_slip", "poll_fill") for i, unit in enumerate(("bps", "r"))}
    out.update({k: distribution([r.gap[k] for r in scored if r.gap]) for k in _GAP_KEYS})
    return out


def ledger_cells(rows, *, n_resamples: int, seed: int) -> dict:
    """Live net R per ledger over closed and manual rows (live figures only, no interval)."""
    book = [r for r in rows if r.klass in ("closed", "manual") and r.r_live_net is not None]
    return {name: cell_stats([WeekItem(r.entry_date, r.r_live_net) for r in book
                              if r.ledger == name],
                             n_resamples=n_resamples, seed=seed, with_interval=False).to_dict()
            for name in sorted({r.ledger for r in book})}


def cell_count(report: dict) -> int:
    """Means shown: effect cells and tag means per block, plus layer 2 sub-reasons."""
    n = 0
    for by_era in report.get("layer1", {}).values():
        for by_model in by_era.values():
            for block in by_model.values():
                n += len(block.get("effects", {})) + len(block.get("tags", {}))
    for by_era in report.get("selection", {}).values():
        for cell in by_era.values():
            n += len(cell["live_only"]["by_bucket"]) + len(cell["replay_only"]["by_reason"])
    return n
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_intervals.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/intervals.py tests/scout/test_reconcile_intervals.py
git commit -m "feat(v232): week-cluster intervals, cells, confusion, tag means, populations and slip"
```

### Task V232-14: Report assembly and the results Markdown

**Model:** sonnet — finished aggregates into a fixed layout; every label decided below.

**Files:**
- Create: `scripts/reports/reconcile/render.py`
- Create: `tests/scout/test_reconcile_render.py`

**Interfaces:**
- Consumes: `table.*` (V232-12; its line labels stay as written), `intervals.*` (V232-13), `layer2.SIDES`, `ERAS`, the `selection_counts` cell (V232-10), `records.deploys_between` (V232-6), `layer1.FILL_MODELS`, `OUTCOME_CLASSES`. Fixture: `tests.scout.test_reconcile_table.BOOK`.
- Produces (ledger V232-14; consumed by V232-15): `TITLE`, `CAVEAT`, `NOTES`, `EFFECT_LABELS`, `MODEL_NAMES`, `BOUNDARY_DAY`, `build_report`, `render_markdown` (ledger signatures). **`leaks`, `FORBIDDEN_KEYS`, `BACKTEST_R_KEYS` move to V232-15** (same module and signatures; 20 KB task cap). `meta` must hold `window` (`[start, end]`, ISO) and `coverage` (`layer2_run.coverage`); other keys are copied.

**Layout (frozen; `intervals.cell_count` reads it):** top level `title`, `caveat`, `interval_label`, `notes`, `meta`, `deploys` (headline window), `cells`; per `[side][era]`: `populations`, `layer1[fill_model]` (`table`, `selection`, `effects{gap_net, entry, exit, costs}`, `cost_check`, `confusion`, `tags`, `rebase`), `slip`, `live_by_ledger`, `selection` (level diffs as distributions, plus `live_only.unexplained_share`).

**Decisions (V232-14 owns the wording, Handoff):**
- Per filled trade `gap_net = entry + exit - cost_r` (= live net minus backtest, Goal 1), `costs = -cost_r`. `table.self_check` runs for every block.
- **Cost check** (spec: "zero by construction; printed as a check"): `equally_costed = sum(r_live_net - r_live_gross + cost_r)` (the backtest at each trade's own cost); above `TOLERANCE_R` it raises `ReconcileError`.
- **Holdout by layout:** backtest R lives only under `layer1[side][era][fill_model]`; the ledger split is `live_by_ledger`, live R only. V232-15's `leaks` enforces it.

- [ ] **Step 1: Write the failing tests** — `tests/scout/test_reconcile_render.py`:

```python
"""v232 V232-14: report assembly and the results Markdown."""
import dataclasses
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import intervals, layer2, records, render, table  # noqa: E402
from tests.scout.test_reconcile_table import BOOK  # noqa: E402

EXPORT = records.Export(records=(), rejections=(), watchlist=(), deploys=(
    {"ts": "2026-10-01T12:00:00+00:00", "git_sha": "abc1234"},
    {"ts": "2026-08-01T12:00:00+00:00", "git_sha": "old0000"}))
META = {"window": ["2026-07-01", "2026-11-16"], "commit": "f00d", "params_digest": "d" * 64,
        "coverage": {"sessions": 40, "spy_missing": False, "base_missing_days": {"AAA": 2},
                     "panel_gaps": {}, "snapshot_missing": [], "extra_missing": {}}}


def _report(rows=BOOK):
    selection = layer2.selection_counts(layer2.MatchResult([], [], [], []), EXPORT)
    return render.build_report(rows, selection, EXPORT, meta=META, n_resamples=200, seed=42)


REPORT = _report()
MD = render.render_markdown(REPORT)


def test_every_block_holds_per_trade_sums_and_the_cost_check():
    assert all(set(REPORT["layer1"][s][e][m]["effects"]) == {"gap_net", "entry", "exit", "costs"}
               for s in layer2.SIDES for e in layer2.ERAS for m in ("v1", "v2"))
    block = REPORT["layer1"]["long"]["headline"]["v1"]
    assert (block["effects"]["exit"]["n"], block["effects"]["exit"]["total"]) == (3, -0.8)
    assert block["effects"]["costs"]["total"] == -0.4
    assert block["cost_check"] == {"zero_cost_backtest": -0.4, "equally_costed": 0.0}
    assert block["table"] == [dataclasses.asdict(line) for line in
                              table.build_table(BOOK, side="long", fill_model="v1")]


def test_sections_use_the_interval_helpers_and_the_headline_deploys():
    long_rows = [r for r in BOOK if r.side == "long" and r.era == "headline"]
    assert REPORT["populations"]["long"]["headline"] == intervals.population(long_rows)
    assert REPORT["slip"]["long"]["headline"] == intervals.slip(long_rows)
    assert REPORT["deploys"] == [{"ts": "2026-10-01T12:00:00+00:00", "git_sha": "abc1234"}]


def test_a_tampered_row_fails_the_self_check():
    rows = [dataclasses.replace(BOOK[0], r_live_net=BOOK[0].r_live_net + 0.3)] + BOOK[1:]
    with pytest.raises(table.ReconcileError):
        _report(rows)


def test_the_doc_opens_with_the_caveat_and_carries_the_labels():
    lines = MD.splitlines()
    assert lines[0] == f"# {render.TITLE}" and lines[2] == f"> {render.CAVEAT}"
    assert render.CAVEAT.startswith("The live book is a paper book.")
    assert "(includes code changes)" in MD and "(incl. intraday drift to the close)" in MD
    assert intervals.INTERVAL_LABEL in MD and "zero by construction" in MD
    assert f"Cells shown: {REPORT['cells']} " in MD
    assert "2026-10-01T12:00:00+00:00 abc1234" in MD


def test_coverage_counts_and_refused_tickers_are_listed():
    assert REPORT["meta"]["coverage"]["base_missing_days"] == {"AAA": 2} and "AAA 2" in MD
    assert REPORT["populations"]["long"]["headline"]["refused_tickers"]["split_in_window"] == ["AAA"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_render.py`
Expected: FAIL — `ImportError: cannot import name 'render' from 'reconcile'`. (V232-15 appends its leak tests here, reusing `REPORT` and `MD`.)

- [ ] **Step 3: Implement `scripts/reports/reconcile/render.py`**

```python
"""v232 report assembly and Markdown (spec ### The reconciliation table, ### Statistics).

Aggregates only; backtest R sits under report["layer1"][side][era][fill_model] alone.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

from autopsy.eras import ERA_BOUNDARY_UTC

from . import intervals, layer1, layer2, records, sessions, table

TITLE = "v232 - Live versus replay reconciliation, per direction"
CAVEAT = (
    "The live book is a paper book. Entries and exits are filled at a quote polled once a "
    "minute, with no spread, no queue, no partial fills, no rejected orders and no failed "
    "locates. Costs in this report are modelled (5 bps a fill, commission, 0.5% a year borrow "
    "on shorts), not paid, and borrow availability is not modelled at all. A stop that a real "
    "order would fill at a gapped open is filled here where the poll saw it. So this report "
    "measures the backtest against the paper engine. It does not show that either is "
    "achievable in a real account; the eToro demo stage is the first place that can be "
    "measured. The \"unexplained\" shares carry the same warning.")
NOTES = (
    f"Intervals: one-arm week-cluster bootstrap over entry weeks, {intervals.INTERVAL_LABEL}. "
    "Tag means carry no interval; thin = under 30 trades or under 8 weeks.",
    "R is in the live trade's risk unit |live fill - issued stop|; costs are modelled.",
    "Exit effect = R_live - R_exit_only; entry effect = R_exit_only - R_as_backtest. The other "
    "order needs the backtest entry under live's intraday exits, which nobody observed, so the "
    "entry x exit interaction sits in the exit effect.",
    "The backtest's signal bar is the session of issue, so the entry effect includes the "
    "intraday drift from the live issue to the daily close.",
    "The era boundary (2026-09-15T08:54:50Z) and the manual-close rule were set after the book "
    "autopsy had read this book; acceptable for a description.",
    "Layer 2 replays the live scan with today's parameters, one decision a day at the close, "
    "without the strategy-sourced pass, alert cap, portfolio heat or live track record. "
    "Replay-only counts rest on replay holding periods (no replay outcome is stored or printed) "
    "and are a lower bound: removed tickers that never produced a plan or rejection are missing.",
    "Holdout: no outcome of a signal live did not trade is read; backtest R appears per "
    "direction, fill model and era only; the ledger split is shown for live figures only.",
    "Citation rule: a later spec may cite mechanism counts and shares from this report; it may "
    "not cite a backtest-R effect size from it as evidence, and it still owes its own screen "
    "or pre-registration.")
EFFECT_LABELS = {"gap_net": "live net - backtest",
                 "entry": "entry effect (incl. intraday drift to the close)",
                 "exit": "exit effect (incl. the entry x exit interaction)",
                 "costs": "modelled costs (live net - live gross)"}
MODEL_NAMES = {"v1": "v1 walk", "v2": "v2 fills"}
BOUNDARY_DAY = sessions.ny_time(ERA_BOUNDARY_UTC).date().isoformat()
_PAIRS = tuple((s, e) for s in layer2.SIDES for e in layer2.ERAS)


def _pick(rows, side: str, era: str) -> list:
    return [r for r in rows if r.side == side and r.era == era]


def _grid(fn) -> dict:
    return {s: {e: fn(s, e) for e in layer2.ERAS} for s in layer2.SIDES}


def _total(values) -> float:
    return round(float(sum(v for v in values if v is not None)), 4)


def _effect_fns(m: str) -> dict:
    return {"gap_net": lambda r: r.effects[m]["entry"] + r.effects[m]["exit"] - r.cost_r,
            "entry": lambda r: r.effects[m]["entry"], "exit": lambda r: r.effects[m]["exit"],
            "costs": lambda r: -r.cost_r}


def _cost_check(filled) -> dict:
    equal = sum(r.r_live_net - r.r_live_gross + r.cost_r for r in filled)
    if abs(equal) > table.TOLERANCE_R:
        raise table.ReconcileError(f"cost check: {equal:+.4f}R against an equally costed backtest")
    return {"zero_cost_backtest": _total(r.r_live_net - r.r_live_gross for r in filled),
            "equally_costed": round(abs(equal), 4)}      # abs: within tolerance, never "-0.00"


def _model_block(rows, side: str, era: str, m: str, selection: dict, kw: dict) -> dict:
    lines = table.build_table(rows, side=side, fill_model=m, era=era)
    table.self_check(lines, rows, side=side, fill_model=m, era=era)
    picked = _pick(rows, side, era)
    filled = [r for r in picked if r.scored and not r.values[m]["backtest_no_fill"]]
    shifts = [r.values[m]["stop_shift_pct"] for r in filled]
    effects = {k: intervals.cell_stats([intervals.WeekItem(r.entry_date, f(r)) for r in filled],
                                       **kw).to_dict() for k, f in _effect_fns(m).items()}
    rebase = {"n_filled": len(filled), "n_no_fill": sum(r.scored for r in picked) - len(filled),
              "n_rebased": sum(s is not None and abs(s) > 1e-9 for s in shifts),
              "r_rebased_total": _total(r.values[m]["r_rebased"] for r in filled),
              "stop_shift_pct": intervals.distribution(shifts)}
    return {"table": [dataclasses.asdict(line) for line in lines],
            "selection": table.selection_line(selection, rows, side=side, era=era),
            "effects": effects, "cost_check": _cost_check(filled),
            "confusion": intervals.confusion(picked, m), "tags": intervals.tag_means(picked, m),
            "rebase": rebase}


def _selection(cell: dict) -> dict:
    live = cell["live_only"]
    share = round(live["unexplained"] / live["n"], 4) if live["n"] else None
    return {**cell,
            "level_diffs": {k: intervals.distribution(v) for k, v in cell["level_diffs"].items()},
            "live_only": {**live, "live_r_net": round(live["live_r_net"], 4),
                          "unexplained_share": share}}


def build_report(rows, selection: dict, export, *, meta: dict, n_resamples: int,
                 seed: int) -> dict:
    """Aggregates only; runs table.self_check for every side, era and fill model."""
    kw = {"n_resamples": n_resamples, "seed": seed}
    found = records.deploys_between(export, dt.date.fromisoformat(BOUNDARY_DAY),
                                    dt.date.fromisoformat(meta["window"][1]))
    report = {
        "title": TITLE, "caveat": CAVEAT, "interval_label": intervals.INTERVAL_LABEL,
        "notes": list(NOTES), "meta": meta,
        "deploys": [{"ts": d.get("ts"), "git_sha": d.get("git_sha")} for d in found],
        "populations": _grid(lambda s, e: intervals.population(_pick(rows, s, e))),
        "layer1": _grid(lambda s, e: {m: _model_block(rows, s, e, m, selection, kw)
                                      for m in layer1.FILL_MODELS}),
        "slip": _grid(lambda s, e: intervals.slip(_pick(rows, s, e))),
        "live_by_ledger": _grid(lambda s, e: intervals.ledger_cells(_pick(rows, s, e), **kw)),
        "selection": _grid(lambda s, e: _selection(selection[s][e]))}
    report["cells"] = intervals.cell_count(report)
    return report


def _num(x, fmt: str = "+.2f") -> str:
    return "n/a" if x is None else format(x, fmt)


def _counts(d: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in d.items()) or "none"


def _dist(d: dict) -> str:
    return f"median {_num(d['median'])}, p90 {_num(d['p90'])} (n {d['n']})"


def _table(header, rows) -> list[str]:
    return (["| " + " | ".join(header) + " |", "|---" * len(header) + "|"]
            + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows] + [""])


def _cell(name: str, c: dict) -> list:
    iv = "n/a" if c["interval"] is None else f"[{c['interval'][0]:+.3f}, {c['interval'][1]:+.3f}]"
    return [name, c["n"], c["weeks"], _num(c["total"]), _num(c["mean"], "+.3f"), iv,
            _num(c["largest_week_share"], ".0%"), "thin" if c["thin"] else ""]


def _era_title(report: dict, side: str, era: str) -> str:
    if era == "headline":
        return f"{side.upper()}, trades opened {BOUNDARY_DAY} to {report['meta']['window'][1]}"
    return f"{side.upper()}, trades opened before {BOUNDARY_DAY} (includes code changes)"


def _block_md(block: dict, title: str, m: str) -> list[str]:
    rb, cc, classes = block["rebase"], block["cost_check"], layer1.OUTCOME_CLASSES
    out = [f"### {title}, {MODEL_NAMES[m]}", "", "```", f"{'':64}total R      N"]
    out += [f"  {line['label']:<62}{line['total_r']:+9.2f}{line['n']:>7}" for line in block["table"]]
    out += ["", f"  {block['selection']}", "```", "",
            f"Re-based backtest total (its own entry-to-stop unit) {rb['r_rebased_total']:+.2f}R "
            f"over {rb['n_filled']} filled, {rb['n_rebased']} re-based; stop-distance shift % "
            f"{_dist(rb['stop_shift_pct'])}. Modelled cost effect {cc['zero_cost_backtest']:+.2f}R "
            f"against a zero-cost backtest, {cc['equally_costed']:+.2f}R against an equally costed "
            "one (zero by construction; a check).", ""]
    out += _table(["Effect", "N", "weeks", "total R", "mean",
                   f"interval ({intervals.INTERVAL_LABEL})", "largest week", "thin"],
                  [_cell(EFFECT_LABELS[k], c) for k, c in block["effects"].items()])
    out += _table(["live \\ exit-only", *classes],
                  [[live, *block["confusion"][live].values()] for live in classes])
    return out + _table(["Tag", "N", "mean exit effect (no interval)"],
                        [[t, v["n"], _num(v["mean_exit_effect"], "+.3f")]
                         for t, v in block["tags"].items()])


def _head_md(report: dict) -> list[str]:
    m = report["meta"]
    bars = {k: f"{v['sha256'][:12]} ({v['n_ok']} ok, {v['n_empty']} empty)" if v else "none"
            for k, v in m.get("bars", {}).items()}
    deploys = ", ".join(f"{d['ts']} {d['git_sha']}" for d in report["deploys"])
    out = [f"# {report['title']}", "", f"> {report['caveat']}", "", "## How to read this", ""]
    out += [f"- {note}" for note in report["notes"]]
    out += [f"- Cells shown: {report['cells']} (effect cells and tag means x directions x fill "
            "models x eras, plus layer 2 sub-reasons); read one large mean against that number.",
            "", "## Run", "",
            f"- Commit {m.get('commit')}; window {m['window'][0]} to {m['window'][1]}; scan "
            f"parameters digest {m.get('params_digest')}; live SHORT lanes "
            f"{', '.join(m.get('short_modes', [])) or 'none'}.",
            f"- Per-trade rows (git-ignored) SHA-256 {m.get('rows_sha256')}; inputs "
            f"{_counts(m.get('inputs', {}))}; raw bars {_counts(bars)}.",
            f"- Deploys inside the headline window (known confounds): {deploys or 'none (measured)'}.",
            "", "## Populations", ""]
    rows, notes = [], []
    for s, e in _PAIRS:
        p = report["populations"][s][e]
        rows.append([s, e, *p["classes"].values(), p["scored"],
                     *(f"{w['yes']}/{w['no']}" for w in p["would_fill"].values())])
        listed = {k: ", ".join(v) for k, v in p["refused_tickers"].items() if v}
        notes.append(f"- {s} {e}: refused {_counts({k: n for k, n in p['refusals'].items() if n})}"
                     f" (bars: {_counts(listed)}); unfilled reasons {_counts(p['unfilled_reasons'])}.")
    header = ["Side", "Era", *records.CLASSES, "scored",
              *(f"would fill {m} (yes/no)" for m in layer1.FILL_MODELS)]
    return out + _table(header, rows) + notes + [""]


def _tail_md(report: dict) -> list[str]:
    slip = [[s, e, k, d["n"], _num(d["median"]), _num(d["p90"])]
            for s, e in _PAIRS for k, d in report["slip"][s][e].items()]
    ledger = [[s, e, name, c["n"], c["weeks"], _num(c["total"]), _num(c["mean"], "+.3f")]
              for s, e in _PAIRS for name, c in report["live_by_ledger"][s][e].items()]
    cov = report["meta"]["coverage"]
    out = (["## Entry slip, poll fill and gaps (live against its own levels)", ""]
           + _table(["Side", "Era", "measure", "N", "median", "p90"], slip)
           + ["## Live net R by ledger (live figures only)", ""]
           + _table(["Side", "Era", "Ledger", "N", "weeks", "total R", "mean"], ledger)
           + ["## Layer 2: which signals each side took (counts only, no R)", "",
              f"- Coverage: {cov['sessions']} decision sessions; SPY missing {cov['spy_missing']}; "
              f"panel gaps {_counts({d: len(v) for d, v in cov['panel_gaps'].items()})}; snapshot "
              f"missing {', '.join(cov['snapshot_missing']) or 'none'}; extra-lane bars missing "
              f"{_counts(cov['extra_missing'])}; base tickers with missing sessions "
              f"{_counts(cov['base_missing_days'])}."])
    for s, e in _PAIRS:
        c = report["selection"][s][e]
        lo, ro, d = c["live_only"], c["replay_only"], c["level_diffs"]
        out.append(
            f"- {s} {e}: matched {c['matched']} (entry % {_dist(d['entry_pct'])}; stop ratio "
            f"{_dist(d['stop_ratio'])}; target ratio {_dist(d['target_ratio'])}); live-only "
            f"{lo['n']} ({_counts(lo['by_bucket'])}; unexplained share "
            f"{_num(lo['unexplained_share'], '.0%')}; live net {lo['live_r_net']:+.2f}R over "
            f"{lo['live_r_n']}); replay-only {ro['n']} ({_counts(ro['by_reason'])}; gates "
            f"{_counts(ro['by_gate'])}); outside the replay (strategy-sourced) {c['outside_replay']}.")
    return out + [""]


def render_markdown(report: dict) -> str:
    """The results doc: title, the caveat, how to read it, then every section in order."""
    out = _head_md(report)
    for s, e in _PAIRS:
        title = _era_title(report, s, e)
        out += [f"## {title}", ""]
        for m in layer1.FILL_MODELS:
            out += _block_md(report["layer1"][s][e][m], title, m)
    return "\n".join(out + _tail_md(report)) + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_render.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/render.py tests/scout/test_reconcile_render.py
git commit -m "feat(v232): report assembly and the results Markdown"
```

### Task V232-15: The leak guard, the CLI, manifest and end-to-end run on fixtures

**Model:** sonnet — finished modules behind one command; refusal and leak rules below.

**Files:**
- Modify: `scripts/reports/reconcile/render.py` (the leak guard, from V232-14)
- Modify: `tests/scout/test_reconcile_render.py`
- Create: `scripts/reports/live_replay_reconcile.py`
- Create: `tests/scout/test_live_replay_reconcile.py`

**Interfaces:**
- Consumes: the earlier parts' ledger names (this file's header lists them); `REPORT`, `MD` of the render tests (V232-14); existing `autopsy.rows.friction_settings`, `ScanParams.from_config` (`swingbot/scan_params.py:107`), `AlpacaProvider(key, secret, live_feed)` (`fetch_alpaca_history.py:190` precedent). Fixtures: `test_reconcile_layer1_run._rec`, `BARS` (V232-9).
- Produces (consumed by V232-16): `render.FORBIDDEN_KEYS`, `BACKTEST_R_KEYS`, `leaks(report, markdown) -> list[str]` (the ledger's V232-14 names); `live_replay_reconcile.main(argv=None) -> int` with the ledger's flags and outputs **except `--expect-params-digest`**, which V232-16 adds with the work-dir claim (20 KB cap); `make_provider()`, `RunRefused`, `_run`, `_sha256`.

**Leak rule** (Global Constraints, "No component R"): the three key checks of `_key_leaks` and the heading check of `leaks` below. Coverage's ticker-keyed day counts and the refused-ticker lists carry no R and pass (Handoff).

**CLI rules:** export → raw bars over `[since, until or today]` → layer 1 → layer 2 (same window) → report → leak guard → write. Every refusal prints `refused: <reason>`, writes nothing and exits 2. Rows come from the checkpoint file through `TradeRow.from_dict`, in export order (Handoff). `meta.inputs` keeps file names only.

- [ ] **Step 1a: Write the failing leak tests** — add `import copy` to the imports of `tests/scout/test_reconcile_render.py`, then append:

```python
def test_backtest_r_keyed_by_strategy_is_a_leak():
    assert render.leaks(REPORT, MD) == [] and "AAA 2" in MD     # coverage counts pass (Handoff)
    bad = copy.deepcopy(REPORT)
    bad["layer1"]["long"]["headline"]["v1"]["by_strategy"] = {"RSI": 0.4}
    assert any("by_strategy" in p for p in render.leaks(bad, MD))


def test_a_forbidden_key_or_backtest_key_outside_layer1_is_a_leak():
    bad = copy.deepcopy(REPORT)
    bad["populations"]["long"]["headline"]["ticker"] = "AAA"
    bad["selection"]["long"]["headline"]["r_as_backtest"] = 1.0
    problems = render.leaks(bad, MD)
    assert any("forbidden key" in p for p in problems)
    assert any("outside layer1" in p for p in problems)


def test_a_heading_with_backtest_r_by_ticker_is_a_leak():
    assert render.leaks(REPORT, MD + "\n## Backtest R by ticker\n")
    assert render.leaks(REPORT, MD + "\n| Strategy | exit effect |\n|---|---|\n")
    assert render.leaks(REPORT, MD + "\n## Live net R by ticker\n") == []
```

- [ ] **Step 1b: Write the failing CLI tests** — `tests/scout/test_live_replay_reconcile.py`:

```python
"""v232 V232-15: the CLI end to end on fixtures (no network, no database)."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from swingbot import config

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import layer2, layer2_run, render, table  # noqa: E402
from tests.scout.test_reconcile_layer1_run import BARS, _rec  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "live_replay_reconcile_script", REPO / "scripts" / "reports" / "live_replay_reconcile.py")
cli = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cli)

SIGNAL = layer2.ReplaySignal(lane="base", ticker="AAA", direction="bullish", source="confluence",
                             mode=None, decision_date="2026-10-06", horizon_key="2w",
                             strategy="RSI", entry=100.0, stop=98.0, target=104.0)
COVERAGE = {"window": ["2026-10-05", "2026-10-20"], "sessions": 12, "spy_missing": False,
            "base_missing_days": {"AAA": 2}, "panel_gaps": {}, "snapshot_missing": [],
            "extra_missing": {}}


class Provider:
    def __init__(self):
        self.calls = 0

    def daily_bars_between(self, tickers, start, end, *, adjustment):
        self.calls += 1
        kind = 0 if adjustment.value == "raw" else 1
        return {t: BARS[t][kind] for t in tickers if t in BARS}


@pytest.fixture
def env(monkeypatch, tmp_path):
    for name, value in (("SLIPPAGE_BPS", 5.0), ("COMMISSION_PER_TRADE", 1.0),
                        ("COMMISSION_RISK_BASIS", 100.0)):
        monkeypatch.setattr(config, name, value, raising=False)
    provider, lanes = Provider(), []

    def run_layer2(frames, window, params, *, base_tickers, modes, checkpoint_dir, out=print):
        lanes.append((window, tuple(base_tickers), tuple(sorted(modes))))
        return [SIGNAL]

    monkeypatch.setattr(cli, "make_provider", lambda: provider)
    monkeypatch.setattr(layer2_run, "params_digest", lambda params: "d" * 64)
    monkeypatch.setattr(layer2_run, "live_short_modes", lambda: frozenset({"broad"}))
    monkeypatch.setattr(layer2_run, "reference_symbols", lambda modes: ("SPY",))
    monkeypatch.setattr(layer2_run, "load_frames", lambda symbols: ({}, ["SPY"]))
    monkeypatch.setattr(layer2_run, "coverage", lambda frames, window, **kw: dict(COVERAGE))
    monkeypatch.setattr(layer2_run, "run_layer2", run_layer2)
    recs = [_rec("P1", "AAA"), _rec("P2", "BBB", "bearish"), _rec("P3", "AAA", klass="unfilled"),
            _rec("P4", "CCC"), _rec("P5", "AAA", klass="manual")]
    lines = [{"kind": "plan", "plan": r.plan, "trade": r.trade, "journal": r.journal} for r in recs]
    lines += [{"kind": "watchlist", "ticker": "AAA", "added_at": "2026-01-02T00:00:00+00:00"},
              {"kind": "deploy", "entry": {"ts": "2026-10-07T12:00:00+00:00", "git_sha": "abc1"}}]
    export = tmp_path / "reconcile.jsonl"
    export.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return {"tmp": tmp_path, "export": export, "provider": provider, "lanes": lanes}


def _argv(env, *extra, since="2026-10-05"):
    t = env["tmp"]
    return ["--export", str(env["export"]), "--since", since, "--until", "2026-10-20",
            "--bars-root", str(t / "bars"), "--work-dir", str(t / "work"),
            "--results-dir", str(t / "results"), "--date", "2026-11-17", "--fetch-bars",
            "--resamples", "200", "--seed", "42", *extra]


def _out(env):
    stem = env["tmp"] / "results" / "2026-11-17-v232-live-replay-reconciliation"
    return Path(f"{stem}.json"), Path(f"{stem}.md")


def _json(env):
    return json.loads(_out(env)[0].read_text(encoding="utf-8"))


def test_trade_rows_are_checkpointed_and_hashed(env):
    assert cli.main(_argv(env)) == 0
    report, markdown = _json(env), _out(env)[1].read_text(encoding="utf-8")
    assert markdown.splitlines()[2] == f"> {render.CAVEAT}"
    assert render.leaks(report, markdown) == []
    assert report["meta"]["window"] == ["2026-10-05", "2026-10-20"]
    assert report["meta"]["inputs"] == {
        "reconcile.jsonl": hashlib.sha256(env["export"].read_bytes()).hexdigest()}
    assert report["populations"]["long"]["headline"]["refused_tickers"]["split_in_window"] == ["CCC"]
    assert '"r_as_backtest"' not in _out(env)[0].read_text(encoding="utf-8")
    rows = env["tmp"] / "work" / "trade-rows.jsonl"
    assert len(rows.read_text(encoding="utf-8").splitlines()) == 5
    assert report["meta"]["rows_sha256"] == hashlib.sha256(rows.read_bytes()).hexdigest()
    assert report["layer1"]["long"]["headline"]["v1"]["table"][-1]["n"] == 3


def test_a_rerun_resumes_and_writes_the_same_report(env):
    assert cli.main(_argv(env)) == 0
    first, calls = _json(env), env["provider"].calls
    assert cli.main(_argv(env)) == 0
    assert env["provider"].calls == calls
    second = _json(env)
    first.pop("meta"), second.pop("meta")
    assert first == second


def test_layer2_gets_the_window_tickers_and_live_modes(env):
    assert cli.main(_argv(env)) == 0
    assert env["lanes"] == [(("2026-10-05", "2026-10-20"), ("AAA", "BBB", "CCC"), ("broad",))]
    assert cli.main(_argv(env, "--short-modes", "none")) == 0
    assert env["lanes"][-1][2] == ()


@pytest.mark.parametrize("guard", ["self_check", "leaks"])
def test_a_failed_guard_writes_nothing(env, monkeypatch, guard):
    def tampered(*args, **kwargs):
        raise table.ReconcileError("tampered")

    if guard == "self_check":
        monkeypatch.setattr(table, "self_check", tampered)
    else:
        monkeypatch.setattr(render, "leaks", lambda report, markdown: ["json x: forbidden key"])
    assert cli.main(_argv(env)) == 2
    assert not _out(env)[0].exists() and not _out(env)[1].exists()


```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_render.py`
Expected: the three new tests FAIL — `AttributeError: module 'reconcile.render' has no attribute 'leaks'`.
Run: `python scripts/dev/testrun.py file tests/scout/test_live_replay_reconcile.py`
Expected: FAIL — `FileNotFoundError` for `scripts/reports/live_replay_reconcile.py`.

- [ ] **Step 3a: Add the leak guard to `scripts/reports/reconcile/render.py`** — add `import re` after `import datetime as dt`, add `tags` to the `from . import ...` line, then append:

```python
FORBIDDEN_KEYS = ("strategy", "horizon", "horizon_key", "ticker", "ledger", "parameter", "params")
BACKTEST_R_KEYS = ("backtest", "r_as_backtest", "r_exit_only", "r_rebased", "r_rebased_total",
                   "effects", "entry", "exit", "gap_net", "table", "confusion", "rebase",
                   "cost_check")
_LAYER1_VOCAB = frozenset({
    *layer2.SIDES, *layer2.ERAS, *layer1.FILL_MODELS, *tags.TAGS, *layer1.OUTCOME_CLASSES,
    *EFFECT_LABELS, *(f.name for f in dataclasses.fields(intervals.CellStats)),
    *(f.name for f in dataclasses.fields(table.Line)),
    "table", "selection", "effects", "cost_check", "confusion", "tags", "rebase",
    "mean_exit_effect", "zero_cost_backtest", "equally_costed", "n_filled", "n_no_fill",
    "n_rebased", "r_rebased_total", "stop_shift_pct", "median", "p90"})
_COMPONENT = re.compile(r"\b(strateg\w*|horizons?|tickers?|ledgers?|parameters?|params)\b", re.I)
_BACKTEST = re.compile(r"backtest|exit[ _-]only|entry effect|exit effect|re-?based", re.I)


def _walk(node, path=()):
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key
            yield from _walk(value, path + (str(key),))
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value, path)


def _key_leaks(path: tuple, key) -> list[str]:
    in_layer1 = path[:1] == ("layer1",)
    checks = ((key in FORBIDDEN_KEYS, "forbidden key"),
              (in_layer1 and key not in _LAYER1_VOCAB, "key outside the per-direction vocabulary"),
              (not in_layer1 and key in BACKTEST_R_KEYS, "backtest R outside layer1"))
    return [f"json {'.'.join(path + (str(key),))}: {why}" for hit, why in checks if hit]


def _is_header(lines: list, i: int) -> bool:
    nxt = lines[i + 1] if i + 1 < len(lines) else ""
    return lines[i].startswith("#") or (lines[i].startswith("|") and nxt.startswith("|-"))


def leaks(report: dict, markdown: str) -> list[str]:
    """Every place backtest R could be keyed by a component; [] when the report is clean."""
    out = [p for path, key in _walk(report) for p in _key_leaks(path, key)]
    lines = markdown.splitlines()
    out += [f"markdown line {i + 1}: {line.strip()}" for i, line in enumerate(lines)
            if _is_header(lines, i) and _COMPONENT.search(line) and _BACKTEST.search(line)]
    return out
```

- [ ] **Step 3b: Implement `scripts/reports/live_replay_reconcile.py`**

```python
#!/usr/bin/env python3
"""v232: live versus replay reconciliation, per direction.

    python scripts/reports/live_replay_reconcile.py --export data/v232/reconcile.jsonl \
        --since 2026-07-01 [--until D] [--fetch-bars] [--short-modes broad,isolated|none]

Checkpoints under --work-dir; the same command resumes. Exit 2: self-check or leak guard.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "reports")]

from autopsy.rows import friction_settings  # noqa: E402
from reconcile import (WORK_DIR, layer1_run, layer2, layer2_run, raw_bars,  # noqa: E402
                       records, render, table)
from reconcile.checkpoint import JsonlCheckpoint  # noqa: E402
from swingbot.core.backtesting.instrument.stats import (  # noqa: E402
    WEEK_BOOTSTRAP_RESAMPLES, WEEK_BOOTSTRAP_SEED)
from swingbot.scan_params import ScanParams  # noqa: E402

STEM = "v232-live-replay-reconciliation"
SHORT_MODES = ("broad", "isolated")


class RunRefused(RuntimeError):
    """The run would not be reproducible or would leak; nothing is written."""


def _modes(text: str) -> frozenset:
    if text == "none":
        return frozenset()
    modes = frozenset(m.strip() for m in text.split(",") if m.strip())
    if not modes or not modes <= set(SHORT_MODES):
        raise argparse.ArgumentTypeError(f"--short-modes {text!r}: use broad, isolated or none")
    return modes


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="v232 live versus replay reconciliation")
    p.add_argument("--export", type=Path, required=True, help="reconcile-mode JSONL (scratch)")
    p.add_argument("--since", type=dt.date.fromisoformat, required=True)
    p.add_argument("--until", type=dt.date.fromisoformat, default=None)
    p.add_argument("--bars-root", type=Path, default=ROOT / WORK_DIR / "bars")
    p.add_argument("--work-dir", type=Path, default=ROOT / WORK_DIR)
    p.add_argument("--fetch-bars", action="store_true", help="fetch raw bars first (resumes)")
    p.add_argument("--date", default=dt.date.today().isoformat())
    p.add_argument("--results-dir", type=Path, default=ROOT / "docs" / "superpowers" / "results")
    p.add_argument("--resamples", type=int, default=WEEK_BOOTSTRAP_RESAMPLES)
    p.add_argument("--seed", type=int, default=WEEK_BOOTSTRAP_SEED)
    p.add_argument("--short-modes", type=_modes, default=None, help="default: live configuration")
    return p


def make_provider():
    """Alpaca from .env through swingbot.config; the keys are never printed."""
    from swingbot import config
    from swingbot.core.marketdata.providers.alpaca_provider import AlpacaProvider
    return AlpacaProvider(config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY,
                          config.ALPACA_DATA_FEED_LIVE)


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _commit() -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip()


def _layer1(export, args) -> list:
    checkpoint = JsonlCheckpoint(args.work_dir / "trade-rows.jsonl")

    def bars(ticker: str):
        return (raw_bars.load_bars(ticker, args.bars_root, "raw"),
                raw_bars.load_bars(ticker, args.bars_root, "split"))

    layer1_run.run_layer1(export, bars, checkpoint, frictions=friction_settings(),
                          start=args.since)
    by_plan = {d["plan_id"]: layer1_run.TradeRow.from_dict(d) for d in checkpoint.rows()}
    return [by_plan[rec.plan_id] for rec in export.records if rec.plan_id in by_plan]


def _layer2(export, rows, window, params, modes, lane_dir: Path) -> tuple[dict, dict]:
    base = layer2_run.replay_tickers(export)
    frames, missing = layer2_run.load_frames(
        tuple(dict.fromkeys(base + layer2_run.reference_symbols(modes))))
    signals = layer2_run.run_layer2(frames, window, params, base_tickers=base, modes=modes,
                                    checkpoint_dir=lane_dir)
    cov = layer2_run.coverage(frames, window, base_tickers=base, modes=modes,
                              snapshot_fn=layer2_run.SNAPSHOT_FN)
    cov["store_missing"] = sorted(missing)
    plans = layer2.live_plans(export, {r.plan_id: r for r in rows})
    return layer2.selection_counts(layer2.match(signals, plans), export), cov


def _meta(args, argv, window, digest, modes, inputs, cov) -> dict:
    lanes = sorted((args.work_dir / "layer2").glob("lane-*.jsonl"))
    return {"commit": _commit(), "window": list(window), "params_digest": digest,
            "short_modes": sorted(modes),
            "inputs": {Path(k).name: v for k, v in inputs.items()},
            "rows_sha256": _sha256(args.work_dir / "trade-rows.jsonl"),
            "lanes_sha256": {p.name: _sha256(p) for p in lanes},
            "bars": raw_bars.bars_manifest(args.bars_root), "coverage": cov,
            "n_resamples": args.resamples, "seed": args.seed,
            "invocation": {"argv": list(argv),
                           "options": {k: str(v) for k, v in vars(args).items()}}}


def _write(args, report: dict, markdown: str) -> None:
    args.results_dir.mkdir(parents=True, exist_ok=True)
    stem = args.results_dir / f"{args.date}-{STEM}"
    outputs = ((Path(f"{stem}.json"), json.dumps(report, indent=2, allow_nan=False) + "\n"),
               (Path(f"{stem}.md"), markdown))
    for path, text in outputs:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {path}")


def _run(args, argv) -> int:
    params = ScanParams.from_config()
    digest = layer2_run.params_digest(params)
    end = args.until or dt.date.today()
    window = (args.since.isoformat(), end.isoformat())
    inputs: dict = {}
    export = records.load_export(args.export, input_fingerprints=inputs, until=args.until)
    if args.fetch_bars:
        raw_bars.fetch_bars(sorted({r.ticker for r in export.records}), args.since, end,
                            args.bars_root, provider=make_provider())
    rows = _layer1(export, args)
    modes = layer2_run.live_short_modes() if args.short_modes is None else args.short_modes
    selection, cov = _layer2(export, rows, window, params, modes, args.work_dir / "layer2")
    report = render.build_report(rows, selection, export,
                                 meta=_meta(args, argv, window, digest, modes, inputs, cov),
                                 n_resamples=args.resamples, seed=args.seed)
    markdown = render.render_markdown(report)
    problems = render.leaks(report, markdown)
    if problems:
        raise RunRefused("leak guard: " + "; ".join(problems))
    _write(args, report, markdown)
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(argv)
    try:
        return _run(args, argv)
    except (RunRefused, table.ReconcileError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_render.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/testrun.py file tests/scout/test_live_replay_reconcile.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/render.py tests/scout/test_reconcile_render.py
git commit -m "feat(v232): the component-R leak guard over the report and its Markdown"
git add scripts/reports/live_replay_reconcile.py tests/scout/test_live_replay_reconcile.py
git commit -m "feat(v232): live_replay_reconcile CLI, manifest and guards"
```

### Task V232-16: Run: export, raw bars, reconciliation and the ledger row

**Model:** sonnet — two small CLI guards, then an operational run whose every command is given; anything unexpected is a stop, not a judgement call.

**Files:**
- Modify: `scripts/reports/live_replay_reconcile.py` (the two run guards, moved here from V232-15 for the 20 KB task cap)
- Modify: `tests/scout/test_live_replay_reconcile.py`
- Create: `docs/superpowers/results/<date>-v232-live-replay-reconciliation.md`, `docs/superpowers/results/<date>-v232-live-replay-reconciliation.json` (written by the CLI, never by hand)
- Modify: `docs/superpowers/results/preregistration-ledger.jsonl` (through `scripts/reports/preregistration_ledger.py`)
- Scratch, git-ignored (`data/v232/`, V232-5): `reconcile.jsonl`, `prod_params.py`, `param_fields.py`, `layer2_symbols.py`, the bar stores, `trade-rows.jsonl`, `layer2/`

**Interfaces:**
- Consumes: V232-15's CLI (`_parser`, `_run`, `_sha256`, `RunRefused`, the test file's `env`, `_argv`, `_out`); `layer2_run.params_digest`, `replay_tickers`, `reference_symbols` (V232-11); the `reconcile` export mode (V232-1); existing `scripts/data/fetch_alpaca_history.py` (`--root`, `--tickers`, `--timeframes daily`, `--start`; refuses during the US regular session, resumes per ticker) and `scripts/reports/preregistration_ledger.py` (`--id --hypothesis --instrument --n --verdict --record --data-source --date`; `exp_r` and `p` default to null; a `DESCRIPTION` row with a p is refused).
- Produces: the ledger's `--expect-params-digest` flag and `<work-dir>/run.json`; the committed results doc and JSON; ledger row `v232-reconciliation` (`instrument` `v1`, verdict `DESCRIPTION`, `p` null, `exp_r` null, `n` = headline scored trades over both sides; Handoff).

**Rules for the run (Global Constraints "Production", "Long run"; CLAUDE.md):**
- Production is touched **read-only** and **only** through `bash scripts/ops/ssh-hetzner.sh`. Nothing on the VM is written, restarted or edited (so `mirror-prod` does not apply).
- **No `.env` value is ever printed.** The parameter check prints a SHA-256 and the live SHORT lane names (Handoff); a mismatch is narrowed to field **names**, hashes stay in files.
- Steps 6 and 7 are long: dispatch each to `backtest-runner` with the exact command. Every unit checkpoints (bar manifests per ticker, `trade-rows.jsonl` per plan, lane files per lane); a killed run is restarted with the **same** command and skips finished units.
- **Stop and report to the controller** (never work around): a parameter digest mismatch, `refused:` from the CLI (a self-check failure is a bug, never a row edit), `spy_missing: True`, or `snapshot missing` on every session while a SHORT lane is on.
- Run from the plan's worktree root. Shell variables do not survive between steps, so each block re-reads what it needs from `data/v232/*.txt`. Git Bash has no zone data: every date is UTC (`date -u +%F`).

- [ ] **Step 1: Write the failing guard tests** — append to `tests/scout/test_live_replay_reconcile.py`:

```python
def test_a_params_digest_mismatch_refuses_before_any_work(env):
    assert cli.main(_argv(env, "--expect-params-digest", "e" * 64)) == 2
    assert env["provider"].calls == 0 and not _out(env)[1].exists()
    assert cli.main(_argv(env, "--expect-params-digest", "d" * 64)) == 0


def test_a_stale_work_dir_refuses(env):
    assert cli.main(_argv(env)) == 0
    held = json.loads((env["tmp"] / "work" / "run.json").read_text(encoding="utf-8"))
    assert (held["since"], held["until"]) == ("2026-10-05", "2026-10-20")
    assert held["export_sha256"] == hashlib.sha256(env["export"].read_bytes()).hexdigest()
    assert cli.main(_argv(env, since="2026-10-01")) == 2
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_live_replay_reconcile.py`
Expected: the two new tests FAIL (`unrecognized arguments: --expect-params-digest`; the stale run returns 0).

- [ ] **Step 3: Add the guards to `scripts/reports/live_replay_reconcile.py`**

In `_parser()`, after the `--seed` argument:

```python
    p.add_argument("--expect-params-digest", default=None, help="production's ScanParams SHA-256")
```

Add above `_layer1`:

```python
def _claim_work_dir(work: Path, key: dict) -> None:
    """A work dir serves one export, window and bars root; another run refuses."""
    path = work / "run.json"
    if path.is_file():
        held = json.loads(path.read_text(encoding="utf-8"))
        if held != key:
            raise RunRefused(f"{work} holds checkpoints for {held}; use a new --work-dir")
        return
    work.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(key, sort_keys=True) + "\n")
```

In `_run`, replace the first four lines with:

```python
    params = ScanParams.from_config()
    digest = layer2_run.params_digest(params)
    if args.expect_params_digest and args.expect_params_digest != digest:
        raise RunRefused("the local ScanParams digest differs from production's; nothing ran")
    end = args.until or dt.date.today()
    window = (args.since.isoformat(), end.isoformat())
    _claim_work_dir(args.work_dir, {"export_sha256": _sha256(args.export), "since": window[0],
                                    "until": args.until and window[1],
                                    "bars_root": str(Path(args.bars_root).resolve())})
```

Both checks run before the export is read or any bar is fetched; the docstring's exit-2 line gains "the parameter digest, another run's work dir".

- [ ] **Step 4: Run the tests to verify they pass, then commit**

Run: `python scripts/dev/testrun.py file tests/scout/test_live_replay_reconcile.py`
Expected: PASS, `0 failed`.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

```bash
git add scripts/reports/live_replay_reconcile.py tests/scout/test_live_replay_reconcile.py
git commit -m "feat(v232): refuse a production parameter mismatch and another run's work dir"
```

- [ ] **Step 5: Export the live book from production (read-only)**

```bash
mkdir -p data/v232
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- reconcile 2026-07-01" \
    < scripts/ops/export_book_rows.sh > data/v232/reconcile.jsonl
date -u +%F > data/v232/export-date.txt
python -c "import collections, json; print(dict(collections.Counter(json.loads(l)['kind'] for l in open('data/v232/reconcile.jsonl', encoding='utf-8') if l.strip())))"
```

Expected: one dict of counts, e.g. `{'plan': <hundreds>, 'rejection': <n>, 'watchlist': <n>, 'deploy': <n>}`; zero rejections or deploys are measured zeros (known-traps T2). The window opens 2026-07-01, before the book's first exit (2026-07-20), so every plan the book closed is in it. Nothing else of the file is printed.

- [ ] **Step 6: Compare production's scan parameters with the local ones (read-only)**

Create `data/v232/prod_params.py`:

```python
"""v232: print the ScanParams digest and the live SHORT lanes -- never a value."""
import dataclasses
import hashlib
import json

from swingbot import config
from swingbot.core.scanning.short_candidates import admitted_short_modes
from swingbot.scan_params import ScanParams

blob = json.dumps(dataclasses.asdict(ScanParams.from_config()), sort_keys=True, default=str)
print("params_digest", hashlib.sha256(blob.encode("utf-8")).hexdigest())
print("short_modes", ",".join(sorted(admitted_short_modes(config))) or "none")
```

The digest is `layer2_run.params_digest`'s formula (V232-11). Run it on production and locally:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
    < data/v232/prod_params.py > data/v232/prod-params.txt
python data/v232/prod_params.py > data/v232/local-params.txt
cat data/v232/prod-params.txt data/v232/local-params.txt
```

Expected: four lines, two digests and two lane lists. **Equal digests:** carry on with `DIGEST` and `MODES` from `prod-params.txt`. **Different digests:** narrow to field names with `data/v232/param_fields.py`:

```python
"""v232: one line per ScanParams field, name and value hash, for a names-only comparison."""
import dataclasses
import hashlib
import json

from swingbot.scan_params import ScanParams

for name, value in sorted(dataclasses.asdict(ScanParams.from_config()).items()):
    print(name, hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest())
```

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
    < data/v232/param_fields.py > data/v232/prod-fields.txt
python data/v232/param_fields.py > data/v232/local-fields.txt
python -c "a = dict(l.split() for l in open('data/v232/prod-fields.txt')); b = dict(l.split() for l in open('data/v232/local-fields.txt')); print(sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k)))"
```

Then **stop** and report the differing field names to the controller: aligning local configuration is the partner's call, and no production value is copied into a printed place.

- [ ] **Step 7: Fetch the adjusted bars layer 2 reads (long: `backtest-runner`)**

Layer 2 reads the adjusted store the live scan reads (index Handoff). A worktree's `data/market_data/` is not the live watchlist store, so the run uses its own adjusted store under `data/v232/adjusted`, selected with `HISTORY_STORE_DIR` (layer 1's `raw_bars.use_store` restores it after each raw read). Create `data/v232/layer2_symbols.py`:

```python
"""v232: the symbols layer 2 needs: replay tickers, then the reference panel."""
import sys

sys.path[:0] = [".", "scripts/reports"]
from reconcile import layer2_run, records  # noqa: E402

modes = frozenset(m for m in sys.argv[1].split(",") if m and m != "none")
export = records.load_export("data/v232/reconcile.jsonl")
symbols = dict.fromkeys(layer2_run.replay_tickers(export) + layer2_run.reference_symbols(modes))
print(",".join(symbols))
```

```bash
MODES=$(awk '/^short_modes/ {print $2}' data/v232/prod-params.txt)
python data/v232/layer2_symbols.py "$MODES" > data/v232/layer2-symbols.txt
python -c "print(len(open('data/v232/layer2-symbols.txt').read().strip().split(',')))"
python scripts/data/fetch_alpaca_history.py --root data/v232/adjusted --timeframes daily \
    --start 2024-01-01 --tickers "$(cat data/v232/layer2-symbols.txt)"
```

Expected: a symbol count, then per-ticker progress and exit 0. The fetch refuses during the US regular session (run it outside 09:30-16:00 New York time) and resumes per ticker. `--start 2024-01-01` leaves two years of history before the window for the scan's lookbacks. Exit 1 or 2 (a guard or the key): stop and report its message.

- [ ] **Step 8: Run the reconciliation (long: `backtest-runner`)**

```bash
DIGEST=$(awk '/^params_digest/ {print $2}' data/v232/prod-params.txt)
MODES=$(awk '/^short_modes/ {print $2}' data/v232/prod-params.txt)
UNTIL=$(cat data/v232/export-date.txt)
[ -f data/v232/run-date.txt ] || date -u +%F > data/v232/run-date.txt
RUN_DATE=$(cat data/v232/run-date.txt)
HISTORY_STORE_DIR=data/v232/adjusted python scripts/reports/live_replay_reconcile.py \
    --export data/v232/reconcile.jsonl --since 2026-07-01 --until "$UNTIL" --fetch-bars \
    --expect-params-digest "$DIGEST" --short-modes "$MODES" --date "$RUN_DATE"
```

Expected: raw-bar progress per kind and ticker, `layer 1: <k>/<N> trades (<p>%)` lines, two `layer 2 lane` lines per lane, then `wrote docs/superpowers/results/<RUN_DATE>-v232-live-replay-reconciliation.json` and `.md`, exit 0. A restart repeats the same block: `run-date.txt` keeps the first attempt's `--date`. Exit 2: report the `refused:` line and stop.

- [ ] **Step 9: Check the outputs**

```bash
F=docs/superpowers/results/$(cat data/v232/run-date.txt)-v232-live-replay-reconciliation
sed -n '1,3p' "$F.md"
grep -n "^- Coverage:" "$F.md"
python -c "import json, sys; sys.path[:0] = ['.', 'scripts/reports']; from reconcile import render; r = json.load(open('$F.json', encoding='utf-8')); print(render.leaks(r, open('$F.md', encoding='utf-8').read())); print({s: r['populations'][s]['headline']['scored'] for s in ('long', 'short')})"
git status --short data/
```

Expected: line 1 the title, line 3 the caveat quote; the coverage line (stop on `SPY missing True`, or snapshot missing on every session with SHORT lanes on); `[]` then the headline scored count per side; `git status` prints nothing for `data/` (per-trade rows stay ignored; the doc records their SHA-256).

- [ ] **Step 10: Append the ledger row**

```bash
RUN_DATE=$(cat data/v232/run-date.txt)
F=docs/superpowers/results/$RUN_DATE-v232-live-replay-reconciliation
N=$(python -c "import json; r = json.load(open('$F.json', encoding='utf-8')); print(sum(r['populations'][s]['headline']['scored'] for s in ('long', 'short')))")
python scripts/reports/preregistration_ledger.py --id v232-reconciliation --date "$RUN_DATE" \
    --instrument v1 --verdict DESCRIPTION --n "$N" --data-source alpaca --record "$F.md" \
    --hypothesis "v232 live versus replay reconciliation, per direction and fill model, headline window (trades opened from 2026-09-15T08:54:50Z), descriptive (no p, outside the BH family). What the run reads: for plans live traded, the daily-bar outcome of the same plan, per direction; live already traded these and the autopsy already read their R. What it does not read: any outcome of a signal live did not trade. n = headline scored trades over both directions; per-direction counts are in the record."
python scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
python scripts/dev/testrun.py file tests/scripts/test_preregistration_ledger_cli.py
```

Expected: `v232-reconciliation: verdict DESCRIPTION, p=null, BH q=n/a (no p-value) across ...`; both test files PASS, `0 failed`.

- [ ] **Step 11: Commit**

```bash
F=docs/superpowers/results/$(cat data/v232/run-date.txt)-v232-live-replay-reconciliation
git add "$F.md" "$F.json"
git commit -m "docs(v232): live versus replay reconciliation results, per direction"
git add docs/superpowers/results/preregistration-ledger.jsonl
git commit -m "docs(v232): ledger row v232-reconciliation (DESCRIPTION)"
```

