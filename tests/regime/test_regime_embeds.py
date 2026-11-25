"""v239 V239-11: one Trend line on every alert builder, under the plan table, <= 80 chars."""
import itertools
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.presentation import ansi, regime_text
from swingbot.core.scanning import alert_embeds, snapshots
from swingbot.core.scanning.alert_embeds import (REGIME_FIELD, build_embed, build_simple_alert,
                                                 build_strategy_alert_embed,
                                                 build_strategy_simple_embed, regime_fields)
from tests.scanning.test_embeds_v3 import PERF_STATS_EMPTY, make_item, make_plan_v2

CASES = [  # (bear_regime, regime_action, plan direction, the spec's line)
    ("BEAR", "would_veto", "bullish", "Regime: Bear (shadow) — engine would skip this long"),
    ("CORRECTION", "would_veto", "bullish", "Regime: Correction · Stress (shadow) — would skip long"),
    ("CORRECTION", "caution", "bullish", "Regime: Correction — dip in an uptrend"),
    ("CORRECTION", "pullback_watch", "bullish", "Regime: Pullback watch — panic easing in a correction"),
    ("BEAR", "aligned", "bearish", "Regime: Bear — with the tape; squeeze risk on rebounds"),
    ("CORRECTION", "aligned", "bearish", "Regime: Correction — short in a dip; uptrend intact"),
]
SILENT = [("NORMAL", "none"), ("UNKNOWN", "none"), ("BEAR", None), (None, None),
          ("CORRECTION", "none"), ("garbage", "would_veto")]
_paths = itertools.count()


def _v2(state=None, action=None, direction="bullish"):
    plan = make_plan_v2(direction=direction)
    plan.entry_context = {"atr_pct": 3.1}
    if state is not None or action is not None:
        plan.entry_context.update(bear_regime=state, regime_action=action)
    return plan


def _strategy_plan(ctx=None):
    plan = SimpleNamespace(plan_id="0123456789ab", ticker="AAPL", strategy="Fibonacci",
                           direction="bullish", horizon_key="4w", trigger_price=100.0,
                           stop_loss=94.0, tp1=110.0, tp2=None, badge="WEAK", ledger="weak",
                           confidence_level=4)
    if ctx is not None:
        plan.entry_context = ctx
    return plan


def _full(plan, monkeypatch, tmp_path):
    # a fresh snapshot file per build, so no "what changed" field appears
    monkeypatch.setattr(snapshots, "_SNAPSHOT_PATH", str(tmp_path / f"s{next(_paths)}.json"))
    return build_embed(make_item(plan_v2=plan), "why", PERF_STATS_EMPTY, None, None)


def _fields(embed):
    return [(f.name, f.value) for f in embed.fields]


def _bytes(embed):
    doc = embed.to_dict()
    doc.pop("timestamp", None)     # apply_chrome stamps the wall clock
    return doc


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_each_case_gives_its_line_within_the_cap(state, action, direction, line):
    assert regime_fields(_v2(state, action, direction)) == [(REGIME_FIELD, line, False)]
    assert REGIME_FIELD == "Trend" and len(line) <= regime_text.MAX_LINE == 80


@pytest.mark.parametrize("state, action", SILENT)
def test_no_line_outside_the_table(state, action):
    assert regime_fields(_v2(state, action)) == []


@pytest.mark.parametrize("plan", [None, SimpleNamespace(), SimpleNamespace(entry_context=None),
                                  SimpleNamespace(entry_context="CORRECTION"), _v2()])
def test_no_line_without_a_readable_stamp(plan):
    assert regime_fields(plan) == []


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_full_embed_adds_one_field_at_the_end_of_the_plan_section(
        monkeypatch, tmp_path, state, action, direction, line):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(alert_embeds, "_market_on_open_fields", lambda plan: [("MOO", "x", False)])
    plain = _full(_v2(direction=direction), monkeypatch, tmp_path)
    stamped = _full(_v2(state, action, direction), monkeypatch, tmp_path)
    names = [name for name, _ in _fields(stamped)]
    assert names.index(REGIME_FIELD) == names.index("MOO") + 1      # directly under the plan table
    assert [f for f in _fields(stamped) if f[0] != REGIME_FIELD] == _fields(plain)
    assert (REGIME_FIELD, line) in _fields(stamped)
    assert stamped.description == plain.description and stamped.footer.text == plain.footer.text
    assert stamped.to_dict().get("image") == plain.to_dict().get("image")


@pytest.mark.parametrize("engine", ["on", "shadow"])          # the v2 ticket, the legacy mirror
@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_simple_alert_ends_with_the_line_on_both_branches(
        monkeypatch, engine, state, action, direction, line):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", engine)
    plain = build_simple_alert(make_item(plan_v2=_v2(direction=direction)))
    stamped = build_simple_alert(make_item(plan_v2=_v2(state, action, direction)))
    assert _fields(stamped) == [*_fields(plain), (REGIME_FIELD, line)]
    assert stamped.description == plain.description


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_strategy_embed_puts_the_line_after_the_ledger(state, action, direction, line):
    embed = build_strategy_alert_embed(_strategy_plan({"bear_regime": state, "regime_action": action}))
    assert _fields(embed)[-2:] == [("Ledger", "weak — P&L tracked separately, never summed into main"),
                                   (REGIME_FIELD, line)]


@pytest.mark.parametrize("state, action, direction, line", CASES)
def test_the_strategy_simple_embed_ends_its_description_with_the_line(state, action, direction, line):
    plain = build_strategy_simple_embed(_strategy_plan())
    embed = build_strategy_simple_embed(_strategy_plan({"bear_regime": state, "regime_action": action}))
    assert embed.description == f"{plain.description}\n{line}"
    assert ansi._ESCAPE_RE.sub("", embed.description).splitlines()[-1] == line
    assert not embed.fields


@pytest.mark.parametrize("engine", ["on", "shadow"])
@pytest.mark.parametrize("ctx", [None, {}, {"atr_pct": 3.1}, {"bear_regime": "NORMAL", "regime_action": "none"}])
def test_without_a_line_every_builder_is_byte_identical_to_pre_v239(monkeypatch, tmp_path, engine, ctx):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", engine)

    def build_all():
        v2 = make_plan_v2()
        if ctx is not None:
            v2.entry_context = dict(ctx)
        strategy = _strategy_plan(None if ctx is None else dict(ctx))
        return [_bytes(_full(v2, monkeypatch, tmp_path)), _bytes(build_simple_alert(make_item(plan_v2=v2))),
                _bytes(build_strategy_alert_embed(strategy)), _bytes(build_strategy_simple_embed(strategy))]

    now = build_all()
    monkeypatch.setattr(alert_embeds, "regime_fields", lambda plan: [])     # the pre-v239 builders
    assert now == build_all()
