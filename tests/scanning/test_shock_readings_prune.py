"""v209: daily_recap trims market_shock_readings after alert_posts; never raises."""
import asyncio
import datetime as dt
import inspect
import logging

from swingbot import config
from swingbot.commands.scanning import loops as loops_mod


class _Repo:
    def __init__(self, fail=False):
        self.cutoffs, self.fail = [], fail

    def prune_before(self, cutoff, *, conn=None):
        if self.fail:
            raise RuntimeError("database is having a day")
        self.cutoffs.append(cutoff)
        return 7


def test_prune_uses_the_keep_days_window(monkeypatch):
    repo = _Repo()
    monkeypatch.setattr(loops_mod, "market_shock_repo", lambda: repo)
    monkeypatch.setattr(config, "SHOCK_READINGS_KEEP_DAYS", 180)
    before = dt.datetime.now(dt.timezone.utc)
    asyncio.run(loops_mod._prune_shock_readings())
    (cutoff,) = repo.cutoffs
    assert cutoff.tzinfo is not None
    assert abs((before - cutoff) - dt.timedelta(days=180)) < dt.timedelta(minutes=1)


def test_prune_runs_under_every_mode(monkeypatch):
    for mode in ("off", "shadow", "live"):
        repo = _Repo()
        monkeypatch.setattr(loops_mod, "market_shock_repo", lambda: repo)
        monkeypatch.setattr(config, "MARKET_SHOCK_MODE", mode)
        asyncio.run(loops_mod._prune_shock_readings())
        assert len(repo.cutoffs) == 1, mode


def test_a_failing_prune_is_logged_and_never_raises(monkeypatch, caplog):
    monkeypatch.setattr(loops_mod, "market_shock_repo", lambda: _Repo(fail=True))
    with caplog.at_level(logging.WARNING):
        asyncio.run(loops_mod._prune_shock_readings())
    assert any("market_shock_readings" in r.getMessage() for r in caplog.records)


def test_daily_recap_calls_it_right_after_the_alert_posts_prune():
    lines = [ln.strip() for ln in inspect.getsource(loops_mod.daily_recap.coro).splitlines()]
    i = lines.index("await _prune_alert_posts()")
    assert lines[i + 1] == "await _prune_shock_readings()"
