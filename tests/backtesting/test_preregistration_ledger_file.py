"""The committed pre-registration ledger (v136 §4): valid, traceable, complete."""
import re
from pathlib import Path

from swingbot.core.backtesting.instrument import stats

ROOT = Path(__file__).resolve().parents[2]
METHODOLOGY = ROOT / "docs" / "claude" / "backtest-methodology.md"

#: The 2026-10-06 backfill (v138 IS9). These rows are never deleted or
#: rewritten; a re-measurement is a new pre-registration with a new id.
BACKFILL_IDS = (
    "e33-avwap-levels", "v17-regime-allow", "v17-level-lifecycle-stops",
    "v17-level-lifecycle-targets", "edge-v4-data-driven-stops", "v34-rs-gate-bearish",
    "v35-avwap-levels", "v31-break-retest", "v31-macd", "v31-vwap",
    "v31-volume-profile", "v36-level-touch-strength", "v49-effective-confluence",
    "v68-dcb-veto", "v69-double-pattern", "legacy-badge-refresh-2026-09-10",
    "v84-ema-crossover", "v84-break-retest-horizon-gate", "v84-vwap-4w",
    "v84-rsi-divergence-persistence", "v84-ma-ribbon-confirm-bars",
    "v84-sr-min-level-touches", "v84-fib-extension-1-0", "v84-elliott-rescue",
    "v86-cohort-label", "v82-earnings-blackout", "v88-armed-confluence",
    "v92-h1-adaptive-runner-trail", "v92-h2-stall-exit", "v90-rejection-armed",
    "v93-bearish-arms", "v98-q-inv", "v101-fib-rescue-v2", "v102-fib-rolling-sr",
    "v103-a-fib-level-stop", "v103-c-fib-continuation", "v104-a-macd-bullish",
    "v104-a-sr-bullish", "v104-a-break-retest-bullish",
    "v104-a-volume-profile-bullish", "v104-a-other-cells", "v104-b-short-mechanisms",
    "v105-pending-range", "v108-e-ema-rearm", "v113-a-downtrend-fade",
    "v113-b-legacy-1w", "v113-d-inverse-etf-longs", "v118-short-universe",
    "v123-hl-trail", "v123-progress-stall", "v119-compression-short",
    "v122-strategy", "v122-confluence",
)


#: Closed-table versions deliberately absent from the ledger (reason each).
EXEMPT = {
    "v124": "read-only diagnostic, four arms, no budget spent",
    "v127": "NO_ELIGIBLE_CELL at Stage 1, budget intact; verdict not in the ledger enum",
    "v140": "ledgered as screen-<idea> (instrument screen-v1), not under a v140- prefix",
    "v72": "named only as the funnel pointer in a screen row's closing sentence",
}


def _has_row(tag, ids) -> bool:
    return any(i.startswith(f"{tag}-") for i in ids)


def _rows():
    return stats.load_ledger()   # validates every row and refuses duplicate ids


def test_the_committed_ledger_loads_and_validates():
    assert len(_rows()) >= len(BACKFILL_IDS) == 53


def test_the_backfill_is_present_and_instrument_v1():
    by_id = {row["id"]: row for row in _rows()}
    assert [i for i in BACKFILL_IDS if i not in by_id] == []
    assert {by_id[i]["instrument"] for i in BACKFILL_IDS} == {"v1"}


def test_every_record_points_at_a_file_in_the_repo():
    missing = [row["record"] for row in _rows() if not (ROOT / row["record"]).is_file()]
    assert missing == []


def _closed_table_tags() -> set:
    lines = METHODOLOGY.read_text(encoding="utf-8").splitlines()
    start = lines.index("### Closed pre-registrations — do not re-run these")
    tags = set()
    for line in lines[start + 1:]:
        if line.startswith("|"):
            tags.update(re.findall(r"\((v\d+)", line))
        elif line.strip():
            break
    return tags


def test_every_closed_table_version_has_a_ledger_row():
    """A new closed-table row must land in the ledger too (one row per pre-registration)."""
    tags = _closed_table_tags()
    assert len(tags) >= 24
    ids = [row["id"] for row in _rows()]
    assert sorted(t for t in tags - set(EXEMPT) if not _has_row(t, ids)) == []


def test_every_exempt_version_is_in_the_table_and_has_no_ledger_row():
    """An exemption must not go stale: the version is still tabled and still unledgered."""
    ids = [row["id"] for row in _rows()]
    tags = _closed_table_tags()
    assert sorted(t for t in EXEMPT if t not in tags) == []
    assert sorted(t for t in EXEMPT if _has_row(t, ids)) == []
