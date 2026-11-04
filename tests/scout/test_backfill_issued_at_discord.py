"""v200 V200-5: the Discord issue-time backfill dry run -- embed parsing, the
exact-then-one-to-one match, the summary. Pure functions only: no Discord, no DB."""
import datetime as dt
import importlib.util
import io
import re
from pathlib import Path

from swingbot.core.market.strategy_types import HORIZONS

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "backfill_issued_at_discord.py"
_spec = importlib.util.spec_from_file_location("backfill_issued_at_discord", SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)

PID_A = "abcd1234-0000-4000-8000-000000000001"
PID_B = "ef567890-0000-4000-8000-000000000002"
LABEL_2W = HORIZONS["2w"]["label"]


def _msg(mid, posted, title, *, setup="RSI", label=LABEL_2W, url=None, footer=None):
    embed = {"title": title, "fields": [{"name": "Setup", "value": setup, "inline": True},
                                        {"name": "Swing type", "value": label, "inline": True}]}
    if url:
        embed["url"] = url
    if footer:
        embed["footer"] = {"text": footer}
    return {"id": mid, "created_at": posted, "embeds": [embed]}


def _plan(pid=PID_A, ticker="AAPL", created=dt.date(2026, 8, 3), **kw):
    base = dict(plan_id=pid, ticker=ticker, direction="bullish", strategy="RSI",
                horizon_key="2w", created_date=created)
    base.update(kw)
    return bf.PlanKey(**base)


def _alert(mid, posted, *, plan_id=None, ticker="AAPL", direction="bullish", strategy="RSI",
           horizon_key="2w"):
    return bf.AlertKey(message_id=mid, posted_at=dt.datetime.fromisoformat(posted), plan_id=plan_id,
                       ticker=ticker, direction=direction, strategy=strategy, horizon_key=horizon_key)


def test_alert_key_reads_the_august_layout():
    key = bf.alert_key(_msg("1", "2026-08-03T21:10:00+00:00", "5️⃣ ✅ VALIDATED · 🟢 BULLISH — AAPL",
                            setup="RSI  +1 more horizon(s)"))
    assert (key.ticker, key.direction, key.strategy, key.horizon_key, key.plan_id) == \
        ("AAPL", "bullish", "RSI", "2w", None)
    assert key.posted_at == dt.datetime(2026, 8, 3, 21, 10, tzinfo=dt.timezone.utc)


def test_alert_key_reads_the_kinds_layout_and_the_full_id_from_the_url():
    key = bf.alert_key(_msg("2", "2026-10-01T13:31:00+00:00", "🆕 ▼ SHORT MSFT · ALERT · Lv4 ⭐",
                            url=f"https://bomeo-capital.com/plans/{PID_A}",
                            footer="Not financial advice · plan abcd1234"))
    assert (key.ticker, key.direction, key.plan_id) == ("MSFT", "bearish", PID_A)


def test_alert_key_falls_back_to_the_footer_prefix():
    key = bf.alert_key(_msg("3", "2026-10-01T13:31:00+00:00", "🆕 ▲ LONG MSFT · ALERT",
                            footer="Not financial advice · plan abcd1234"))
    assert key.plan_id == "abcd1234"


def test_non_alert_messages_are_skipped():
    assert bf.alert_key({"id": "4", "created_at": "2026-08-03T21:10:00+00:00", "embeds": []}) is None
    assert bf.alert_key(_msg("5", "2026-08-03T21:10:00+00:00", "📊 Daily summary")) is None


def test_an_unknown_horizon_label_leaves_the_key_incomplete():
    key = bf.alert_key(_msg("6", "2026-08-03T21:10:00+00:00", "🟢 BULLISH — AAPL", label="weird"))
    assert key.horizon_key is None


def test_a_one_to_one_key_match_is_matched_with_its_lag():
    [row] = bf.match([_plan()], [_alert("m1", "2026-08-03T21:10:00+00:00")])
    assert (row.method, row.message_id, row.plan_candidates, row.message_candidates) == ("key", "m1", 1, 1)
    assert row.issued_at == "2026-08-03T21:10:00+00:00"
    assert row.lag_hours == 17.17                         # 00:00 EDT = 04:00 UTC


def test_the_next_trading_day_matches_across_a_holiday():
    plan = _plan(created=dt.date(2026, 7, 2))             # Thursday; 3 July is the observed holiday
    assert bf.match([plan], [_alert("m1", "2026-07-06T13:30:00+00:00")])[0].method == "key"
    assert bf.match([plan], [_alert("m2", "2026-07-07T13:30:00+00:00")])[0].method == "none"
    assert bf.match([plan], [_alert("m3", "2026-07-01T23:00:00+00:00")])[0].method == "none"


