"""V183-7: the gap floor only ever shrinks what the caps measure.

Per lane: the candidate's heat/cluster inputs are the configured risk_pct (never
shares), open heat and correlated heat over gap-sized trades never exceed the
stop-sized ones, and the v139 risk-sizing check still passes."""
import ast
import pathlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.edge import correlation, heat
from swingbot.core.planning import account
from swingbot.core.planning.account import compute_position_size
from swingbot.core.planning.gap_sizing import size_for
from swingbot.core.planning.stop_scope import risk_sizing_ok
from swingbot.core.scanning import short_run
from tests.planning.test_plan_engine_model import _plan

REPO = pathlib.Path(__file__).resolve().parents[2]
BALANCE = 10_000.0
STATS = {"win_rate": 0.80, "avg_win_r": 0.4, "avg_loss_r": 1.0, "n": 200}
SHORTS = [(100.0, 102.0), (50.0, 50.5), (250.0, 256.0), (10.0, 10.4), (174.5, 178.0)]
P99S = [0.5, 2.0, 4.0, 9.0]
MODES = ["risk_pct", "kelly", "vol_target", "min_of_all", "account_pct"]


@pytest.fixture(autouse=True)
def _no_opex(monkeypatch):
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)


def _cfg(mode, *, abs_caps=False):
    return {"balance": BALANCE, "risk_pct": 1.0, "position_pct": 10.0, "max_position_pct": 20.0,
            "sizing_mode": mode,
            "max_position_value_absolute": 1500.0 if abs_caps else 0.0,
            "max_risk_amount_absolute": 60.0 if abs_caps else 0.0}


def _stamp(p99):
    return {"rule": "gap_p99", "up_gap_p99_pct": p99, "n_up_gaps": 120}


@pytest.mark.parametrize("abs_caps", [False, True])
@pytest.mark.parametrize("mode", MODES)
def test_the_gap_floor_never_raises_any_sized_quantity(mode, abs_caps):
    cfg = _cfg(mode, abs_caps=abs_caps)
    for entry, stop in SHORTS:
        plain = compute_position_size(entry, stop, cfg, strategy_stats=STATS, ticker_atr_pct=3.0)
        for p99 in P99S:
            gap = compute_position_size(entry, stop, cfg, strategy_stats=STATS,
                                        ticker_atr_pct=3.0, gap_floor_pct=p99)
            case = (mode, abs_caps, entry, stop, p99)
            assert gap["shares"] <= plain["shares"], case
            assert gap["risk_amount"] <= plain["risk_amount"] + 0.01, case
            assert gap["position_value"] <= plain["position_value"] + 0.01, case
            assert gap["mode"] == plain["mode"], case
            assert gap["gap_risk_amount"] >= gap["risk_amount"] - 0.01, case


@pytest.mark.parametrize("mode", ["risk_pct", "kelly", "vol_target", "min_of_all"])
def test_a_p99_gap_stays_inside_the_dollar_risk_in_every_risk_mode(mode):
    cfg = _cfg(mode)
    for entry, stop in SHORTS:
        for p99 in P99S:
            gap = compute_position_size(entry, stop, cfg, strategy_stats=STATS,
                                        ticker_atr_pct=3.0, gap_floor_pct=p99)
            assert gap["gap_risk_amount"] <= BALANCE * cfg["risk_pct"] / 100 + 0.01, (mode, entry, p99)


def test_account_pct_is_cut_only_through_the_absolute_risk_cap():
    for entry, stop in SHORTS:
        for p99 in P99S:
            free = compute_position_size(entry, stop, _cfg("account_pct"), gap_floor_pct=p99)
            assert free["shares"] == compute_position_size(entry, stop, _cfg("account_pct"))["shares"]
            capped = compute_position_size(entry, stop, _cfg("account_pct", abs_caps=True),
                                           gap_floor_pct=p99)
            assert capped["gap_risk_amount"] <= 60.0 + 0.01, (entry, p99)


def _book(p99):
    cfg = _cfg("risk_pct")
    rows = []
    for i, (entry, stop) in enumerate(SHORTS):
        stamp = _stamp(p99) if p99 is not None else None
        sizing = size_for(entry, stop, direction="bearish", gap_sizing=stamp, account_cfg=cfg)
        rows.append({"ticker": f"T{i}", "direction": "bearish", "entry": entry,
                     "stop_loss": stop, "shares": sizing["shares"]})
    return rows


