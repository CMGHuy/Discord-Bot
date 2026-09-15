# v86 — Part 2: features, surfaces, verification (C4–C9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-14-v86-cohort-risk-label-design.md` (§4, §5, §8)
**Index (read its Global Constraints first):** `2026-09-14-v86-cohort-risk-label_0-index.md`
**Depends on:** Part 1 (C1–C3) merged. C4 threads the same `regime2_state` that C3's `stamp_cohort` consumes.

---

### Task C4: Stamp the risk features at issuance

The C half of the design: capture, on every plan, the candidate discriminators
that the label is NOT currently keyed on — so the later analysis can answer
"what should it have been keyed on?" from data.

**Files:**
- Create: `swingbot/core/scanning/risk_features.py`
- Create: `tests/test_risk_features.py`
- Modify: `swingbot/core/planning/plan_types.py` (one field)
- Modify: `swingbot/core/scanning/analyze.py:268-297` (`attach_plan_v2`) and its caller

**Interfaces:**
- Consumes: `regime2_state` (already in `ctx["regimes"]` at `analyze.py:146`);
  `item.conf.level`; `htf_result["bias"]`; `rs_percentile`; the plan's own
  `stop_loss`/`trigger_price`.
- Produces:
  - `TradePlanV2.risk_features: dict = field(default_factory=dict)`.
  - `risk_features.build(*, regime2_state, confidence_level, htf_bias, direction,
    confluence_count, entry, level_price, stop_loss, atr_val, close,
    rs_percentile, now, days_to_earnings=None) -> dict`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_risk_features.py`:

```python
import datetime as dt

import pytest

from swingbot.core.scanning.risk_features import build


def _kwargs(**over):
    base = dict(
        regime2_state="bear_volatile", confidence_level=2, htf_bias="bullish",
        direction="bullish", confluence_count=3, entry=100.0, level_price=98.0,
        stop_loss=96.0, atr_val=2.0, close=100.0, rs_percentile=45.0,
        now=dt.datetime(2026, 9, 14, 15, 45),
    )
    base.update(over)
    return base


def test_builds_every_documented_feature():
    f = build(**_kwargs())
    assert set(f) == {
        "regime2_state", "confidence_level", "htf_agree", "confluence_count",
        "dist_to_level_atr", "stop_width_atr", "atr_pct", "rs_percentile",
        "session_bucket", "days_to_earnings",
    }


def test_htf_agree_is_true_only_when_bias_matches_direction():
    assert build(**_kwargs(htf_bias="bullish", direction="bullish"))["htf_agree"] is True
    assert build(**_kwargs(htf_bias="bearish", direction="bullish"))["htf_agree"] is False
    assert build(**_kwargs(htf_bias=None))["htf_agree"] is None


def test_distances_are_expressed_in_atr():
    f = build(**_kwargs(entry=100.0, level_price=98.0, stop_loss=96.0, atr_val=2.0))
    assert f["dist_to_level_atr"] == pytest.approx(1.0)
    assert f["stop_width_atr"] == pytest.approx(2.0)


def test_atr_pct_is_atr_over_close():
    assert build(**_kwargs(atr_val=2.0, close=100.0))["atr_pct"] == pytest.approx(2.0)


def test_zero_atr_yields_none_rather_than_a_divide_by_zero():
    f = build(**_kwargs(atr_val=0.0))
    assert f["dist_to_level_atr"] is None
    assert f["stop_width_atr"] is None
    assert f["atr_pct"] is None


def test_session_buckets_split_open_midday_close():
    assert build(**_kwargs(now=dt.datetime(2026, 9, 14, 9, 45)))["session_bucket"] == "open"
    assert build(**_kwargs(now=dt.datetime(2026, 9, 14, 12, 30)))["session_bucket"] == "midday"
    assert build(**_kwargs(now=dt.datetime(2026, 9, 14, 15, 50)))["session_bucket"] == "close"


def test_days_to_earnings_is_null_when_no_calendar_is_available():
    assert build(**_kwargs())["days_to_earnings"] is None
    assert build(**_kwargs(days_to_earnings=3))["days_to_earnings"] == 3


