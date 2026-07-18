from swingbot.core.analytics.journal import tags_for


def _base(**kw):
    base = {"direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "take_profit": 110.0,
            "status": "loss", "exit_price": 95.0, "opened_at": "2026-03-01T00:00:00+00:00",
            "closed_at": "2026-03-02T00:00:00+00:00", "badge": "VALIDATED"}
    base.update(kw)
    return base


def test_runner_tag_matches_v2_prefixed_reason():
    t = _base(status="win", exit_price=110.0, legs=[{"fraction": 1.0, "exit_price": 110.0,
                                                       "r": 2.0, "reason": "tp1_runner_trail"}])
    assert "runner_trail" in tags_for(t, None)


def test_legacy_close_reason_also_matches():
    t = _base(status="win", exit_price=110.0, close_reason="auto (runner_be exit)")
    assert "runner_be" in tags_for(t, None)


def test_gap_fill_tag():
    # Loss exit 93.0 is 2.0 below the 95.0 stop -- 2.0/100 = 2% > 0.5% threshold.
    t = _base(status="loss", exit_price=93.0)
    assert "gap_fill" in tags_for(t, None)


def test_near_miss_tp_tag():
    # tp1_r = |110-100|/|100-95| = 2.0; need mfe_r >= 1.6
    t = _base(status="loss", exit_price=95.0)
    assert "near_miss_tp" in tags_for(t, {"mfe_r": 1.8, "mae_r": 1.0, "exit_efficiency": None})
    assert "near_miss_tp" not in tags_for(t, {"mfe_r": 1.0, "mae_r": 1.0, "exit_efficiency": None})


def test_fast_win_and_slow_burn_and_weak_source():
    fast = _base(status="win", exit_price=110.0, opened_at="2026-03-01T00:00:00+00:00",
                 closed_at="2026-03-02T12:00:00+00:00")
    assert "fast_win" in tags_for(fast, None)

    slow = _base(status="loss", opened_at="2026-01-01T00:00:00+00:00",
                closed_at="2026-02-15T00:00:00+00:00")
    assert "slow_burn" in tags_for(slow, None)

    weak = _base(badge="WEAK")
    assert "weak_source" in tags_for(weak, None)


def test_multiple_tags_can_apply_at_once():
    t = _base(status="loss", exit_price=93.0, badge="WEAK")  # gap_fill + weak_source
    tags = tags_for(t, None)
    assert "gap_fill" in tags and "weak_source" in tags
