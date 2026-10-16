"""v161 TS7: assemble the book autopsy -- every cut, one BH pass over all cells,
fill and alert-supply tallies, give-back, header -- and render the Markdown
summary (at most MD_MAX_LINES lines) that is the only thing a generator role reads."""
from __future__ import annotations

import statistics
import hashlib
import json
import shlex
from collections import Counter
from pathlib import Path

from . import bars, cuts, exits
from .cells import apply_bh, cut_cells, net_value
from .rows import closed_trades, friction_settings

MD_MAX_LINES = 150
DEFAULT_BALANCE = 10_000.0
REJECTION_LINES = 8
BAR_CUT_NAMES = frozenset(name for name, _ in bars.bar_cuts())
NOTES = (
    "net R is modelled locally (apply_frictions slippage on both fills plus commission_r); "
    "live rows store gross R only",
    f"bar cuts read only --bars-dir; anchor lag is at most {bars.MAX_ANCHOR_LAG_DAYS} "
    f"calendar days (weekends/holidays included); its close must lie within "
    f"{bars.SPLIT_GUARD:.0%} of its planned entry",
    "alert hour has hour granularity: 09:00-09:29 ET counts as the regular session",
    "every row drawn from this report is exploratory: the window overlaps the 2026 holdout "
    "(spec v161 boundary 5)",
)


def _key_text(value) -> str | None:
    return None if value is None else str(value).replace(";", ",")


def _all_cuts(sector_of: dict) -> tuple:
    return (*cuts.categorical_cuts(sector_of), *bars.bar_cuts(), *exits.exit_cuts())


def _decorate(cell, members: list, covered_n: int, balance: float) -> None:
    if cell.cut in BAR_CUT_NAMES:
        cell.bar_covered_n = covered_n
    if cell.cut in exits.STOP_CUTS:
        cell.extra.update(exits.stop_extra(members, balance))


def _cells(trades: list, covered_n: int, sector_of: dict, *, n_resamples: int, seed: int,
           balance: float) -> list:
    out = []
    for name, key in _all_cuts(sector_of):
        for cell in cut_cells(name, trades, key, n_resamples=n_resamples, seed=seed):
            members = [t for t in trades if _key_text(key(t)) == cell.value]
            _decorate(cell, members, covered_n, balance)
            out.append(cell)
    return out


def _notes(trades: list, balance: float) -> list[str]:
    out = list(NOTES)
    out += [f"{key}: {text}" for key, text in sorted(cuts.CUT_NOTES.items())]
    gross_only = sum(1 for t in trades if t.net_r is None)
    if gross_only:
        out.append(f"{gross_only} trades could not be modelled net and count at gross R")
    out.append(f"stop cells price the dollar loss at 2% of {balance:,.0f} USD")
    return out


def _header(trades: list, covered_n: int, tested: int, *, n_resamples: int, seed: int,
            balance: float) -> dict:
    exit_days = sorted(t.exit_date for t in trades if t.exit_date)
    pooled = round(statistics.fmean(net_value(t) for t in trades), 4) if trades else None
    wins = round(sum(1 for t in trades if t.gross_r > 0) / len(trades), 4) if trades else None
    return {"window": [exit_days[0], exit_days[-1]] if exit_days else [None, None],
            "n": len(trades), "pooled_net_expr": pooled, "pooled_win_rate": wins,
            "net_of_frictions": "modelled", "cells_tested": tested, "bar_covered_n": covered_n,
            "resamples": n_resamples, "seed": seed, "notes": _notes(trades, balance)}


def build_report(rows: list, rejections: list, *, bars_dir: Path | None, n_resamples: int,
                 seed: int, balance: float, frictions: dict | None = None,
                 input_fingerprints: dict | None = None, invocation: dict | None = None) -> dict:
    """The Autopsy JSON (index § Shared contracts) for one export."""
    inputs = dict(input_fingerprints or {})
    covered_n = bars.enrich_with_bars(rows, bars_dir, input_fingerprints=inputs)
    trades = closed_trades(rows)
    cells = _cells(trades, covered_n, cuts.load_sector_map(), n_resamples=n_resamples,
                   seed=seed, balance=balance)
    tested = apply_bh(cells)
    tallies = bars.fill_tallies(rows) + exits.alert_supply_tallies(rows, rejections)
    header = _header(trades, covered_n, tested, n_resamples=n_resamples, seed=seed, balance=balance)
    header.update(frictions=dict(frictions if frictions is not None else friction_settings()),
                  input_fingerprints=inputs, invocation=invocation)
    return {"header": header,
            "cells": [c.to_json() for c in cells],
            "tallies": [t.to_json() for t in tallies],
            "giveback": exits.giveback_summary(trades)}


def _fmt(value, spec: str = ".3f") -> str:
    return "n/a" if value is None else format(value, spec)


