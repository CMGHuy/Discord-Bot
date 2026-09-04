from swingbot.core.tracking.retrospective import (summarize_runner_outcomes,
                                         summarize_badge_split)


def _v2(reason, badge="VALIDATED"):
    return {"status": "win" if reason.startswith("tp1_") else "loss",
            "plan_id": "p", "badge": badge,
            "legs": [{"fraction": 0.5, "exit_price": 0, "r": 0.35,
                      "reason": "tp1"},
                     {"fraction": 0.5, "exit_price": 0, "r": 0.0,
                      "reason": reason}]}


def test_runner_outcomes_line():
    closed = [_v2("tp1_runner_tp2"), _v2("tp1_runner_tp2"),
              _v2("tp1_runner_trail"), _v2("tp1_runner_be")]
    assert summarize_runner_outcomes(closed) == "runners: 2 tp2, 1 trail, 1 be"


def test_no_v2_trades_no_line():
    assert summarize_runner_outcomes([{"status": "win"}]) is None


def test_badge_split_line():
    closed = [_v2("tp1_runner_be"), _v2("tp1_runner_be", badge="WEAK"),
              {"status": "loss", "badge": "WEAK"}]
    line = summarize_badge_split(closed)
    assert "VALIDATED" in line and "WEAK" in line and "1W" in line


def test_load_history_logs_on_corrupt_file(tmp_path, monkeypatch, caplog):
    from swingbot.core.tracking import retrospective as retro

    bad_path = tmp_path / "history.json"
    bad_path.write_text("{not valid json")
    monkeypatch.setattr(retro, "_HISTORY_PATH", str(bad_path))

    with caplog.at_level("WARNING", logger="swing-bot.retrospective"):
        result = retro._load_history()

    assert result == []
    assert any("history" in r.message.lower() for r in caplog.records)


def test_to_berlin_logs_on_unparseable_timestamp(caplog):
    from swingbot.core.tracking import retrospective as retro

    with caplog.at_level("WARNING", logger="swing-bot.retrospective"):
        result = retro._to_berlin("not-a-timestamp")

    assert result is None
    assert any("timestamp" in r.message.lower() or "berlin" in r.message.lower()
               for r in caplog.records)


import datetime as dt


def _manual_close(ticker, level, closed_at):
    """A trade closed manually -- status is neither 'win' nor 'loss', so it
    counts toward level_calibration()'s n but contributes nothing to
    metrics.win_rate(), which then returns None."""
    return {"ticker": ticker, "status": "closed", "confidence_level": level,
            "opened_at": "2026-09-03T08:00:00+00:00", "closed_at": closed_at,
            "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 101.0}


def test_retrospective_survives_a_level_with_only_manual_closes(tmp_path, monkeypatch):
    from swingbot.core.tracking import retrospective as retro

    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))
    trades = [_manual_close("AAPL", 3, "2026-09-03T18:00:00+00:00")]

    messages = retro.build_daily_retrospective(trades, today=dt.date(2026, 9, 3))

    joined = "\n".join(messages)
    assert "Level 3" in joined
    assert "n/a" in joined          # rendered, not dropped and not "0%"
    assert "0% WR" not in joined    # None must never render as zero


def test_one_failing_section_does_not_lose_the_whole_report(tmp_path, monkeypatch, caplog):
    """A raise inside one part must cost that part only. Before isolation,
    it aborted all ten parts and the report never posted."""
    from swingbot.core.tracking import retrospective as retro

    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))

    def _boom(*a, **kw):
        raise RuntimeError("calibration exploded")

    monkeypatch.setattr(retro.calibration, "level_calibration", _boom)
    trades = [_manual_close("AAPL", 3, "2026-09-03T18:00:00+00:00")]

    with caplog.at_level("ERROR"):
        messages = retro.build_daily_retrospective(trades, today=dt.date(2026, 9, 3))

    joined = "\n".join(messages)
    assert "Daily Retrospective" in joined          # Part 1 still posted
    assert "calibration" in joined.lower()          # the degraded notice names it
    assert any("calibration" in r.message for r in caplog.records)


def test_weekly_risk_report_failure_still_triggers_degraded_notice(tmp_path, monkeypatch, caplog):
    """Part 8 (weekly risk report) has its own finer-grained inner
    try/except that logs and swallows the exception. Before this fix, that
    inner handler never told the outer _section() wrapper anything failed,
    so the degraded-report notice never fired for a Sunday whose weekly
    risk report throws."""
    import swingbot.commands.growth as growth
    from swingbot.core.tracking import retrospective as retro

    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))

    def _boom(*a, **kw):
        raise RuntimeError("weekly risk report exploded")

    monkeypatch.setattr(growth, "weekly_risk_report", _boom)
    trades = [_manual_close("AAPL", 3, "2026-09-03T18:00:00+00:00")]

    with caplog.at_level("ERROR"):
        # 2026-09-06 is a Sunday (weekday() == 6), so Part 8 runs.
        messages = retro.build_daily_retrospective(trades, today=dt.date(2026, 9, 6))

    joined = "\n".join(messages)
    assert "Daily Retrospective" in joined          # Part 1 still posted
    assert "weekly risk" in joined.lower()          # the degraded notice names it
    assert any("weekly risk" in r.message for r in caplog.records)
