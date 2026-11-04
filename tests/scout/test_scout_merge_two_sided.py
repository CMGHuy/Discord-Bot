"""v200 Part 5: the two-sided, known-at-entry merge rule (schema 2) and the schema-1 legacy rule."""
import json
import sys
from dataclasses import fields
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import scout_merge as merge  # noqa: E402


def _cell(cid, *, lo, hi, q=0.04, n=40, weeks=12, defined_at="entry"):
    cut, value = cid.split("=", 1)
    ci = None if lo is None else [lo, hi]
    delta = None if lo is None else round((lo + hi) / 2, 6)
    out = {"id": cid, "cut": cut, "value": value, "n": n, "weeks": weeks, "win_rate": 0.5,
           "net_expr": 0.2, "gross_expr": 0.22, "delta": delta, "ci": ci, "p": 0.01, "q": q,
           "thin": False, "bar_covered_n": None, "extra": {}}
    if defined_at is not None:
        out["defined_at"] = defined_at
    return out


def _evidence(cell):
    if cell["ci"] is None:
        return f"cell {cell['id']}; N {cell['n']}; weeks {cell['weeks']}; Δ net ExpR 0.000 [0.000, 0.000]; q 0.040"
    lo, hi = cell["ci"]
    return (f"cell {cell['id']}; N {cell['n']}; weeks {cell['weeks']}; "
            f"Δ net ExpR {cell['delta']:.3f} [{lo:.3f}, {hi:.3f}]; q {cell['q']:.3f}")


def _row(cell, direction, idea=None, role="regime-desk"):
    base = {f.name: "" for f in fields(merge.ScoutRow)}
    base.update(role=role, idea=idea or f"{direction}-{cell['id']}", claim="A claim.",
                evidence=_evidence(cell), exploratory="yes", edge="expectancy",
                direction=direction, mechanism="Why.", order_form="limit, day order",
                manual_actions="none", pairs_with="n/a", divergence="no", route="/prereg")
    return merge.ScoutRow(**base)


def _screen(rows, cells, schema=2):
    return merge.screen_rows(rows, closed=set(), ledger={}, cells={c["id"]: c for c in cells},
                             schema=schema)


def _reasons(drops):
    return {d.idea: d.reason for d in drops}


UP = _cell("regime=risk_on", lo=0.05, hi=0.35)
DOWN = _cell("regime=risk_off", lo=-0.35, hi=-0.05)
STRADDLE = _cell("regime=chop", lo=-0.10, hi=0.0)


@pytest.mark.parametrize("header, schema", [
    ({}, 1), ({"autopsy_schema": 1}, 1), ({"autopsy_schema": 2}, 2)])
def test_autopsy_schema_reads_the_header(header, schema):
    assert merge.autopsy_schema(header) == schema


@pytest.mark.parametrize("value", ["2", 3, 0, True, None, 2.0])
def test_an_unknown_autopsy_schema_fails_loudly(value):
    with pytest.raises(merge.SchemaError, match="autopsy_schema"):
        merge.autopsy_schema({"autopsy_schema": value})


def test_exploit_needs_a_lower_bound_above_zero():
    kept, drops = _screen([_row(UP, "exploit"), _row(DOWN, "exploit")], [UP, DOWN, STRADDLE])
    assert [r.idea for r in kept] == ["exploit-regime=risk_on"]
    assert _reasons(drops) == {"exploit-regime=risk_off":
        "cell regime=risk_off Δ lower bound -0.350 is at or below zero or unavailable"}


def test_avoid_needs_an_upper_bound_below_zero():
    rows = [_row(DOWN, "avoid"), _row(STRADDLE, "avoid"), _row(UP, "avoid")]
    kept, drops = _screen(rows, [UP, DOWN, STRADDLE])
    assert [r.idea for r in kept] == ["avoid-regime=risk_off"]
    assert _reasons(drops) == {
        "avoid-regime=chop": "cell regime=chop Δ upper bound +0.000 is at or above zero or unavailable",
        "avoid-regime=risk_on": "cell regime=risk_on Δ upper bound +0.350 is at or above zero or unavailable"}


