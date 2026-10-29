from swingbot.commands.growth import portfolio_report


def test_unavailable_controls_do_not_claim_safe_defaults():
    unavailable = {"state": "unavailable", "reason": "source_unavailable", "checked_at": "2026-10-28T00:00:00+00:00"}
    state = {"open_heat": None, "heat_cap": 6.0, "sector_heat": None,
             "clusters": None, "throttle_mult": None, "paused": None,
             "kill": {"on": None}, "growth": {},
             "availability": {key: unavailable for key in
                              ("heat", "sector_heat", "clusters", "throttle", "killswitch")}}
    text = portfolio_report(state)
    assert "heat: unavailable" in text
    assert "killswitch: unavailable" in text
    assert "throttle: unavailable" in text
    assert "sector heat: unavailable" in text
    assert "clusters: unavailable" in text
    assert "x1.00" not in text


def test_partial_sector_coverage_preserves_known_rows():
    state = {"open_heat": 0.6, "heat_cap": 6, "sector_heat": {"Tech": 0.4},
             "clusters": [], "throttle_mult": 0.75, "paused": False,
             "kill": {"on": False}, "unmapped_count": 1,
             "availability": {"sector_heat": {"state": "partial"}}}
    text = portfolio_report(state)
    assert "Tech" in text
    assert "sector heat: partial" in text
    assert "1 unmapped" in text
    assert "x0.75" in text
