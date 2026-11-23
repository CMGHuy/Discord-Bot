# v245 — Exact analysis caching — Part 5: shadow comparator and its wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V245-14" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md) (§ Knob and shadow check, § Error handling, § Testing "Shadow comparator")
**Index:** [2026-11-23-v245-exact-analysis-cache_0-index.md](2026-11-23-v245-exact-analysis-cache_0-index.md): Global Constraints, Parallelisation and the task ledger apply to every task here.

Scope: V245-13 builds `swingbot/core/scanning/cache_shadow.py` (sampling, a
recording and a side-effect-free `ScanIO`, thread-scoped log demotion, the
field-by-field comparator, the 20 MB × 3 jsonl). V245-14 wires it into the
base-lane scan only (`scan_run._sync_run_scan`), with `cache_compared` and
`cache_diffs` in each `scan_telemetry` row.

Both tasks run only if V245-6 missed the exit criterion (Phase B shipped).
V245-13 can run in parallel with V245-12; V245-14 waits for V245-11b,
V245-12 and V245-13.

Two names here refine the ledger without changing any cross-part contract:
- The swallowed tag is **`scan.analysis_cache_shadow`**: the ledger's bare
  `analysis_cache_shadow` fails `tests/infra/test_swallowed_ratchet.py`'s
  `TAG_RE` (`^(scan|marketdata|earnings|runstate|ops)\.…`). No test pins a
  tag list, so `tests/market/test_swallowed_tags_oh14.py` is not touched.
- `SHADOW_LOG_PATH` is `os.path.join(config.LOG_DIR, "analysis_cache_shadow.jsonl")`,
  which is the ledger's `logs/analysis_cache_shadow.jsonl` resolved the way
  `config.LOG_FILE` is (`config.py:67`), so the file lands next to `bot.log`
  on the VM whatever the working directory.

---

# Phase C — shadow check

### Task V245-13: Shadow comparator module

**Model:** sonnet — one new self-contained module with fixed field lists and tests; no existing code changes.

Spec § Knob and shadow check. The parts of the shadow check, without scan
wiring (V245-14 wires them in).