def test_every_feature_is_json_serialisable():
    import json
    json.dumps(build(**_kwargs()))   # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_risk_features.py`
Expected: FAIL — `ModuleNotFoundError: swingbot.core.scanning.risk_features`

- [ ] **Step 3a: Write the module**

Create `swingbot/core/scanning/risk_features.py`:

```python
"""Candidate discriminators stamped on every plan at issuance (v86 spec §4).

These are NOT scored, weighted or combined -- deliberately. v32 and v33 both
regressed folding signals into one number. This module only RECORDS what was
knowable at the creating bar, so scripts/reports/cohort_separation_report.py
can later measure which of these actually separates winners from losers,
before anyone spends a pre-registration on a richer key.

NO-LOOKAHEAD: every argument is a reading from the creating bar or earlier.
Nothing in here reads a dataframe, so there is no bar index to get wrong --
the caller passes scalars it already holds in scope.
"""
from __future__ import annotations

import datetime as dt

# Berlin-local RTH buckets. Boundaries are deliberately coarse: the point is
# to find out whether time-of-day matters at all (median live hold is ~2h
# against horizons labelled 2w-9m), not to slice it finely on 782 trades.
_OPEN_UNTIL = dt.time(11, 0)
_CLOSE_FROM = dt.time(15, 30)


def _ratio(numerator: float, atr_val: float) -> float | None:
    if not atr_val:
        return None
    return round(abs(float(numerator)) / float(atr_val), 4)


def session_bucket(now: dt.datetime) -> str:
    t = now.time()
    if t < _OPEN_UNTIL:
        return "open"
    if t >= _CLOSE_FROM:
        return "close"
    return "midday"


def build(*, regime2_state, confidence_level, htf_bias, direction,
          confluence_count, entry, level_price, stop_loss, atr_val, close,
          rs_percentile, now, days_to_earnings=None) -> dict:
    return {
        "regime2_state": regime2_state,
        "confidence_level": confidence_level,
        # None, not False, when there is no bias reading -- "we did not know"
        # and "it disagreed" are different facts and must not pool.
        "htf_agree": None if htf_bias is None else bool(htf_bias == direction),
        "confluence_count": confluence_count,
        "dist_to_level_atr": _ratio(entry - level_price, atr_val) if level_price is not None else None,
        "stop_width_atr": _ratio(entry - stop_loss, atr_val),
        "atr_pct": round(100.0 * float(atr_val) / float(close), 4) if atr_val and close else None,
        "rs_percentile": rs_percentile,
        "session_bucket": session_bucket(now),
        # Opportunistic: null unless v82's calendar is merged and wired. This
        # plan does not depend on v82 and must never block on it.
        "days_to_earnings": days_to_earnings,
    }
```

- [ ] **Step 3b: Add the plan field**

In `swingbot/core/planning/plan_types.py`, beside C3's `cohort_label` /
`cohort_stats`:

```python
    # v86 §4: what was knowable about this plan at its creating bar. Recorded,
    # never scored -- see scanning/risk_features.py.
    risk_features: dict = field(default_factory=dict)
```

- [ ] **Step 3c: Thread it through `attach_plan_v2`**

In `swingbot/core/scanning/analyze.py`, add `regime2_state=None` to
`attach_plan_v2`'s signature (after `breadth=None`), pass it to
`build_confluence_plan` as `regime2_state=regime2_state` (the argument C3
added), and stamp the features after the plan is built, immediately before
`item.plan_v2 = plan`:

```python
        plan.risk_features = risk_features.build(
            regime2_state=regime2_state,
            confidence_level=getattr(getattr(item, "conf", None), "level", None),
            htf_bias=getattr(item, "htf_bias", None),
            direction=scenario.direction,
            confluence_count=getattr(item, "target_confluence_count", None),
            entry=scenario.entry, level_price=getattr(scenario, "level_price", None),
            stop_loss=plan.stop_loss,
            atr_val=_safe_atr_value(scenario.entry, _atr_for(df)),
            close=float(df["Close"].iloc[-1]),
            rs_percentile=rs_percentile,
            now=dt.datetime.now(),
        )
        item.plan_v2 = plan
```

