"""v244 V244-3: the regime shadow report -- live monitoring, never a screen."""
import json

from scripts.reports import regime_shadow_report as rsr


def _trade(direction="bullish", action="would_veto", r=1.0, **extra):
    """A closed trade whose closed_r_multiple is exactly ``r`` (risk = 5)."""
    long = direction == "bullish"
    ctx = {} if action is None else {"bear_regime": "CORRECTION", "regime_action": action}
    trade = {"direction": direction, "entry": 100.0, "stop_loss": 95.0 if long else 105.0,
             "exit_price": 100.0 + (5.0 * r if long else -5.0 * r),
             "status": "closed", "entry_context": ctx}
    trade.update(extra)
    return trade


def _row(rows, direction, action):
    return next(r for r in rows if (r["direction"], r["action"]) == (direction, action))


def test_rows_and_floor_are_the_spec():
    assert rsr.MIN_N == 30
    assert rsr.ROWS == (("LONG", "would_veto"), ("LONG", "caution"), ("LONG", "pullback_watch"),
                        ("LONG", "none"), ("SHORT", "aligned"), ("SHORT", "none"))


def test_every_row_is_present_even_when_empty():
    rows = rsr.summarise([])
    assert [(r["direction"], r["action"]) for r in rows] == list(rsr.ROWS)
    assert all(r["n"] == 0 and r["too_few"] and r["sum_r"] == 0.0 for r in rows)


def test_stats_per_action():
    trades = [_trade(r=2.0)] * 10 + [_trade(r=-1.0)] * 20 + [_trade("bearish", "aligned", 1.5)] * 2
    rows = rsr.summarise(trades)
    veto = _row(rows, "LONG", "would_veto")
    assert (veto["n"], veto["win_rate"], veto["expectancy_r"], veto["sum_r"], veto["too_few"]) == (
        30, 33.33, 0.0, 0.0, False)
    aligned = _row(rows, "SHORT", "aligned")
    assert (aligned["n"], aligned["sum_r"], aligned["too_few"]) == (2, 3.0, True)


def test_a_breakeven_trade_is_not_a_win():
    rows = rsr.summarise([_trade(r=0.0)] * 30)
    assert _row(rows, "LONG", "would_veto")["win_rate"] == 0.0


def test_below_thirty_prints_too_few_instead_of_stats():
    rows = rsr.summarise([_trade("bullish", "caution", 1.0)] * 29)
    assert _row(rows, "LONG", "caution")["too_few"] is True
    line = next(l for l in rsr.render(rows).splitlines() if "caution" in l)
    assert "too few" in line and "29" in line and "ExpR" not in line


def test_thirty_prints_the_stats():
    rows = rsr.summarise([_trade("bullish", "caution", 1.0)] * 30)
    line = next(l for l in rsr.render(rows).splitlines() if "caution" in l)
    assert "too few" not in line and "ExpR +1.00R" in line and "WR 100.00%" in line


def test_unstamped_and_unpriced_trades_are_coverage_not_none():
    trades = [_trade(action=None), _trade("bearish", "pullback_watch"),
              _trade(action="none", exit_price=None), _trade(action="none", r=1.0),
              _trade("sideways", "none")]
    rows = rsr.summarise(trades)
    assert _row(rows, "LONG", "none")["n"] == 1
    assert _row(rows, "SHORT", "none")["n"] == 0
    assert rsr.coverage(trades) == {"closed": 5, "stamped": 2, "no_r": 1}


def test_render_says_it_is_not_a_screen():
    text = rsr.render(rsr.summarise([]), {"closed": 0, "stamped": 0, "no_r": 0})
    assert "live monitoring, not a screen" in text
    assert "closed 0 · stamped 0 · no R 0" in text


def test_no_stamped_trades_yet_prints_every_row_and_says_so():
    trades = [_trade(action=None)] * 4
    text = rsr.render(rsr.summarise(trades), rsr.coverage(trades))
    assert "No stamped trades yet" in text
    assert sum("too few" in line for line in text.splitlines()) == len(rsr.ROWS)
    stamped = [_trade()]
    assert "No stamped trades yet" not in rsr.render(rsr.summarise(stamped), rsr.coverage(stamped))


def test_main_reads_a_trades_file_and_keeps_the_main_ledger(tmp_path, capsys):
    trades = ([_trade(r=1.0)] * 3 + [_trade(r=1.0, ledger="weak")] * 5
              + [_trade(r=1.0, status="open")] * 2)
    path = tmp_path / "trades.json"
    path.write_text(json.dumps(trades), encoding="utf-8")
    assert rsr.main(["--trades", str(path)]) == 0
    assert "closed 3 · stamped 3" in capsys.readouterr().out


def test_main_on_an_empty_trades_file_exits_zero(tmp_path, capsys):
    path = tmp_path / "trades.json"
    path.write_text("[]", encoding="utf-8")
    assert rsr.main(["--trades", str(path)]) == 0
    out = capsys.readouterr().out
    assert "closed 0 · stamped 0 · no R 0" in out and "No stamped trades yet" in out


def test_main_counts_every_closed_status_in_a_trades_file(tmp_path, capsys):
    path = tmp_path / "trades.json"
    path.write_text(json.dumps([_trade(status=s) for s in ("win", "loss", "closed", "open")]),
                    encoding="utf-8")
    assert rsr.main(["--trades", str(path)]) == 0
    assert "closed 3 · stamped 3" in capsys.readouterr().out


def test_the_table_read_keeps_win_and_loss_rows(monkeypatch, capsys):
    from swingbot.core.tracking import performance
    seen = {}

    class FakeLog:
        def get_trades(self, **kwargs):
            seen.update(kwargs)
            return [_trade(status=s) for s in ("win", "loss", "closed", "open")]

    monkeypatch.setattr(performance, "TradeLog", FakeLog)
    assert rsr.main([]) == 0
    assert seen == {"status": None, "limit": None, "ledger": "main"}
    assert "closed 3 · stamped 3" in capsys.readouterr().out
