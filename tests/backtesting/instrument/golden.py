"""The v1 instrument golden (v136 cross-cutting rule 1).

A pinned 3-ticker v1 run -- every case in tests/fixtures/ohlcv_parity.py
(TSLA, DOCU, DELL; frozen OHLCV) under both v1 exit models -- serialised one
JSON record per line. tests/backtesting/instrument/test_v1_golden.py asserts the
current code renders it byte for byte (line endings normalised), so any change
to v1 output, however small, is a red test.

Regenerating it is a cutover decision, not a fix: the writer below refuses to
overwrite an existing file without --force. Captured by v137 IC1 on unmodified
code, under every config field pinned to its code default.

    python <repo>/tests/backtesting/instrument/golden.py --write
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402

from swingbot.core.backtesting import backtest as bt  # noqa: E402
from tests.fixtures.ohlcv_parity import PARITY_CASES, load_ohlcv  # noqa: E402

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "instrument" / "v1_golden.jsonl"

CONFIGS = (
    ("exit_v1_frictions", {"exit_model": "v1", "frictions": True}),
    ("exit_v2_scale_out_tp2_levels",
     {"exit_model": "v2", "scale_out": True, "tp2_mode": "levels", "frictions": True}),
)


def _jsonable(value):
    """numpy scalars inside trade contexts -> plain Python (json's only gap)."""
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON-serialisable: {type(value).__name__}")


def _line(record) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"), default=_jsonable)


def golden_records(**extra):
    """One summary record, then one record per trade, per (case, config)."""
    for ticker, strategy, horizon in PARITY_CASES:
        frame = load_ohlcv(ticker)
        for name, kwargs in CONFIGS:
            summary = dataclasses.asdict(
                bt.run_backtest(ticker, frame, strategy, horizon, **kwargs, **extra))
            trades = summary.pop("trades")
            case = [ticker, strategy, horizon, name]
            yield {"case": case, "summary": summary}
            for k, trade in enumerate(trades):
                yield {"case": case, "trade": k, "row": trade}


def render_v1_golden(**extra) -> str:
    """The golden text the current code produces; `extra` goes to run_backtest."""
    return "".join(_line(record) + "\n" for record in golden_records(**extra))


def golden_text() -> str:
    return GOLDEN.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _write(force: bool) -> None:
    import pytest

    from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

    if GOLDEN.exists() and not force:
        raise SystemExit(f"{GOLDEN} exists; regenerating the v1 golden is a cutover "
                         "decision -- pass --force only with that decision recorded")
    with pytest.MonkeyPatch.context() as mp:
        pin_code_defaults(mp)
        text = render_v1_golden()
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN} ({text.count(chr(10))} records)")


if __name__ == "__main__":
    if "--write" not in sys.argv:
        raise SystemExit("usage: golden.py --write [--force]")
    _write("--force" in sys.argv)