def test_a_two_way_key_collision_leaves_every_plan_unknown():
    rows = bf.match([_plan(PID_A), _plan(PID_B)], [_alert("m1", "2026-08-03T21:10:00+00:00")])
    assert [(r.method, r.plan_candidates, r.message_candidates) for r in rows] == [("none", 2, 1)] * 2
    [row] = bf.match([_plan()], [_alert("m1", "2026-08-03T21:10:00+00:00"),
                                 _alert("m2", "2026-08-04T13:40:00+00:00")])
    assert (row.method, row.message_candidates, row.issued_at, row.lag_hours) == ("none", 2, None, None)


def test_an_exact_plan_id_match_wins_over_key_candidates():
    plans = [_plan(PID_A), _plan(PID_B)]
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id=PID_A),
              _alert("m2", "2026-08-03T21:11:00+00:00")]
    a, b = bf.match(plans, alerts)
    assert (a.method, a.message_id) == ("exact", "m1")
    assert (b.method, b.message_id, b.plan_candidates) == ("key", "m2", 1)


def test_an_eight_character_prefix_resolves_only_when_unique():
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id="abcd1234")]
    assert bf.match([_plan(PID_A)], alerts)[0].method == "exact"
    twin = _plan("abcd1234-ffff-4000-8000-000000000003")
    assert [r.method for r in bf.match([_plan(PID_A), twin], alerts)] == ["none", "none"]


def test_two_exact_messages_for_one_plan_stay_unknown():
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id=PID_A),
              _alert("m2", "2026-08-03T21:12:00+00:00", plan_id=PID_A)]
    [row] = bf.match([_plan()], alerts)
    assert (row.method, row.message_candidates) == ("none", 2)


def test_a_message_carrying_an_unresolved_plan_id_never_key_matches():
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id="99999999")]
    assert bf.match([_plan()], alerts)[0].method == "none"


def test_summary_reports_rate_methods_ambiguity_and_lags():
    rows = [bf.MatchRow("p1", 1, 1, "m1", "2026-08-03T21:10:00+00:00", 17.17, "exact"),
            bf.MatchRow("p2", 1, 1, "m2", "2026-08-04T13:40:00+00:00", 33.67, "key"),
            bf.MatchRow("p3", 2, 1, None, None, None, "none"),
            bf.MatchRow("p4", 0, 0, None, None, None, "none")]
    text = "\n".join(bf.summary_lines(rows, messages_read=9, messages_parsed=7))
    assert "matched 2 of 4 plans (50.0%)" in text
    assert "exact 1, key 1" in text
    assert "ambiguous 1, no candidate 1" in text
    assert "messages read 9, parsed as alerts 7" in text
    assert re.search(r"lag hours: min 17\.17, p25 [\d.]+, median 25\.42, p75 [\d.]+, max 33\.67", text)


def test_the_csv_has_the_pinned_columns():
    buf = io.StringIO()
    bf.write_csv([bf.MatchRow("p1", 1, 1, "m1", "2026-08-03T21:10:00+00:00", 17.17, "key")], buf)
    lines = buf.getvalue().splitlines()
    assert lines[0] == ",".join(bf.CSV_COLUMNS) == \
        "plan_id,plan_candidates,message_candidates,message_id,issued_at,lag_hours,method"
    assert lines[1] == "p1,1,1,m1,2026-08-03T21:10:00+00:00,17.17,key"


def test_the_script_is_read_only_rest_only_and_never_the_mirror():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "config.DISCORD_CHANNEL_TRADES_SIMPLE_ID" not in source
    assert "config.DISCORD_CHANNEL_TRADES_ID" in source
    assert not re.search(r"client\.(connect|start|run)\(", source)      # no gateway session
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP)\b", source)
    assert "READ ONLY" in source
    assert not re.search(r"print\([^)]*TOKEN", source)


def test_alert_key_reads_the_july_layout_with_the_order_word():
    key = bf.alert_key(_msg("7", "2026-07-03T08:45:33+00:00", "⭐ 🔴 SHORT (sell) — AAPL",
                            setup="S/R Confluence"))
    assert (key.ticker, key.direction, key.strategy) == ("AAPL", "bearish", "S/R Confluence")
    weak = bf.alert_key(_msg("8", "2026-07-19T15:20:28+00:00", "🅲 ⚠️ WEAK · ⭐ 🟢 LONG (buy) — GOOGL",
                             footer="Technical signal only -- not financial advice. · plan 0976c5ef"))
    assert (weak.ticker, weak.direction, weak.plan_id) == ("GOOGL", "bullish", "0976c5ef")
