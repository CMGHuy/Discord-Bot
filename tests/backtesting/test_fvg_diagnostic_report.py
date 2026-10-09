"""v143 report and results document: 27 cells, the context tables, the
multiple-looks warning."""
from swingbot.core.backtesting import fvg_diagnostic as fd
from tests.backtesting.fvg_diagnostic_rows import row, table


def rows():
    """The passing table plus one unidentified winner in 2023."""
    return table() + [row("2023", role="unidentified", gap_age=None, gap_open=None)]


def test_report_has_27_cells_and_names_the_candidate():
    report = fd.build_report(rows())
    assert (report["n"], report["unidentified"], len(report["cells"])) == (201, 1, 27)
    assert report["gap_split"] == {"target": 200, "stop": 0, "unidentified": 1,
                                   "open": 200, "filled": 0}
    assert report["coverage"]["gap_age"] == {"computable": 200, "not_computable": 1,
                                             "share": 200 / 201, "tested": True}
    assert ("gap_age", "live") in report["candidates"]
    assert report["population"]["live"]["n"] == 201
    assert report["exit_mix"]["live"] == {"stop": 104, "tp1+runner_trail": 97}


def test_context_tables_cover_role_direction_horizon_and_year():
    context = fd.build_report(rows())["context"]
    assert set(context) == set(fd.CONTEXT_DIMENSIONS)
    assert set(context["year"]) == set(fd.YEARS)
    assert set(context["fvg_role"]) == {"target", "unidentified"}
    assert context["fvg_role"]["unidentified"]["g100"]["n"] == 1


def test_the_document_carries_the_warning_the_rule_and_every_table():
    text = fd.render(fd.build_report(rows()), run_date="2026-10-10", tickers=75,
                     tolerance_pct=2.0)
    expected = ["9 features at 3 geometries is 27 looks",
                "**Gap role: 200 target / 0 stop / 1 unidentified. Gap at the signal bar: "
                "200 open / 0 filled.**",
                "**Population N = 201** (expected 1278). **Unidentified: 1 (0.5%)**",
                "replay quality 60, ATR14/close 0.02.", "| 4/4 | 1 (0.5%) | **CANDIDATE** |",
                "## Feature coverage", "| Gap age <= 20 bars | 200 | 1 | 99.5% | tested |",
                "Replay quality score, not the live one", "within 2% of the scenario target",
                "Share of gap filled: not testable on this population",
                "### By gap role", "### By plan direction", "### By horizon", "### By year",
                "### Exit mix", "VALIDATION never read"]
    assert [piece for piece in expected if piece not in text] == []
    assert text.count("| Gap age <= 20 bars | live |") == 1
    assert "Not tested:" not in text


def test_a_feature_under_the_floor_is_reported_as_not_tested_not_closed():
    blind = dict(role="unidentified", gap_age=None, gap_height_atr=None, displacement=None,
                 gap_open=None)
    report = fd.build_report(table() + [row(**blind) for _ in range(60)])
    gap_features = ["gap_age", "gap_height_atr", "displacement", "gap_open"]
    assert fd.not_tested(report) == gap_features
    assert all(cell["failures"] == [fd.NOT_TESTED]
               for cell in report["cells"] if cell["feature"] in gap_features)
    assert not [pair for pair in report["candidates"] if pair[0] in gap_features]
    text = fd.render(report, run_date="2026-10-10", tickers=75)
    assert "**Not tested: gap_age, gap_height_atr, displacement, gap_open.**" in text
    assert "this diagnostic does not close them" in text
    assert "| Gap age <= 20 bars | 200 | 60 | 76.9% | **NOT TESTED** |" in text
    assert "**Unidentified: 60 (23.1%)**" in text


def test_the_document_counts_gaps_filled_before_the_signal_bar():
    stale = [row("2021", fav=False, outcome="loss", r=-1.0, gap_open=False) for _ in range(7)]
    report = fd.build_report(table() + stale + [row(role="stop")])
    assert report["gap_split"] == {"target": 207, "stop": 1, "unidentified": 0,
                                   "open": 201, "filled": 7}
    text = fd.render(report, run_date="2026-10-10", tickers=75)
    assert "Gap at the signal bar: 201 open / 7 filled.**" in text
    assert "builds its level map fresh" in text


def test_an_empty_population_renders_no_candidate():
    text = fd.render(fd.build_report([]), run_date="2026-10-10", tickers=0)
    assert "**Verdict: NO CANDIDATE.**" in text and "replay quality n/a" in text
