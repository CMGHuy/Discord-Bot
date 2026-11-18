"""v230 A2: what a v2 Δ means -- cost, regime and sector blocks, never gating."""
import json

import pytest

from swingbot.core.backtesting.screen import v2_report


def _row(day, ticker="AAA", r_event=0.2, r_null=0.1, cost_event=0.05, cost_null=0.04):
    return {"ticker": ticker, "entry_date": day, "r_event": r_event, "r_null": r_null,
            "cost_event": cost_event, "cost_null": cost_null}


@pytest.mark.parametrize("day, regime", [
    ("2011-01-03", "2011–2017"), ("2017-12-29", "2011–2017"), ("2018-09-28", "rest"),
    ("2018-10-01", "2018 Q4"), ("2018-12-31", "2018 Q4"), ("2019-01-02", "rest")])
def test_each_entry_date_falls_in_one_regime(day, regime):
    block = v2_report.v2_summary([_row(day)], scope="ticker", sectors=None)
    assert block["regimes"][regime] == (1, pytest.approx(0.2), pytest.approx(0.1))
    assert sum(n for n, _, _ in block["regimes"].values()) == 1
    assert list(block["regimes"]) == ["2011–2017", "2018 Q4", "rest"]


def test_mean_costs_and_the_sector_mix_of_both_arms():
    rows = [_row("2012-01-03", "AAA", 0.4, 0.0, 0.06, 0.02),
            _row("2012-01-04", "BBB", 0.0, 0.2, 0.04, 0.04), _row("2012-01-05", "CCC")]
    block = v2_report.v2_summary(rows, scope="market", sectors={"AAA": "Tech", "BBB": "Tech"})
    assert block["cost"]["event"] == pytest.approx(0.05)
    assert block["cost"]["null"] == pytest.approx(0.1 / 3)
    assert block["sectors"] == {"Tech": (2, pytest.approx(0.2), pytest.approx(0.1)),
                                "unmapped": (1, pytest.approx(0.2), pytest.approx(0.1))}
    assert block["scope"] == "market"


def test_an_empty_book_and_no_sector_map_render_as_such():
    block = v2_report.v2_summary([], scope="ticker", sectors=None)
    assert block["cost"] == {"event": None, "null": None} and block["sectors"] is None
    text = "\n".join(v2_report.render_v2(block))
    assert "**Sector mix:** omitted" in text and "| rest | 0 | — | — |" in text


def test_load_sectors_drops_unknown_and_missing_sectors(tmp_path):
    path = tmp_path / "pit.json"
    path.write_text(json.dumps([{"symbol": "A", "sector": "Health Care"},
                                {"symbol": "AAL", "sector": "Unknown"}, {"symbol": "X"}]),
                    encoding="utf-8")
    assert v2_report.load_sectors(path) == {"A": "Health Care"}
    assert v2_report.load_sectors(tmp_path / "missing.json") is None


def test_render_states_the_meaning_and_every_omitted_block():
    block = v2_report.v2_summary([_row("2012-01-03")], scope="ticker", sectors={"AAA": "Tech"})
    text = "\n".join(v2_report.render_v2(block))
    assert v2_report.MEANING["ticker"] in text and v2_report.LOOKAHEAD in text
    assert {n for n, _ in v2_report.OMITTED_V2_BLOCKS} == {
        "restricted", "stressed", "repriced", "shock", "control"}
    assert all(f"`{name}`" in text for name, _ in v2_report.OMITTED_V2_BLOCKS)
    assert "| Tech | 1 | +0.2000 | +0.1000 |" in text
    assert set(v2_report.MEANING) == {"ticker", "market"}
