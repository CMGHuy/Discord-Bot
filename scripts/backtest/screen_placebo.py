#!/usr/bin/env python3
"""v230 A1 placebo harness: the screen's own pipeline over universes with no edge.

    python scripts/backtest/screen_placebo.py --null v1 --date <YYYY-MM-DD>

Builds (or reuses) the gbm and shuffled universes under --work-dir on the real
session calendar of the screen window, runs each placebo trigger through the
screen pipeline under --null and upserts one cell per universe x trigger into
<json-dir>/placebo-<null>.json as it finishes (a restart skips finished cells;
a cell checkpoints per ticker). Renders <results-dir>/<date>-v230-null-placebo.md
from every placebo-v*.json. Never touches the pre-registration ledger.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import null_v2, placebo  # noqa: E402
from swingbot.core.backtesting.screen.placebo import Cell  # noqa: E402

NULLS = ("v1", "v2")
KINDS = ("gbm", "shuffled")
DEFAULT_WORK = Path(config.DATA_DIR) / "v230-placebo"
DEFAULT_JSON = screen_idea.RESULTS_DIR / "v230"
PLANTED_JSON = "placebo-planted.json"

SPEC_LINK = "../specs/2026-11-16-v230-screen-v2-ladder-additive-gate-design.md"
_SIZE = re.compile(r"(\d+)$")
HEADER = ("| Universe | Trigger | Null | N | mean R event | mean R null | Δ | 95% interval "
          "| half-width | rule |", "|---|---|---|---:|---:|---:|---:|---|---:|---|")
GATE_TEXT = {
    "BIAS": "At least one cell has |Δ| > 0.02R: the v1 bias is measured, meeting "
            "v234's prerequisite for the v2 null.",
    "NO-BIAS": "Every cell has |Δ| ≤ 0.02R: the premise of spec v230 is wrong; "
               "v234 stops. Parts B and C proceed on the v1 null."}


def universe_label(kind: str, size: int) -> str:
    """gbm-<tickers> / shuffled-c<copies>: an enlarged universe is a new label."""
    return f"gbm-{size}" if kind == "gbm" else f"{kind}-c{size}"


def load_cells(path) -> list[Cell]:
    path = Path(path)
    if not path.is_file():
        return []
    return [Cell.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))]


def save_cell(path, cell: Cell) -> None:
    """Upsert by (universe, trigger, null); tmp file + os.replace, never a torn file."""
    path = Path(path)
    key = (cell.universe, cell.trigger, cell.null)
    cells = [c for c in load_cells(path) if (c.universe, c.trigger, c.null) != key] + [cell]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps([c.to_dict() for c in cells], indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


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


def _build_gbm(out, source, calendar, args):
    quartiles = placebo.atr_pct_quartiles(source, calendar)
    return placebo.gbm_universe(out, calendar, quartiles, n_tickers=args.gbm_tickers)


def _build_shuffled(out, source, calendar, args):
    return placebo.shuffled_universe(out, source, calendar, copies=args.shuffled_copies)


BUILDERS = {"gbm": (_build_gbm, "gbm_tickers"), "shuffled": (_build_shuffled, "shuffled_copies")}


def build_universes(args) -> dict[str, Path]:
    """Every requested universe, built once; one with a universe.json is reused."""
    source = Path(args.source_cache)
    calendar = placebo.trading_calendar(source / f"{placebo.INDEX_TICKER}.csv",
                                        screen_idea.WINDOW_START, screen_idea.WINDOW_END)
    built = {}
    for kind in args.universes:
        build, size_attr = BUILDERS[kind]
        label = universe_label(kind, getattr(args, size_attr))
        out = Path(args.work_dir) / "universes" / label
        reuse = (out / placebo.MANIFEST_FILE).is_file()
        print(f"[placebo] universe {label}: {'reused' if reuse else 'building'}", flush=True)
        if not reuse:
            build(out, source, calendar, args)
        built[label] = out
    return built


def _label_key(label: str) -> tuple[str, int]:
    match = _SIZE.search(label)
    return label.split("-", 1)[0], int(match.group(1)) if match else 0


def latest_cells(cells) -> list[Cell]:
    """The largest universe per (kind, trigger, null); an enlarged run supersedes."""
    best: dict[tuple, Cell] = {}
    for cell in cells:
        kind, size = _label_key(cell.universe)
        key = (kind, cell.trigger, cell.null)
        if key not in best or size >= _label_key(best[key].universe)[1]:
            best[key] = cell
    return list(best.values())


def v1_gate(cells) -> str | None:
    v1 = [c for c in latest_cells(cells) if c.null == "v1"]
    if not v1:
        return None
    return "BIAS" if placebo.v1_premise_holds(v1) else "NO-BIAS"


def _run_cells(universes: dict[str, Path], args) -> list[str]:
    """Every cell not yet saved; a refused cell is no cell (record-and-ask) and the
    rest still run. Returns the refusals as ``<label>/<trigger>: <code>: <detail>``."""
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


def _num(x, sign: bool = True) -> str:
    return "—" if x is None else (f"{x:+.4f}" if sign else f"{x:.4f}")


def _cell_row(c: Cell) -> str:
    interval = "—" if c.ci_low is None else f"[{c.ci_low:+.4f}, {c.ci_high:+.4f}]"
    return (f"| {c.universe} | {c.trigger} | {c.null} | {c.n} | {_num(c.mean_r_event)} | "
            f"{_num(c.mean_r_null)} | {_num(c.delta)} | {interval} | "
            f"{_num(c.half_width, sign=False)} | {placebo.accept_cell(c)} |")


def _detail(m: dict) -> str:
    if m.get("kind") == "planted":
        return (f"planted on {m['base']}, +{m['plant_atr']} ATR14 over {m['cap']} bars, "
                f"spacing {m['spacing']}")
    if "quartiles" in m:
        return "ATR% quartiles " + ", ".join(f"{q:.4f}" for q in m["quartiles"])
    return f"copies {m.get('copies', 1)}, {len(m.get('source_sha256', {}))} source files"


def _universe_lines(manifests: dict) -> list[str]:
    lines = ["## Universes", "", "| Label | Kind | Tickers | Calendar | Seed | Detail |",
             "|---|---|---:|---|---:|---|"]
    hashes: list[str] = []
    for label, m in sorted(manifests.items()):
        lines.append(f"| {label} | {m['kind']} | {len(m['tickers'])} | "
                     f"{m['calendar_start']}..{m['calendar_end']} | {m['seed']} | {_detail(m)} |")
        if m.get("source_sha256"):
            hashes += ["", f"<details><summary>Source file sha256 ({label})</summary>", "",
                       *(f"- `{f}` `{d}`" for f, d in sorted(m["source_sha256"].items())),
                       "", "</details>"]
    return lines + hashes + [""]


def _cell_lines(cells) -> list[str]:
    lines: list[str] = []
    for null in sorted({c.null for c in cells}):
        rows = sorted((c for c in cells if c.null == null), key=lambda c: (c.universe, c.trigger))
        lines += [f"## Cells, null {null}", "", *HEADER, *map(_cell_row, rows), ""]
    return lines


def _gate_lines(cells) -> list[str]:
    gate = v1_gate(cells)
    if gate is None:
        return []
    beyond = sorted(f"{c.universe}/{c.trigger} ({c.delta:+.4f})" for c in latest_cells(cells)
                    if c.null == "v1" and placebo.v1_premise_holds([c]))
    tail = ["", "Cells past 0.02R: " + ", ".join(beyond) + "."] if beyond else []
    return ["## Stop gate 1 (v1)", "", f"Gate: **{gate}**", "", GATE_TEXT[gate], *tail, ""]


def _verdict_lines(planted: Cell | None, acceptance: dict | None) -> list[str]:
    lines = [] if planted is None else ["## Planted edge", "", *HEADER, _cell_row(planted), ""]
    if acceptance is None:
        return lines
    p = acceptance["planted"]
    return lines + ["## Stop gate 2 (v2)", "", f"Verdict: **{acceptance['verdict']}**", "",
                    "| Cell | Rule |", "|---|---|",
                    *(f"| {k} | {v} |" for k, v in sorted(acceptance["cells"].items())), "",
                    f"Planted value {_num(p['value'])} R; recovered: {p['recovered']}; "
                    f"noisy: {p['noisy']}.", ""]


def _pending_lines(refused) -> list[str]:
    """Refused cells leave stop gate 2 open: record-and-ask, the partner decides."""
    if not refused:
        return []
    return ["## Stop gate 2 (v2)", "", "Verdict: **PENDING**", "",
            "Refused cells are no cells and no verdict (never read as STOP or ENLARGE); "
            "the partner decides how to proceed. Refusals:", "",
            *(f"- {line}" for line in refused), ""]


def render_doc(cells, *, date: str, manifests: dict, planted: Cell | None = None,
               acceptance: dict | None = None, refused=()) -> str:
    head = [f"# v230 null placebo — {date}", "", f"**Spec:** [v230]({SPEC_LINK}) A1",
            "**Script:** `scripts/backtest/screen_placebo.py`", "",
            f"Every trigger races long, fixed (stop 1.5 x ATR14, target 3 x ATR14), next-open "
            f"entry, cap {placebo.PLACEBO_CAP} bars, base costs, against the screen's matched "
            f"null (K = 20). Δ = mean R event − mean R null, week-clustered 95% interval. "
            f"Rule: PASS iff |Δ| ≤ 0.02R and half-width ≤ 0.02R (inclusive); only the "
            f"largest universe per kind and trigger is judged.", ""]
    body = (_universe_lines(manifests) + _cell_lines(cells) + _gate_lines(cells)
            + _verdict_lines(planted, acceptance) + _pending_lines(refused))
    return "\n".join(head + body).rstrip("\n") + "\n"


def _all_cells(json_dir) -> list[Cell]:
    return [c for p in sorted(Path(json_dir).glob("placebo-v*.json")) for c in load_cells(p)]


def write_doc(args, *, planted: Cell | None = None, acceptance: dict | None = None,
              refused=()) -> Path:
    manifests = {p.parent.name: json.loads(p.read_text(encoding="utf-8")) for p in
                 sorted((Path(args.work_dir) / "universes").glob(f"*/{placebo.MANIFEST_FILE}"))}
    path = Path(args.results_dir) / f"{args.date}-v230-null-placebo.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_doc(_all_cells(args.json_dir), date=args.date, manifests=manifests,
                               planted=planted, acceptance=acceptance, refused=refused),
                    encoding="utf-8", newline="\n")
    return path


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--null", choices=NULLS, default="v1")
    p.add_argument("--universes", nargs="+", choices=KINDS, default=list(KINDS))
    p.add_argument("--triggers", nargs="+", choices=list(placebo.TRIGGERS),
                   default=list(placebo.TRIGGERS))
    p.add_argument("--work-dir", type=Path, default=DEFAULT_WORK)
    p.add_argument("--source-cache", type=Path, default=screen_idea.DEFAULT_CACHE)
    p.add_argument("--gbm-tickers", type=int, default=placebo.GBM_TICKERS)
    p.add_argument("--shuffled-copies", type=int, default=1)
    p.add_argument("--date", default=datetime.date.today().isoformat())
    p.add_argument("--results-dir", type=Path, default=screen_idea.RESULTS_DIR)
    p.add_argument("--json-dir", type=Path, default=DEFAULT_JSON)
    p.add_argument("--planted", action="store_true",
                   help="v2 only: also run the planted-edge check on the gbm universe")
    return p


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
    doc = write_doc(args, planted=planted, acceptance=verdict, refused=refused)
    print(f"[placebo] wrote {doc}", flush=True)
    gate = v1_gate(_all_cells(args.json_dir))
    if gate is not None:
        print(f"gate: {gate}", flush=True)
    if refused:
        for line in refused:
            print(f"refused: {line}", file=sys.stderr)
        print("stop gate 2: PENDING -- refused cells await the partner", file=sys.stderr)
        return 2
    if verdict is not None:
        print(f"acceptance: {verdict['verdict']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
