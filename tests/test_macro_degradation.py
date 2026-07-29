"""THE proof: entire internet down + cold caches -> the bot still gets a
full snapshot skeleton (every section None/unknown, stale=True) and
scanning proceeds. G121 extends this proof through the gate.

Adapted per the G43 audit note: the plan monkeypatched
swingbot.core.macro.health, the provider health ledger cut with G10, and
asserted sections (inflation, rates, news) whose provider tasks were also
cut. The contract itself is unchanged and is what this asserts — a dead
internet degrades to "unknown", never to an exception or a blocked scan.
"""
import pytest

import swingbot.config as config_mod
import swingbot.core.macro.httpcache as httpcache
import swingbot.core.macro.snapshot as snap_mod


@pytest.fixture
def darkness(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("internet down")
    monkeypatch.setattr(httpcache.requests, "get", boom)
    monkeypatch.setattr(httpcache, "CACHE_DIR", str(tmp_path / "cache"))   # cold
    monkeypatch.setattr(httpcache, "LAST_SERVED_STALE", False)
    monkeypatch.setattr(snap_mod, "SNAPSHOT_PATH", str(tmp_path / "snap.json"))
    monkeypatch.setattr(snap_mod, "HISTORY_PATH", str(tmp_path / "hist.jsonl"))
    monkeypatch.setattr(snap_mod, "_last_future_refresh_day", None)
    monkeypatch.setattr(snap_mod.calendar_events, "load_events", lambda: [])
    monkeypatch.setattr(snap_mod.sectors, "sector_bars", lambda loader=None: {})
    monkeypatch.setattr(config_mod, "MACRO_ENABLED", True, raising=False)
    monkeypatch.setattr(config_mod, "FRED_API_KEY", "key-set-net-down", raising=False)
    monkeypatch.setattr(config_mod, "FINNHUB_API_KEY", "key-set-net-down", raising=False)


def test_total_darkness(darkness):
    snap = snap_mod.build_snapshot()
    assert snap["stale"] is True
    assert snap["composite"]["label"] == "unknown"
    assert snap["risk"]["vix"] is None
    assert snap["sectors"]["rs_rows"] == []
    assert snap["sectors"]["rotation"]["posture"] == "unknown"
    assert snap["breadth"]["n"] == 0
    assert snap["events"]["next_high_impact"] is None
    assert snap["quality_warnings"]                       # says what is missing
    # the scheduler still serves it — a scan would proceed normally
    served = snap_mod.ensure_fresh_snapshot()
    assert served is not None and served["composite"]["label"] == "unknown"


def test_no_provider_raises_through(darkness):
    """Every provider is called with a live API key and a dead network. None
    of them may raise: the scan loop has no handler for provider errors."""
    from swingbot.core.macro import calendar_events, earnings, fred, vix

    assert fred.fred_series("VIXCLS") is None
    assert fred.fred_release_dates(10) == []
    assert vix.vix_state() is None
    assert earnings.days_to_earnings("NVDA") is None
    assert earnings.earnings_within("NVDA", 5) is None    # unknown, not False
    assert calendar_events.refresh_future_events() == 0


def test_unknown_never_penalises_the_score():
    """The other half of the contract (G4): an unknown check is excluded from
    the score denominator, so darkness widens uncertainty — it cannot push a
    candidate toward a worse tier."""
    from swingbot.core.gate.score import score
    from swingbot.core.gate.types import CheckResult

    def _c(status, weight, cid):
        return CheckResult(cid, "context", status, weight, "", {})

    lit = [_c("pass", 10, "a"), _c("pass", 10, "b")]
    dark = lit + [_c("unknown", 40, "macro1"), _c("unknown", 40, "macro2")]
    assert score(lit) == score(dark) == 100.0
