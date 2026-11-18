"""v232 reconciliation table (spec ### The reconciliation table), per side, fill model, era.

Every line is a sum of per-trade rows; there is no remainder line. self_check re-derives
each line from the rows and fails the run on a mismatch above TOLERANCE_R.
"""
from __future__ import annotations

import dataclasses

TOLERANCE_R = 0.01
NO_LIVE_R = ("no_journal", "zero_risk")
LINE_KEYS = ("backtest", "entry", "exit", "live_gross", "costs", "live_net",
             "backtest_no_fill", "manual", "refused", "book_net")
LABELS = {
    "backtest": "Backtest of the plans live traded (zero cost)",
    "entry": "+ entry effect (incl. intraday drift to the close)",
    "exit": "+ exit effect",
    "live_gross": "= Live, gross, scored trades",
    "costs": "- modelled costs",
    "live_net": "= Live, net, scored trades",
    "backtest_no_fill": "+ backtest would not have filled (live net)",
    "manual": "+ manual closes (live net)",
    "refused": "+ not scoreable: bars refused (live net)",
    "book_net": "= Live book, net",
}
_NET_GROUPS = (("backtest_no_fill", "no_fill"), ("manual", "manual"),
               ("refused", "refused"), ("book_net", "book"))
_CHAINS = (("live_gross", ("backtest", "entry", "exit"), ()),
           ("live_net", ("live_gross",), ("costs",)),
           ("book_net", ("live_net", "backtest_no_fill", "manual", "refused"), ()))


class ReconcileError(RuntimeError):
    """The table does not reproduce the live book from its own rows."""


@dataclasses.dataclass(frozen=True)
class Line:
    key: str
    label: str
    total_r: float
    n: int


def _pick(rows, side: str, era: str) -> list:
    return [r for r in rows if r.side == side and r.era == era]


def _where(rows, pred) -> list:
    return [r for r in rows if pred(r)]


def _no_fill(row, fill_model: str) -> bool:
    return bool(row.values[fill_model]["backtest_no_fill"])


def _groups(rows, fill_model: str) -> dict:
    book = _where(rows, lambda r: r.klass in ("closed", "manual"))
    scored = _where(book, lambda r: r.scored)
    return {"filled": _where(scored, lambda r: not _no_fill(r, fill_model)),
            "no_fill": _where(scored, lambda r: _no_fill(r, fill_model)),
            "manual": _where(book, lambda r: r.klass == "manual" and r.refusal is None),
            "refused": _where(book, lambda r: r.refusal is not None),
            "book": book}


def _sum(values) -> float:
    return float(sum(v for v in values if v is not None))      # None: no live R, 0R


def _refused_label(refused: list) -> str:
    k = sum(r.refusal in NO_LIVE_R for r in refused)
    if not k:
        return LABELS["refused"]
    return f"{LABELS['refused']}; {k} without live R (no journal R or zero risk), counted at 0R"


def build_table(rows, *, side: str, fill_model: str, era: str = "headline") -> list[Line]:
    """The ten lines for one side, fill model and era, each summed from the rows."""
    g = _groups(_pick(rows, side, era), fill_model)
    f = g["filled"]
    totals = {
        "backtest": _sum(r.values[fill_model]["r_as_backtest"] for r in f),
        "entry": _sum(r.effects[fill_model]["entry"] for r in f),
        "exit": _sum(r.effects[fill_model]["exit"] for r in f),
        "live_gross": _sum(r.r_live_gross for r in f),
        "costs": _sum(r.cost_r for r in f),
        "live_net": _sum(r.r_live_net for r in f),
        **{key: _sum(r.r_live_net for r in g[group]) for key, group in _NET_GROUPS},
    }
    sizes = {key: len(g[group]) for key, group in _NET_GROUPS}
    labels = {**LABELS, "refused": _refused_label(g["refused"])}
    return [Line(k, labels[k], totals[k], sizes.get(k, len(f))) for k in LINE_KEYS]


def book_total(rows, *, side: str, era: str) -> float:
    """The live book's net R from gross and cost (not from r_live_net), closed and manual."""
    return float(sum(r.r_live_gross - r.cost_r for r in _pick(rows, side, era)
                     if r.klass in ("closed", "manual") and r.r_live_gross is not None
                     and r.cost_r is not None))


def _line_errors(lines, expected) -> list[str]:
    if [line.key for line in lines] != list(LINE_KEYS):
        return [f"line keys {[line.key for line in lines]} are not LINE_KEYS"]
    return [f"line {got.key}: table {got.total_r:+.4f} (n {got.n}) vs rows "
            f"{want.total_r:+.4f} (n {want.n})"
            for got, want in zip(lines, expected)
            if abs(got.total_r - want.total_r) > TOLERANCE_R or got.n != want.n]


def _chain_errors(t: dict) -> list[str]:
    errors = []
    for result, plus, minus in _CHAINS:
        got = sum(t[k].total_r for k in plus) - sum(t[k].total_r for k in minus)
        if abs(got - t[result].total_r) > TOLERANCE_R:
            errors.append(f"{result}: lines above give {got:+.4f}, "
                          f"line is {t[result].total_r:+.4f}")
    parts = sum(t[k].n for k in ("live_net", "backtest_no_fill", "manual", "refused"))
    if parts != t["book_net"].n:
        errors.append(f"book_net n {t['book_net'].n} is not the sum of its parts {parts}")
    return errors


def self_check(lines, rows, *, side: str, fill_model: str, era: str) -> None:
    """Raise ReconcileError unless the table re-derives from the rows and closes on the book."""
    errors = _line_errors(lines, build_table(rows, side=side, fill_model=fill_model, era=era))
    if not errors or not errors[0].startswith("line keys"):
        t = {line.key: line for line in lines}
        errors += _chain_errors(t)
        book = book_total(rows, side=side, era=era)
        if abs(book - t["book_net"].total_r) > TOLERANCE_R:
            errors.append(f"book_net {t['book_net'].total_r:+.4f} vs live book {book:+.4f}")
    if errors:
        raise ReconcileError(f"{side} {fill_model} {era}: " + "; ".join(errors))


def selection_line(counts: dict, rows, *, side: str, era: str) -> str:
    """The selection counts under the table; still-open and unfilled come from the rows."""
    cell = counts[side][era]
    picked = _pick(rows, side, era)
    still_open = sum(r.klass == "still_open" for r in picked)
    unfilled = sum(r.klass == "unfilled" for r in picked)
    return (f"Selection, counts only: matched {cell['matched']}"
            f" · live-only {cell['live_only']['n']} · replay-only {cell['replay_only']['n']}"
            f" · outside the replay (strategy-sourced) {cell['outside_replay']}"
            f" · still open {still_open} · unfilled {unfilled}")
