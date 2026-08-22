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