def test_an_avoid_row_without_an_interval_is_unavailable():
    none = _cell("regime=none", lo=None, hi=None)
    _, drops = _screen([_row(none, "avoid")], [none])
    assert drops[0].reason == "cell regime=none Δ upper bound n/a is at or above zero or unavailable"


@pytest.mark.parametrize("direction, cell", [("exploit", _cell("regime=hiq", lo=0.05, hi=0.3, q=0.2)),
                                             ("avoid", _cell("regime=hiq", lo=-0.3, hi=-0.05, q=0.2))])
def test_q_still_applies_to_both_directions(direction, cell):
    _, drops = _screen([_row(cell, direction)], [cell])
    assert "q must be finite and between 0 and 0.10" in drops[0].reason


@pytest.mark.parametrize("tag", ["fill", "outcome"])
@pytest.mark.parametrize("direction, lo, hi", [("exploit", 0.05, 0.35), ("avoid", -0.35, -0.05)])
def test_fill_and_outcome_cells_drop_as_not_known_at_entry(tag, direction, lo, hi):
    cell = _cell("exit_reason=stop", lo=lo, hi=hi, defined_at=tag)
    kept, drops = _screen([_row(cell, direction)], [cell])
    assert kept == []
    assert drops[0].reason == f"cell exit_reason=stop is {tag}-defined (not known at entry)"


@pytest.mark.parametrize("bad", [None, "later", ""])
def test_schema_2_cell_without_defined_at_fails_loudly(bad):
    broken = _cell("weekday=Mon", lo=0.05, hi=0.3, defined_at=bad)
    if bad == "":
        broken["defined_at"] = ""
    with pytest.raises(merge.SchemaError, match="weekday=Mon"):
        _screen([_row(UP, "exploit")], [UP, broken])          # fails even when the cell is not cited


def test_schema_1_keeps_the_legacy_one_sided_rule_without_a_ban():
    outcome = _cell("exit_reason=stop", lo=0.05, hi=0.35, defined_at=None)
    down = _cell("regime=risk_off", lo=-0.35, hi=-0.05, defined_at=None)
    kept, drops = _screen([_row(outcome, "exploit"), _row(down, "avoid")], [outcome, down], schema=1)
    assert [r.idea for r in kept] == ["exploit-exit_reason=stop"]
    assert _reasons(drops) == {"avoid-regime=risk_off":
        "cell regime=risk_off Δ lower bound -0.350 is at or below zero or unavailable"}


FRI_YES = _cell("friday_entry=yes", lo=-0.35, hi=-0.05)
FRI_NO = _cell("friday_entry=no", lo=0.05, hi=0.35)


def test_avoid_x_and_exploit_not_x_dedupe_by_cut():
    rows = [_row(FRI_YES, "avoid", idea="skip-friday"),
            _row(FRI_NO, "exploit", idea="weekday-entries-only", role="setup-scout")]
    kept, drops = _screen(rows, [FRI_YES, FRI_NO])
    assert [r.idea for r in kept] == ["skip-friday"]
    assert _reasons(drops) == {"weekday-entries-only":
        "same rule as the regime-desk row skip-friday on two-value cut friday_entry"}
    cells = {c["id"]: c for c in (FRI_YES, FRI_NO)}
    assert merge.rule_key(rows[0], cells) == merge.rule_key(rows[1], cells) == ("friday_entry", "no")


def test_a_cut_with_three_values_is_never_deduped():
    cells = [_cell("weekday=Mon", lo=0.05, hi=0.3), _cell("weekday=Tue", lo=0.05, hi=0.3),
             _cell("weekday=Fri", lo=-0.3, hi=-0.05)]
    rows = [_row(cells[2], "avoid"), _row(cells[0], "exploit")]
    kept, drops = _screen(rows, cells)
    assert len(kept) == 2 and drops == []
    assert merge.rule_key(rows[0], {c["id"]: c for c in cells}) is None


def test_a_dropped_row_does_not_claim_its_rule():
    weak = _cell("friday_entry=yes", lo=-0.35, hi=-0.05, q=0.5)
    rows = [_row(weak, "avoid", idea="skip-friday"), _row(FRI_NO, "exploit", idea="weekday-only")]
    kept, _ = _screen(rows, [weak, FRI_NO])
    assert [r.idea for r in kept] == ["weekday-only"]


