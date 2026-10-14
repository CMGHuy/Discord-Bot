"""Expectancy attribution (v146): the latest report on disk and its loader.

LIGHT BY CONTRACT: stdlib, ``swingbot.config`` and ``swingbot.core.infra.jsonio``
only. The v150 Reports page imports ``load_latest`` from here, so this module
must never pull in pandas, numpy or ``swingbot.core.backtesting`` (v150 spec,
"Cross-spec requirements on the v146 and v147 plans"). The study itself lives
in ``swingbot/core/analytics/expectancy_attribution.py``, which re-exports
``load_latest``.

Retention is overwrite-latest: one file, replaced atomically on every run
(temp file + ``os.replace`` via ``jsonio.atomic_write_json``). The verdict is
pre-registered and computed once; ``verdict_of_record`` is therefore carried
forward unchanged by every later write, and a later run's ``verdict`` is a
descriptive reading only (spec, "The verdict").
"""
from __future__ import annotations

from pathlib import Path

from swingbot import config
from swingbot.core.infra import jsonio

REPORT_PATH = Path(config.DATA_DIR) / "reports" / "expectancy-attribution.json"
_RECORD_KEYS = ("verdict", "date", "n")


def _target(path: Path | str | None) -> Path:
    return Path(path) if path is not None else REPORT_PATH


def load_latest(path: Path | None = None) -> dict | None:
    """The latest Expectancy attribution report, or None when there is none
    (missing, empty, corrupt, or not a JSON object)."""
    data = jsonio.read_json(str(_target(path)), None)
    return data if isinstance(data, dict) else None


def _complete(record) -> bool:
    return (isinstance(record, dict) and all(key in record for key in _RECORD_KEYS)
            and bool(record.get("verdict")))


def _monotonicity_n(result: dict) -> int:
    total = 0
    for population in (result.get("populations") or {}).values():
        monotonicity = (population or {}).get("monotonicity") or {}
        total += int(monotonicity.get("n") or 0)
    return total


def _record_from(result: dict) -> dict:
    record = result.get("verdict_of_record")
    if _complete(record):
        return {key: record[key] for key in _RECORD_KEYS}
    return {"verdict": result.get("verdict"),
            "date": str(result.get("generated_at") or "")[:10] or None,
            "n": _monotonicity_n(result)}


def write_latest(result: dict, path: Path | None = None) -> dict:
    """Atomically replace the report with ``result`` and return what was
    written. A complete ``verdict_of_record`` already on disk wins."""
    target = _target(path)
    previous = (load_latest(target) or {}).get("verdict_of_record")
    out = dict(result)
    out["verdict_of_record"] = (
        {key: previous[key] for key in _RECORD_KEYS} if _complete(previous)
        else _record_from(result))
    jsonio.atomic_write_json(str(target), out)
    return out
