"""v147: the gate-counterfactual report file, `data/reports/gate-counterfactual.json`.

The light half of the report: `gate_counterfactual_report.build_report` (analytics, pandas/numpy)
writes through `write_report`; v150's Reports endpoint and the analytics module's re-export read
through `load_report`. This module imports only the stdlib, `swingbot.config` and `jsonio`, so the
admin process can load a report without pandas, numpy or `swingbot.core.backtesting`
(tests/infra/test_gate_counterfactual_store.py proves it in a fresh interpreter).

Retention is overwrite-latest; the one thing never overwritten is a cell's `verdict_of_record` --
the first reading at distinct filled N >= 30 (spec § Freeze), carried forward from the file on disk.
"""
from __future__ import annotations

import copy
from pathlib import Path

from swingbot import config
from swingbot.core.infra import jsonio

REPORT_NAME = "gate-counterfactual.json"
RECORD_KEYS = ("verdict", "date", "n")


def report_path() -> Path:
    """`<DATA_DIR>/reports/gate-counterfactual.json`, read at call time (DATA_DIR is hot-reloadable)."""
    return Path(config.DATA_DIR) / "reports" / REPORT_NAME


def load_report(path=None) -> dict | None:
    """The last written report, or None when the file is missing, empty, corrupt or not a JSON object."""
    content = jsonio.read_json(str(path or report_path()), None)
    return content if isinstance(content, dict) else None


def _complete(record) -> bool:
    return isinstance(record, dict) and all(record.get(key) is not None for key in RECORD_KEYS)


def _records_on_disk(previous: dict | None) -> dict:
    """(gate, population) -> the complete verdict of record already on disk."""
    cells = (previous or {}).get("cells") or []
    return {(cell.get("gate"), cell.get("population")): cell["verdict_of_record"]
            for cell in cells if isinstance(cell, dict) and _complete(cell.get("verdict_of_record"))}


def write_report(result: dict, path=None) -> dict:
    """Atomically write `result` with every frozen verdict of record carried forward; return what was written.

    `result` itself is never mutated."""
    target = Path(path or report_path())
    frozen = _records_on_disk(load_report(target))
    out = copy.deepcopy(result)
    for cell in out.get("cells") or []:
        key = (cell.get("gate"), cell.get("population"))
        if key in frozen:
            cell["verdict_of_record"] = copy.deepcopy(frozen[key])
    jsonio.atomic_write_json(str(target), out)
    return out