def _pct(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _provenance_lines(h: dict) -> list[str]:
    if "frictions" not in h:
        return []
    settings = json.dumps(h["frictions"], sort_keys=True)
    inputs = h["input_fingerprints"]
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode("utf-8")).hexdigest()
    invocation = h.get("invocation")
    command = shlex.join(invocation["command"]) if invocation else "direct build (no CLI)"
    return [f"- Effective frictions: {settings}",
            f"- Input SHA-256 manifest: {digest} ({len(inputs)} files; file hashes in JSON)",
            f"- Invocation: {command}"]


def _header_lines(h: dict) -> list[str]:
    w0, w1 = h["window"]
    lines = [f"# Book autopsy, {w0} to {w1}", "",
             f"- Window (first and last exit date): {w0} to {w1}",
             f"- N closed trades: {h['n']}; bar-covered: {h['bar_covered_n']}",
             f"- Pooled net ExpR (modelled): {_fmt(h['pooled_net_expr'])}; "
             f"pooled win rate: {_pct(h['pooled_win_rate'])}",
             f"- Net of frictions: {h['net_of_frictions']}",
             f"- Cells tested: {h['cells_tested']} (one BH pass over all of them); "
             f"bootstrap resamples {h['resamples']}, seed {h['seed']}"]
    return lines + _provenance_lines(h) + [f"- Note: {note}" for note in h["notes"]] + [""]


def _sort_key(c: dict) -> tuple:
    q = c["q"] if c["q"] is not None else 2.0
    return (q, -abs(c["delta"] or 0.0), c["id"])


def _extra_text(c: dict) -> str:
    e = c["extra"]
    parts = [f"tickers {e.get('tickers')}", f"top share {_pct(e.get('top_ticker_share'))}"]
    if c["bar_covered_n"] is not None:
        parts.append(f"bar-covered {c['bar_covered_n']}")
    if "mean_stop_atr" in e:
        parts.append(f"stop {_fmt(e['mean_stop_atr'], '.2f')} ATR, loss at 2% "
                     f"${_fmt(e['dollar_loss_at_2pct'], '.0f')}, "
                     f"overshoot {_fmt(e['mean_overshoot_r'])}")
    return "; ".join(parts)


def _escape_table_text(text: str) -> str:
    return text.replace("|", "\\|")


def _cell_row(c: dict) -> str:
    ci = "n/a" if c["ci"] is None else f"[{c['ci'][0]:.3f}, {c['ci'][1]:.3f}]"
    delta = "n/a" if c["delta"] is None else f"{c['delta']:+.3f}"
    return (f"| {_escape_table_text(c['id'])} | {c['n']} | {c['weeks']} | {_pct(c['win_rate'])} | "
            f"{_fmt(c['net_expr'])} | {_fmt(c['gross_expr'])} | {delta} {ci} | "
            f"{_fmt(c['q'])} | {_escape_table_text(_extra_text(c))} |")


def _cell_lines(cells: list, budget: int) -> list[str]:
    ranked = sorted((c for c in cells if not c["thin"]), key=_sort_key)
    lines = ["## Cells (not thin; by q, then |Δ|)", "",
             "| cell | N | weeks | WR | net ExpR | gross ExpR | Δ net ExpR [95% CI] | q | notes |",
             "|---|---|---|---|---|---|---|---|---|"]
    shown = ranked[:max(0, budget - len(lines) - 2)]
    lines += [_cell_row(c) for c in shown]
    if len(shown) < len(ranked):
        lines.append(f"- {len(ranked) - len(shown)} more cells in the JSON")
    return lines + [""]


def _thin_lines(cells: list) -> list[str]:
    counts = Counter(c["cut"] for c in cells if c["thin"])
    text = ", ".join(f"{cut} {n}" for cut, n in sorted(counts.items())) or "none"
    return [f"Thin cells (tested and counted in BH, never evidence): {text}", ""]


def _giveback_lines(g: dict) -> list[str]:
    return ["## Give-back (mfe_r minus gross R, every trade)", "",
            f"- N {g['n']}; mean {_fmt(g['mean'])}; median {_fmt(g['median'])}", ""]


def _tally_extra(t: dict) -> str:
    if not t["extra"]:
        return ""
    return " (" + ", ".join(f"{k} {v}" for k, v in t["extra"].items()) + ")"


def _tally_lines(tallies: list) -> list[str]:
    rejections = [t for t in tallies if t["cut"] == "rejection_reason"]
    kept = [t for t in tallies if t["cut"] != "rejection_reason"] + rejections[:REJECTION_LINES]
    lines = ["## Tallies", ""] + [f"- {t['id']}: {t['count']}{_tally_extra(t)}" for t in kept]
    if len(rejections) > REJECTION_LINES:
        lines.append(f"- {len(rejections) - REJECTION_LINES} more rejection reasons in the JSON")
    return lines + [""]


def render_markdown(report: dict) -> str:
    """Header, the non-thin cell table cut to the line budget, thin counts, give-back, tallies."""
    head = _header_lines(report["header"])
    tail = (_thin_lines(report["cells"]) + _giveback_lines(report["giveback"])
            + _tally_lines(report["tallies"]))
    body = _cell_lines(report["cells"], MD_MAX_LINES - len(head) - len(tail))
    return "\n".join((head + body + tail)[:MD_MAX_LINES]) + "\n"