Add `import datetime as dt` and `from swingbot.core.scanning import risk_features`
at the top of the module if absent. `_atr_for(df)` is whatever ATR helper
`_build_quality_inputs` already uses — reuse it rather than recomputing; grep
`_build_quality_inputs` (around `analyze.py:220`) for the exact call and copy it.
This sits inside `attach_plan_v2`'s existing `try/except`, so a feature-build
failure degrades to a plan with empty `risk_features` and never breaks a scan.

- [ ] **Step 3d: Pass the regime from the caller**

Find the call site of `attach_plan_v2` (grep `attach_plan_v2(` in
`swingbot/core/scanning/`) and pass the creating bar's regime label from the
scan context built at `analyze.py:146`:

```python
            regime2_state=_regime_at(ctx.get("regimes"), df.index[-1]),
```

Add the helper beside `attach_plan_v2`:

```python
def _regime_at(regimes, when) -> str | None:
    """The regime label for THIS bar, never the latest one. regime_series is
    causal at every bar, so indexing it by the creating bar's timestamp is
    lookahead-free; taking .iloc[-1] instead would stamp a replayed 2024 plan
    with 2026 volatility."""
    if regimes is None or when is None:
        return None
    try:
        hit = regimes[regimes.index.normalize() == pd_normalize(when)]
    except Exception:
        return None
    return None if hit.empty else str(hit.iloc[0])


def pd_normalize(when):
    import pandas as pd
    return pd.Timestamp(when).normalize()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_risk_features.py`
Then confirm the scan path still builds plans:
Run: `python scripts/dev/testrun.py file tests/test_scan_engine.py`
Expected: both PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/risk_features.py swingbot/core/scanning/analyze.py \
        swingbot/core/planning/plan_types.py tests/test_risk_features.py
git commit -m "feat(v86): stamp NO-LOOKAHEAD risk features on every plan at issuance"
```

---

### Task C5: Carry the features into the journal at close

Without this the features die with the open plan and the §6 analysis has
nothing to join against.

**Files:**
- Modify: `swingbot/core/analytics/journal.py` (`build_entry`, around line 176-205)
- Create: `tests/test_journal_risk_features.py`

**Interfaces:**
- Consumes: `TradePlanV2.risk_features` (C4), `TradePlanV2.cohort_label` /
  `cohort_stats` (C3), carried on the closed trade dict.
- Produces: journal entries with `risk_features`, `cohort_label`,
  `cohort_run_date` keys.

- [ ] **Step 1: Write the failing test**

Create `tests/test_journal_risk_features.py`:

```python
from swingbot.core.analytics.journal import build_entry


def _trade(**over):
    t = {
        "trade_id": "t1", "ticker": "AAPL", "direction": "bullish",
        "outcome": "loss", "r_realized": -1.0, "strategy": "RSI",
        "source": "confluence", "horizon_key": "2w",
        "risk_features": {"regime2_state": "bear_volatile", "session_bucket": "close"},
        "cohort_label": "COHORT_POOR",
        "cohort_stats": {"run_date": "2026-09-14", "expectancy_r": -0.38},
    }
    t.update(over)
    return t


def test_entry_carries_the_risk_features_verbatim():
    e = build_entry(_trade(), None)
    assert e["risk_features"]["regime2_state"] == "bear_volatile"
    assert e["risk_features"]["session_bucket"] == "close"


def test_entry_carries_the_cohort_label_and_its_freeze_date():
    e = build_entry(_trade(), None)
    assert e["cohort_label"] == "COHORT_POOR"
    assert e["cohort_run_date"] == "2026-09-14"


