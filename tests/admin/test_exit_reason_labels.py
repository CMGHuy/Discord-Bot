"""v166 -- the trade page's exit-reason wording covers every backend reason.

`frontend/src/app/workspaces/trades/exit-reasons.ts` maps the reason text a
leg or a status_history entry carries to the words the trade page shows
("TP1 + Runner at breakeven"). The backend vocabulary in
`swingbot/core/analytics/metrics.py` owns the keys; the frontend owns only
the wording. A reason added to the backend without a label would render as
raw text on the page -- this test makes that a red build instead.

Read-a-file style: no Flask client, no store.
"""
import re
from pathlib import Path

from swingbot.core.analytics import metrics

_TS = (Path(__file__).resolve().parents[2]
       / "frontend" / "src" / "app" / "workspaces" / "trades" / "exit-reasons.ts")
_KEY = re.compile(r"^\s*'([^']+)'\s*:\s*'", re.M)

# `other` is the metrics bucket for "none of the above", never a reason
# text written onto a leg or a status_history entry.
_NOT_A_REASON = {"other"}


def _table_keys() -> set[str]:
    source = _TS.read_text(encoding="utf-8")
    start = source.index("export const EXIT_REASON_LABELS")
    end = source.index("};", start)
    return set(_KEY.findall(source[start:end]))


def test_the_label_table_parses():
    """Guards the parser itself: an empty set would make every check below pass."""
    assert len(_table_keys()) >= 10


def test_every_exit_reason_has_a_label():
    missing = set(metrics.EXIT_REASONS) - _NOT_A_REASON - _table_keys()
    assert not missing, f"exit-reasons.ts has no label for {sorted(missing)}"


def test_every_exit_reason_alias_has_a_label():
    missing = set(metrics._EXIT_REASON_ALIASES) - _table_keys()
    assert not missing, f"exit-reasons.ts has no label for {sorted(missing)}"


def test_stall_exit_has_a_label():
    """plan_manager writes `stall_exit`, but metrics lists it in neither
    EXIT_REASONS nor the aliases, so the two checks above never see it."""
    assert "stall_exit" in _table_keys()


def test_keys_are_stored_the_way_the_lookup_reads_them():
    """`reasonLabel` trims and lower-cases before the lookup."""
    assert all(key == key.strip().lower() for key in _table_keys())
