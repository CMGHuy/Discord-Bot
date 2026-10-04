"""Classify which searchable knobs the replay engines can observe (v100)."""
from __future__ import annotations

from dataclasses import dataclass

REACHABLE = "reachable"
LIVE_SCAN_ONLY = "live_scan_only"
JOURNAL_DEPENDENT = "journal_dependent"
OUTSIDE_REPLAY = "outside_replay"
UNCLASSIFIED = "unclassified"

C, S = frozenset({"confluence"}), frozenset({"strategy"})
CS = C | S
#: Whole-scan population engines (v118): a knob they observe needs every
#: ticker's frame at once, not one (ticker, df) at a time.
SU = frozenset({"short_universe"})
POPULATION_ENGINES = SU


@dataclass(frozen=True)
class Reach:
    cls: str
    reason: str
    observed_by: frozenset = frozenset()
    fixture_observable: bool = False


def _live(reason):
    return Reach(LIVE_SCAN_ONLY, reason)


def _outside(reason):
    return Reach(OUTSIDE_REPLAY, reason)


_V123 = "v123: the runner walk does not read this yet (wired in V123-5, reclassified in V123-10)."

_OPEX = "OPEX adjustment needs the calendar-aware live scan date path; replay has no OPEX-date input."
_RS = "Relative strength is cross-sectional and evaluated in scanning/engine.py, which no replay runs."
_DCB = "Measured through its dedicated DCB harness (replay_scenarios takes dcb_params, not config)."
_TIGHTEN = "Only active when ADAPTIVE_RUNNER_TRAIL_ENABLED=true; a lone perturbation at the default is inert by design."

