"""``--instrument v1|v2`` for backtest scripts (v136 spec, cross-cutting rule 2:
"Scripts never define dates").

Every live script under ``scripts/backtest/`` calls ``add_instrument_arg`` and
takes its windows from here, so no script picks a date or words a refusal
itself. v1 (the default) returns exactly today's windows and passes
``instrument=None`` to ``run_backtest``; v2 returns the research span, seals the
holdout, and lets a script refuse a path a later phase owns (``require_v1``).
"""
from __future__ import annotations

import argparse

from swingbot.core.backtesting.instrument import contract
from swingbot.core.backtesting.instrument.contract import InstrumentSpec

HOLDOUT_SEALED = ("the holdout is sealed: one shot per pre-registration, read only after "
                  "the research verdict is committed; no phase-3 script reads it")
_STAGES = ("train", "validation")


def add_instrument_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--instrument`` (default v1) to a script's parser."""
    parser.add_argument(
        "--instrument", choices=contract.VERSIONS, default="v1",
        help="backtest instrument (v136 spec): v1 = today's windows and fills (default); "
             "v2 = research span, point-in-time S&P 500, purged folds")


def spec_from_args(args: argparse.Namespace) -> InstrumentSpec:
    """The InstrumentSpec named by the parsed ``--instrument``."""
    return contract.resolve(args.instrument)


def run_instrument(spec: InstrumentSpec) -> InstrumentSpec | None:
    """What a script passes as ``run_backtest(..., instrument=...)``: None under
    v1, exactly today's argument (rule 1, v1 byte-identical)."""
    return None if spec.version == "v1" else spec


def _has_v1_split(spec: InstrumentSpec) -> bool:
    """True for an instrument carrying the v1 TRAIN/VALIDATION split."""
    return spec.train_window is not None


def window_for(spec: InstrumentSpec, stage: str) -> tuple[str, str]:
    """The (from, to) entry-date window for ``--train`` / ``--validation``.
    v1: its split windows. v2: ``train`` is the research span; ``validation``
    is the sealed holdout and exits."""
    if stage not in _STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {_STAGES}")
    if _has_v1_split(spec):
        return spec.train_window if stage == "train" else spec.validation_window
    if stage == "validation":
        raise SystemExit(f"--instrument {spec.version}: {HOLDOUT_SEALED} "
                         f"(holdout starts {spec.holdout_start})")
    return spec.research_span


def check_inside_research(spec: InstrumentSpec, date_from: str, date_to: str) -> None:
    """Under v2, a ``--from/--to`` window must lie inside the research span (and
    be ordered); under v1 any window is accepted, as today."""
    if _has_v1_split(spec):
        return
    start, end = spec.research_span
    if not start <= str(date_from)[:10] <= str(date_to)[:10] <= end:
        raise SystemExit(f"--instrument {spec.version}: --from/--to {date_from}..{date_to} "
                         f"must lie inside the research span {start}..{end}; {HOLDOUT_SEALED}")


def require_v1(spec: InstrumentSpec, script: str, owner: str) -> None:
    """Exit under any instrument but v1, naming the phase that wires v2 for
    `script`. v1 (the default) runs exactly as before."""
    if spec.version != "v1":
        raise SystemExit(f"{script}: --instrument {spec.version} is not wired yet; "
                         f"{owner} wires it. Run with --instrument v1 (the default).")
