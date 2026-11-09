"""v209: only the scheduled session scan steps the market-shock state.

!check, the recap and the admin-UI scan go through run_scan without the flag
and only read the stored label (spec § The reading, Gating)."""
import ast
import asyncio
import inspect
from datetime import datetime, timezone
from pathlib import Path

import pytest

from swingbot import config
from swingbot.commands.scanning import loops
from swingbot.core.scanning import fetch, runstate, scan_run, shock_scan
from tests.helpers import make_ohlcv

REPO = Path(__file__).resolve().parents[2]
SCAN_CALLS = {"run_scan", "_run_scan_posting_partial"}


class _Calls(ast.NodeVisitor):
    """Every run_scan-family call with its innermost enclosing function."""

    def __init__(self, filename):
        self.filename, self.stack, self.found = filename, [], []

    def _function(self, node):
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def visit_Call(self, node):
        func = node.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if called in SCAN_CALLS:
            flag = next((k.value for k in node.keywords if k.arg == "step_shock"), None)
            self.found.append((self.filename, self.stack[-1] if self.stack else None,
                               None if flag is None else ast.unparse(flag)))
        self.generic_visit(node)


def _scan_calls():
    found = []
    for path in sorted((REPO / "swingbot" / "commands").rglob("*.py")):
        visitor = _Calls(path.name)
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        found.extend(visitor.found)
    return found


def test_only_the_scheduled_session_scan_passes_step_shock():
    stepping = [call for call in _scan_calls() if call[2] is not None]
    assert stepping == [("loops.py", "_session_scan_tick", "True")]


def test_check_recap_and_the_admin_scan_still_call_run_scan_without_the_flag():
    calls = _scan_calls()
    readers = {(name, fn) for name, fn, flag in calls if flag is None}
    assert ("commands.py", "_check_live") in readers
    assert any(name == "recap.py" for name, _fn, _flag in calls)
    assert all(flag is None for name, _fn, flag in calls if name in ("commands.py", "recap.py"))
    loops_readers = [fn for name, fn, flag in calls
                     if name == "loops.py" and flag is None and fn != "_run_scan_posting_partial"]
    assert loops_readers, "the admin-UI scan call in loops.py must exist and carry no step_shock"


def test_posting_partial_forwards_the_flag_to_run_scan(monkeypatch):
    seen = {}

    async def fake_run_scan(**kwargs):
        seen.update(kwargs)
        return []

    monkeypatch.setattr(loops.scan_engine, "run_scan", fake_run_scan)
    asyncio.run(loops._run_scan_posting_partial("chan", require_confirmation=True, step_shock=True))
    assert seen == {"require_confirmation": True, "step_shock": True}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    # Same isolation as tests/scanning/test_run_scan_scan_id.py.
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_mark_running", lambda running: None)
    monkeypatch.setattr(runstate, "_clear_stop", lambda: None)


def test_run_scan_takes_step_shock_by_keyword_only_and_defaults_off():
    param = inspect.signature(scan_run.run_scan).parameters["step_shock"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY and param.default is False
    assert inspect.signature(scan_run._sync_run_scan).parameters["step_shock"].default is False


@pytest.mark.parametrize("kwargs,expected", [({}, False), ({"step_shock": True}, True)])
def test_run_scan_hands_the_flag_to_the_worker_thread(isolated, monkeypatch, kwargs, expected):
    seen = []

    def fake_sync_run(horizon_filter, require_confirmation, progress, min_confluence,
                      step_shock=False):
        seen.append(step_shock)
        return [], [], []

    monkeypatch.setattr(scan_run, "_sync_run_scan", fake_sync_run)
    asyncio.run(scan_run.run_scan(**kwargs))
    assert seen == [expected]


class _Halt(BaseException):
    """Raised by the fake shock pass so the worker stops right after it. A
    BaseException, so _shock_state_for_pass's `except Exception` lets it through."""


@pytest.fixture
def worker(monkeypatch):
    frames = {"AAA": make_ohlcv([100.0] * 60), "SPY": make_ohlcv([400.0] * 60)}
    order, asked = [], []
    monkeypatch.setattr(config, "MARKET_REGIME_TICKER", "SPY")
    monkeypatch.setattr(config, "MARKET_SHOCK_MODE", "shadow")
    monkeypatch.setattr(scan_run, "_reload_config_before_scan", lambda: {})
    monkeypatch.setattr(scan_run, "_scan_tickers", lambda: ["AAA"])
    monkeypatch.setattr(scan_run.opex, "current_tier", lambda: None)
    monkeypatch.setattr(fetch, "_crawl_latest_data", lambda tickers, progress=None: dict(frames))

    def live(tickers, progress=None):
        order.append(("live", datetime.now(timezone.utc)))
        asked.append(list(tickers))
        return {t: QUOTES[t] for t in tickers}

    monkeypatch.setattr(fetch, "_fetch_live_prices", live)
    monkeypatch.setattr(scan_run.rs_factors, "refresh_rs_cache", lambda data, spy: None)
    monkeypatch.setattr(scan_run, "get_regime", lambda df: None)
    monkeypatch.setattr(fetch, "_etf_symbol_of_sector", lambda: {"Information Technology": "XLK"})
    monkeypatch.setattr(fetch, "_sector_etfs_for_tickers",
                        lambda tickers: ({"AAA": "Information Technology"}, []))

    def shock_pass(**kwargs):
        order.append(("shock", kwargs))
        raise _Halt

    monkeypatch.setattr(shock_scan, "run_shock_pass", shock_pass)
    return frames, order, asked


QUOTES = {"AAA": 97.0, "SPY": 400.0, "QQQ": 300.0}


@pytest.mark.parametrize("flag", [False, True])
def test_the_worker_hands_the_pass_its_own_frames_quotes_sectors_and_clock(worker, flag):
    frames, order, _asked = worker
    with pytest.raises(_Halt):
        scan_run._sync_run_scan("all", True, None, None, step_shock=flag)
    (first, live_at), (second, kwargs) = order
    assert (first, second) == ("live", "shock")
    assert kwargs["step_shock"] is flag
    assert set(kwargs["frames"]) == {"AAA", "SPY"}
    assert kwargs["live_prices"] == {"AAA": 97.0}
    assert kwargs["sector_of"] == {"AAA": "Information Technology"}
    assert kwargs["spy_df"] is frames["SPY"]
    quotes_at = kwargs["quotes_at"]
    assert quotes_at.tzinfo is not None and quotes_at >= live_at


def test_a_raising_shock_pass_yields_no_label_and_the_scan_goes_on(monkeypatch, caplog):
    def boom(**kwargs):
        raise RuntimeError("shock pass blew up")

    monkeypatch.setattr(shock_scan, "run_shock_pass", boom)
    assert scan_run._shock_state_for_pass(step_shock=True) is None
    assert any(getattr(r, "swallowed_tag", "") == "scan.shock.call" for r in caplog.records)


def test_the_label_is_bound_once_before_any_plan_is_built():
    src = inspect.getsource(scan_run._sync_run_scan)
    assert src.count("_shock_state_for_pass(") == 1 and "run_shock_pass(" not in src
    assert src.index("shock_state = _shock_state_for_pass(") < src.index("_attach_item_plan(")
    assert src.index("quotes_at = datetime.now(timezone.utc)") < src.index("_shock_state_for_pass(")
