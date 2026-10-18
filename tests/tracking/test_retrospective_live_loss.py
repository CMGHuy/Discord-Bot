"""v164 D3: retrospective Part 11 -- the Sunday live loss watch digest."""
import datetime as dt

from swingbot.core.analytics import calibration
from swingbot.core.tracking import live_loss_watch as lw
from swingbot.core.tracking import retrospective as retro

SUNDAY = dt.date(2026, 10, 18)
MONDAY = dt.date(2026, 10, 19)
LATER = dt.date(2026, 10, 21)          # the real date for a backdated !recap
_HORIZONS = ("4w", "2w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m", None)
_STRATEGIES = ("Bollinger Bands", "Candlestick Pattern", "Fibonacci", "Ichimoku", "MACD",
               "Moving Average", "Pivot Points", "RSI", "Stochastic", "Trendline",
               "Volume Profile")


def _row(source, strategy, horizon, *, alert=False, bound=0.1):
    return {"source": source, "strategy": strategy, "horizon": horizon, "live_n": 24,
            "live_wr": 41.7, "live_expr": -0.12, "bound_upper": bound, "alert": alert,
            "registry_status": "WEAK", "registry_window_kind": "TRAIN",
            "registry_run_date": "2026-09-01", "registry_expr": -0.04}


def _watch():
    """22 rows in LW2's order: the one alert row (confluence 4w) first."""
    rows = [_row("confluence", "ALL", "4w", alert=True, bound=-0.05)]
    rows += [_row("confluence", "ALL", h) for h in _HORIZONS[1:]]
    rows += [_row("strategy", name, None) for name in _STRATEGIES]
    counts = {key: index + 1 for index, key in enumerate(calibration.WATCH_COUNT_KEYS)}
    return {"rows": rows, "counts": counts}


def _isolate(monkeypatch, tmp_path, watch, *, real_today=SUNDAY):
    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))
    calls = []

    def load(**kwargs):
        calls.append(kwargs)
        return watch

    monkeypatch.setattr(lw, "load_watch", load)
    monkeypatch.setattr(retro, "_berlin_today", lambda: real_today)
    return calls


def _part11(messages):
    return [message for message in messages if "Live loss watch" in message]


def test_part_11_posts_on_sunday_only(tmp_path, monkeypatch):
    calls = _isolate(monkeypatch, tmp_path, _watch(), real_today=MONDAY)
    assert _part11(retro.build_daily_retrospective([], today=MONDAY)) == []
    assert calls == []                              # no bootstrap on a weekday

    calls = _isolate(monkeypatch, tmp_path, _watch())
    assert len(_part11(retro.build_daily_retrospective([], today=SUNDAY))) >= 3
    assert len(calls) == 1


def test_part_11_always_splits_into_fenced_chunks_under_the_discord_limit():
    messages = retro._format_live_loss_watch(_watch())
    tables = [message for message in messages if "```" in message]
    assert len(tables) >= 2
    assert "(part 1/" in tables[0]
    assert all(len(message) < 2000 for message in messages)
    assert all(table.count("```") == 2 for table in tables)
    body = "\n".join(tables)
    for name in _STRATEGIES:
        assert name in body
    assert "confluence pooled" in body


def test_rows_keep_the_rule_order_and_the_alert_row_is_marked():
    messages = retro._format_live_loss_watch(_watch())
    first_table_lines = messages[0].splitlines()
    first_row = first_table_lines[4]                # title, ```, header, separator, row 1
    assert first_row.startswith("confluence 4w")
    assert "LOSS" in first_row
    tables = [message for message in messages if "```" in message]
    assert sum("LOSS" in line for table in tables for line in table.splitlines()) == 1
    assert "1 of 22 row(s) flagged" in messages[0]


def test_notes_state_meaning_label_population_counts_and_caveat():
    watch = _watch()
    notes = retro._format_live_loss_watch(watch)[-1]
    assert calibration.LIVE_LOSS_MEANING in notes
    assert calibration.REGISTRY_CONTEXT_LABEL in notes
    assert calibration.LIVE_LOSS_LOOKS_CAVEAT in notes
    assert calibration.EXPR_WATCH_START.isoformat() in notes
    for key in calibration.WATCH_COUNT_KEYS:
        assert f"{key} {watch['counts'][key]}" in notes


def test_empty_watch_still_posts_the_notes():
    messages = retro._format_live_loss_watch(
        {"rows": [], "counts": {key: 0 for key in calibration.WATCH_COUNT_KEYS}})
    assert len(messages) == 1
    assert "0 of 0 row(s) flagged" in messages[0]


def test_a_raising_loader_lands_in_failed_sections(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path, _watch())

    def boom(**kwargs):
        raise RuntimeError("bootstrap exploded")

    monkeypatch.setattr(lw, "load_watch", boom)
    messages = retro.build_daily_retrospective([], today=SUNDAY)
    assert _part11(messages) == []
    assert "live loss watch" in messages[-1]
    assert "failed to build" in messages[-1]


def test_sunday_digest_for_the_real_today_clears_recovered_latches(tmp_path, monkeypatch):
    watch = _watch()
    alert_row, recovered_row = watch["rows"][0], watch["rows"][1]
    for row in (alert_row, recovered_row):
        lw.mark_latched(row, dt.date(2026, 10, 14))
    _isolate(monkeypatch, tmp_path, watch, real_today=SUNDAY)

    retro.build_daily_retrospective([], today=SUNDAY)

    assert lw.is_latched(alert_row) is True          # still below zero
    assert lw.is_latched(recovered_row) is False     # bound back at >= 0


def test_backdated_sunday_digest_reports_but_never_clears(tmp_path, monkeypatch):
    watch = _watch()
    recovered_row = watch["rows"][1]
    lw.mark_latched(recovered_row, dt.date(2026, 10, 14))
    _isolate(monkeypatch, tmp_path, watch, real_today=LATER)

    messages = retro.build_daily_retrospective([], today=SUNDAY)

    assert _part11(messages)                          # Deviation 4: still shown
    assert lw.is_latched(recovered_row) is True
