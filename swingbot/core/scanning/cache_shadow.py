"""v245 shadow check (ANALYSIS_CACHE=shadow): a sampled ticker's cached,
authoritative `_scan_one` against an uncached rerun with no side effects.
Any diff is a bug. Removed by V245-17."""
from __future__ import annotations

import contextlib
import itertools
import json
import logging
import math
import os
import threading
import zlib
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from swingbot import config

from .analyze import ScanIO

SAMPLE_EVERY = 3
SHADOW_LOG_PATH = os.path.join(config.LOG_DIR, "analysis_cache_shadow.jsonl")
SHADOW_MAX_BYTES = 20 * 1024 * 1024
SHADOW_BACKUPS = 3
SCAN_LOGGERS: tuple[str, ...] = ("swingbot.core",)

_SEQ = itertools.count(1)
_ABSENT = object()
_WRITERS: dict[str, RotatingFileHandler] = {}
_WRITERS_LOCK = threading.Lock()


def next_scan_seq() -> int:
    """The next base-lane shadow scan number in this process (1, 2, 3, ...)."""
    return next(_SEQ)


def in_sample(ticker: str, scan_seq: int) -> bool:
    """True on one scan in SAMPLE_EVERY for each ticker (index Decision 8)."""
    return zlib.crc32(ticker.encode()) % SAMPLE_EVERY == scan_seq % SAMPLE_EVERY


def recording_io(base: ScanIO) -> tuple[ScanIO, dict]:
    """`base` unchanged, plus a record of its stop flag and track records."""
    answers: dict = {"stop_requested": False, "track_record": {}}

    def stop_requested():
        answers["stop_requested"] = base.stop_requested()
        return answers["stop_requested"]

    def track_record(base_level):
        answers["track_record"][base_level] = base.track_record(base_level)
        return answers["track_record"][base_level]

    return ScanIO(stop_requested, base.monitor_scan, base.monitor_open, track_record), answers


def comparison_io(answers: dict) -> ScanIO:
    """The rerun's ScanIO: no monitoring, the recorded stop flag and track records."""
    return ScanIO(
        stop_requested=lambda: answers["stop_requested"],
        monitor_scan=lambda ticker, df, current_price: ([], []),
        monitor_open=lambda ticker, df, live_price=None: ([], []),
        track_record=lambda base_level: answers["track_record"].get(base_level, (None, 0)),
    )


class _ThreadDemotion(logging.Filter):
    """This thread's records become DEBUG, kept only if root shows DEBUG."""

    def __init__(self, thread_id: int):
        super().__init__()
        self.thread_id = thread_id

    def filter(self, record: logging.LogRecord) -> bool:
        if record.thread != self.thread_id or record.levelno <= logging.DEBUG:
            return True
        record.levelno, record.levelname = logging.DEBUG, logging.getLevelName(logging.DEBUG)
        return logging.getLogger().isEnabledFor(logging.DEBUG)


def _loggers_under(names: tuple[str, ...]) -> list[logging.Logger]:
    found = {name: logging.getLogger(name) for name in names}
    for name, obj in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(obj, logging.Logger) and any(name.startswith(p + ".") for p in names):
            found[name] = obj
    return list(found.values())


@contextlib.contextmanager
def demoted_logs(names: tuple[str, ...] = SCAN_LOGGERS):
    """Inside the block, what this thread logs under `names` is DEBUG."""
    demotion = _ThreadDemotion(threading.get_ident())
    loggers = _loggers_under(names)
    for logger in loggers:
        logger.addFilter(demotion)
    try:
        yield
    finally:
        for logger in loggers:
            logger.removeFilter(demotion)


def _count(confluence):
    return confluence[0] if confluence else None


def _fields(item) -> dict:
    """The compared fields of one ScanItem (spec § Knob and shadow check)."""
    plan, conf = item.plan, item.conf
    fields = {"entry": plan.entry, "stop_loss": plan.stop_loss, "take_profit": plan.take_profit,
              "target_confluence": _count(item.target_confluence),
              "stop_confluence": _count(item.stop_confluence),
              "conf.level": getattr(conf, "level", None), "conf.score": getattr(conf, "score", None),
              "all_ok": item.all_requirements_met}
    fields.update({f"requirement:{check.key}": check.passed for check in item.requirements or ()})
    return fields


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return bool(a == b)


def _diff(ticker, horizon, direction, field, cached, uncached) -> dict:
    return {"ticker": ticker, "horizon": horizon, "direction": direction, "field": field,
            "cached": cached, "uncached": uncached}


def _by_slot(stats: dict) -> dict:
    slots: dict = {}
    for item in stats.get("items") or ():
        slots.setdefault((item.result.horizon_key, item.plan.direction), []).append(item)
    return slots


def _compare_slot(ticker, slot, cached: list, uncached: list) -> list[dict]:
    horizon, direction = slot
    if len(cached) != len(uncached):
        return [_diff(ticker, horizon, direction, "scenario", len(cached), len(uncached))]
    out = []
    for a, b in zip(cached, uncached):
        fa, fb = _fields(a), _fields(b)
        out.extend(_diff(ticker, horizon, direction, name, fa.get(name), fb.get(name))
                   for name in sorted(set(fa) | set(fb)) if not _same(fa.get(name), fb.get(name)))
    return out


def _trendlines(stats: dict):
    return next((item.trendline_candidates for item in stats.get("items") or ()), _ABSENT)


def compare_stats(ticker: str, cached: dict, uncached: dict) -> list[dict]:
    """Every compared field that differs between two `_scan_one` stats; [] if none."""
    a, b = _by_slot(cached), _by_slot(uncached)
    diffs = []
    for slot in sorted(set(a) | set(b), key=str):
        diffs.extend(_compare_slot(ticker, slot, a.get(slot, []), b.get(slot, [])))
    ta, tb = _trendlines(cached), _trendlines(uncached)
    if ta is not _ABSENT and tb is not _ABSENT and not _same(ta, tb):
        diffs.append(_diff(ticker, None, None, "trendline_candidates", ta, tb))
    return diffs


def _json_default(obj):
    item = getattr(obj, "item", None)
    return item() if callable(item) else str(obj)


def _writer(path: str) -> RotatingFileHandler:
    with _WRITERS_LOCK:
        handler = _WRITERS.get(path)
        if handler is None:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=SHADOW_MAX_BYTES, backupCount=SHADOW_BACKUPS,
                                          encoding="utf-8", delay=True)
            handler.setFormatter(logging.Formatter("%(message)s"))
            _WRITERS[path] = handler
        return handler


def write_diffs(diffs: list[dict], path: str = SHADOW_LOG_PATH) -> None:
    """One JSON line per diff, rotated 20 MB x 3."""
    if not diffs:
        return
    handler = _writer(path)
    at = datetime.now(timezone.utc).isoformat()
    for diff in diffs:
        line = json.dumps({"at": at, **diff}, default=_json_default, sort_keys=True)
        handler.handle(logging.makeLogRecord({"msg": line, "levelno": logging.INFO, "levelname": "INFO"}))


def close_writers() -> None:
    with _WRITERS_LOCK:
        for handler in _WRITERS.values():
            handler.close()
        _WRITERS.clear()