REGISTRY: dict[str, Reach] = {
    "MIN_REWARD_PCT": Reach(REACHABLE, "Scenario admission gate in replay_scenarios.", C, True),
    "MIN_STOP_DISTANCE_PCT": Reach(REACHABLE, "Scenario admission gate in replay_scenarios.", C, True),
    "MAX_STOP_LOSS_PCT": Reach(REACHABLE, "Scenario admission gate; fixture never reaches the max-stop boundary.", C),
    "MIN_TARGET_CONFLUENCE_COUNT": Reach(REACHABLE, "passes_confluence in replay; fixture scenarios clear it either way.", C),
    "AVWAP_LEVELS_ENABLED": Reach(REACHABLE, "Level-map source; fixture has no anchor changing a selected plan.", C),
    "VOLUME_PROFILE_NODES_ENABLED": Reach(REACHABLE, "Level-map source; fixture nodes do not change a selected plan.", C),
    "LEVEL_LIFECYCLE_STOPS_ENABLED": Reach(REACHABLE, "apply_level_lifecycle inside build_strategy_plan. Not observable on the v74 fixture since the v104 stop ceiling (verified 2026-09-28): every widening it made there went past the 2% cap. Covered by tests/planning/test_lifecycle_ceiling.py.", S),
    "RSI_DIV_MIN_CONSECUTIVE_TURN": Reach(REACHABLE, "Read from config in entry_filters.py at entry time.", S, True),
    "MA_RIBBON_CONFIRM_BARS": Reach(REACHABLE, "Read from config in entry_filters.py at entry time. Not observable on the two-ticker v74 fixture (verified 2026-09-27).", S),
    "SR_MIN_LEVEL_TOUCHES": Reach(REACHABLE, "Read from config in entry_filters.py at entry time. Not observable on the two-ticker v74 fixture (verified 2026-09-27).", S),
    "FIB_TARGET_1_0_EXTENSION": Reach(REACHABLE, "Read from config in targets.py; rare in the fixture.", S),
    "ADAPTIVE_RUNNER_TRAIL_ENABLED": Reach(REACHABLE, "Post-TP1 runner trail in simulate_exit. Not observable on the v74 fixture since the v104 stop ceiling (verified 2026-09-28): its one trade past TIGHTEN_TRIGGER_R was a lifecycle-widened plan. Covered by tests/planning/test_exit_sim_scaleout.py.", CS),
    "TIGHTEN_TRIGGER_R": Reach(REACHABLE, _TIGHTEN, CS),
    "TIGHTEN_ATR_MULT": Reach(REACHABLE, _TIGHTEN, CS),
    "SHORT_UNIVERSE_RESEARCH_MODE": Reach(REACHABLE, (
        "v118: the short_universe population engine replays the base scan and the extra "
        "lane per decision date through the live selector (build_extra_candidates), "
        "scan_extra_candidate and qualify_short_item, on PIT membership/sector intervals. "
        "Proven on the fixture in tests/backtesting/test_measure_short_universe.py; a real "
        "run needs data/universe/sp500_sector_history.csv, which does not exist yet."), SU),
    "COMPRESSION_SHORT_RESEARCH_MODE": Reach(REACHABLE, (
        "v119: StrategyEngine adds the masked compression short inside its scoped "
        "('bearish', '2w') research cell, admitting only the named weakness mode, through the "
        "shared pre-entry decision and the live constructor. Proven to change outcomes on the "
        "stamped pilot fixture in tests/backtesting/test_measure_compression_short.py (not the "
        "v74 fixture: a select has no perturbation there). A real run reads "
        "compression_research.offline_context(): no as-of earnings archive exists, so every "
        "historical candidate is excluded earnings_unknown."), S),
    "CONFLUENCE_DEVIATION_PCT": _live("Confirmation counting happens in scan analysis; replay uses fixed tolerance."),
    "MIN_ALERT_CONFIDENCE_LEVEL": _live("Confidence scoring belongs to scanning.confidence."),
    "UNIFIED_CONFIDENCE": _live("Confidence scoring belongs to scanning.confidence."),
    "DEDUP_TOLERANCE_PCT": _live("Deduplication runs when the live scan builds its alert set."),
    "MAX_ALERTS_PER_SCAN": _live("Alert-delivery cap in the scan run."),
    "RS_GATE": _live(_RS), "RS_LEADER_PERCENTILE": _live(_RS), "RS_LAGGARD_PERCENTILE": _live(_RS),
    "REGIME_GATES_ENABLED": _live("Needs the benchmark ticker and live market context."),
    "HTF_CONFLUENCE_ENABLED": _live("Higher-timeframe confirmation is evaluated in scan analysis."),
    "MTF_ADJACENT_GATE": _live("Adjacent-horizon alignment is evaluated in scan analysis."),
    "OPEX_CAUTION_ENABLED": _live(_OPEX), "OPEX_MONTHLY_CONFIDENCE_BUMP": _live(_OPEX),
    "OPEX_MONTHLY_CONFLUENCE_BUMP": _live(_OPEX), "OPEX_WEEKLY_CONFLUENCE_BUMP": _live(_OPEX),
    "OPEX_STOP_WIDEN_PCT": _live(_OPEX),
    "DATA_DRIVEN_STOPS_ENABLED": Reach(JOURNAL_DEPENDENT, "Resolves stops from the live journal (edge E31/E32)."),
    "STALL_EXIT_ENABLED": Reach(JOURNAL_DEPENDENT, "Resolves stall_exit_day from journal days_to_half_r (v92 H2)."),
    "UNIVERSE_MIN_DOLLAR_VOL": _outside("Universe construction precedes replay."),
    "UNIVERSE_MIN_PRICE": _outside("Universe construction precedes replay."),
    "OPEX_SIZE_REDUCTION_PCT": _outside("Position sizing; replay records plan prices and exits only."),
    "PYRAMIDING_ENABLED": _outside("Live portfolio decision after a plan is open."),
    "PLAN_ENGINE_V2": _outside("Replay is the v2 plan path by construction."),
    "SCALE_OUT_ENABLED": _outside("Engines always simulate scale_out=True; switch is not a replay dimension."),
    "DEAD_CAT_BOUNCE_VETO": _outside(_DCB), "DCB_DECLINE_PCT": _outside(_DCB),
    "DCB_GAP_REQUIRED": _outside(_DCB), "DCB_VOLUME_RATIO": _outside(_DCB),
    "RUNNER_STRUCTURE_EXIT": _outside(_V123),
    "RUNNER_HL_TRAIL_ATR_BUFFER": _outside(_V123),
    "RUNNER_STALL_RANGE_MAX": _outside(_V123),
}


def classify(attr: str) -> str:
    """Return a knob's registry class, including unknown names."""
    reach = REGISTRY.get(attr)
    return reach.cls if reach else UNCLASSIFIED


def reason(attr: str) -> str:
    """Return the durable explanatory reason for a classification."""
    reach = REGISTRY.get(attr)
    return reach.reason if reach else f"{attr} is not a searchable knob (config.searchable_attrs())."
