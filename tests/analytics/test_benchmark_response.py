"""v208 V208-10b: stats, vs, capture, daily rows, Today card, status, the response."""
from datetime import date, datetime, timedelta, timezone
from itertools import count

import pytest

from swingbot.core.analytics import benchmark as bm
from swingbot.core.analytics import benchmark_view as bv
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar

UTC = timezone.utc
THU, FRI = date(2026, 11, 5), date(2026, 11, 6)
SESS = nyse_calendar().sessions(date(2026, 6, 1), THU)[-71:]      # 71 closes -> 70 returns
PRE_FRI = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)                # 07:00 ET
OPEN_FRI = datetime(2026, 11, 6, 15, 0, tzinfo=UTC)               # 10:00 ET
CLOSED_FRI = datetime(2026, 11, 6, 22, 0, tzinfo=UTC)             # 17:00 ET
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")
_ids = count(1)


def _idx(i):
    return 0.01 if i % 2 else -0.008             # 35 up / 35 down sessions over i = 1..70


def _bot(i):
    return 0.5 * _idx(i) + 0.0004 * (i % 3)


def _row(day, equity, *, hh=15, mm=55, realized=10_000.0, notional=None):
    at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(UTC)
    row = {"id": next(_ids), "at": at, "equity": equity, "realized_balance": realized,
           "unrealized_pnl": equity - realized, "open_n": 1, "skipped_n": 0, "source": "live", "kind": "point"}
    if notional is not None:
        row["open_notional"] = notional
    return row


def _book(skip=(), jump_at=None, notional=None):
    rows, equity, realized = [], 10_000.0, 10_000.0
    for i, day in enumerate(SESS):
        equity *= 1 + (_bot(i) if i else 0.0)
        if i == jump_at:                          # a base_balance edit: no leg explains it
            realized += 500.0
            equity += 500.0
        if i not in skip:
            rows.append(_row(day, round(equity, 2), realized=realized, notional=notional))
    return rows


def _bar(symbol, day, pct, final=True):
    return {"symbol": symbol, "session": day, "close": None, "adj_close": None, "day_pct": pct,
            "source_symbol": symbol, "final": final,
            "as_of": OPEN_FRI if day == FRI else datetime(day.year, day.month, day.day, 20, tzinfo=UTC)}


def _bars(fri=True, final_fri=False):
    bars = [_bar(s, d, _idx(i)) for s in SYMBOLS for i, d in enumerate(SESS)]
    return bars + ([_bar(s, FRI, 0.004, final_fri) for s in SYMBOLS] if fri else [])


def _inputs(rows=None, bars=None, now=OPEN_FRI, refresher_on=True, currency="USD", mixed=(), sessions=None):
    return bv.BenchmarkInputs(rows=_book() if rows is None else rows, legs=[],
                              bars=_bars() if bars is None else bars,
                              sessions=[*SESS, FRI] if sessions is None else sessions, now=now,
                              account_currency=currency, mixed_tickers=list(mixed), refresher_on=refresher_on)


def _body(inputs, start=None, end=None, capture="SPY"):
    return bv.build_benchmark(inputs, start=start, end=end, capture=capture)


def _day(body, i):
    return next(r for r in body["daily"] if r["date"] == SESS[i].isoformat())


def test_the_response_carries_every_contract_key():
    body = _body(_inputs())
    assert set(body) == {"range", "as_of", "session_state", "account_currency", "mixed_tickers",
                         "benchmarks_status", "benchmarks_last_session", "today", "series", "markers",
                         "exposure", "stats", "vs", "capture", "daily"}
    assert body["range"] == {"from": SESS[0].isoformat(), "to": THU.isoformat(),
                             "live_since": SESS[0].isoformat(), "sessions_n": 71,
                             "clamped": False, "is_all": True}
    assert (body["as_of"], body["session_state"]) == (OPEN_FRI.isoformat(), "open")
    assert set(body["stats"]) == set(bv.SERIES_KEYS) and set(body["vs"]) == set(SYMBOLS)
    assert set(body["stats"]["bot_account"]) == {"total_pct", "max_dd_pct", "sharpe", "money_dd",
                                                 "losing_streak", "approx_share"}
    assert set(body["stats"]["SPY"]) == {"total_pct", "max_dd_pct", "sharpe"}
    assert body["stats"]["bot_account"]["total_pct"]["n"] == 70
    assert body["stats"]["bot_account"]["approx_share"] is None
    assert body["stats"]["bot_account"]["money_dd"]["value"] <= 0


