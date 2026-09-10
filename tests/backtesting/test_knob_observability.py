"""Every searchable scan parameter must be observable or explicitly exempt."""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.scan_params import ScanParams

from .test_v74_fixture import load_v74_fixture

EXEMPT = {
    "EARNINGS_BLACKOUT_DAYS": "Needs earnings-calendar data, while this committed fixture contains only OHLCV bars.",
    "UNIVERSE_MIN_DOLLAR_VOL": "Universe construction precedes replay; the committed fixture already defines the universe.",
    "UNIVERSE_MIN_PRICE": "Universe construction precedes replay; the committed fixture already defines the universe.",
    "MAX_ALERTS_PER_SCAN": "This cap belongs to scan-run alert delivery and replay_scenarios does not execute that path.",
    "MIN_ALERT_CONFIDENCE_LEVEL": "Confidence scoring belongs to scanning.confidence and is not evaluated by replay_scenarios.",
    "UNIFIED_CONFIDENCE": "Confidence scoring belongs to scanning.confidence and is not evaluated by replay_scenarios.",
    "RS_GATE": "Relative strength is cross-sectional; two committed ticker histories cannot form the shipped percentile universe.",
    "RS_LEADER_PERCENTILE": "Relative strength is cross-sectional; two committed ticker histories cannot form the shipped percentile universe.",
    "RS_LAGGARD_PERCENTILE": "Relative strength is cross-sectional; two committed ticker histories cannot form the shipped percentile universe.",
    "REGIME_GATES_ENABLED": "The regime gate requires its benchmark ticker and attached market context, neither represented in this fixture.",
    "PLAN_ENGINE_V2": "Replay is intentionally the v2 plan path, so its on/off live switch is not an observable replay dimension.",
    "MAX_STOP_LOSS_PCT": "The fixture's viable scenarios never reach the max-stop boundary after their horizon floor is applied.",
    "CONFLUENCE_DEVIATION_PCT": "Confirmation counting is performed by the scan analysis layer, while replay uses its fixed historical tolerance.",
    "MIN_TARGET_CONFLUENCE_COUNT": "This fixture's accepted scenarios have enough confirmations on both tested horizons after the one-step perturbation.",
    "DEDUP_TOLERANCE_PCT": "Deduplication occurs after scenario replay when the live scan constructs its alert set.",
    "OPEX_CAUTION_ENABLED": "OPEX adjustment requires the calendar-aware live scan date path, which replay does not evaluate.",
    "OPEX_MONTHLY_CONFIDENCE_BUMP": "OPEX confidence adjustment is applied in the live confidence path, not historical scenario replay.",
    "OPEX_MONTHLY_CONFLUENCE_BUMP": "OPEX confluence adjustment requires calendar-tier evaluation absent from the OHLCV-only fixture.",
    "OPEX_WEEKLY_CONFLUENCE_BUMP": "OPEX confluence adjustment requires calendar-tier evaluation absent from the OHLCV-only fixture.",
    "OPEX_STOP_WIDEN_PCT": "OPEX stop widening belongs to the live calendar adjustment and replay has no OPEX-date input.",
    "OPEX_SIZE_REDUCTION_PCT": "Position size is portfolio/live execution behavior and replay records only plan prices and exits.",
    "HTF_CONFLUENCE_ENABLED": "Higher-timeframe confirmation is evaluated in scan analysis, outside replay_scenarios' scenario reconstruction.",
    "MTF_ADJACENT_GATE": "Adjacent-horizon alignment is evaluated by the live scan analysis layer, not the single-horizon replay.",
    "SCALE_OUT_ENABLED": "Replay builds plans only; scale-out is an explicit simulator option and is not selected in plan construction.",
    "LEVEL_LIFECYCLE_STOPS_ENABLED": "Lifecycle stop adjustment needs scan-level level-map context not represented in this replay fixture path.",
    "AVWAP_LEVELS_ENABLED": "The fixture has no qualifying AVWAP anchors that survive into a changed selected plan on its tested horizons.",
    "PYRAMIDING_ENABLED": "Pyramiding is a live portfolio decision after an open plan exists, outside historical signal replay.",
    "VOLUME_PROFILE_NODES_ENABLED": "This fixture's volume-profile nodes do not alter the selected scenario plans on the two tested horizons.",
    "DATA_DRIVEN_STOPS_ENABLED": "Data-driven stops require journal-derived live statistics; replay intentionally does not read live journal state.",
    "DEAD_CAT_BOUNCE_VETO": "The veto is measured through its dedicated DCB harness; baseline replay does not enable a DCB arm.",
    "DCB_DECLINE_PCT": "The veto is measured through its dedicated DCB harness; baseline replay does not enable a DCB arm.",
    "DCB_GAP_REQUIRED": "The veto is measured through its dedicated DCB harness; baseline replay does not enable a DCB arm.",
    "DCB_VOLUME_RATIO": "The veto is measured through its dedicated DCB harness; baseline replay does not enable a DCB arm.",
}
PERTURB = {bool: lambda value: not value, int: lambda value: max(1, value + 1),
           float: lambda value: value * 1.75 + 0.5}


def _run(params):
    rows = []
    for ticker, frame in load_v74_fixture().items():
        for horizon in ("4w", "3m"):
            for index, plan in replay_scenarios(ticker, frame, horizon, params=params):
                rows.append((ticker, horizon, index, plan.trigger_price, plan.entry_price,
                             plan.stop_loss, plan.tp1, plan.tp2))
    return rows


@pytest.fixture(scope="module")
def baseline():
    return _run(ScanParams.from_config())


@pytest.mark.slow
@pytest.mark.parametrize("attr", [attr for attr in config.searchable_attrs() if attr not in EXEMPT])
def test_knob_is_observable(attr, baseline):
    base = ScanParams.from_config()
    field = attr.lower()
    current = getattr(base, field)
    changed = _run(dataclasses.replace(base, **{field: PERTURB[type(current)](current)}))
    assert changed != baseline, f"{attr} changed nothing; thread it or document a genuine replay limitation"


def test_every_exempt_entry_is_searchable():
    assert set(EXEMPT) <= set(config.searchable_attrs())


def test_exempt_reasons_are_substantive():
    assert all(len(reason) > 40 for reason in EXEMPT.values())