def _autopsy(tmp_path, cells, schema=2):
    header = {"window": ["2026-01-05", "2026-10-09"], "n": 212, "pooled_net_expr": 0.11,
              "pooled_win_rate": 0.52, "net_of_frictions": "modelled", "cells_tested": 3,
              "notes": []}
    if schema is not None:
        header["autopsy_schema"] = schema
    path = tmp_path / "autopsy.json"
    path.write_text(json.dumps({"header": header, "cells": cells, "tallies": [],
                                "giveback": {"n": 0, "mean": None, "median": None}}),
                    encoding="utf-8")
    return path


def _role_file(tmp_path, rows):
    blocks = []
    for r in rows:
        blocks.append("\n".join([f"- idea: {r.idea}"] + [
            f"  {name}: {getattr(r, name)}" for name in merge.ROW_FIELDS[1:]]))
    path = tmp_path / "roles.md"
    path.write_text("## role: regime-desk\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")
    return path


def test_main_returns_2_on_a_schema_error_and_writes_no_slate(tmp_path, capsys):
    broken = _cell("weekday=Mon", lo=0.05, hi=0.3, defined_at=None)
    out_dir = tmp_path / "out"
    code = merge.main([str(_role_file(tmp_path, [_row(UP, "exploit", idea="kept-idea")])),
                       "--autopsy", str(_autopsy(tmp_path, [UP, broken])),
                       "--out-dir", str(out_dir), "--date", "2026-10-30"])
    assert code == 2
    err = capsys.readouterr().err
    assert err.startswith("scout_merge: ") and "weekday=Mon" in err
    assert not out_dir.exists() or not any(out_dir.iterdir())


def test_main_applies_the_schema_from_the_header(tmp_path):
    outcome = _cell("exit_reason=stop", lo=0.05, hi=0.35, defined_at="outcome")
    rows = [_row(outcome, "exploit", idea="kept-idea")]
    code = merge.main([str(_role_file(tmp_path, rows)),
                       "--autopsy", str(_autopsy(tmp_path, [outcome])),
                       "--out-dir", str(tmp_path), "--date", "2026-10-30"])
    assert code == 0
    slate = (tmp_path / "2026-10-30-scout-slate.md").read_text(encoding="utf-8")
    assert "is outcome-defined (not known at entry)" in slate.split("## Dropped")[1]


def test_the_generator_roles_doc_states_the_two_sided_rule():
    text = (ROOT / "docs" / "claude" / "skills-tools.md").read_text(encoding="utf-8")
    section = text[text.index("## Generator roles (v161)"):text.index("## Which agent for what (v107)")]
    for phrase in ("`exploit`", "`avoid`", "upper bound is below 0", "not known at entry",
                   "schema-1", "q ≤ 0.10"):
        assert phrase in section, phrase


HEAD2 = {"window": ["2026-01-05", "2026-10-09"], "n": 212, "pooled_net_expr": 0.11,
         "pooled_win_rate": 0.52, "net_of_frictions": "modelled", "cells_tested": 3,
         "autopsy_schema": 2}


def test_projected_change_for_exploit_is_cell_minus_pooled():
    cell = dict(UP, n=40, net_expr=0.3)
    assert merge.projected_pooled_change(cell, HEAD2, "exploit") == pytest.approx(0.19)


def test_projected_change_for_avoid_is_the_exact_complement_minus_pooled():
    cell = dict(DOWN, n=40, net_expr=-0.2)
    got = merge.projected_pooled_change(cell, HEAD2, "avoid")
    complement = (212 * 0.11 - 40 * -0.2) / (212 - 40)
    assert got == round(complement - 0.11, 4) == 0.0721
    share, delta = 40 / 212, -0.2 - complement
    assert got == pytest.approx(-share * delta, abs=1e-4)