def test_a_trade_predating_v86_journals_without_raising():
    t = _trade()
    del t["risk_features"], t["cohort_label"], t["cohort_stats"]
    e = build_entry(t, None)
    assert e["risk_features"] == {}
    assert e["cohort_label"] is None
    assert e["cohort_run_date"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_journal_risk_features.py`
Expected: FAIL — `KeyError: 'risk_features'`

- [ ] **Step 3: Write minimal implementation**

In `swingbot/core/analytics/journal.py`, inside `build_entry`'s returned dict,
beside the existing `"mfe_r"` / `"mae_r"` / `"exit_efficiency"` keys:

```python
        # v86: copied, not re-derived. The registry may be regenerated after
        # this trade was stamped; §6's verification must read what the plan
        # was TOLD at issuance, so the journal freezes it alongside the outcome.
        "risk_features": trade.get("risk_features") or {},
        "cohort_label": trade.get("cohort_label"),
        "cohort_run_date": (trade.get("cohort_stats") or {}).get("run_date"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/test_journal_risk_features.py`
Then: `python scripts/dev/testrun.py file tests/test_journal.py`
Expected: both PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/journal.py tests/test_journal_risk_features.py
git commit -m "feat(v86): journal the risk features and cohort verdict at close"
```

---

### Task C6: The separation report

The instrument that answers both §6's question ("did the label work?") and the
question behind it ("what should it have been keyed on?").

**Files:**
- Create: `scripts/reports/cohort_separation_report.py`
- Create: `tests/test_cohort_separation_report.py`

**Interfaces:**
- Consumes: journal entries with `risk_features` / `cohort_label` /
  `cohort_run_date` (C5).
- Produces:
  - `label_separation(entries: list[dict], run_date: str) -> dict` — the §6
    verdict.
  - `feature_separation(entries: list[dict], feature: str) -> list[dict]` — per
    feature value, `n` / `win_rate` / `expectancy_r`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cohort_separation_report.py`:

```python
import pytest

from scripts.reports.cohort_separation_report import (label_separation,
                                                      feature_separation,
                                                      MIN_N_PER_GROUP,
                                                      PASS_SEPARATION_R)


def _entry(label, r, created_at="2026-10-01", **feats):
    return {"cohort_label": label, "r_realized": r, "created_at": created_at,
            "cohort_run_date": "2026-09-14", "risk_features": feats}


def test_a_plan_created_before_the_freeze_is_excluded():
    entries = [_entry("COHORT_POOR", -1.0, created_at="2026-09-01")]
    assert label_separation(entries, "2026-09-14")["n_poor"] == 0


def test_unknown_plans_are_excluded_from_both_groups():
    entries = [_entry("COHORT_UNKNOWN", -1.0)] * 10
    out = label_separation(entries, "2026-09-14")
    assert out["n_poor"] == 0 and out["n_other"] == 0


def test_verdict_is_withheld_below_the_minimum_n():
    entries = [_entry("COHORT_POOR", -1.0)] * 5 + [_entry("COHORT_TYPICAL", 1.0)] * 5
    out = label_separation(entries, "2026-09-14")
    assert out["verdict"] == "INSUFFICIENT_N"


def test_clear_separation_at_full_n_passes():
    entries = ([_entry("COHORT_POOR", -1.0)] * MIN_N_PER_GROUP
               + [_entry("COHORT_TYPICAL", 1.0)] * MIN_N_PER_GROUP)
    out = label_separation(entries, "2026-09-14")
    assert out["separation_r"] == pytest.approx(-2.0)
    assert out["verdict"] == "PASS"


def test_no_separation_at_full_n_fails():
    entries = ([_entry("COHORT_POOR", 0.0)] * MIN_N_PER_GROUP
               + [_entry("COHORT_TYPICAL", 0.0)] * MIN_N_PER_GROUP)
    out = label_separation(entries, "2026-09-14")
    assert out["separation_r"] == pytest.approx(0.0)
    assert out["verdict"] == "FAIL"
    assert PASS_SEPARATION_R < 0


def test_feature_separation_groups_by_value():
    entries = [_entry("COHORT_POOR", -1.0, session_bucket="close"),
               _entry("COHORT_TYPICAL", 1.0, session_bucket="open"),
               _entry("COHORT_TYPICAL", 1.0, session_bucket="open")]
    rows = {r["value"]: r for r in feature_separation(entries, "session_bucket")}
    assert rows["open"]["n"] == 2 and rows["open"]["expectancy_r"] == pytest.approx(1.0)
    assert rows["close"]["n"] == 1 and rows["close"]["win_rate"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_cohort_separation_report.py`
Expected: FAIL — `ModuleNotFoundError: scripts.reports.cohort_separation_report`

- [ ] **Step 3: Write minimal implementation**

Create `scripts/reports/cohort_separation_report.py`:

```python
#!/usr/bin/env python3
"""v86 §6: did the cohort label separate outcomes, and what should it have
been keyed on instead?

Two questions, deliberately answered by two functions:

  label_separation()    the PRE-REGISTERED verdict. One shot. The thresholds
                        below were committed on 2026-09-14, before any
                        labelled plan had closed. Do not edit them to reach a
                        verdict -- an edited threshold is a new hypothesis and
                        needs its own pre-registration.
  feature_separation()  exploratory. Free to run, free to slice, and its
                        output may NOT be used to revise the verdict above.

Run: python scripts/reports/cohort_separation_report.py --journal data/journal.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MIN_N_PER_GROUP = 150        # frozen 2026-09-14, spec §6
PASS_SEPARATION_R = -0.20    # ExpR(POOR) - ExpR(non-POOR) must be <= this


def _stats(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0, "win_rate": 0.0, "expectancy_r": 0.0}
    return {"n": len(rs),
            "win_rate": round(100.0 * sum(1 for r in rs if r > 0) / len(rs), 2),
            "expectancy_r": round(sum(rs) / len(rs), 4)}


def _eligible(entries: list[dict], run_date: str) -> list[dict]:
    """Forward-only: a plan created on or before the freeze was never
    labelled by this table, and including it would let the table be scored
    against the trades that built it."""
    return [e for e in entries
            if e.get("r_realized") is not None
            and str(e.get("created_at", "")) > run_date]


def label_separation(entries: list[dict], run_date: str) -> dict:
    rows = _eligible(entries, run_date)
    poor = [float(e["r_realized"]) for e in rows if e.get("cohort_label") == "COHORT_POOR"]
    other = [float(e["r_realized"]) for e in rows
             if e.get("cohort_label") in ("COHORT_TYPICAL", "COHORT_STRONG")]

    s_poor, s_other = _stats(poor), _stats(other)
    separation = round(s_poor["expectancy_r"] - s_other["expectancy_r"], 4)

    if s_poor["n"] < MIN_N_PER_GROUP or s_other["n"] < MIN_N_PER_GROUP:
        verdict = "INSUFFICIENT_N"
    elif separation <= PASS_SEPARATION_R:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return {"verdict": verdict, "separation_r": separation,
            "n_poor": s_poor["n"], "n_other": s_other["n"],
            "poor": s_poor, "other": s_other,
            "min_n_per_group": MIN_N_PER_GROUP,
            "pass_separation_r": PASS_SEPARATION_R}


def feature_separation(entries: list[dict], feature: str) -> list[dict]:
    buckets: dict = {}
    for e in entries:
        if e.get("r_realized") is None:
            continue
        value = (e.get("risk_features") or {}).get(feature)
        buckets.setdefault(value, []).append(float(e["r_realized"]))
    return [dict(value=v, **_stats(rs)) for v, rs in
            sorted(buckets.items(), key=lambda kv: str(kv[0]))]


FEATURES = ("regime2_state", "confidence_level", "htf_agree", "confluence_count",
            "dist_to_level_atr", "stop_width_atr", "atr_pct", "rs_percentile",
            "session_bucket", "days_to_earnings")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="data/journal.json")
    ap.add_argument("--run-date", default=None,
                    help="registry freeze date; default: the cohort_run_date on the entries")
    args = ap.parse_args()

    entries = json.loads(Path(args.journal).read_text(encoding="utf-8"))
    run_date = args.run_date or next(
        (e["cohort_run_date"] for e in entries if e.get("cohort_run_date")), "")
    if not run_date:
        print("no cohort_run_date on any entry -- nothing was stamped yet.")
        return 1

    v = label_separation(entries, run_date)
    print(f"\n=== v86 §6 pre-registered verdict (freeze {run_date}) ===")
    print(f"POOR      n={v['poor']['n']:>5}  WR {v['poor']['win_rate']:>6.2f}%  "
          f"ExpR {v['poor']['expectancy_r']:+.4f}")
    print(f"non-POOR  n={v['other']['n']:>5}  WR {v['other']['win_rate']:>6.2f}%  "
          f"ExpR {v['other']['expectancy_r']:+.4f}")
    print(f"separation {v['separation_r']:+.4f}R  (PASS needs <= {PASS_SEPARATION_R:+.2f}R "
          f"with n >= {MIN_N_PER_GROUP} per group)")
    print(f"VERDICT: {v['verdict']}")
    if v["verdict"] == "PASS":
        print("PASS makes a suppression flip a CANDIDATE. It does not authorise one.")

    print("\n=== exploratory: per-feature separation (NOT part of the verdict) ===")
    for feature in FEATURES:
        rows = [r for r in feature_separation(entries, feature) if r["n"] >= 20]
        if not rows:
            continue
        print(f"\n{feature}")
        for r in rows:
            print(f"  {str(r['value']):>16}  n={r['n']:>5}  WR {r['win_rate']:>6.2f}%  "
                  f"ExpR {r['expectancy_r']:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/test_cohort_separation_report.py`
Expected: PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/cohort_separation_report.py tests/test_cohort_separation_report.py
git commit -m "feat(v86): pre-registered separation verdict and exploratory feature report"
```

---

### Task C7: The Discord surfaces

Render only. No gate, exit, fill or sizing rule may move in this task.

**Files:**
- Modify: `swingbot/core/scanning/plan_table.py:30-40`
- Modify: `swingbot/core/scanning/alert_embeds.py:118-125`
- Create: `tests/test_cohort_render.py`

**Interfaces:**
- Consumes: `plan.cohort_label`, `plan.cohort_stats` (C3).
- Produces: `plan_table.cohort_line(plan) -> str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cohort_render.py`:

```python
from swingbot.core.scanning.plan_table import cohort_line


def _plan(label, **stats):
    class P:
        cohort_label = label
        cohort_stats = dict({"regime2_state": "bear_volatile", "win_rate": 41.2,
                             "expectancy_r": -0.38, "n_live": 100,
                             "n_backtest": 500, "run_date": "2026-09-14"}, **stats)
        direction = "bearish"
    return P()


def test_poor_renders_the_caution_with_its_own_numbers():
    line = cohort_line(_plan("COHORT_POOR"))
    assert "⚠️" in line
    assert "bear_volatile" in line
    assert "41.2" in line
    assert "-0.38" in line
    assert "600" in line          # n_live + n_backtest
    assert "2026-09-14" in line


def test_typical_renders_nothing():
    assert cohort_line(_plan("COHORT_TYPICAL")) is None


def test_strong_renders_a_stat_line_without_a_warning():
    line = cohort_line(_plan("COHORT_STRONG", win_rate=61.0, expectancy_r=0.42))
    assert "⚠️" not in line
    assert "61.0" in line


def test_unknown_says_not_enough_data_never_safe():
    line = cohort_line(_plan("COHORT_UNKNOWN"))
    assert "Not enough" in line
    assert "safe" not in line.lower()


def test_a_plan_with_no_cohort_stats_renders_nothing_rather_than_crashing():
    class P:
        cohort_label = "COHORT_POOR"
        cohort_stats = {}
        direction = "bearish"
    assert cohort_line(P()) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_cohort_render.py`
Expected: FAIL — `ImportError: cannot import name 'cohort_line'`

- [ ] **Step 3a: Add the renderer**

In `swingbot/core/scanning/plan_table.py`, beside the existing
`WEAK_CAUTION_TEXT` handling:

```python
# v86: the cohort line names its own cohort and numbers, the way
# badge_stats_line does. A vague "be careful" teaches the reader nothing and
# gets tuned out; "bearish setups in a volatile bear have closed 41.2% /
# -0.38R over 600 trades" is a fact they can act on.
COHORT_POOR_TEXT = (
    "⚠️ **Cohort:** {direction} setups in a {regime} regime have closed "
    "**{win_rate:.1f}% WR / {expectancy_r:+.2f}R** (n={n}, frozen {run_date}). "
    "Reduced size, manual confirmation."
)
COHORT_STRONG_TEXT = (
    "**Cohort:** {direction} setups in a {regime} regime have closed "
    "**{win_rate:.1f}% WR / {expectancy_r:+.2f}R** (n={n}, frozen {run_date})."
)
COHORT_UNKNOWN_TEXT = (
    "**Cohort:** Not enough closed trades under these conditions to say "
    "anything yet (n={n})."
)


def cohort_line(plan) -> str | None:
    """The one line a reader sees about how trades like this one have closed.
    Returns None when there is nothing honest to say -- an unstamped plan
    renders nothing rather than an empty reassurance."""
    stats = getattr(plan, "cohort_stats", None) or {}
    label = getattr(plan, "cohort_label", "COHORT_UNKNOWN")
    if not stats:
        return None
    fields = {
        "direction": plan.direction,
        "regime": (stats.get("regime2_state") or "unknown").replace("_", " "),
        "win_rate": stats.get("win_rate", 0.0),
        "expectancy_r": stats.get("expectancy_r", 0.0),
        "n": stats.get("n_live", 0) + stats.get("n_backtest", 0),
        "run_date": stats.get("run_date", ""),
    }
    if label == "COHORT_POOR":
        return COHORT_POOR_TEXT.format(**fields)
    if label == "COHORT_STRONG":
        return COHORT_STRONG_TEXT.format(**fields)
    if label == "COHORT_UNKNOWN":
        return COHORT_UNKNOWN_TEXT.format(**fields)
    return None
```

- [ ] **Step 3b: Show it on the alert**

In `swingbot/core/scanning/alert_embeds.py`, immediately after the existing
`sections["quality"].append(ui.confidence_field(conf.level, conf.score))`
(around line 121):

```python
    line = cohort_line(plan) if plan is not None else None
    if line:
        sections["quality"].append(line)
```

Import `cohort_line` from `swingbot.core.scanning.plan_table` at the top of the
module. If `plan` is not already in scope at that point, grep the enclosing
function's signature — the v2 plan is carried on the scan item as
`item.plan_v2`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/test_cohort_render.py`
Then, because embeds are touched:
Run: `python scripts/dev/testrun.py fast`
Expected: PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/plan_table.py swingbot/core/scanning/alert_embeds.py \
        tests/test_cohort_render.py
git commit -m "feat(v86): render the cohort line on plan tables and alerts"
```

---

### Task C8: The admin chip

**Files:**
- Modify: `admin/api_v1/` trade serializer (grep `cohort` after C3 to find where
  `badge` is serialised; the chip rides the same payload)
- Modify: the Angular trade-detail header component under `frontend/src/app/`
- Create: `tests/admin/test_cohort_api.py`

**Interfaces:**
- Consumes: `trade["cohort_label"]`, `trade["cohort_stats"]`.
- Produces: `cohort_label` and `cohort_stats` on the trade detail API payload.

- [ ] **Step 1: Write the failing test**

Create `tests/admin/test_cohort_api.py`:

```python
def test_trade_detail_exposes_the_cohort_verdict(client, sample_trade):
    sample_trade["cohort_label"] = "COHORT_POOR"
    sample_trade["cohort_stats"] = {"regime2_state": "bear_volatile",
                                    "win_rate": 41.2, "expectancy_r": -0.38,
                                    "n_live": 100, "n_backtest": 500,
                                    "run_date": "2026-09-14"}
    body = client.get(f"/api/v1/trades/{sample_trade['trade_id']}").get_json()
    assert body["cohort_label"] == "COHORT_POOR"
    assert body["cohort_stats"]["run_date"] == "2026-09-14"


def test_a_trade_predating_v86_reports_unknown_not_null(client, sample_trade):
    sample_trade.pop("cohort_label", None)
    body = client.get(f"/api/v1/trades/{sample_trade['trade_id']}").get_json()
    assert body["cohort_label"] == "COHORT_UNKNOWN"
```

Use whatever `client` / `sample_trade` fixtures the neighbouring
`tests/admin/test_*.py` files already use — grep one before writing.

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/admin/test_cohort_api.py`
Expected: FAIL — `KeyError: 'cohort_label'`

- [ ] **Step 3: Write minimal implementation**

Add both keys to the trade serializer, defaulting an absent label to
`"COHORT_UNKNOWN"` and absent stats to `{}`. Then render the chip in the
Angular trade-detail header beside the existing badge chip, using the
established chip component and the v80 token palette (`docs/claude/` has no
component list — copy the badge chip's markup and swap the label source).
`COHORT_POOR` uses the danger token; `COHORT_STRONG` the positive token;
`COHORT_TYPICAL` renders no chip; `COHORT_UNKNOWN` the muted token.

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/admin/test_cohort_api.py`
Expected: PASS, 0 failed, 0 xfailed.

- [ ] **Step 5: Commit**

```bash
git add admin/ frontend/ tests/admin/test_cohort_api.py
git commit -m "feat(v86): expose the cohort verdict on the admin trade detail"
```

---

### Task C9: Postgres mirror, version bump, full verification

The only task that runs the full suite.

**Files:**
- Modify: the v67 plans-table schema and row mapper (grep
  `badge_stats` under the v67 data-access layer — the three new fields ride the
  same path)
- Modify: `VERSION.json`
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table)

- [ ] **Step 1: Mirror the new plan fields into the v67 schema**

`cohort_label`, `cohort_stats` and `risk_features` are persisted plan fields.
Wherever v67's plans table enumerates columns or maps rows, add all three
alongside `badge`/`badge_stats`. If v67 has not yet landed the plans table,
this step is a no-op — say so explicitly in the commit message rather than
skipping it silently, so the v67 executor knows to pick it up.

- [ ] **Step 2: Record the pre-registration**

Add a row to the closed-pre-registrations table in
`docs/claude/backtest-methodology.md`:

| v86 cohort label | `COHORT_POOR` plans close at `ExpR ≤ non-POOR − 0.20R`, n ≥ 150 per group, plans created after the registry `run_date` | registered 2026-09-14, **open — do not re-run at a different N, window or margin** |

- [ ] **Step 3: Bump `VERSION.json`**

`bot` minor, `ui` patch — two independent lines, resolved from the
then-current `VERSION.json` at close-out, never from a number predicted in this
plan.

- [ ] **Step 4: Run the full suite — once**

Dispatch the `test-runner` subagent so ~1150 progress lines stay out of the
main context:

Run: `python scripts/dev/testrun.py full`
Expected: **0 failed, 0 xfailed.** A changed pass count is not a failure
(`docs/claude/testing-cost.md`); a non-zero failure count is.

- [ ] **Step 5: Verify the Edge claim holds**

The spec claims pooled paper `ExpR` is unchanged **by construction**. Confirm
it by inspection, not by a backtest: `git diff main...HEAD --stat` must show no
change to any gate, exit, fill or sizing path — nothing under
`swingbot/core/planning/exit_sim.py`, `targets.py`, `swingbot/core/scanning/gating.py`
or `swingbot/core/edge/sizing.py`. If any of those files appears in the diff,
the `Edge: none (integrity)` header is wrong and the spec must be corrected
before merge.

- [ ] **Step 6: Commit and close out**

```bash
git add VERSION.json docs/claude/backtest-methodology.md admin/ swingbot/
git commit -m "chore(v86): mirror plan fields to v67 schema, register §6, bump versions"
```

Then move all three plan parts to `docs/superpowers/plans/implemented/` per
`docs/claude/document-lifecycle.md`.
