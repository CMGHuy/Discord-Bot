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