def test_beta_alpha_lead_and_the_headline_on_the_all_range():
    body = _body(_inputs())
    spy = body["vs"]["SPY"]
    assert set(spy) == {"lead_pp", "beta", "alpha"}
    assert (spy["beta"]["n"], spy["beta"]["reason"]) == (70, None)
    assert spy["beta"]["value"] == pytest.approx(0.5, abs=0.05) and spy["beta"]["se"] is not None
    assert spy["alpha"]["n"] == 70 and spy["alpha"]["value"] is not None
    assert spy["alpha"]["headline"] is True and body["vs"]["QQQ"]["alpha"]["headline"] is False
    lead = body["stats"]["bot_account"]["total_pct"]["value"] - body["stats"]["SPY"]["total_pct"]["value"]
    assert spy["lead_pp"]["value"] == pytest.approx(lead, abs=1e-3)


def test_short_ranges_keep_n_and_say_why():
    body = _body(_inputs(), start=SESS[-19])
    beta, alpha = body["vs"]["SPY"]["beta"], body["vs"]["SPY"]["alpha"]
    assert (beta["value"], beta["n"], beta["reason"]) == (None, 19, "needs ≥ 20 sessions")
    assert (alpha["value"], alpha["reason"], alpha["headline"]) == (None, "needs ≥ 60 sessions", False)
    assert body["stats"]["bot_account"]["sharpe"] == {"value": None, "n": 19, "reason": "needs ≥ 20 sessions"}
    assert body["capture"]["up_pct"]["value"] is None
    assert body["capture"]["up_pct"]["reason"] == bm.CAPTURE_REASON
    assert (body["range"]["is_all"], body["range"]["sessions_n"]) == (False, 19)


def test_a_missing_session_counts_toward_total_but_never_toward_pairs():
    body = _body(_inputs(rows=_book(skip={40})))
    assert body["stats"]["bot_account"]["total_pct"]["n"] == 69
    assert body["vs"]["SPY"]["beta"]["n"] == 68
    gap, span = _day(body, 40), _day(body, 41)
    assert gap["missing"] and gap["lines"]["bot_account"] is None and gap["beat"] is None
    assert gap["lines"]["SPY"] == pytest.approx(bv.pct(_idx(40)))      # the index cell still shows
    assert span["span"] == 2 and span["beat"] is None and span["lines"]["bot_account"] is not None


def test_a_base_balance_session_is_left_out_of_every_stat():
    body = _body(_inputs(rows=_book(jump_at=30)))
    assert body["stats"]["bot_account"]["total_pct"]["n"] == 69
    assert body["vs"]["SPY"]["beta"]["n"] == 69
    assert body["markers"] == [{"date": SESS[30].isoformat(), "kind": "base_balance"}]
    assert _day(body, 30)["lines"]["bot_account"] is None


def test_capture_and_beat_use_the_selected_index():
    cap = _body(_inputs(), capture="QQQ")["capture"]
    assert cap["index"] == "QQQ" and (cap["up_n"], cap["down_n"]) == (35, 35)
    assert cap["up_pct"]["reason"] is None and cap["up_pct"]["value"] == pytest.approx(50.0, abs=5.0)
    assert cap["ratio"]["value"] == pytest.approx(cap["up_pct"]["value"] / cap["down_pct"]["value"], rel=1e-3)
    assert cap["beat"] == {"up_days": 35, "up_beat": 0, "down_days": 35, "down_beat": 35}


