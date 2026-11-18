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

import json
import os
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import screen_idea  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import placebo  # noqa: E402
from swingbot.core.backtesting.screen.placebo import Cell  # noqa: E402

NULLS = ("v1", "v2")
KINDS = ("gbm", "shuffled")
DEFAULT_WORK = Path(config.DATA_DIR) / "v230-placebo"
DEFAULT_JSON = screen_idea.RESULTS_DIR / "v230"


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


def run_cell_v1(universe_dir, trigger, *, checkpoint_dir) -> list[dict]:
    """One placebo trigger through the v1 screen pipeline; its event rows."""
    udir = Path(universe_dir)
    manifest = json.loads((udir / placebo.MANIFEST_FILE).read_text(encoding="utf-8"))
    index = screen_idea.load_context(udir, (), end=screen_idea.WINDOW_END,
                                     context_start=manifest["calendar_start"]).calendar
    universe = screen_idea.load_universe(udir, udir / placebo.MEMBERSHIP_FILE)
    screens, _ = screen_idea.screen_universe(
        placebo.placebo_idea(trigger, index), universe, udir, start=screen_idea.WINDOW_START,
        end=screen_idea.WINDOW_END, checkpoint_dir=Path(checkpoint_dir),
        event_start=screen_idea.EVENT_START)
    return [row for screen in screens for row in screen.events]


RUNNERS: dict[str, Callable] = {"v1": run_cell_v1}


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
