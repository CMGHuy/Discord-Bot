"""Requirement evaluation and confidence presentation helpers."""
from dataclasses import dataclass

import discord

from swingbot import config
from swingbot.core.market import opex
@dataclass
class RequirementCheck:
    """
    One named settings requirement (min reward %, min strategies
    confirmed, min confidence level, ...) checked against a single
    scenario, independent of whether it passed -- unlike the old
    sequential filter chain, EVERY requirement is always evaluated and
    kept, so a scenario can fail more than one at once and still be
    shown in full (see build_embed / _build_trade_plan_table) with
    every failing one marked, rather than silently vanishing at
    whichever filter it hit first.
    """
    key: str
    label: str
    passed: bool
    detail: str    # human-readable "actual value (needs threshold)", used verbatim when displaying a failure


CONFIDENCE_COLORS = {
    1: (231, 76, 60),    # red -- Very Low
    2: (230, 126, 34),   # orange -- Low
    3: (241, 196, 15),   # yellow -- Medium
    4: (154, 205, 50),   # yellow-green -- High
    5: (39, 174, 96),    # green -- Very High
}
CONFIDENCE_EMOJI = {1: "🔴", 2: "🟠", 3: "🟡", 4: "🟢", 5: "🟢"}

# Discord's ANSI code-block palette only has 8 foreground colors (30-37),
# so the 5-level confidence scale maps onto the closest available color --
# red -> yellow -> yellow -> green -> green. Always paired with "1;" for
# bold, so the Confidence field visually matches the embed's own
# confidence-color accent instead of rendering as plain white text.
CONFIDENCE_ANSI = {1: 31, 2: 33, 3: 33, 4: 32, 5: 32}


def confidence_color(level: int) -> discord.Color:
    r, g, b = CONFIDENCE_COLORS.get(level, (150, 150, 150))
    return discord.Color.from_rgb(r, g, b)


def _sources_str(sources) -> str:
    return ", ".join(dict.fromkeys(sources)) if sources else "n/a"


def _build_requirement_checks(scenario, target_confluence: tuple, conf,
                              effective_min_confluence: int,
                              effective_min_confidence: int, *, opex_tier=None) -> list:
    """
    Evaluates EVERY configured requirement against one scenario --
    always all of them, never stopping at the first failure -- and
    returns a RequirementCheck per one. This is the single source of
    truth the posting decision for BOTH scan modes is built from
    (`ScanItem.all_requirements_met` -- see engine.py's alert-building
    loop, which only posts a scenario once every one of these passes),
    so `!check` and the automatic scan can never disagree about what
    "meets the settings" means.
    """
    confluence_count, confluence_families = target_confluence
    c = scenario.constraints

    checks = [
        RequirementCheck(
            key="min_reward", label="Min reward %", passed=c.get("min_reward", True),
            detail=f"{scenario.target_distance_pct:.1f}% (needs {config.MIN_REWARD_PCT:.1f}%+)",
        ),
        RequirementCheck(
            key="min_stop_distance", label="Min stop distance %", passed=c.get("min_stop_distance", True),
            detail=f"{scenario.stop_distance_pct:.1f}% away (needs {config.MIN_STOP_DISTANCE_PCT:.1f}%+)",
        ),
        RequirementCheck(
            key="max_stop_distance", label="Max stop-loss %", passed=c.get("max_stop_distance", True),
            detail=f"{scenario.stop_distance_pct:.1f}% away (needs ≤{config.MAX_STOP_LOSS_PCT:.1f}%)",
        ),
        RequirementCheck(
            key="min_risk_reward", label="Min reward:risk", passed=c.get("min_risk_reward", True),
            detail=f"{scenario.risk_reward_ratio}:1 (needs {config.MIN_RISK_REWARD_RATIO:.1f}:1+)",
        ),
        RequirementCheck(
            key="min_confluence", label="Min strategies confirmed", passed=confluence_count >= effective_min_confluence,
            detail=(
                f"{confluence_count} strateg{'y' if confluence_count == 1 else 'ies'} "
                f"({', '.join(confluence_families) or 'none'}) within {config.CONFLUENCE_DEVIATION_PCT:.1f}% "
                f"(needs {effective_min_confluence}+)"
            ),
        ),
        RequirementCheck(
            key="min_confidence", label="Min confidence level", passed=conf.level >= effective_min_confidence,
            detail=f"Lv{conf.level} {conf.label} (needs Lv{effective_min_confidence}+)",
        ),
    ]

    # Appended only while the window is open, so an ordinary day's embeds
    # and funnel counters keep exactly the shape they have today. A failing
    # check blocks the post via `all_requirements_met` and is counted in the
    # funnel, which is what makes the quiet hour explainable afterwards.
    if opex.suppress_new_entries(tier=opex_tier):
        checks.append(RequirementCheck(
            key="opex_close_window", label="Outside the opex close window", passed=False,
            detail=(
                f"Monthly opex: no new entries within "
                f"{config.OPEX_NEAR_CLOSE_SUPPRESS_MINUTES} min of the 16:00 US/Eastern close."
            ),
        ))

    return checks


def _confidence_block(conf) -> str:
    ansi_code = CONFIDENCE_ANSI.get(conf.level, 37)
    text = f"{CONFIDENCE_EMOJI.get(conf.level, '⚪')} {conf.label} (Lv{conf.level}/5, {conf.score}/100)"
    return f"```ansi\n[1;{ansi_code}m{text}[0m\n```"