def test_daily_rows_are_newest_first_and_complete():
    daily = _body(_inputs())["daily"]
    assert [r["date"] for r in daily] == [d.isoformat() for d in reversed(SESS)]
    assert set(daily[0]) == {"date", "lines", "exposure_pct", "open_n", "beat", "span", "missing"}
    assert set(daily[0]["lines"]) == set(bv.SERIES_KEYS)
    assert daily[-1]["lines"]["bot_account"] is None        # the first live session has no prior close


def test_deployed_stats_carry_the_approximated_share():
    rows = _book(notional=3_000.0)
    for row in rows[:36]:
        row["open_notional_approx"] = True
    stats = _body(_inputs(rows=rows))["stats"]["bot_deployed"]
    assert stats["total_pct"]["n"] == 70
    # sessions 1..36 (36 via its approx previous close); session 0 has no previous close -> not approx
    assert stats["approx_share"] == pytest.approx(36 / 71 * 100, abs=1e-3)
    assert stats["money_dd"] == {"value": None, "n": 70, "reason": "account line only"}


def test_today_while_open_with_a_sample():
    prev = _book()[-1]["equity"]
    today = _body(_inputs(rows=_book() + [_row(FRI, 10_100.0, hh=10, mm=0)]))["today"]
    assert (today["session"], today["final"]) == ("2026-11-06", False)
    assert today["lines"]["bot_account"] == {"pct": pytest.approx(bv.pct(10_100.0 / prev - 1)), "final": False}
    assert today["lines"]["SPY"] == {"pct": 0.4, "final": False}


def test_today_while_open_without_a_sample_is_a_dash_never_zero():
    today = _body(_inputs())["today"]
    assert today["lines"]["bot_account"] == {"pct": None, "final": False}
    assert today["lines"]["SPY"]["pct"] == 0.4


def test_before_the_open_the_card_is_the_last_completed_session_and_final():
    today = _body(_inputs(now=PRE_FRI, bars=_bars(fri=False)))["today"]
    assert (today["session"], today["final"]) == (THU.isoformat(), True)
    assert today["lines"]["bot_account"]["final"] is True
    assert today["lines"]["SPY"] == {"pct": bv.pct(_idx(70)), "final": True}


def test_after_the_close_with_final_bars_today_is_final_and_joins_the_series():
    body = _body(_inputs(rows=_book() + [_row(FRI, 10_100.0)], now=CLOSED_FRI, bars=_bars(final_fri=True)))
    assert (body["today"]["session"], body["today"]["final"]) == ("2026-11-06", True)
    assert body["daily"][0]["date"] == "2026-11-06" and body["range"]["to"] == "2026-11-06"


def test_benchmark_status_empty_stale_ok():
    empty = _body(_inputs(bars=[], refresher_on=False))
    assert (empty["benchmarks_status"], empty["benchmarks_last_session"]) == ("empty", None)
    assert empty["stats"]["SPY"]["total_pct"] == {"value": None, "n": 0, "reason": None}
    ok = _body(_inputs())
    assert (ok["benchmarks_status"], ok["benchmarks_last_session"]) == ("ok", THU.isoformat())
    behind = [b for b in _bars() if b["session"] != THU]
    stale = _body(_inputs(bars=behind, refresher_on=False))
    assert (stale["benchmarks_status"], stale["benchmarks_last_session"]) == ("stale", SESS[-2].isoformat())
    assert _body(_inputs(bars=behind))["benchmarks_status"] == "ok"        # refresher on: catching up


def test_no_live_book_is_an_empty_response_not_zeros():
    body = _body(_inputs(rows=[], bars=[], sessions=[]))
    assert body["range"] == {"from": None, "to": None, "live_since": None, "sessions_n": 0,
                             "clamped": False, "is_all": True}
    assert body["stats"]["bot_account"]["total_pct"] == {"value": None, "n": 0, "reason": None}
    assert body["daily"] == [] and body["today"] == {"session": None, "final": False, "as_of": None, "lines": {}}


