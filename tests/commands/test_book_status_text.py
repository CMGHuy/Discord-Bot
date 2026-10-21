"""v175: the book-status line and its embed -- pure, no store, no channel."""
import re

import pytest

from swingbot.commands.scanning import book_status
from swingbot.core.analytics import variance_band as vb
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind

_CAVEAT = "This book's past results are not positive. A run within their range is still a losing run."
_FORBIDDEN = re.compile(r"\b(edge|stop|check|skip|size|review)\b", re.IGNORECASE)


def _band(zone="rough", *, run=4, drawdown=3.24, usd=312.34, not_positive=False):
    band = {
        "status": "ok", "scope": "whole_book", "asof": "2026-10-16", "days": 140, "weeks": 30,
        "pool": "v2",
        "composition": {"days_by_era": {"v2": 140, "legacy": 0}, "trades_by_horizon": {"4w": 180}},
        "horizons": [],
        "current": {"run": run, "run_age_days": 6, "drawdown": drawdown, "drawdown_age_days": 12,
                    "run_zone": zone, "drawdown_zone": "normal", "zone": zone},
        "expr": {"value": 0.21, "n": 180, "start": "2026-03-02", "end": "2026-10-16",
                 "ci": [0.05, 0.37], "not_positive": not_positive},
    }
    if usd is not None:
        band["dollars"] = {"median_risk": 96.4, "drawdown_usd": usd}
    return band


def test_rough_line_is_verbatim_with_dollars():
    assert book_status.book_status_text(_band("rough"), "$") == (
        "Book: 4 losing days in a row / 3.2R (≈ $312.34) down over 50 close days, "
        "deeper than 80% of simulated runs, within 95%. Closed trades only.")


def test_outside_line_is_verbatim_without_dollars():
    band = _band("outside", run=7, drawdown=6.0, usd=None)
    assert book_status.book_status_text(band, "$") == (
        "Book: 7 losing days in a row / 6.0R down over 50 close days, "
        "beyond 95% of simulated runs. Closed trades only.")


def test_dollars_are_unsigned_with_a_thousands_separator():
    text = book_status.book_status_text(_band("outside", usd=1234.5), "€")
    assert "(≈ €1,234.50) down" in text
    assert "+" not in text


def test_caveat_is_appended_only_when_expr_is_not_positive():
    assert book_status.book_status_text(_band(not_positive=False), "$").endswith("Closed trades only.")
    text = book_status.book_status_text(_band(not_positive=True), "$")
    assert text.endswith("Closed trades only. " + _CAVEAT)
    assert vb.CAVEAT == _CAVEAT


@pytest.mark.parametrize("band", [
    _band("normal"),
    {"status": "insufficient", "scope": "whole_book", "days": 40, "weeks": 9},
    {"status": "ok", "current": {"zone": "unknown"}},
])
def test_nothing_to_post_unless_the_zone_is_rough_or_outside(band):
    assert book_status.book_status_text(band, "$") is None
    assert book_status.book_status_embed(band, "$") is None


@pytest.mark.parametrize("zone", ["rough", "outside"])
@pytest.mark.parametrize("not_positive", [False, True])
@pytest.mark.parametrize("usd", [None, 312.34])
def test_copy_has_no_instruction_verb_and_never_says_edge(zone, not_positive, usd):
    text = book_status.book_status_text(_band(zone, not_positive=not_positive, usd=usd), "$")
    assert _FORBIDDEN.search(text) is None, text


def test_zone_phrases_cover_exactly_the_posting_zones():
    assert set(book_status.ZONE_PHRASE) == {"rough", "outside"}


def test_embed_is_a_book_status_push():
    band = _band("rough")
    embed = book_status.book_status_embed(band, "$")
    assert embed.title == "📉 BOOK STATUS"
    assert embed.push_text == "📉 BOOK · BOOK STATUS"
    assert embed.description == book_status.book_status_text(band, "$")
    assert embed.color.value == kinds.BOOK_INDIGO
    assert embed.footer.text == "BOOK"
    assert embed.timestamp is not None
    assert embed.kind is Kind.BOOK_STATUS