**Decisions this task fixes (spec silent):**
- **Recorded answers.** `recording_io` records the authoritative run's stop flag and `track_record` answers; `comparison_io` replays them (`(None, 0)` for a level never asked, possible only when scenarios already differ) and monitors nothing. A run that stopped early so compares two empty results.
- **Demotion = "logged at DEBUG".** Handlers carry no level (`logsetup.configure_logging`), so the filter demotes the record and keeps it only if the root logger shows DEBUG. A logger filter sees only its own logger's records, so it goes on every logger under `SCAN_LOGGERS = ("swingbot.core",)`, for the entering thread only (index Decision 7).
- **Compared fields**, per `(horizon, direction)` slot: `scenario` (item count), `entry`, `stop_loss`, `take_profit`, `target_confluence`/`stop_confluence` (counts), `conf.level`, `conf.score`, `requirement:<key>` (one side only is a diff), `all_ok`; per ticker `trendline_candidates` (first item's, when both sides have items). Exact floats; NaN equals NaN.
- **jsonl**: a `RotatingFileHandler` per path fed records directly (never `bot.log`); lines `{"at": <UTC ISO>, **diff}`.

**Files:**
- Create: `swingbot/core/scanning/cache_shadow.py`
- Test: `tests/scanning/test_cache_shadow.py` (suite `scanning`)

**Interfaces:**
- Consumes: `analyze.ScanIO` (`analyze.py:764`); `config.LOG_DIR`; V245-1/9 `tests/scanning/v245_golden_cases.py` (`CASE_BY_NAME`, `HERMETIC_IO`, `GOLDEN_HARD_FILTERS`, `TICKER`, `MIN_CONFLUENCE`, `MIN_CONFIDENCE`, `GOLDEN_NOW`, `_pin_config_defaults`); V245-9 `_scan_one(..., now=)`.
- Produces: the ledger row's names, plus `SHADOW_MAX_BYTES`, `SHADOW_BACKUPS`, `close_writers() -> None`, `_diff(ticker, horizon, direction, field, cached, uncached) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_cache_shadow.py`:

```python
"""v245 V245-13: the shadow comparator -- sampling, side-effect-free IO,
thread-scoped log demotion, field-by-field diffs, the rotating jsonl."""
import copy
import json
import logging
import os
import threading
import zlib
from types import SimpleNamespace

import numpy as np
import pytest

from swingbot import config
from swingbot.core.scanning import analyze, cache_shadow
from tests.scanning import v245_golden_cases as golden

ANALYZE_LOG = logging.getLogger("swingbot.core.scanning.analyze")
LEVELS_LOG = logging.getLogger("swingbot.core.market.levels")     # exists before any block is entered


def test_one_scan_in_three_per_ticker_and_the_seq_counts_up():
    for ticker in ("AAPL", "XLE", "GOLD", "BRK-B"):
        hits = [seq for seq in range(30) if cache_shadow.in_sample(ticker, seq)]
        assert len(hits) == 10 and all(b - a == 3 for a, b in zip(hits, hits[1:]))
        assert hits[0] == zlib.crc32(ticker.encode()) % 3
    first = cache_shadow.next_scan_seq()
    assert cache_shadow.next_scan_seq() == first + 1


def test_recording_io_records_and_passes_through():
    base = analyze.ScanIO(lambda: False, lambda t, d, p: (["closed"], ["near"]),
                          lambda t, d, live_price=None: (["o"], []), lambda lvl: (55.0, lvl * 10))
    io, answers = cache_shadow.recording_io(base)
    assert io.stop_requested() is False
    assert io.monitor_scan("T", None, 1.0) == (["closed"], ["near"])
    assert io.track_record(3) == (55.0, 30) and io.track_record(4) == (55.0, 40)
    assert answers == {"stop_requested": False, "track_record": {3: (55.0, 30), 4: (55.0, 40)}}


def test_comparison_io_answers_from_the_record_and_monitors_nothing():
    io = cache_shadow.comparison_io({"stop_requested": True, "track_record": {3: (55.0, 30)}})
    assert io.stop_requested() is True
    assert io.monitor_scan("T", None, 1.0) == ([], []) and io.monitor_open("T", None) == ([], [])
    assert io.track_record(3) == (55.0, 30) and io.track_record(9) == (None, 0)


class _Journal:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append(name)
            return [] if name == "get_trades" else {"win_rate": None, "closed": 0}
        return call


def _run(case, io):
    df = case.frame()
    live = case.live_price(df)
    hard_filters = {**golden.GOLDEN_HARD_FILTERS, "mtf_adjacent_gate": case.mtf_adjacent_gate,
                    "confluence_atr_stop_floor": case.atr_stop_floor}
    with pytest.MonkeyPatch.context() as mp:
        golden._pin_config_defaults(mp)
        return analyze._scan_one(golden.TICKER, df, list(case.horizons), None, None,
                                 golden.MIN_CONFLUENCE, golden.MIN_CONFIDENCE,
                                 live_prices={golden.TICKER: live} if live else None,
                                 hard_filters=hard_filters, allowed_directions=case.allowed_directions,
                                 io=io, now=golden.GOLDEN_NOW)


def test_the_comparison_run_writes_no_journal_and_matches_the_recorded_run(monkeypatch):
    journal = _Journal()
    monkeypatch.setattr(analyze, "trade_log", journal)
    case = golden.CASE_BY_NAME["wave_forming"]
    io, answers = cache_shadow.recording_io(golden.HERMETIC_IO)
    authoritative = _run(case, io)
    assert authoritative["items"] and answers["track_record"], "the case must build scored scenarios"
    uncached = _run(case, cache_shadow.comparison_io(answers))
    assert journal.calls == []
    assert cache_shadow.compare_stats(golden.TICKER, authoritative, uncached) == []


def _item(horizon="4w", direction="bullish", **over):
    fields = dict(
        result=SimpleNamespace(horizon_key=horizon),
        plan=SimpleNamespace(direction=direction, entry=100.0, stop_loss=95.0, take_profit=110.0),
        conf=SimpleNamespace(level=3, score=61),
        requirements=[SimpleNamespace(key="min_reward", passed=True),
                      SimpleNamespace(key="min_confidence", passed=False)],
        target_confluence=(2, ("F", "P")), stop_confluence=(1, ("D",)),
        trendline_candidates=[(101.25, "TL")], all_requirements_met=False)
    fields.update(over)
    return SimpleNamespace(**fields)


def _stats(*items):
    return {"items": list(items)}


def test_equal_inputs_give_no_diffs_nan_included():
    stats = _stats(_item(), _item(direction="bearish"), _item(horizon="2m"))
    assert cache_shadow.compare_stats("T", stats, copy.deepcopy(stats)) == []
    assert cache_shadow.compare_stats("T", _stats(), _stats()) == []
    nan = _stats(_item(conf=SimpleNamespace(level=3, score=float("nan"))))
    assert cache_shadow.compare_stats("T", nan, copy.deepcopy(nan)) == []


MUTATIONS = {
    "entry": lambda i: setattr(i.plan, "entry", 100.01),
    "stop_loss": lambda i: setattr(i.plan, "stop_loss", 94.99),
    "take_profit": lambda i: setattr(i.plan, "take_profit", 110.5),
    "target_confluence": lambda i: setattr(i, "target_confluence", (3, ("F", "P", "V"))),
    "stop_confluence": lambda i: setattr(i, "stop_confluence", (0, ())),
    "conf.level": lambda i: setattr(i.conf, "level", 4),
    "conf.score": lambda i: setattr(i.conf, "score", 62),
    "requirement:min_reward": lambda i: setattr(i.requirements[0], "passed", False),
    "all_ok": lambda i: setattr(i, "all_requirements_met", True),
    "trendline_candidates": lambda i: setattr(i, "trendline_candidates", [(101.26, "TL")]),
}


@pytest.mark.parametrize("field", sorted(MUTATIONS))
def test_each_compared_field_gives_exactly_one_diff(field):
    cached = _stats(_item())
    uncached = copy.deepcopy(cached)
    MUTATIONS[field](uncached["items"][0])
    (diff,) = cache_shadow.compare_stats("T", cached, uncached)
    assert diff["field"] == field and diff["ticker"] == "T"
    expected_slot = (None, None) if field == "trendline_candidates" else ("4w", "bullish")
    assert (diff["horizon"], diff["direction"]) == expected_slot


def test_a_missing_scenario_and_a_one_sided_requirement_are_one_diff_each():
    (diff,) = cache_shadow.compare_stats("T", _stats(_item(), _item(direction="bearish")), _stats(_item()))
    assert (diff["direction"], diff["field"], diff["cached"], diff["uncached"]) == ("bearish", "scenario", 1, 0)
    extra = _stats(_item())
    extra["items"][0].requirements.append(SimpleNamespace(key="max_stop", passed=True))
    (diff,) = cache_shadow.compare_stats("T", _stats(_item()), extra)
    assert (diff["field"], diff["cached"], diff["uncached"]) == ("requirement:max_stop", None, True)


def test_demoted_logs_hide_this_threads_lines_and_restore_after(caplog):
    with caplog.at_level(logging.INFO):
        with cache_shadow.demoted_logs():
            ANALYZE_LOG.info("plan rejected (inside)")
            LEVELS_LOG.warning("levels inside")
        ANALYZE_LOG.info("plan rejected (after)")
    assert [r.getMessage() for r in caplog.records] == ["plan rejected (after)"]


def test_demoted_lines_show_at_debug_when_debug_is_on(caplog):
    with caplog.at_level(logging.DEBUG):
        with cache_shadow.demoted_logs():
            ANALYZE_LOG.info("plan rejected (inside)")
    (record,) = [r for r in caplog.records if r.getMessage() == "plan rejected (inside)"]
    assert (record.levelno, record.levelname) == (logging.DEBUG, "DEBUG")


def test_other_threads_and_other_loggers_keep_their_level(caplog):
    with caplog.at_level(logging.INFO):
        with cache_shadow.demoted_logs():
            worker = threading.Thread(target=ANALYZE_LOG.info, args=("other thread",))
            worker.start()
            worker.join()
            logging.getLogger("swingbot.commands.scanning.loops").info("outside the names")
    assert sorted(r.getMessage() for r in caplog.records) == ["other thread", "outside the names"]
    assert all(r.levelno == logging.INFO for r in caplog.records)


def test_write_diffs_appends_one_json_line_per_diff(tmp_path):
    path = tmp_path / "shadow" / "diffs.jsonl"
    diffs = [cache_shadow._diff("T", "4w", "bullish", "entry", np.float64(100.0), 100.01),
             cache_shadow._diff("T", None, None, "trendline_candidates", [(1.5, "x")], [(1.25, "x")])]
    try:
        cache_shadow.write_diffs([], str(path))
        cache_shadow.write_diffs(diffs, str(path))
    finally:
        cache_shadow.close_writers()
    lines = [json.loads(row) for row in path.read_text(encoding="utf-8").splitlines()]
    assert [line["field"] for line in lines] == ["entry", "trendline_candidates"]
    assert lines[0]["cached"] == 100.0 and lines[1]["cached"] == [[1.5, "x"]] and lines[0]["at"]


def test_write_diffs_rotates_at_the_size_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_shadow, "SHADOW_MAX_BYTES", 400)
    path = tmp_path / "diffs.jsonl"
    try:
        for n in range(40):
            cache_shadow.write_diffs([cache_shadow._diff("T", "4w", "bullish", "entry", n, n + 1)], str(path))
    finally:
        cache_shadow.close_writers()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "diffs.jsonl", "diffs.jsonl.1", "diffs.jsonl.2", "diffs.jsonl.3"]


def test_the_shadow_file_and_its_cap():
    assert cache_shadow.SHADOW_LOG_PATH == os.path.join(config.LOG_DIR, "analysis_cache_shadow.jsonl")
    assert (cache_shadow.SHADOW_MAX_BYTES, cache_shadow.SHADOW_BACKUPS) == (20 * 1024 * 1024, 3)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `python scripts/dev/testrun.py file tests/scanning/test_cache_shadow.py`
Expected: collection error, `cannot import name 'cache_shadow'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/scanning/cache_shadow.py`:

```python
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
```

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_cache_shadow.py
python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
```

Expected: both PASS, `0 failed`, `0 xfailed` (no `except Exception` here, so
the ratchet count is unchanged). Journal calls in the no-journal test mean
`_scan_one` reaches `trade_log` outside `ScanIO`, a side effect the spec
forbids: stop and report it, never loosen the assertion.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py` — passes; every new function ≤ 6.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/cache_shadow.py tests/scanning/test_cache_shadow.py
git commit -m "feat(v245): shadow comparator module (V245-13)"
```

### Task V245-14: Wire shadow into the base-lane scan

**Model:** opus — edits `_sync_run_scan` (complexity 94, must not grow) and the live analysis path, where a side effect in the rerun would double-monitor trades or double-count ops greps.

Spec § Knob and shadow check, § Error handling. In `ANALYSIS_CACHE=shadow`
the base lane runs every ticker cached (authoritative, as in `on`). On a
sampled ticker it then reruns `_scan_one` uncached with `comparison_io`,
`progress=None`, the same `now` and `live_prices`, under `demoted_logs()`,
and compares. The SHORT lane is untouched (index Decision 3). `off` and `on`
behave exactly as after V245-12.

**Decisions this task fixes (spec silent):**
- **One per-scan context.** `_AnalysisCtx` holds the mode and cache from
  `_start_analysis_cache()` (V245-12; never `_analysis_cache()`, which would
  skip the counter reset), the scan clock (replacing V245-9's `scan_now`
  local), the shadow scan number (`cache_shadow.next_scan_seq()` in `shadow`,
  else 0) and the compared/diff counts, bumped under a lock so a future
  `SCAN_WORKERS > 1` counts right.
- **What is compared.** A ticker is compared when the mode is `shadow`, the
  cache exists, its frame is not `None` and `in_sample` says so. The
  comparison counts only when it completes; a failure goes through
  `swallowed(log, "scan.analysis_cache_shadow", ...)` at WARNING with the
  traceback and the cached stats are returned untouched.
- **Telemetry.** `cache_compared` and `cache_diffs` are integers in `shadow`
  and `None` otherwise (the `_cache_telemetry` convention), so V245-15's
  soak report reads only shadow rows. A diff also logs one WARNING line
  naming the ticker, the count and the jsonl path.

**Files:**
- Modify: `swingbot/core/scanning/scan_run.py` (imports; helpers below `_cache_telemetry`; the analysis call site ~753; the telemetry dict ~1358)
- Test: `tests/scanning/test_cache_shadow_wiring.py` (suite `scanning`)
- Not touched: `tests/market/test_swallowed_tags_oh14.py` (it pins no tag list; `tests/infra/test_swallowed_ratchet.py` checks the new tag's form and uniqueness)

**Interfaces:**
- Consumes: V245-13 `cache_shadow` (`next_scan_seq`, `in_sample`, `recording_io`, `comparison_io`, `demoted_logs`, `compare_stats`, `write_diffs`, `SHADOW_LOG_PATH`, `close_writers`); V245-12 `scan_run._start_analysis_cache()`, `_cache_telemetry`, and the call-site lines it left (`cache_mode, analysis_cache = _start_analysis_cache()`, then V245-9's `scan_now = datetime.now(timezone.utc)` and `log.debug("analysis cache: %s", cache_mode)`, the lambda ending `structure=analysis_cache, now=scan_now),`); V245-9 `_scan_one(..., structure=, now=)`; `analyze.LIVE_IO`; `scan_run.ScanProgress`; `infra.swallowed.swallowed/snapshot/reset`; `tests/scanning/test_mtf_gate._scan_with_funnel`; `tests.store_seed.seed_store`; the golden helpers.
- Produces (ledger): `@dataclass _AnalysisCtx(mode, cache, scan_now, scan_seq, compared=0, diffs=0)`; `_scan_ticker(ticker, df, scan_kwargs: dict, ctx) -> dict`; telemetry keys `cache_compared`, `cache_diffs`; swallowed tag `scan.analysis_cache_shadow`. Also `_new_analysis_ctx(mode, cache) -> _AnalysisCtx`, `_shadow_telemetry(ctx) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_cache_shadow_wiring.py`:

```python
"""v245 V245-14: the shadow comparison wired into the base-lane scan."""
import logging
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.infra import swallowed as sw
from swingbot.core.scanning import analyze, cache_shadow, scan_run, structure, telemetry
from swingbot.core.scanning.structure import StructureCache
from tests.scanning import v245_golden_cases as golden
from tests.scanning.test_mtf_gate import _scan_with_funnel
from tests.store_seed import seed_store

NOW = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
SEQ = zlib.crc32(b"T") % 3            # the scan number on which ticker "T" is sampled
KWARGS = {"horizons_to_scan": ["4w"], "progress": "PROGRESS", "regime": None,
          "effective_min_confluence": 0, "effective_min_confidence": 0, "live_prices": {"T": 101.0}}


def _stats(entry=100.0):
    item = SimpleNamespace(
        result=SimpleNamespace(horizon_key="4w"),
        plan=SimpleNamespace(direction="bullish", entry=entry, stop_loss=95.0, take_profit=110.0),
        conf=SimpleNamespace(level=3, score=60), requirements=[], target_confluence=(2, ()),
        stop_confluence=(1, ()), trendline_candidates=[], all_requirements_met=True)
    return {"items": [item]}


@pytest.fixture
def calls(monkeypatch):
    """A fake `_scan_one` recording each call's kwargs; an uncached call
    (structure None) returns `calls.uncached_entry` as its entry."""
    seen = SimpleNamespace(log=[], uncached_entry=100.0)

    def fake(ticker, df, **kwargs):
        seen.log.append(kwargs)
        return _stats(seen.uncached_entry if kwargs.get("structure") is None else 100.0)

    monkeypatch.setattr(analyze, "_scan_one", fake)
    monkeypatch.setattr(cache_shadow, "write_diffs", lambda diffs, path: seen.log.append({"written": diffs}))
    return seen


def _ctx(mode, seq=SEQ):
    return scan_run._AnalysisCtx(mode, None if mode == "off" else StructureCache(4), NOW, seq)


def test_on_scans_once_with_the_cache_and_the_scan_clock(calls):
    ctx = _ctx("on")
    scan_run._scan_ticker("T", object(), KWARGS, ctx)
    (kwargs,) = calls.log
    assert kwargs["structure"] is ctx.cache and kwargs["now"] is NOW and kwargs["progress"] == "PROGRESS"
    assert "io" not in kwargs and ctx.compared == 0


def test_shadow_reruns_a_sampled_ticker_uncached_without_side_effects(calls):
    ctx = _ctx("shadow")
    stats = scan_run._scan_ticker("T", object(), KWARGS, ctx)
    cached, uncached, written = calls.log
    assert cached["structure"] is ctx.cache and cached["progress"] == "PROGRESS"
    assert uncached["structure"] is None and uncached["progress"] is None
    assert cached["now"] is uncached["now"] is NOW and uncached["live_prices"] is cached["live_prices"]
    assert uncached["io"].monitor_scan("T", None, 1.0) == ([], [])
    assert stats["items"][0].plan.entry == 100.0 and written == {"written": []}
    assert (ctx.compared, ctx.diffs) == (1, 0)


@pytest.mark.parametrize("seq, df", [(SEQ + 1, object()), (SEQ, None)])
def test_shadow_skips_unsampled_tickers_and_missing_frames(calls, seq, df):
    ctx = _ctx("shadow", seq=seq)
    scan_run._scan_ticker("T", df, KWARGS, ctx)
    assert len(calls.log) == 1 and ctx.compared == 0


def test_a_diff_is_counted_written_and_warned(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(analyze, "_scan_one",
                        lambda t, df, **kw: _stats(100.5 if kw.get("structure") is None else 100.0))
    path = tmp_path / "shadow.jsonl"
    monkeypatch.setattr(cache_shadow, "SHADOW_LOG_PATH", str(path))
    ctx = _ctx("shadow")
    with caplog.at_level(logging.WARNING, logger=scan_run.log.name):
        stats = scan_run._scan_ticker("T", object(), KWARGS, ctx)
    cache_shadow.close_writers()
    assert stats["items"][0].plan.entry == 100.0           # the cached result stays authoritative
    assert (ctx.compared, ctx.diffs) == (1, 1)
    (line,) = path.read_text(encoding="utf-8").splitlines()
    assert '"field": "entry"' in line
    assert "analysis cache shadow: T: 1 diff(s)" in caplog.text


def test_a_comparator_failure_is_swallowed(calls, monkeypatch):
    sw.reset()

    def boom(*args):
        raise RuntimeError("comparator")

    monkeypatch.setattr(cache_shadow, "compare_stats", boom)
    ctx = _ctx("shadow")
    stats = scan_run._scan_ticker("T", object(), KWARGS, ctx)
    assert stats["items"][0].plan.entry == 100.0 and (ctx.compared, ctx.diffs) == (0, 0)
    assert sw.snapshot()["scan.analysis_cache_shadow"]["count"] == 1
    sw.reset()


def test_the_rerun_logs_at_debug_only(calls, monkeypatch, caplog):
    def fake(ticker, df, **kwargs):
        analyze.log.info("plan rejected (%s)", "uncached" if kwargs["structure"] is None else "cached")
        return _stats()

    monkeypatch.setattr(analyze, "_scan_one", fake)
    with caplog.at_level(logging.INFO):
        scan_run._scan_ticker("T", object(), KWARGS, _ctx("shadow"))
    assert [r.getMessage() for r in caplog.records if "plan rejected" in r.getMessage()] == [
        "plan rejected (cached)"]


def test_new_ctx_and_shadow_telemetry(monkeypatch):
    monkeypatch.setattr(cache_shadow, "next_scan_seq", lambda: 7)
    assert scan_run._new_analysis_ctx("shadow", None).scan_seq == 7
    on = scan_run._new_analysis_ctx("on", None)
    assert on.scan_seq == 0 and on.scan_now.tzinfo is not None and (on.compared, on.diffs) == (0, 0)
    shadow = _ctx("shadow")
    shadow.compared, shadow.diffs = 31, 0
    assert scan_run._shadow_telemetry(shadow) == {"cache_compared": 31, "cache_diffs": 0}
    assert scan_run._shadow_telemetry(on) == {"cache_compared": None, "cache_diffs": None}


@pytest.mark.parametrize("name", ["wave_forming", "wave_completed_gate", "long_forming", "down_completed"])
def test_real_analysis_cached_and_uncached_agree_cold_and_warm(name, monkeypatch):
    case = golden.CASE_BY_NAME[name]
    df = case.frame()
    live = case.live_price(df)
    kwargs = {"horizons_to_scan": list(case.horizons), "regime": None,
              "effective_min_confluence": golden.MIN_CONFLUENCE,
              "effective_min_confidence": golden.MIN_CONFIDENCE,
              "live_prices": {golden.TICKER: live} if live else None,
              "hard_filters": {**golden.GOLDEN_HARD_FILTERS, "mtf_adjacent_gate": case.mtf_adjacent_gate,
                               "confluence_atr_stop_floor": case.atr_stop_floor},
              "allowed_directions": case.allowed_directions}
    monkeypatch.setattr(analyze, "LIVE_IO", golden.HERMETIC_IO)
    monkeypatch.setattr(cache_shadow, "write_diffs", lambda diffs, path: None)
    golden._pin_config_defaults(monkeypatch)
    seq = zlib.crc32(golden.TICKER.encode()) % 3
    shadow = scan_run._AnalysisCtx("shadow", StructureCache(20), golden.GOLDEN_NOW, seq)
    on = scan_run._AnalysisCtx("on", StructureCache(20), golden.GOLDEN_NOW, 0)
    shadow_progress, on_progress = scan_run.ScanProgress(), scan_run.ScanProgress()
    for _ in range(2):                                         # cold, then warm
        stats = scan_run._scan_ticker(golden.TICKER, df, {**kwargs, "progress": shadow_progress}, shadow)
        scan_run._scan_ticker(golden.TICKER, df, {**kwargs, "progress": on_progress}, on)
    assert (shadow.compared, shadow.diffs) == (2, 0)
    assert shadow_progress.done == on_progress.done           # the rerun never writes progress
    assert golden.first_diff(golden.snapshot(stats), golden.run_case(case)) is None
    if name == "wave_forming":
        assert stats["items"], "the comparison must cover real scenarios"


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """test_mtf_gate.py's isolate_data_dir, requested explicitly."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    seed_store("account", {
        "balance": 10000.0, "risk_pct": 1.0, "max_position_pct": 20.0, "sizing_mode": "risk_pct",
        "balance_history": [{"ts": "2026-08-01T00:00:00+00:00", "balance": 10000.0}],
    })


def _rows(monkeypatch, mode) -> list:
    rows: list = []
    monkeypatch.setattr(structure, "STRUCTURE_CACHE", StructureCache(50))
    monkeypatch.setattr(config, "ANALYSIS_CACHE", mode)
    monkeypatch.setattr(telemetry, "log_scan_telemetry", lambda stats, path=None: rows.append(stats))
    monkeypatch.setattr(telemetry, "scan_slowdown", lambda *args, **kwargs: False)
    return rows


def test_shadow_scan_rows_carry_compared_and_zero_diffs(data_dir, monkeypatch, tmp_path, caplog):
    rows = _rows(monkeypatch, "shadow")
    monkeypatch.setattr(cache_shadow, "in_sample", lambda ticker, seq: True)
    monkeypatch.setattr(cache_shadow, "SHADOW_LOG_PATH", str(tmp_path / "shadow.jsonl"))
    with caplog.at_level(logging.INFO):
        _scan_with_funnel("bullish")
        _scan_with_funnel("bullish")                           # cold, then warm
    assert len(rows) == 2, caplog.text                         # a swallowed telemetry error shows here
    assert [(r["cache_mode"], r["cache_compared"], r["cache_diffs"]) for r in rows] == [
        ("shadow", 1, 0), ("shadow", 1, 0)]
    assert not (tmp_path / "shadow.jsonl").exists()


def test_on_scan_rows_have_no_shadow_counts(data_dir, monkeypatch):
    rows = _rows(monkeypatch, "on")
    _scan_with_funnel("bullish")
    (row,) = rows
    assert (row["cache_compared"], row["cache_diffs"]) == (None, None)
```

- [ ] **Step 2: Run them to make sure they fail**

The last two tests run a real `_sync_run_scan`, whose telemetry block reads
the local Postgres: run `/replicate-prod-db` first unless a sibling task in
this session already did (CLAUDE.md).

Run: `python scripts/dev/testrun.py file tests/scanning/test_cache_shadow_wiring.py`
Expected: FAIL, `module 'swingbot.core.scanning.scan_run' has no attribute '_AnalysisCtx'`.

- [ ] **Step 3: Helpers in `scan_run.py`**

Add `import threading` to the stdlib imports and
`from . import cache_shadow` next to V245-9's
`from . import structure as analysis_structure`. Below `_cache_telemetry`:

```python
@dataclass
class _AnalysisCtx:
    """The base lane's analysis settings for one scan (v245): cache mode and
    cache read once, one clock, the shadow scan number and its counts."""
    mode: str
    cache: object
    scan_now: datetime
    scan_seq: int
    compared: int = 0
    diffs: int = 0


_SHADOW_LOCK = threading.Lock()


def _new_analysis_ctx(mode: str, cache) -> _AnalysisCtx:
    seq = cache_shadow.next_scan_seq() if mode == "shadow" else 0
    return _AnalysisCtx(mode, cache, datetime.now(timezone.utc), seq)


def _shadow_sampled(ticker: str, df, ctx: _AnalysisCtx) -> bool:
    return (ctx.mode == "shadow" and ctx.cache is not None and df is not None
            and cache_shadow.in_sample(ticker, ctx.scan_seq))


def _scan_ticker(ticker: str, df, scan_kwargs: dict, ctx: _AnalysisCtx) -> dict:
    """One base-lane `_scan_one` (v245), cached per `ctx`; in shadow, a sampled
    ticker is also rerun uncached and compared. The cached stats are returned."""
    if not _shadow_sampled(ticker, df, ctx):
        return analyze._scan_one(ticker, df, **scan_kwargs, structure=ctx.cache, now=ctx.scan_now)
    io, answers = cache_shadow.recording_io(analyze.LIVE_IO)
    stats = analyze._scan_one(ticker, df, **scan_kwargs, structure=ctx.cache, now=ctx.scan_now, io=io)
    _shadow_compare(ticker, df, stats, scan_kwargs, ctx, answers)
    return stats


def _shadow_compare(ticker: str, df, cached: dict, scan_kwargs: dict, ctx: _AnalysisCtx,
                    answers: dict) -> None:
    """The uncached, side-effect-free rerun and the comparison; a failure is
    logged and swallowed and never touches the cached result (spec § Error handling)."""
    try:
        with cache_shadow.demoted_logs():
            uncached = analyze._scan_one(ticker, df, **{**scan_kwargs, "progress": None}, structure=None,
                                         now=ctx.scan_now, io=cache_shadow.comparison_io(answers))
        diffs = cache_shadow.compare_stats(ticker, cached, uncached)
        cache_shadow.write_diffs(diffs, cache_shadow.SHADOW_LOG_PATH)
    except Exception as exc:
        swallowed(log, "scan.analysis_cache_shadow", exc,
                  "analysis cache shadow: comparison failed for %s", ticker, exc_info=True)
        return
    _count_shadow(ctx, ticker, len(diffs))


def _count_shadow(ctx: _AnalysisCtx, ticker: str, n_diffs: int) -> None:
    with _SHADOW_LOCK:
        ctx.compared += 1
        ctx.diffs += n_diffs
    if n_diffs:
        log.warning("analysis cache shadow: %s: %d diff(s) between the cached and the uncached "
                    "analysis (%s)", ticker, n_diffs, cache_shadow.SHADOW_LOG_PATH)


def _shadow_telemetry(ctx: _AnalysisCtx) -> dict:
    """cache_compared / cache_diffs: counts in shadow, None in off and on."""
    if ctx.mode != "shadow":
        return {"cache_compared": None, "cache_diffs": None}
    return {"cache_compared": ctx.compared, "cache_diffs": ctx.diffs}
```

`SHADOW_LOG_PATH` is passed explicitly because `write_diffs`'s default is
bound at definition time, so a test's monkeypatch of the constant would
otherwise be ignored.

- [ ] **Step 4: Two edits in `_sync_run_scan`**

1. At the analysis call site (~753), the block V245-9 and V245-12 left
   (`cache_mode, analysis_cache = _start_analysis_cache()`, `scan_now = ...`,
   `log.debug(...)`, `per_ticker_results = fetch.map_tickers(lambda t: analyze._scan_one(...), tickers,)`)
   becomes:

   ```python
       cache_mode, analysis_cache = _start_analysis_cache()
       analysis_ctx = _new_analysis_ctx(cache_mode, analysis_cache)   # one clock and shadow seq per scan (v245)
       log.debug("analysis cache: %s", cache_mode)
       scan_kwargs = dict(horizons_to_scan=horizons_to_scan, progress=progress, regime=regime,
                          effective_min_confluence=effective_min_confluence,
                          effective_min_confidence=effective_min_confidence, rs_cache=rs_cache,
                          spy_df=spy_df, breadth=breadth, live_prices=live_prices,
                          hard_filters=hard_filters, opex_tier_today=opex_tier_today)
       per_ticker_results = fetch.map_tickers(
           lambda t: _scan_ticker(t, fresh_data.get(t), scan_kwargs, analysis_ctx), tickers)
   ```

   The keyword names are `_scan_one`'s own parameter names (`analyze.py:941`),
   so `_scan_one` receives the same values as before; V245-9's spy test
   (`test_base_lane_passes_the_cache_and_one_now`) still sees `structure`
   and one `now` in kwargs. Then `git grep -n "scan_now" swingbot/core/scanning/scan_run.py`
   must show only `_AnalysisCtx`'s field and its uses.
2. In the telemetry dict (~1358), after `**_cache_telemetry(cache_mode, analysis_cache),` add
   `**_shadow_telemetry(analysis_ctx),`.

No branch is added to `_sync_run_scan`: the conditions live in the helpers.

- [ ] **Step 5: Run the tests and the neighbours**

```bash
python scripts/dev/testrun.py file tests/scanning/test_cache_shadow_wiring.py
python scripts/dev/testrun.py file tests/scanning/test_cache_shadow.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_wiring.py
python scripts/dev/testrun.py file tests/scanning/test_analysis_cache_telemetry.py
python scripts/dev/testrun.py file tests/scanning/test_mtf_gate.py
python scripts/dev/testrun.py file tests/scanning/test_v245_scan_one_golden.py
python scripts/dev/testrun.py file tests/infra/test_swallowed_ratchet.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. A real-analysis or scan-row
test reporting `cache_diffs > 0` has found a cache bug (the exact thing the
shadow exists for): print the diff with `cache_shadow.compare_stats`, stop
and report it, never relax the test. `len(rows) == 0` means the telemetry
block swallowed an error (usually the local database not running): fix the
environment, not the assertion.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py` — passes; `_sync_run_scan` stays at 94; each new helper ≤ 5.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/scanning/scan_run.py tests/scanning/test_cache_shadow_wiring.py
git commit -m "feat(v245): shadow compares a rotating third of the base lane uncached (V245-14)"
```