def test_banner_inputs_pass_through_and_capture_is_checked():
    body = _body(_inputs(currency="EUR", mixed=("SAP.DE",)))
    assert (body["account_currency"], body["mixed_tickers"]) == ("EUR", ["SAP.DE"])
    with pytest.raises(ValueError, match="capture"):
        _body(_inputs(), capture="IWM")


def test_money_drawdown_excludes_balance_jumps_and_uses_the_range_anchor():
    days = SESS[:4]
    rows = [_row(days[0], 100), _row(days[1], 90),
            _row(days[2], 290, realized=10_200), _row(days[3], 261, realized=10_200)]
    body = _body(_inputs(rows=rows, sessions=days), start=days[1])
    stats = body['stats']['bot_account']
    assert stats['money_dd'] == {'value': -19.0, 'n': 2, 'reason': None}
    assert stats['total_pct'] == {'value': -19.0, 'n': 2, 'reason': None}
    assert stats['max_dd_pct']['value'] == -19.0
    assert stats['losing_streak'] == 2


def test_index_stats_skip_first_session_but_daily_shows_its_own_return():
    days = SESS[:3]
    bars = [_bar('SPY', days[0], 0.9), _bar('SPY', days[1], 0.1),
            _bar('SPY', days[2], -0.1)]
    body = _body(_inputs(rows=_book()[:3], bars=bars, sessions=days))
    assert body['stats']['SPY']['total_pct'] == {'value': -1.0, 'n': 2, 'reason': None}
    assert body['daily'][-1]['lines']['SPY'] == 90.0
    assert body['vs']['QQQ']['lead_pp']['value'] is None
    assert body['vs']['QQQ']['beta']['n'] == 0


def test_selected_capture_and_beat_follow_distinct_index_returns():
    bars = _bars()
    for bar in bars:
        if bar['symbol'] == 'QQQ':
            bar['day_pct'] *= -1
    body = _body(_inputs(bars=bars), capture='QQQ')
    assert body['capture']['beat'] == {'up_days': 35, 'up_beat': 0, 'down_days': 35, 'down_beat': 35}
    assert _day(body, 69)['beat'] is True
    assert _day(body, 70)['beat'] is False
    assert body['capture']['up_pct']['value'] < 0


def test_missing_benchmark_bar_is_excluded_only_from_its_pairs():
    bars = [b for b in _bars() if not (b['symbol'] == 'SPY' and b['session'] == SESS[20])]
    body = _body(_inputs(bars=bars))
    assert body['vs']['SPY']['beta']['n'] == 69
    assert body['vs']['QQQ']['beta']['n'] == 70
    assert _day(body, 20)['beat'] is None
    assert _day(body, 20)['lines']['SPY'] is None


def test_today_first_sample_or_zero_prior_close_has_no_account_return():
    first = _body(_inputs(rows=[_row(FRI, 100)], sessions=[FRI], bars=[]))['today']
    assert first['lines']['bot_account'] == {'pct': None, 'final': False}
    assert first['lines']['SPY'] == {'pct': None, 'final': False}
    zero = _body(_inputs(rows=[_row(THU, 0), _row(FRI, 100)], sessions=[THU, FRI]))['today']
    assert zero['lines']['bot_account']['pct'] is None


def test_empty_range_keeps_today_but_no_money_anchor_or_approx_share():
    body = _body(_inputs(), start=FRI)
    assert body['daily'] == []
    assert body['stats']['bot_account']['money_dd']['value'] is None
    assert body['stats']['bot_deployed']['approx_share'] is None
    assert body['today']['session'] == FRI.isoformat()


