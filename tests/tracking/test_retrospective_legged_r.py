"""v189 D1: the daily recap's R is `metrics.r_multiple`, so a scaled-out
trade counts its TP1 leg instead of pricing only the runner's exit."""
import datetime as dt

from swingbot.core.presentation import tokens
from swingbot.core.tracking import retrospective as retro
from tests.analytics.test_golden_partial_trade_metrics import closed_case, golden_closed_trade

MONDAY = dt.date(2026, 10, 19)                 # a weekday: no Sunday-only parts
CLOSED_AT = "2026-10-19T18:00:00+00:00"        # 20:00 Berlin, same day


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(retro, "_berlin_today", lambda: MONDAY)


def _avg_r_line(messages) -> str:
    text = "\n".join(messages)
    return next(line for line in text.splitlines() if line.startswith("**Avg R-multiple:**"))


def test_the_private_copy_is_gone():
    assert not hasattr(retro, "_r_multiple")


def test_scaled_out_trade_is_blended_not_runner_only(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    trade = golden_closed_trade(closed_case("manual"), closed_at=CLOSED_AT)
    # TP1 +2R on half + runner +3R on half = 2.5R. The runner-only figure was 3.0R.
    messages = retro.build_daily_retrospective([trade], today=MONDAY)
    assert _avg_r_line(messages) == f"**Avg R-multiple:** {tokens.fmt_r(2.5)}"


def test_gap_loss_is_the_small_net_not_the_runner_gap(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    trade = golden_closed_trade(closed_case("gap"), closed_at=CLOSED_AT)
    # Net -0.2R; pricing the runner's 88 exit alone read -2.4R.
    messages = retro.build_daily_retrospective([trade], today=MONDAY)
    assert _avg_r_line(messages) == f"**Avg R-multiple:** {tokens.fmt_r(-0.2)}"


def test_single_exit_trade_is_unchanged(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    trade = {"id": "single", "ticker": "LOSS", "direction": "bullish", "status": "loss",
             "entry": 100.0, "stop_loss": 95.0, "exit_price": 96.5, "shares": 10,
             "opened_at": "2026-10-16T14:00:00+00:00", "closed_at": CLOSED_AT,
             "realized_pnl_amount": -35.0, "strategy": "S/R Confluence",
             "target_sources": [], "stop_sources": []}
    messages = retro.build_daily_retrospective([trade], today=MONDAY)
    assert _avg_r_line(messages) == f"**Avg R-multiple:** {tokens.fmt_r(-0.7)}"
