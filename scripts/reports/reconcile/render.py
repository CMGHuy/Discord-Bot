"""v232 report assembly and Markdown (spec ### The reconciliation table, ### Statistics).

Aggregates only; backtest R sits under report["layer1"][side][era][fill_model] alone.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import re

from autopsy.eras import ERA_BOUNDARY_UTC

from . import intervals, layer1, layer2, records, sessions, table, tags

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