@pytest.mark.parametrize("cell, header, direction", [
    (None, HEAD2, "exploit"),
    (dict(UP, n=40, net_expr=0.3), {"n": 212}, "exploit"),
    (dict(UP, n=40, net_expr=None), HEAD2, "exploit"),
    (dict(DOWN, n=212, net_expr=-0.2), HEAD2, "avoid"),
    (dict(DOWN, n=40, net_expr=float("nan")), HEAD2, "avoid"),
    (dict(DOWN, n=40, net_expr=-0.2), dict(HEAD2, n=None), "avoid")])
def test_projected_change_is_none_when_it_cannot_be_computed(cell, header, direction):
    assert merge.projected_pooled_change(cell, header, direction) is None


def test_schema_2_ranks_exploit_and_avoid_by_the_bound_nearest_zero():
    a = _cell("regime=a", lo=0.05, hi=0.35)
    b = _cell("regime=b", lo=-0.40, hi=-0.20)
    c = _cell("regime=c", lo=0.10, hi=0.30)
    cells = {x["id"]: x for x in (a, b, c)}
    rows = [_row(a, "exploit"), _row(b, "avoid"), _row(c, "exploit")]
    assert [r.idea for r in merge.rank(rows, cells, schema=2)] == [
        "avoid-regime=b", "exploit-regime=c", "exploit-regime=a"]


def test_schema_1_ranks_every_row_by_its_lower_bound():
    legacy_avoid = _cell("regime=x", lo=0.20, hi=0.40)
    plain = _cell("regime=y", lo=0.10, hi=0.30)
    cells = {x["id"]: x for x in (legacy_avoid, plain)}
    rows = [_row(plain, "exploit"), _row(legacy_avoid, "avoid")]
    assert [r.idea for r in merge.rank(rows, cells)] == ["avoid-regime=x", "exploit-regime=y"]
    assert [r.idea for r in merge.rank(rows, cells, schema=2)] == ["exploit-regime=y", "avoid-regime=x"]


def test_the_slate_shows_the_projected_pooled_change_per_row():
    up, down = dict(UP, n=40, net_expr=0.3), dict(DOWN, n=40, net_expr=-0.2)
    cells = {up["id"]: up, down["id"]: down}
    playbook = _row(UP, "exploit", idea="pb")
    playbook.evidence, playbook.route = "playbook gap-and-hold", "/screen pb"
    text = merge.render_slate([_row(up, "exploit"), _row(down, "avoid"), playbook], [], HEAD2,
                              date="2026-10-30", autopsy_path="a.json", cells=cells)
    assert "- projected pooled change: +0.190 R (keep only this cell)" in text
    assert "- projected pooled change: +0.072 R (drop this cell)" in text
    assert "- projected pooled change: n/a (no autopsy cell)" in text
    bare = merge.render_slate([_row(up, "exploit")], [], HEAD2, date="2026-10-30",
                              autopsy_path="a.json")
    assert "- projected pooled change: n/a (no autopsy cell)" in bare


def test_a_schema_1_slate_opens_with_the_legacy_banner():
    legacy = {k: v for k, v in HEAD2.items() if k != "autopsy_schema"}
    lines = merge.render_slate([], [], legacy, date="2026-10-30", autopsy_path="a.json").splitlines()
    assert lines[0] == "# Scout slate 2026-10-30"
    assert [line for line in lines[1:] if line.strip()][0] == merge.LEGACY_BANNER
    assert merge.LEGACY_BANNER == "legacy autopsy (schema 1): no known-at-entry check"
    modern = merge.render_slate([], [], HEAD2, date="2026-10-30", autopsy_path="a.json")
    assert merge.LEGACY_BANNER not in modern


def test_the_cli_marks_a_schema_1_autopsy_as_legacy(tmp_path):
    up = _cell("regime=risk_on", lo=0.05, hi=0.35, defined_at=None)
    code = merge.main([str(_role_file(tmp_path, [_row(up, "exploit", idea="kept-idea")])),
                       "--autopsy", str(_autopsy(tmp_path, [up], schema=None)),
                       "--out-dir", str(tmp_path), "--date", "2026-10-30"])
    assert code == 0
    slate = (tmp_path / "2026-10-30-scout-slate.md").read_text(encoding="utf-8")
    assert merge.LEGACY_BANNER in slate.split("## Ranked")[0]
    assert "### 1. kept-idea (regime-desk)" in slate