@pytest.mark.parametrize('hour,minute,want', [(17, 59, date(2026, 11, 25)), (18, 0, date(2026, 11, 27))])
def test_last_closed_session_uses_the_official_half_day_close(hour, minute, want):
    sessions = [date(2026, 11, 27), date(2026, 11, 25)]
    assert bv.last_closed_session(sessions, datetime(2026, 11, 27, hour, minute, tzinfo=UTC)) == want
    assert bv.last_closed_session([], OPEN_FRI) is None


@pytest.mark.parametrize('refresher_on,want', [(False, 'stale'), (True, 'ok')])
def test_provisional_only_benchmark_status_keeps_no_final_session(refresher_on, want):
    assert bv.benchmarks_status([_bar('SPY', FRI, 0.01, False)], THU, refresher_on) == (want, None)
    assert bv.benchmarks_status([_bar('SPY', THU, 0.01)], None, refresher_on) == (('ok' if refresher_on else 'stale'), None)


def test_spanning_daily_row_compounds_index_over_the_same_sessions():
    body = _body(_inputs(rows=_book(skip={40})))
    row = _day(body, 41)
    expected = (1 + _idx(40)) * (1 + _idx(41)) - 1
    assert row["span"] == 2
    assert row["lines"]["SPY"] == pytest.approx(bv.pct(expected))


def test_base_balance_break_excludes_deployed_return_from_stats_and_daily():
    body = _body(_inputs(rows=_book(jump_at=30, notional=3000)))
    assert _day(body, 30)["lines"]["bot_deployed"] is None
    assert body["stats"]["bot_deployed"]["total_pct"]["n"] == 69


def test_today_hides_returns_across_a_base_balance_change_even_outside_chart_range():
    rows = [_row(THU, 10000), _row(FRI, 10600, hh=10, mm=0, realized=10500, notional=5000)]
    body = _body(_inputs(rows=rows, sessions=[THU, FRI]), start=FRI)
    assert body["today"]["lines"]["bot_account"]["pct"] is None
    assert body["today"]["lines"]["bot_deployed"]["pct"] is None


def test_today_as_of_is_oldest_displayed_source_not_request_time():
    rows = [_row(THU, 10000), _row(FRI, 10100, hh=9, mm=50)]
    bars = _bars()
    stale = datetime(2026, 11, 6, 14, 40, tzinfo=UTC)
    next(b for b in bars if b["symbol"] == "SPY" and b["session"] == FRI)["as_of"] = stale
    body = _body(_inputs(rows=rows, bars=bars, sessions=[THU, FRI]))
    assert body["today"]["as_of"] == stale.isoformat()


def test_today_is_unchanged_when_future_account_samples_are_added():
    rows = [_row(THU, 10000), _row(FRI, 10100, hh=9, mm=50)]
    future = _row(FRI, 12000, hh=15, mm=0, realized=12000)
    before = _body(_inputs(rows=rows, sessions=[THU, FRI]))["today"]
    after = _body(_inputs(rows=rows + [future], sessions=[THU, FRI]))["today"]
    assert after == before


def test_pre_session_card_is_not_final_when_a_prior_index_bar_is_missing():
    bars = [b for b in _bars(fri=False) if not (b["symbol"] == "QQQ" and b["session"] == THU)]
    today = _body(_inputs(now=PRE_FRI, bars=bars))["today"]
    assert today["session"] == THU.isoformat()
    assert today["final"] is False


def test_today_withholds_bot_returns_when_the_immediately_prior_session_is_missing():
    days = [SESS[-3], SESS[-2], THU, FRI]
    rows = [_row(days[0], 10000, notional=5000), _row(FRI, 10100, hh=10, mm=0, notional=5000)]
    today = _body(_inputs(rows=rows, sessions=days))["today"]
    assert today["lines"]["bot_account"]["pct"] is None
    assert today["lines"]["bot_deployed"]["pct"] is None