@pytest.mark.parametrize("p99", P99S)
def test_open_heat_over_gap_sized_shorts_never_exceeds_stop_sized(p99):
    gap_book, stop_book = _book(p99), _book(None)
    assert heat.open_heat(gap_book, BALANCE) <= heat.open_heat(stop_book, BALANCE) + 1e-9
    gap_chk = heat.heat_check(gap_book, BALANCE, candidate_risk_pct=1.0)
    stop_chk = heat.heat_check(stop_book, BALANCE, candidate_risk_pct=1.0)
    assert gap_chk["remaining"] >= stop_chk["remaining"]
    assert gap_chk["allowed"] or not stop_chk["allowed"]


@pytest.mark.parametrize("p99", P99S)
def test_correlated_heat_over_gap_sized_shorts_never_exceeds_stop_sized(p99):
    rng = np.random.default_rng(7)
    frame = pd.DataFrame({"Close": 100 * np.cumprod(1 + rng.normal(0, 0.01, 150))},
                         index=pd.bdate_range("2026-01-01", periods=150))
    dfs = {f"T{i}": frame for i in range(len(SHORTS))} | {"CAND": frame}
    gap = correlation.cluster_exposure(_book(p99), "CAND", dfs, BALANCE)
    stop = correlation.cluster_exposure(_book(None), "CAND", dfs, BALANCE)
    assert len(stop["cluster"]) == len(SHORTS)          # every name correlates: the check is live
    assert gap["correlated_heat"] <= stop["correlated_heat"] + 1e-9
    assert (correlation.cluster_check(gap, 1.0)["allowed"]
            or not correlation.cluster_check(stop, 1.0)["allowed"])


def test_short_lane_flags_ignore_the_gap_stamp(monkeypatch):
    """v118/v119/v144: _stamp_risk_flags reads config risk_pct, so a stamped and
    an unstamped candidate get the same heat and cluster verdicts."""
    open_book = [{"ticker": "AAA", "direction": "bearish", "entry": 100.0, "stop_loss": 102.0,
                  "shares": 290.0}]                     # 5.8% open heat: the next 1% breaches 6%
    monkeypatch.setattr(short_run, "trade_log", SimpleNamespace(get_trades=lambda **k: open_book))
    monkeypatch.setattr(short_run.throttle, "kill_state", lambda: {"on": False})
    monkeypatch.setattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)
    monkeypatch.setattr(config, "CORRELATED_HEAT_CAP_PCT", 3.0)
    cfg = _cfg("risk_pct")
    verdicts = []
    for stamp in (_stamp(4.0), None):
        item = SimpleNamespace(result=SimpleNamespace(ticker="TSLA"),
                               plan_v2=_plan(direction="bearish", stop_loss=102.0, gap_sizing=stamp),
                               heat_blocked=None, cluster_blocked=None, kill_switch_blocked=None)
        short_run._stamp_risk_flags(item, {}, cfg)
        verdicts.append((item.heat_blocked, item.cluster_blocked))
    assert verdicts[0] == verdicts[1]
    assert verdicts[0][0] is not None                   # the heat check did fire


@pytest.mark.parametrize("path", ["swingbot/core/scanning/scan_run.py",
                                  "swingbot/core/scanning/short_run.py"])
def test_candidate_heat_and_cluster_inputs_are_the_configured_risk_pct(path):
    """The confluence lane's checks are inline in run_scan; pin their inputs."""
    tree = ast.parse((REPO / path).read_text(encoding="utf-8"))
    seen = 0
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr == "heat_check":
            arg = next(kw.value for kw in node.keywords if kw.arg == "candidate_risk_pct")
        elif node.func.attr == "cluster_check":
            arg = node.args[1]
        else:
            continue
        seen += 1
        assert ast.unparse(arg) == "account_cfg.get('risk_pct', 1.0)", (path, node.lineno)
    assert seen == 2, path


def test_the_seventh_sizing_site_still_passes_on_a_gap_cut_size():
    cfg = _cfg("risk_pct")
    for entry, stop in SHORTS:
        plan = _plan(direction="bearish", trigger_price=entry, stop_loss=stop, stop_ceiling_pct=3.0)
        stop_only = risk_sizing_ok(plan, sizing_fn=lambda e, s: compute_position_size(e, s, cfg))
        for p99 in P99S:
            gap_fn = (lambda e, s, p=p99: size_for(e, s, direction="bearish",
                                                  gap_sizing=_stamp(p), account_cfg=cfg))
            assert risk_sizing_ok(plan, sizing_fn=gap_fn) or not stop_only, (entry, p99)
