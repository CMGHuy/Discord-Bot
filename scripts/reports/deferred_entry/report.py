"""v229 results: one Markdown doc and one JSON payload (spec section "Outputs").

Everything is disclosure except the verdict block, which V229-10 fills from
``verdict.study_verdict``. Each output records the archive's last bar, the
script's git SHA and the frozen rule's hash, so a run can be reproduced.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from . import analysis
from .verdict import FROZEN, rule_hash

ARMS = ("C", "A", "B")
DISCLOSURES = (
    "Single leg to TP1: no runner, no TP2; the live scale-out is not reproduced.",
    "The control starts at the first bar at or after opened_at, so a stop-out inside the entry bar is "
    "missed: this flatters the control and biases d_A downward on exactly the noise stops tested.",
    "The live path class comes from the export's last leg only: a TP1 partial whose runner leg is "
    "labelled scratch classes as scratch.",
    "Trades still open at the read date are not in the export and are absent from the population.",
    "All R is net of frictions; arms A and B pay twice the entry slippage (a market order in the last "
    "half hour). Gross R is printed beside and gates nothing.",
    "Arm B's skip is a mechanical wick touch, not a trader's judgement that the level held.",
)
_MEANS = ("fill_vs_entry_r", "day_low_vs_stop_r", "price_1530_vs_entry_r")
_COUNTS = ("shifted_stop_above_day_low", "plan_expired", "entry_bar_stopout",
           "earnings_after_close", "monthly_opex", "fomc", "event_day")
_BAR_KEYS = ("volume", "range_r", "open_vs_last_close_r")


def _present(values) -> list[float]:
    return [float(v) for v in values if v is not None]


def _mean(values) -> float | None:
    vals = _present(values)
    return float(np.mean(vals)) if vals else None


def _median(values) -> float | None:
    vals = _present(values)
    return float(np.median(vals)) if vals else None


def _sub(recs, field, key):
    return [(r.get(field) or {}).get(key) for r in recs]


def _means_and_counts(recs: list[dict]) -> dict:
    out = {f"mean_{key}": _mean(r.get(key) for r in recs) for key in _MEANS}
    out.update({f"count_{key}": sum(1 for r in recs if r.get(key) is True) for key in _COUNTS})
    return out


def tradeability_summary(pairs) -> dict:
    recs = [p["tradeability"] for p in pairs]
    out = _means_and_counts(recs)
    out["first_gap_r"] = {arm: _mean(_sub(recs, "first_gap_r", arm)) for arm in ARMS}
    out["gap_through_stop"] = {arm: sum(1 for p in pairs if p["arms"][arm]["gap_stop"]) for arm in ARMS}
    out["bar_1530_median"] = {key: _median(_sub(recs, "bar_1530", key)) for key in _BAR_KEYS}
    return out


def _bearish_summary(pairs: list[dict]) -> dict:
    def delta(arm):
        return _mean(analysis.arm_r(p, arm) - analysis.arm_r(p, "C") for p in pairs)
    return {"n": len(pairs), "arms": {arm: analysis.arm_summary(pairs, arm) for arm in ARMS},
            "d_a": delta("A"), "d_b": delta("B")}


def build_payload(*, phase, t0, pairs, bearish, funnel, close_bucket, archive_last_bar,
                  git_sha, verdict=None) -> dict:
    pairs, bearish = list(pairs), list(bearish)
    return {"study": "v229-deferred-entry", "phase": phase, "t0": str(t0), "rule_hash": rule_hash(),
            "frozen": dict(FROZEN), "archive_last_bar": archive_last_bar, "git_sha": git_sha or "unknown",
            "disclosures": list(DISCLOSURES), "funnel": dict(funnel),
            "buckets": dict(Counter(p["bucket"] for p in pairs)),
            "arms": {arm: analysis.arm_summary(pairs, arm) for arm in ARMS},
            "deltas": {arm: analysis.delta_stats(pairs, arm) for arm in ("A", "B")},
            "b_over_taken": analysis.delta_over_taken(pairs, "B"),
            "calibration": analysis.calibration(pairs), "weekly": analysis.weekly_deltas(pairs),
            "splits": analysis.split_deltas(pairs), "skips": analysis.skip_summary(pairs),
            "tradeability": tradeability_summary(pairs), "close_bucket": dict(close_bucket),
            "bearish": _bearish_summary(bearish), "verdict": verdict}


def label(payload: dict) -> str:
    calibrated = payload["calibration"]["calibrated"]
    if payload["phase"] == "exploratory":
        tail = "" if calibrated else " -- UNCALIBRATED: the forward read is not started"
        return "EXPLORATORY (no verdict)" + tail
    if payload.get("verdict"):
        return f"VERDICT: {payload['verdict']['study']}"
    return "UNCALIBRATED (no verdict)" if not calibrated else "FORWARD (no verdict yet)"


def _r(value) -> str:
    return "n/a" if value is None else f"{value:+.3f}"


def _num(value) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _table(headers, rows) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    return lines + ["| " + " | ".join(str(c) for c in row) + " |" for row in rows] + [""]


def _header(p: dict) -> list[str]:
    return [f"# v229 deferred-entry counterfactual: {p['phase']} read", "", f"**{label(p)}**", "",
            f"- T0: {p['t0']}", f"- Archive last bar: {p['archive_last_bar'] or 'n/a'}",
            f"- Script git SHA: {p['git_sha']}", f"- Frozen rule hash: {p['rule_hash']}", "",
            "Disclosures:", "", *[f"- {line}" for line in p["disclosures"]], ""]


def _population(p: dict) -> list[str]:
    rows = list(p["funnel"].items()) + [(f"bucket {k}", v) for k, v in sorted(p["buckets"].items())]
    return ["## Population funnel", "", *_table(("reason", "count"), rows)]


def _arms(p: dict) -> list[str]:
    rows = [(arm, s["n"], s["taken"], s["wins"], _num(s["win_rate"]), _r(s["exp_r"]), _r(s["total_r"]),
             _r(s["exp_r_gross"])) for arm, s in p["arms"].items()]
    return ["## Arms", "", *_table(("arm", "N", "taken", "wins", "win rate", "ExpR net",
                                    "total R", "ExpR gross"), rows)]


def _deltas(p: dict) -> list[str]:
    rows = [(f"d_{arm}", d["n"], d["weeks"], _r(d["mean"]), _r(d["lower"]), _num(d["p"]))
            for arm, d in p["deltas"].items()]
    taken = p["b_over_taken"]
    return ["## Deltas", "", *_table(("delta", "N", "weeks", "mean", "97.5% lower", "one-sided p"), rows),
            f"d_B over the plans B took (disclosure): n={taken['n']}, mean {_r(taken['mean'])}", ""]


def _calibration(p: dict) -> list[str]:
    cal = p["calibration"]
    rows = [(sim, *(cal["table"][sim][live] for live in analysis.CLASSES)) for sim in analysis.CLASSES]
    return ["## Calibration", "", *_table(("sim \\ live", *analysis.CLASSES), rows),
            f"- Agreement: {_num(cal['agreement'])} over n={cal['n']} (threshold "
            f"{FROZEN['calibration_min']:.2f}); excluded {cal['excluded']}",
            f"- Mean R_C {_r(cal['mean_r_c'])}, mean live R {_r(cal['mean_live_r'])}, "
            f"Spearman {_num(cal['spearman'])} (information only)", ""]


def _weekly_and_splits(p: dict) -> list[str]:
    weeks = [(w["week"], w["n"], _r(w["d_a"]), _r(w["d_b"])) for w in p["weekly"]]
    splits = [(name, c["n"], _r(c["d_a"]), _r(c["d_b"])) for name, c in p["splits"].items()]
    return ["## Per week", "", *_table(("week", "N", "d_A", "d_B"), weeks),
            "## Splits", "", *_table(("cell", "N", "d_A", "d_B"), splits)]


def _tradeability(p: dict) -> list[str]:
    t, skips = p["tradeability"], p["skips"]
    lines = [f"- {key}: {_r(value) if key.startswith('mean_') else value}"
             for key, value in t.items() if not isinstance(value, dict)]
    lines += [f"- {key}: " + ", ".join(f"{k} {_r(v) if isinstance(v, float) or v is None else v}"
                                       for k, v in value.items())
              for key, value in t.items() if isinstance(value, dict)]
    return ["## Arm B skips", "", f"- Skipped: {skips['skipped']}; control R of the skipped plans "
            f"{_r(skips['control_r_of_skipped'])}", "", "## Tradeability", "", *lines, ""]


def _context(p: dict) -> list[str]:
    close, bear = p["close_bucket"], p["bearish"]
    rows = [(arm, s["n"], s["taken"], _r(s["exp_r"])) for arm, s in bear["arms"].items()]
    return ["## Context", "", f"- Live LONG trades opened at or after 15:30 ET: n={close['n']}, "
            f"ExpR {_r(close['exp_r'])}", "", "## Bearish disclosure", "",
            f"Never enters the verdict. n={bear['n']}, d_A {_r(bear['d_a'])}, d_B {_r(bear['d_b'])}", "",
            *_table(("arm", "N", "taken", "ExpR net"), rows)]


def _verdict(p: dict) -> list[str]:
    v = p.get("verdict")
    if not v:
        return []
    ledger = v["ledger"]
    return ["## Verdict", "", f"- Study: {v['study']}",
            *[f"- Arm {arm}: {word}" for arm, word in v["arms"].items()],
            f"- Ledger row: verdict {ledger['verdict']}, n={ledger['n']}, exp_r {_r(ledger['exp_r'])}, "
            f"p {_num(ledger['p'])}", ""]


_SECTIONS = (_header, _population, _arms, _deltas, _calibration, _weekly_and_splits,
             _tradeability, _context, _verdict)


def render_markdown(payload: dict) -> str:
    return "\n".join(line for section in _SECTIONS for line in section(payload)).rstrip() + "\n"