def test_today_excludes_a_bar_not_yet_available_at_request_time():
    bars = _bars()
    future = next(b for b in bars if b["symbol"] == "SPY" and b["session"] == FRI)
    future["as_of"] = datetime(2026, 11, 6, 16, 0, tzinfo=UTC)
    without = [bar for bar in bars if bar is not future]
    assert _body(_inputs(bars=bars))["today"] == _body(_inputs(bars=without))["today"]


def test_incomplete_account_sample_is_missing_not_a_fabricated_close():
    rows = _book(notional=3000)
    rows[40]["skipped_n"] = 1
    body = _body(_inputs(rows=rows))
    assert _day(body, 40)["missing"] is True
    assert _day(body, 40)["lines"]["bot_account"] is None
    assert _day(body, 40)["open_n"] is None
    assert _day(body, 41)["span"] == 2


def test_incomplete_today_sample_does_not_produce_bot_returns():
    rows = [_row(THU, 10000, notional=5000), _row(FRI, 10100, hh=10, mm=0, notional=5000)]
    rows[-1]["skipped_n"] = 1
    today = _body(_inputs(rows=rows, sessions=[THU, FRI]))["today"]
    assert today["lines"]["bot_account"]["pct"] is None
    assert today["lines"]["bot_deployed"]["pct"] is None


def test_status_requires_each_index_to_reach_the_latest_closed_session():
    bars = [b for b in _bars(fri=False) if not (b['symbol'] == 'QQQ' and b['session'] == THU)]
    status, last = bv.benchmarks_status(bars, THU, refresher_on=False)
    assert status == 'stale' and last == SESS[-2]


def test_incomplete_intraday_point_marks_the_session_unavailable():
    earlier = _row(THU, 10000, hh=10, mm=0, notional=9000)
    earlier['skipped_n'] = 1
    rows = [_row(SESS[-2], 10000, notional=5000), earlier, _row(THU, 10000, notional=5000)]
    body = _body(_inputs(rows=rows, sessions=[SESS[-2], THU]))
    exposure = next(item for item in body['exposure'] if item['date'] == THU.isoformat())
    assert exposure['pct'] is None
    assert _day(body, 70)['missing'] is True


def test_missing_session_has_no_open_count_but_a_valid_zero_remains_zero():
    rows = _book(skip={40})
    rows[41]['open_n'] = 0
    body = _body(_inputs(rows=rows))
    assert _day(body, 40)['open_n'] is None
    assert _day(body, 42)['open_n'] == 0
    exposure = {item['date']: item for item in body['exposure']}
    assert exposure[SESS[40].isoformat()]['open_n'] is None


def test_premarket_request_excludes_historical_bars_recorded_after_its_cutoff():
    bars = _bars(fri=False)
    for bar in bars:
        bar['as_of'] = PRE_FRI - timedelta(hours=1)
    future = next(b for b in bars if b['symbol'] == 'QQQ' and b['session'] == THU)
    future['as_of'] = PRE_FRI + timedelta(minutes=1)
    without = [bar for bar in bars if bar is not future]
    assert _body(_inputs(bars=bars, now=PRE_FRI)) == _body(_inputs(bars=without, now=PRE_FRI))


def test_deployed_return_after_a_gap_is_withheld_without_a_complete_peak():
    body = _body(_inputs(rows=_book(skip={40}, notional=5000)))
    assert _day(body, 41)['span'] == 2
    assert _day(body, 41)['lines']['bot_deployed'] is None
    assert body['stats']['bot_deployed']['total_pct']['n'] == 68


@pytest.mark.parametrize('session,final', [(THU, True), (FRI, False)])
def test_request_excludes_bars_persisted_after_its_cutoff(session, final):
    bars = _bars()
    target = next(b for b in bars if b['symbol'] == 'SPY' and b['session'] == session)
    target['final'] = final
    target['as_of'] = OPEN_FRI - timedelta(minutes=1)
    target['updated_at'] = OPEN_FRI + timedelta(seconds=1)
    without = [bar for bar in bars if bar is not target]
    assert _body(_inputs(bars=bars)) == _body(_inputs(bars=without))
